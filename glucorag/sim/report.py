"""Markdown/JSON report and CVGA plots for an in-silico trial run."""

import json
import math
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

from glucorag.core.registry import ModelMeta
from glucorag.sim import cvga
from glucorag.sim.trial import ARMS, ArmResult, TrialConfig

# Appendix B of Zhu et al., IEEE TBioCAS 2024 (open loop -> PLGM).
PAPER = {
    "open_loop": {"tbr_pct": 5.3, "tir_pct": 74.6, "A+B": 71.0},
    "plgm": {"tbr_pct": 1.9, "tir_pct": 75.2, "A+B": 80.0},
    "d_plus_e_reduction_pct_points": 9.0,
}
_ARM_LABEL = {"open_loop": "Open loop (basal-bolus)", "plgm": "PLGM (EPS-TFT)"}


def aggregate(results: Sequence[ArmResult], arm: str) -> dict[str, Any]:
    """Patient-mean outcomes, CVGA pooled over all patient-days, pooled forecast RMSE."""
    rows = [r for r in results if r.arm == arm]
    if not rows:
        raise ValueError(f"No results for arm {arm!r}")
    out: dict[str, Any] = {
        k: float(np.mean([r.outcomes[k] for r in rows])) for k in rows[0].outcomes
    }
    mins = [v for r in rows for v in r.daily_min]
    maxs = [v for r in rows for v in r.daily_max]
    out["cvga"] = cvga.summarize(mins, maxs)
    out["cvga_points"] = len(mins)
    out["suspended_pct"] = float(np.mean([r.suspended_pct for r in rows]))
    out["basal_u_per_day"] = float(np.mean([r.basal_u_per_day for r in rows]))
    out["bolus_u_per_day"] = float(np.mean([r.bolus_u_per_day for r in rows]))
    out["rescue_carbs_g_per_day"] = float(np.mean([r.rescue_carbs_g_per_day for r in rows]))
    n = sum(r.forecast_n for r in rows)
    sq = sum(r.forecast_n * r.forecast_rmse_mg_dl**2 for r in rows if r.forecast_rmse_mg_dl)
    out["forecast_rmse_mg_dl"] = math.sqrt(sq / n) if n else None
    return out


def _fmt(v: float | None, digits: int = 1) -> str:
    return "n/a" if v is None else f"{v:.{digits}f}"


