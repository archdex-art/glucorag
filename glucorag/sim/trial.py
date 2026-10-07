"""In-silico PLGM trial: open-loop basal-bolus vs. EPS-TFT predictive low-glucose management.

Hardware-free reproduction of the paper's Appendix B on simglucose 0.2.11 (the open-source
Python port of the UVA/Padova T1D simulator): 10 virtual adults, a seeded random meal
scenario and two paired arms that share meals, carb-counting errors and sensor noise:

* ``open_loop`` — basal-bolus therapy from simglucose's Quest/params tables (steady-state
  basal, carb-ratio meal bolus with correction above 150 mg/dL). Carbohydrates are counted
  with a seeded per-meal multiplicative error ~ N(1.2, 0.3), i.e. meals are overestimated by
  20 % on average, so boluses overshoot and the open-loop baseline shows hypoglycemia as in
  the paper (calibrated on 45 days: open-loop TBR 4.9 %, paper 5.3 %). Both arms self-treat
  level-2 hypoglycemia with 15 g rescue carbs (see ``RescueRule``).
* ``plgm`` — the same therapy, but every CGM sample (5 min) the real ``ForecastEngine`` predicts
  BG ``horizon_min`` ahead; basal is suspended while the chosen quantile (median by default)
  is <= 70 mg/dL and resumed once it is above. If no forecast can be made (warm-up shorter than
  the look-back window) basal is delivered, i.e. the pump falls back to open-loop therapy.

CGM: simglucose's GuardianRT sensor model (5-min sampling, same noise model as its Dexcom
entry). For a forecaster trained at a coarser interval (ShanghaiDM, 15 min) the history passed
to the engine is the CGM trace strided to that interval, ending at the newest sample.

Static covariates for the virtual adults (the model's encoder needs gender/age/BMI/type):
type T1D; age from simglucose's Quest table; simglucose provides body weight but not height
or sex, so BMI and gender use the ShanghaiDM T1D cohort median BMI (20.9 kg/m^2) and majority
gender (M, 9 of 16 records).

    python -m glucorag.sim.trial --artifact models/shanghai-v1 --days 90
"""

import argparse
import contextlib
import io
import logging
import time
import warnings
from collections import deque
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import cache
from typing import Any, Protocol

import numpy as np
import pandas as pd
import torch

from glucorag.core.config import settings
from glucorag.core.registry import latest_artifact
from glucorag.inference.engine import DataGapError, ForecastEngine, Reading
from glucorag.sim import cvga
from glucorag.sim.outcomes import glycemic_outcomes

# simglucose imports gym (prints an "unmaintained" notice to stderr) and pkg_resources
# (DeprecationWarning); both are irrelevant here because only the patient/sensor/pump models
# are used, not the gym environment.
with warnings.catch_warnings(), contextlib.redirect_stderr(io.StringIO()):
    warnings.simplefilter("ignore")
    import simglucose
    from simglucose.actuator.pump import InsulinPump
    from simglucose.controller.basal_bolus_ctrller import CONTROL_QUEST
    from simglucose.patient.t1dpatient import PATIENT_PARA_FILE, Action, T1DPatient
    from simglucose.sensor.cgm import CGMSensor
    from simglucose.simulation.scenario_gen import RandomScenario

log = logging.getLogger("glucorag.sim")

ADULTS = tuple(f"adult#{i:03d}" for i in range(1, 11))
CGM_SENSOR = "GuardianRT"
CGM_INTERVAL_MIN = 5
PUMP = "Insulet"
# Midnight start so each CVGA point is one calendar day.
START = datetime(2024, 1, 1)
VIRTUAL_ADULT_GENDER = "M"
VIRTUAL_ADULT_BMI = 20.9
ARMS = ("open_loop", "plgm")


@dataclass(frozen=True)
class VirtualAdult:
    name: str
    age: float
    body_weight_kg: float
    basal_u_per_min: float
    carb_ratio_g_per_u: float
    correction_factor_mg_dl_per_u: float
    params: pd.Series = field(repr=False, compare=False)

    def profile(self) -> dict[str, Any]:
        return {
            "gender": VIRTUAL_ADULT_GENDER,
            "age": self.age,
            "bmi": VIRTUAL_ADULT_BMI,
            "diabetes_type": "T1D",
        }


