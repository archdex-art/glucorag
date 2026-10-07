"""Release gates: decide whether a registered artifact may be promoted to serving.

    python -m glucorag.release --artifact models/shanghai-v1 --data-root data/raw/shanghai \
        --sim-report reports/sim/report.json [--waive significance --reason "..."]

Gates (all must pass or be explicitly waived with a recorded reason):
  integrity     weights checksum verifies on load
  accuracy      per-patient mean test RMSE at 30/60 min within limits (``glucorag.evaluate.run``)
  significance  EPS-TFT significantly better than the next-best baseline (paper's p < 0.05)
  parity        serving ``ForecastEngine`` reproduces offline predictions (< 1e-3 mg/dL)
  in_silico     PLGM lowers time below 70 mg/dL vs open loop (``glucorag.sim.trial``)

Promotion writes ``<models>/CURRENT`` (version name) and appends to ``promotions.jsonl``.
"""

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch

from glucorag.core.registry import ModelMeta, load_artifact

# Paper Table II EPS-TFT mean RMSE + 1 mg/dL tolerance.
DEFAULT_MAX_RMSE = {"30": 13.7, "60": 22.7}
PARITY_TOL_MG_DL = 1e-3
GATES = ("integrity", "accuracy", "significance", "parity", "in_silico")


@dataclass
class GateResult:
    gate: str
    passed: bool
    detail: str
    waived: str | None = None


def check_accuracy(meta: ModelMeta, max_rmse: dict[str, float]) -> GateResult:
    summary = meta.metrics.get("test", {}).get("summary")
    if not summary:
        return GateResult("accuracy", False, "no test metrics; run glucorag.evaluate.run")
    parts, ok = [], True
    for h, limit in max_rmse.items():
        rmse = float(summary[h]["RMSE"]["mean"])
        ok &= rmse <= limit
        parts.append(f"{h} min RMSE {rmse:.2f} (limit {limit})")
    return GateResult("accuracy", ok, "; ".join(parts))


def check_significance(meta: ModelMeta) -> GateResult:
    sig = meta.metrics.get("test", {}).get("significance")
    if not sig:
        return GateResult("significance", False, "no significance results")
    parts, ok = [], True
    for h, s in sorted(sig.items()):
        ok &= bool(s["significant"])
        parts.append(
            f"{h} min vs {s['comparator']}: dRMSE {s['mean_difference']:+.3f}, "
            f"t-test p={s['t_p']:.3g}, normal={s['differences_normal']}"
        )
    return GateResult("significance", ok, "; ".join(parts))


def check_parity(artifact: Path, data_root: Path, n_samples: int, seed: int) -> GateResult:
    from glucorag.data.pipeline import load_dataset, make_windows
    from glucorag.inference.engine import ForecastEngine, Reading

    _, meta = load_artifact(artifact)
    max_gap_min = int(meta.train_config.get("max_gap_min", 60))
    engine = ForecastEngine.from_artifact(artifact, max_gap_min=max_gap_min)
    data = load_dataset(
        meta.dataset, data_root, max_gap_min, meta.train_config.get("ohio_profiles")
    )
    windows, static = make_windows(data, "test", meta.lookback_min, meta.horizon_min)
    idx = np.random.default_rng(seed).choice(len(windows), min(n_samples, len(windows)), False)
    profiles = data.profiles.set_index("series_id")
    test = data.test
    worst = 0.0
    for i in idx:
        sid, t0 = windows.series_id[i], windows.t0[i]
        rows = test[(test["series_id"] == sid) & (test["timestamp"] <= t0) & test["observed"]]
        history = [
            Reading(ts.to_pydatetime(), float(g))
            for ts, g in zip(rows["timestamp"], rows["glucose_mg_dl"], strict=True)
        ]
        profile = profiles.loc[sid].to_dict()
        served = np.array(engine.predict(str(sid), engine.context_for(profile), history).values)
        with torch.no_grad():
            ref, _ = engine.model(
                torch.from_numpy(static[i : i + 1]),
                torch.from_numpy(windows.x_enc[i : i + 1]),
                torch.from_numpy(windows.x_dec[i : i + 1]),
            )
        offline = np.sort(
            meta.glucose_normalizer().inverse_transform(ref[0].numpy().astype(np.float64)), -1
        )
        offline = np.clip(offline, 40.0, 400.0)
        worst = max(worst, float(np.abs(served - offline).max()))
    return GateResult(
        "parity",
        worst < PARITY_TOL_MG_DL,
        f"max |served - offline| = {worst:.2e} mg/dL over {len(idx)} test windows",
    )