def _markdown(
    results: Sequence[ArmResult],
    agg: dict[str, dict[str, Any]],
    config: TrialConfig,
    meta: ModelMeta,
    runtime_s: float,
    simglucose_version: str,
) -> str:
    ol, pl = agg["open_loop"], agg["plgm"]
    lines = [
        "# In-silico PLGM trial (paper Appendix B, hardware-free)",
        "",
        f"- Simulator: simglucose {simglucose_version} (UVA/Padova adult cohort), "
        f"{len(config.patients)} virtual adults x {config.days:g} days, seed {config.seed}",
        f"- Forecaster: `{meta.version}` ({meta.dataset}, {meta.interval_min}-min CGM, "
        f"look-back {meta.lookback_min} min); suspend basal when the "
        f"q={config.quantile} forecast at {config.horizon_min} min is <= "
        f"{config.threshold_mg_dl:g} mg/dL, decision every 5 min",
        f"- Carb counting error per meal ~ N({config.carb_bias}, {config.carb_sd}); "
        f"{config.rescue.carbs_g:g} g rescue carbs when CGM < {config.rescue.below_mg_dl:g} "
        f"mg/dL (at most every {config.rescue.every_min} min), both arms",
        f"- Wall-clock runtime: {runtime_s:.0f} s",
        "",
        "## Cohort outcomes (true simulated BG; TBR/TIR/TAR = patient mean, CVGA pooled over "
        "patient-days)",
        "",
        "| Metric | Open loop | PLGM | Paper open loop | Paper PLGM |",
        "|---|---|---|---|---|",
        f"| TBR <70 mg/dL (%) | {ol['tbr_pct']:.1f} | {pl['tbr_pct']:.1f} | "
        f"{PAPER['open_loop']['tbr_pct']} | {PAPER['plgm']['tbr_pct']} |",
        f"| TIR 70-180 mg/dL (%) | {ol['tir_pct']:.1f} | {pl['tir_pct']:.1f} | "
        f"{PAPER['open_loop']['tir_pct']} | {PAPER['plgm']['tir_pct']} |",
        f"| TAR >180 mg/dL (%) | {ol['tar_pct']:.1f} | {pl['tar_pct']:.1f} | - | - |",
        f"| Mean BG (mg/dL) | {ol['mean_mg_dl']:.1f} | {pl['mean_mg_dl']:.1f} | - | - |",
        f"| CVGA A+B (%) | {ol['cvga']['A+B']:.1f} | {pl['cvga']['A+B']:.1f} | "
        f"{PAPER['open_loop']['A+B']:.0f} | {PAPER['plgm']['A+B']:.0f} |",
        f"| CVGA D+E (%) | {ol['cvga']['D+E']:.1f} | {pl['cvga']['D+E']:.1f} | - | "
        f"-{PAPER['d_plus_e_reduction_pct_points']:.0f} pts vs open loop |",
        f"| Basal suspended (% time) | {ol['suspended_pct']:.1f} | {pl['suspended_pct']:.1f} "
        "| - | - |",
        f"| Basal / bolus insulin (U/day) | {ol['basal_u_per_day']:.1f} / "
        f"{ol['bolus_u_per_day']:.1f} | {pl['basal_u_per_day']:.1f} / "
        f"{pl['bolus_u_per_day']:.1f} | - | - |",
        f"| Rescue carbs (g/day) | {ol['rescue_carbs_g_per_day']:.1f} | "
        f"{pl['rescue_carbs_g_per_day']:.1f} | - | - |",
        f"| {config.horizon_min}-min forecast RMSE vs BG (mg/dL) | - | "
        f"{_fmt(pl['forecast_rmse_mg_dl'])} | - | - |",
        "",
        "## Per patient",
        "",
        "| Patient | Arm | TBR | TIR | TAR | A+B | D+E | Suspended | Forecast RMSE |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        o = r.outcomes
        lines.append(
            f"| {r.patient} | {r.arm} | {o['tbr_pct']:.1f} | {o['tir_pct']:.1f} | "
            f"{o['tar_pct']:.1f} | {r.cvga['A+B']:.0f} | {r.cvga['D+E']:.0f} | "
            f"{r.suspended_pct:.1f} | {_fmt(r.forecast_rmse_mg_dl)} |"
        )
    if meta.interval_min == 5:
        cadence = "a 5-min model, as in the paper's trial."
    else:
        cadence = (
            f"a {meta.interval_min}-min model, whereas the paper's trial used a 5-min model: "
            f"the engine is fed the 5-min GuardianRT CGM trace strided to {meta.interval_min} "
            f"min ({meta.lookback_steps} samples of look-back); suspension decisions are still "
            "made every 5 min."
        )
    lines += [
        "",
        "## Differences from the paper's trial",
        "",
        f"- Simulator: open-source simglucose {simglucose_version} (2008 UVA/Padova adult "
        "parameter set) instead of the paper's UVA/Padova T1D simulator; no hardware: the "
        "wristband/USB link is replaced by an in-process call of the production "
        "`ForecastEngine` (float32 PyTorch, not the quantized edge build).",
        f"- Forecaster: trained on {meta.dataset} ({meta.interval_min}-min CGM) and applied "
        f"zero-shot to simulated T1D adults (no fine-tuning on simulator data); {cadence}",
        "- Static covariates: simglucose has age and weight but not height or sex, so every "
        "virtual adult is T1D with Quest-table age, ShanghaiDM T1D median BMI (20.9) and "
        "majority gender (M).",
        "- Therapy and scenario: simglucose RandomScenario meals (seeded) and its basal-bolus "
        "rule with a per-meal carb-counting error chosen so the open-loop TBR is close to the "
        "paper's, plus rescue carbs for level-2 hypoglycemia (without them simglucose BG can "
        "collapse to 0 and stay there); the paper does not specify its scenario, baseline "
        "therapy or hypotreatment. Simglucose adults under this therapy spend much less time "
        "above range than the paper's cohort, so TIR/CVGA baselines are not directly comparable.",
        f"- Duration: {config.days:g} days (paper: 3 months).",
        "- Outcomes are computed on true simulated BG at 5-min resolution; CVGA uses one point "
        "per patient-day pooled over the cohort (the paper's Fig. 8 shows one virtual adult; "
        "per-patient CVGA is in the table above and `report.json`).",
        "",
    ]
    return "\n".join(lines)


def write_report(
    results: Sequence[ArmResult],
    config: TrialConfig,
    meta: ModelMeta,
    runtime_s: float,
    out_dir: str | Path,
    simglucose_version: str,
) -> list[Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    agg = {arm: aggregate(results, arm) for arm in ARMS}

    pooled = out / "cvga.png"
    cvga.plot(
        {
            _ARM_LABEL[arm]: (
                [v for r in results if r.arm == arm for v in r.daily_min],
                [v for r in results if r.arm == arm for v in r.daily_max],
            )
            for arm in ARMS
        },
        pooled,
        f"CVGA, {len(config.patients)} virtual adults x {config.days:g} days (one dot per day)",
    )
    first = config.patients[0]
    single = out / f"cvga_{first.replace('#', '')}.png"
    cvga.plot(
        {
            _ARM_LABEL[r.arm]: (r.daily_min, r.daily_max)
            for r in results
            if r.patient == first
        },
        single,
        f"CVGA, {first} ({config.days:g} days)",
    )

    report = {
        "config": asdict(config),
        "model": {
            "version": meta.version,
            "dataset": meta.dataset,
            "interval_min": meta.interval_min,
            "lookback_min": meta.lookback_min,
            "horizon_min": meta.horizon_min,
        },
        "simglucose_version": simglucose_version,
        "runtime_s": runtime_s,
        "aggregate": agg,
        "paper": PAPER,
        "patients": [asdict(r) for r in results],
    }
    json_path = out / "report.json"
    json_path.write_text(json.dumps(report, indent=2))
    md_path = out / "report.md"
    md_path.write_text(_markdown(results, agg, config, meta, runtime_s, simglucose_version))
    return [md_path, json_path, pooled, single]