def load_virtual_adult(name: str) -> VirtualAdult:
    params = pd.read_csv(PATIENT_PARA_FILE).set_index("Name", drop=False)
    quest = pd.read_csv(CONTROL_QUEST).set_index("Name")
    if name not in params.index or name not in quest.index:
        raise ValueError(f"Unknown simglucose patient {name!r}")
    p = params.loc[name]
    q = quest.loc[name]
    return VirtualAdult(
        name=name,
        age=float(q["Age"]),
        body_weight_kg=float(p["BW"]),
        # simglucose's steady-state basal: u2ss (pmol/kg/min) * BW / 6000 -> U/min.
        basal_u_per_min=float(p["u2ss"]) * float(p["BW"]) / 6000.0,
        carb_ratio_g_per_u=float(q["CR"]),
        correction_factor_mg_dl_per_u=float(q["CF"]),
        params=p,
    )


class _AttrParams:
    """Plain-attribute view of a simglucose parameter row.

    ``T1DPatient.model`` reads ~60 parameters per ODE right-hand-side evaluation via attribute
    access; on a ``pd.Series`` that dominates runtime. This view exposes the same attributes
    (plus ``iloc`` used by ``reset``) as Python floats: identical dynamics, ~10x faster.
    """

    def __init__(self, row: pd.Series) -> None:
        self.__dict__.update(row.to_dict())
        self.iloc = row.iloc


def make_patient(adult: VirtualAdult) -> T1DPatient:
    return T1DPatient(_AttrParams(adult.params))


class Forecaster(Protocol):
    interval_min: int
    history_steps: int

    def predict_mg_dl(self, history: Sequence[Reading]) -> float | None:
        """BG forecast at the PLGM horizon, or None when no forecast is possible."""
        ...


class EngineForecaster:
    """One quantile of one horizon from the production ``ForecastEngine``."""

    def __init__(
        self,
        engine: ForecastEngine,
        patient_id: str,
        profile: dict[str, Any],
        horizon_min: int,
        quantile: float,
    ) -> None:
        if horizon_min not in engine.horizons_min:
            raise ValueError(f"Horizon {horizon_min} not in model horizons {engine.horizons_min}")
        if quantile not in engine.meta.quantiles:
            raise ValueError(f"Quantile {quantile} not in model quantiles {engine.meta.quantiles}")
        self.engine = engine
        self.patient_id = patient_id
        self.ctx = engine.context_for(profile)
        self.interval_min = engine.meta.interval_min
        # Superset of what the engine reads (look-back + imputation span); extra is ignored.
        self.history_steps = 2 * engine.meta.lookback_steps + engine.max_gap_steps
        self._h = engine.horizons_min.index(horizon_min)
        self._q = engine.meta.quantiles.index(quantile)

    def predict_mg_dl(self, history: Sequence[Reading]) -> float | None:
        try:
            pred = self.engine.predict(self.patient_id, self.ctx, history)
        except DataGapError:
            return None
        return pred.values[self._h][self._q]


class Controller(Protocol):
    @property
    def suspended(self) -> bool: ...

    @property
    def last_prediction_mg_dl(self) -> float | None: ...

    def on_cgm(self, history: Sequence[Reading]) -> None:
        """Called at every CGM sample with the CGM history (oldest first, newest last)."""
        ...

    def basal_u_per_min(self) -> float: ...

    def meal_bolus_u(self, carbs_estimate_g: float, cgm_mg_dl: float) -> float: ...


class BasalBolusController:
    """simglucose's BBController therapy: fixed basal + carb-ratio bolus with correction."""

    suspended = False
    last_prediction_mg_dl = None

    def __init__(
        self,
        adult: VirtualAdult,
        target_mg_dl: float = 140.0,
        correction_above_mg_dl: float = 150.0,
    ) -> None:
        self.adult = adult
        self.target_mg_dl = target_mg_dl
        self.correction_above_mg_dl = correction_above_mg_dl

    def on_cgm(self, history: Sequence[Reading]) -> None:
        return None

    def basal_u_per_min(self) -> float:
        return self.adult.basal_u_per_min

    def meal_bolus_u(self, carbs_estimate_g: float, cgm_mg_dl: float) -> float:
        bolus = carbs_estimate_g / self.adult.carb_ratio_g_per_u
        if cgm_mg_dl > self.correction_above_mg_dl:
            bolus += (cgm_mg_dl - self.target_mg_dl) / self.adult.correction_factor_mg_dl_per_u
        return max(bolus, 0.0)


