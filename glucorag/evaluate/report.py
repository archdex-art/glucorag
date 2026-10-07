"""Markdown rendering of evaluation results (the ``metrics.json`` structure of ``run.py``)."""

from collections.abc import Mapping
from typing import Any

import pandas as pd

from glucorag.evaluate.metrics import METRICS, summarize

# Zhu et al. 2024, Table II and Appendix A (ShanghaiDM): RMSE in mg/dL, mean +- STD.
PAPER_SHANGHAI_RMSE: dict[str, dict[int, str]] = {
    "EPS-TFT": {30: "12.7 ± 3.8", 60: "21.7 ± 6.9"},
    "EPS-TFT w/o LSTM decoder": {60: "22.0"},
    "EPS-TFT w/o covariate encoder": {60: "22.4"},
}
PAPER_SHANGHAI_CV_RMSE = {30: 14.7, 60: 23.5}

Summary = dict[str, dict[str, dict[str, float]]]  # horizon -> metric -> {mean, std}


def summary_dict(per_patient: pd.DataFrame) -> Summary:
    """JSON-friendly ``{horizon: {metric: {"mean", "std"}}}``."""
    table = summarize(per_patient)
    return {
        str(h): {
            m: {"mean": float(table.loc[h, (m, "mean")]), "std": float(table.loc[h, (m, "std")])}
            for m in METRICS
        }
        for h in table.index
    }


def _cell(stats: Mapping[str, float]) -> str:
    return f"{stats['mean']:.2f} ± {stats['std']:.2f}"


def _metric_table(methods: Mapping[str, Mapping[str, Any]], horizon: str, key: str) -> list[str]:
    lines = ["| Method | RMSE | MAE | MAPE (%) | gRMSE |", "|---|---|---|---|---|"]
    rows = [(name, m[key][horizon]) for name, m in methods.items() if horizon in m.get(key, {})]
    for name, s in sorted(rows, key=lambda r: r[1]["RMSE"]["mean"]):
        lines.append(f"| {name} | " + " | ".join(_cell(s[m]) for m in METRICS) + " |")
    return lines


def render_report(results: Mapping[str, Any]) -> str:
    horizons = [str(h) for h in results["horizons_min"]]
    methods: Mapping[str, Mapping[str, Any]] = results["methods"]
    out = [
        f"# Evaluation report: {results['artifact']}",
        "",
        f"- Dataset: {results['dataset']} ({results['interval_min']}-min CGM), test split",
        f"- Test windows: {results['n_test_windows']} from {results['n_test_patients']} patients"
        " (targets restricted to real CGM observations)",
        "- Metrics computed per patient, reported as mean ± sample STD across patients;"
        " point forecast = 0.5 quantile for EPS-TFT variants.",
        f"- Data hash matches training artifact: {results['data_hash_matches']}",
        "",
    ]
    for h in horizons:
        out += [f"## {h}-minute prediction horizon", ""]
        out += _metric_table(methods, h, "summary")
        out.append("")

    if results["dataset"] == "shanghai":
        out += [
            "## Comparison with the paper (Table II / Appendix A, RMSE mg/dL)",
            "",
            "| Method | Horizon | Paper | This run |",
            "|---|---|---|---|",
        ]
        for name, ref in PAPER_SHANGHAI_RMSE.items():
            for h, paper in ref.items():
                ours = methods.get(name, {}).get("summary", {}).get(str(h))
                mine = _cell(ours["RMSE"]) if ours else "not evaluated"
                out.append(f"| {name} | {h} min | {paper} | {mine} |")
        out.append("")

    by_type = {n: m for n, m in methods.items() if m.get("by_type")}
    if by_type:
        out += ["## RMSE by diabetes type", ""]
        types = sorted({t for m in by_type.values() for t in m["by_type"]})
        header = " | ".join(f"{t} {h} min" for t in types for h in horizons)
        out.append(f"| Method | {header} |")
        out.append("|---" * (1 + len(types) * len(horizons)) + "|")
        for name, m in by_type.items():
            cells = [
                _cell(m["by_type"][t][h]["RMSE"]) if h in m["by_type"].get(t, {}) else "-"
                for t in types
                for h in horizons
            ]
            out.append(f"| {name} | " + " | ".join(cells) + " |")
        out.append("")

    sig = results.get("significance", {})
    if sig:
        out += [
            "## Significance (paired per-patient RMSE)",
            "",
            "Shapiro–Wilk on paired differences, then paired two-sided t-test of EPS-TFT vs the"
            " next-best method (Wilcoxon signed-rank shown for robustness).",
            "",
            "| Horizon | Comparator | n | mean Δ RMSE | Shapiro p | normal | t | t-test p |"
            " Wilcoxon p | significant |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        for h in horizons:
            if h not in sig:
                continue
            s = sig[h]
            out.append(
                f"| {h} min | {s['comparator']} | {s['n']} | {s['mean_difference']:+.3f} | "
                f"{s['shapiro_p']:.3g} | {s['differences_normal']} | {s['t_statistic']:.3f} | "
                f"{s['t_p']:.3g} | {s['wilcoxon_p']:.3g} | {s['significant']} |"
            )
        out.append("")

    explain = results.get("explain")
    if explain:
        out += ["## Explainability (EPS-TFT, test windows)", "", "Encoder VSN importance:", ""]
        out += ["| Variable | Mean selection weight |", "|---|---|"]
        out += [f"| {k} | {v:.3f} |" for k, v in explain["encoder_vsn_importance"].items()]
        out += ["", "Mean attention by position (minutes relative to forecast origin):", ""]
        positions = explain["attention_by_position"]
        out.append("| " + " | ".join(f"{k}" for k in positions) + " |")
        out.append("|---" * len(positions) + "|")
        out.append("| " + " | ".join(f"{v:.3f}" for v in positions.values()) + " |")
        out.append("")

    notes = results.get("notes", [])
    if notes:
        out += ["## Notes", ""] + [f"- {n}" for n in notes] + [""]
    return "\n".join(out)


def render_cv_report(cv: Mapping[str, Any]) -> str:
    horizons = [str(h) for h in cv["horizons_min"]]
    out = [
        f"# Cross-individual {cv['n_folds']}-fold validation: {cv['artifact']}",
        "",
        "Folds split patients (stratified by diabetes type); EPS-TFT is retrained per fold on"
        " the chronological train/val portions of the training patients and tested on the"
        " full recordings of the held-out patients.",
        "",
        "| Fold | Test patients | Epochs | " + " | ".join(f"RMSE {h} min" for h in horizons) + " |",
        "|---" * (3 + len(horizons)) + "|",
    ]
    for f in cv["folds"]:
        cells = " | ".join(_cell(f["summary"][h]["RMSE"]) for h in horizons)
        out.append(f"| {f['fold']} | {len(f['test_patients'])} | {f['epochs_run']} | {cells} |")
    out += [
        "",
        "| Aggregate | " + " | ".join(f"{h} min" for h in horizons) + " |",
        "|---" * (1 + len(horizons)) + "|",
        "| Mean of fold means | "
        + " | ".join(f"{cv['mean_of_fold_means'][h]:.2f}" for h in horizons) + " |",
        "| All held-out patients (mean ± STD) | "
        + " | ".join(_cell(cv["pooled"][h]["RMSE"]) for h in horizons) + " |",
    ]
    if cv.get("dataset") == "shanghai":
        out.append(
            "| Paper (mean RMSE) | "
            + " | ".join(f"{PAPER_SHANGHAI_CV_RMSE.get(int(h), float('nan')):.1f}"
                         for h in horizons)
            + " |"
        )
    out.append("")
    return "\n".join(out)