def check_in_silico(meta: ModelMeta, sim_report: Path | None) -> GateResult:
    if sim_report is None or not sim_report.is_file():
        return GateResult("in_silico", False, "no in-silico report; run glucorag.sim.trial")
    report: dict[str, Any] = json.loads(sim_report.read_text())
    version = report.get("model", {}).get("version")
    if version != meta.version:
        return GateResult("in_silico", False, f"report is for {version}, not {meta.version}")
    agg = report["aggregate"]
    before, after = agg["open_loop"]["tbr_pct"], agg["plgm"]["tbr_pct"]
    return GateResult(
        "in_silico",
        after < before,
        f"TBR open loop {before:.2f}% -> PLGM {after:.2f}% "
        f"({report['config']['days']:.0f} days, {len(report['config']['patients'])} patients)",
    )


def run_gates(args: argparse.Namespace) -> list[GateResult]:
    try:
        _, meta = load_artifact(args.artifact)
        results = [GateResult("integrity", True, f"{meta.version}: checksum OK")]
    except (ValueError, FileNotFoundError) as exc:
        return [GateResult("integrity", False, str(exc))]
    max_rmse = {"30": args.max_rmse_30, "60": args.max_rmse_60}
    results.append(check_accuracy(meta, max_rmse))
    results.append(check_significance(meta))
    if args.data_root is None:
        results.append(GateResult("parity", False, "--data-root required for parity check"))
    else:
        results.append(check_parity(args.artifact, args.data_root, args.parity_samples, 0))
    results.append(check_in_silico(meta, args.sim_report))
    for r in results:
        if not r.passed and r.gate in args.waive:
            r.waived = args.reason
    return results


def promote(artifact: Path, results: list[GateResult]) -> None:
    root = artifact.parent
    (root / "CURRENT").write_text(artifact.name + "\n")
    record = {
        "version": artifact.name,
        "promoted_at": datetime.now(UTC).isoformat(),
        "gates": [asdict(r) for r in results],
    }
    with (root / "promotions.jsonl").open("a") as f:
        f.write(json.dumps(record) + "\n")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--artifact", type=Path, required=True)
    p.add_argument("--data-root", type=Path)
    p.add_argument("--sim-report", type=Path)
    p.add_argument("--max-rmse-30", type=float, default=DEFAULT_MAX_RMSE["30"])
    p.add_argument("--max-rmse-60", type=float, default=DEFAULT_MAX_RMSE["60"])
    p.add_argument("--parity-samples", type=int, default=200)
    p.add_argument("--waive", action="append", default=[], choices=GATES)
    p.add_argument("--reason", default=None, help="required with --waive; stored in the log")
    p.add_argument("--dry-run", action="store_true", help="evaluate gates without promoting")
    args = p.parse_args(argv)
    if args.waive and not args.reason:
        p.error("--waive requires --reason")

    results = run_gates(args)
    for r in results:
        status = "PASS" if r.passed else ("WAIVED" if r.waived else "FAIL")
        waiver = f"  (waiver: {r.waived})" if r.waived else ""
        print(f"[{status:6}] {r.gate:12} {r.detail}{waiver}")
    blocked = [r.gate for r in results if not r.passed and not r.waived]
    if blocked:
        print(f"NOT PROMOTED: failing gates {blocked}")
        return 1
    if args.dry_run:
        print("all gates satisfied (dry run, not promoted)")
        return 0
    promote(args.artifact, results)
    print(f"PROMOTED {args.artifact.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