class PLGMController:
    """Predictive low-glucose management wrapped around a basal-bolus controller.

    Suspends basal while the forecast is <= ``threshold_mg_dl`` and resumes as soon as it is
    above; boluses are never altered. With no forecast available basal is delivered.
    """

    def __init__(
        self,
        base: Controller,
        forecaster: Forecaster,
        cgm_interval_min: int,
        threshold_mg_dl: float = settings.alert_thresholds.hypo_mg_dl,
    ) -> None:
        if forecaster.interval_min % cgm_interval_min:
            raise ValueError(
                f"Forecaster interval {forecaster.interval_min} min is not a multiple of the "
                f"CGM interval {cgm_interval_min} min"
            )
        self.base = base
        self.forecaster = forecaster
        self.threshold_mg_dl = threshold_mg_dl
        self._stride = forecaster.interval_min // cgm_interval_min
        self._suspended = False
        self._last_prediction: float | None = None

    @property
    def suspended(self) -> bool:
        return self._suspended

    @property
    def last_prediction_mg_dl(self) -> float | None:
        return self._last_prediction

    @property
    def history_len(self) -> int:
        """CGM samples (at the CGM interval) the caller must retain."""
        return self.forecaster.history_steps * self._stride

    def on_cgm(self, history: Sequence[Reading]) -> None:
        strided = list(history)[::-1][:: self._stride][: self.forecaster.history_steps][::-1]
        self._last_prediction = self.forecaster.predict_mg_dl(strided)
        self._suspended = (
            self._last_prediction is not None and self._last_prediction <= self.threshold_mg_dl
        )

    def basal_u_per_min(self) -> float:
        return 0.0 if self._suspended else self.base.basal_u_per_min()

    def meal_bolus_u(self, carbs_estimate_g: float, cgm_mg_dl: float) -> float:
        return self.base.meal_bolus_u(carbs_estimate_g, cgm_mg_dl)


@dataclass(frozen=True)
class PatientSeeds:
    scenario: int
    sensor: int
    carb_error: int

    @classmethod
    def derive(cls, trial_seed: int, patient_index: int) -> "PatientSeeds":
        s = np.random.SeedSequence([trial_seed, patient_index]).generate_state(3)
        return cls(int(s[0]), int(s[1]), int(s[2]))


@dataclass(frozen=True)
class RescueRule:
    """Self-treatment of hypoglycemia ("15-15 rule", ADA Standards of Care).

    ``carbs_g`` of fast carbohydrate (not bolused) when CGM < ``below_mg_dl``, at most once per
    ``every_min``; ``carbs_g = 0`` disables it. Without it simglucose BG can fall to 0 and stay
    there (its states are clamped at zero), which no real subject would do. The default trigger
    is level-2 hypoglycemia (< 54 mg/dL, the usual CGM urgent-low alarm): treating at < 70
    would itself remove almost all time below range and leave nothing for PLGM to prevent.
    """

    carbs_g: float = 15.0
    below_mg_dl: float = 54.0
    every_min: int = 15


@dataclass(frozen=True)
class SimTrace:
    """Per-CGM-sample (5-min) record of one arm for one patient."""

    bg_mg_dl: np.ndarray
    cgm_mg_dl: np.ndarray
    suspended: np.ndarray
    prediction_mg_dl: np.ndarray
    basal_u: float
    bolus_u: float
    meals: int
    rescues: int


def simulate(
    adult: VirtualAdult,
    controller: Controller,
    days: float,
    seeds: PatientSeeds,
    carb_bias: float,
    carb_sd: float,
    rescue: RescueRule,
    history_len: int = 1,
) -> SimTrace:
    """Run one arm at the simulator's 1-min step; controller decisions at each CGM sample."""
    patient = make_patient(adult)
    sensor = CGMSensor.withName(CGM_SENSOR, seed=seeds.sensor)
    if int(sensor.sample_time) != CGM_INTERVAL_MIN:
        raise RuntimeError(f"{CGM_SENSOR} samples every {sensor.sample_time} min")
    pump = InsulinPump.withName(PUMP)
    scenario = RandomScenario(start_time=START, seed=seeds.scenario)
    carb_rng = np.random.default_rng(seeds.carb_error)

    total_min = round(days * 1440)
    n = total_min // CGM_INTERVAL_MIN
    bg = np.empty(n)
    cgm = np.empty(n)
    suspended = np.zeros(n, dtype=bool)
    prediction = np.full(n, np.nan)
    history: deque[Reading] = deque(maxlen=max(history_len, 1))
    basal_total = bolus_total = 0.0
    meals = rescues = 0
    last_rescue = -rescue.every_min
    last_cgm = float("nan")

    for minute in range(n * CGM_INTERVAL_MIN):
        now = START + timedelta(minutes=minute)
        rescue_g = 0.0
        if minute % CGM_INTERVAL_MIN == 0:
            k = minute // CGM_INTERVAL_MIN
            last_cgm = float(sensor.measure(patient))
            history.append(Reading(now, last_cgm))
            controller.on_cgm(history)
            bg[k] = patient.observation.Gsub
            cgm[k] = last_cgm
            suspended[k] = controller.suspended
            if controller.last_prediction_mg_dl is not None:
                prediction[k] = controller.last_prediction_mg_dl
            if (
                rescue.carbs_g > 0
                and last_cgm < rescue.below_mg_dl
                and minute - last_rescue >= rescue.every_min
            ):
                rescue_g = rescue.carbs_g
                rescues += 1
                last_rescue = minute
        carbs = float(scenario.get_action(now).meal)
        insulin = pump.basal(controller.basal_u_per_min())
        basal_total += insulin
        if carbs > 0:
            meals += 1
            estimate = carbs * max(carb_rng.normal(carb_bias, carb_sd), 0.0)
            # Bolus delivered within the 1-min step: U over 1 min == U/min.
            bolus = pump.bolus(controller.meal_bolus_u(estimate, last_cgm))
            bolus_total += bolus
            insulin += bolus
        patient.step(Action(CHO=carbs + rescue_g, insulin=insulin))

    return SimTrace(bg, cgm, suspended, prediction, basal_total, bolus_total, meals, rescues)


@dataclass(frozen=True)
class TrialConfig:
    artifact: str
    days: float = 90.0
    seed: int = 0
    patients: tuple[str, ...] = ADULTS
    horizon_min: int = 60
    quantile: float = 0.5
    threshold_mg_dl: float = settings.alert_thresholds.hypo_mg_dl
    # Per-meal carb-count multiplier ~ N(bias, sd); overestimated meals drive open-loop hypos.
    carb_bias: float = 1.2
    carb_sd: float = 0.3
    rescue: RescueRule = RescueRule()
    max_gap_min: int = settings.alert_thresholds.data_gap_min


@dataclass(frozen=True)
class ArmResult:
    patient: str
    arm: str
    outcomes: dict[str, float]
    daily_min: list[float]
    daily_max: list[float]
    cvga: dict[str, float]
    suspended_pct: float
    basal_u_per_day: float
    bolus_u_per_day: float
    rescue_carbs_g_per_day: float
    forecast_rmse_mg_dl: float | None
    forecast_n: int
    runtime_s: float


@cache
def _engine(path: str, max_gap_min: int) -> ForecastEngine:
    return ForecastEngine.from_artifact(path, max_gap_min)


def forecast_rmse(trace: SimTrace, horizon_min: int) -> tuple[float | None, int]:
    """RMSE of the stored forecasts against the simulated BG ``horizon_min`` later."""
    lag = horizon_min // CGM_INTERVAL_MIN
    pred = trace.prediction_mg_dl[:-lag] if lag else trace.prediction_mg_dl
    actual = trace.bg_mg_dl[lag:]
    ok = ~np.isnan(pred)
    if not ok.any():
        return None, 0
    return float(np.sqrt(np.mean((pred[ok] - actual[ok]) ** 2))), int(ok.sum())


def run_arm(config: TrialConfig, patient_index: int, arm: str) -> ArmResult:
    started = time.perf_counter()
    torch.set_num_threads(1)
    adult = load_virtual_adult(config.patients[patient_index])
    base = BasalBolusController(adult)
    controller: Controller = base
    history_len = 1
    if arm == "plgm":
        engine = _engine(config.artifact, config.max_gap_min)
        forecaster = EngineForecaster(
            engine, adult.name, adult.profile(), config.horizon_min, config.quantile
        )
        plgm = PLGMController(base, forecaster, CGM_INTERVAL_MIN, config.threshold_mg_dl)
        controller = plgm
        history_len = plgm.history_len
    elif arm != "open_loop":
        raise ValueError(f"Unknown arm {arm!r}")
    seeds = PatientSeeds.derive(config.seed, patient_index)
    trace = simulate(
        adult,
        controller,
        config.days,
        seeds,
        config.carb_bias,
        config.carb_sd,
        config.rescue,
        history_len,
    )
    mins, maxs = cvga.daily_extremes(trace.bg_mg_dl, 1440 // CGM_INTERVAL_MIN)
    rmse, n_forecasts = forecast_rmse(trace, config.horizon_min)
    days = trace.bg_mg_dl.size * CGM_INTERVAL_MIN / 1440
    return ArmResult(
        patient=adult.name,
        arm=arm,
        outcomes=glycemic_outcomes(trace.bg_mg_dl).to_dict(),
        daily_min=mins.tolist(),
        daily_max=maxs.tolist(),
        cvga=cvga.summarize(mins, maxs),
        suspended_pct=100.0 * float(trace.suspended.mean()),
        basal_u_per_day=trace.basal_u / days,
        bolus_u_per_day=trace.bolus_u / days,
        rescue_carbs_g_per_day=trace.rescues * config.rescue.carbs_g / days,
        forecast_rmse_mg_dl=rmse,
        forecast_n=n_forecasts,
        runtime_s=time.perf_counter() - started,
    )


def _run_job(job: tuple[TrialConfig, int, str]) -> ArmResult:
    return run_arm(*job)


def run_trial(config: TrialConfig, workers: int) -> list[ArmResult]:
    """Both arms for every patient; jobs run in parallel processes, results in input order."""
    jobs = [(config, i, arm) for i in range(len(config.patients)) for arm in ARMS]
    if workers <= 1:
        return [_run_job(j) for j in jobs]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(_run_job, jobs))


def main(argv: Sequence[str] | None = None) -> None:
    from glucorag.sim.report import write_report

    parser = argparse.ArgumentParser(description="In-silico PLGM trial on simglucose adults")
    parser.add_argument("--artifact", default=None, help="Model dir (default: latest shanghai)")
    parser.add_argument("--models-dir", default="models")
    parser.add_argument("--days", type=float, default=90.0)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--patients", nargs="+", default=list(ADULTS))
    parser.add_argument("--horizon-min", type=int, default=60)
    parser.add_argument("--quantile", type=float, default=0.5)
    parser.add_argument("--threshold", type=float, default=settings.alert_thresholds.hypo_mg_dl)
    parser.add_argument("--carb-bias", type=float, default=TrialConfig.carb_bias)
    parser.add_argument("--carb-sd", type=float, default=TrialConfig.carb_sd)
    parser.add_argument(
        "--rescue-carbs", type=float, default=RescueRule.carbs_g, help="0 disables self-treatment"
    )
    parser.add_argument("--rescue-below", type=float, default=RescueRule.below_mg_dl)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--out", default="reports/sim")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

    artifact = args.artifact or str(latest_artifact(args.models_dir, "shanghai"))
    config = TrialConfig(
        artifact=artifact,
        days=args.days,
        seed=args.seed,
        patients=tuple(args.patients),
        horizon_min=args.horizon_min,
        quantile=args.quantile,
        threshold_mg_dl=args.threshold,
        carb_bias=args.carb_bias,
        carb_sd=args.carb_sd,
        rescue=RescueRule(carbs_g=args.rescue_carbs, below_mg_dl=args.rescue_below),
    )
    log.info(
        "trial: %d patients x %s days, artifact %s", len(config.patients), config.days, artifact
    )
    started = time.perf_counter()
    results = run_trial(config, args.workers)
    runtime = time.perf_counter() - started
    meta = _engine(artifact, config.max_gap_min).meta
    paths = write_report(
        results, config, meta, runtime, args.out, simglucose_version=_simglucose_version()
    )
    log.info("runtime %.1f s; wrote %s", runtime, ", ".join(str(p) for p in paths))


def _simglucose_version() -> str:
    from importlib.metadata import version

    return version(simglucose.__name__)


if __name__ == "__main__":
    main()
