"""Markdown rendering of ``glucorag-bench`` results (the ``results.json`` structure of ``run``)."""

from collections.abc import Mapping
from typing import Any

from glucorag.evaluate.metrics import METRICS
from glucorag.evaluate.run import MAIN

# Availability checked 2026-10-08; see the report's "Not run" section.
NOT_RUN: list[dict[str, str]] = [
    {
        "name": "GluFormer (Lutsker et al., Nature 2026)",
        "source": "https://github.com/Guylu/GluFormer",
        "licence": "Code Apache-2.0; no weights",
        "reason": (
            "No pretrained checkpoint is published: the official repository holds training/"
            "inference code, demo CSVs and a small tokenised sample tensor, and no weights are on"
            " the Hugging Face Hub. The GlucoFM paper (arXiv:2605.30865v2, App. B) also reports"
            " that official GluFormer checkpoints were unavailable and retrains it. Zero-shot"
            " evaluation is impossible without the authors' weights; retraining on our data"
            " would no longer be zero-shot."
        ),
    },
    {
        "name": "GlucoFM (Li et al., arXiv:2605.30865, NeurIPS 2026)",
        "source": "https://arxiv.org/abs/2605.30865",
        "licence": "Official weights not released",
        "reason": (
            "The authors state that code will be released; no official weights are public."
            " Community reconstructions exist (sfourdrinier/opencgm, eugenehp/glucofm-encoder,"
            " MIT) but are encoder-only representation models (128-d embeddings of one-day,"
            " 288-point 5-min windows) with no forecasting head, and they are not the authors'"
            " model, so there is no zero-shot forecast to evaluate."
        ),
    },
    {
        "name": "Moirai 1.1 / 2.0 (Salesforce)",
        "source": "https://huggingface.co/Salesforce/moirai-2.0-R-small",
        "licence": "Weights CC-BY-NC-4.0 (research use allowed)",
        "reason": (
            "Runnable in principle, but its package uni2ts 2.0.0 pins torch<2.5, numpy~=1.26"
            " and scipy~=1.11, which conflict with this project's environment (torch 2.14,"
            " numpy 2.5 when checked); it would need a separate virtualenv. Chronos and TimesFM"
            " cover the general-purpose models instead."
        ),
    },
]


def _cell(stats: Mapping[str, float]) -> str:
    return f"{stats['mean']:.2f} ± {stats['std']:.2f}"


def _params(n: int | None) -> str:
    if not n:
        return "–"
    return f"{n / 1e6:.1f} M" if n >= 1e6 else f"{n / 1e3:.0f} k"


def _rmse(method: Mapping[str, Any], h: str) -> float:
    return float(method["summary"][h]["RMSE"]["mean"])


def _models_table(methods: Mapping[str, Mapping[str, Any]], n_windows: int) -> list[str]:
    lines = [
        "| Method | Weights (revision) | Params | Licence | Device | Load (s) | Inference (s)"
        " | ms / window |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name, m in methods.items():
        if m["kind"] == "reference":
            continue
        rt = m["runtime"]
        weights = f"`{m['model_id']}`" if m.get("model_id") else "–"
        if m["kind"] == "tsfm" and m.get("revision"):
            weights += f" @ `{str(m['revision'])[:10]}`"
        load = "–" if rt["load_s"] is None else f"{rt['load_s']:.1f}"
        per = 1000.0 * rt["predict_s"] / n_windows
        lines.append(
            f"| {name} | {weights} | {_params(m.get('params'))} | {m['licence']} | {m['device']}"
            f" | {load} | {rt['predict_s']:.1f} | {per:.2f} |"
        )
    return lines


def _metric_table(methods: Mapping[str, Mapping[str, Any]], h: str) -> list[str]:
    lines = ["| Method | RMSE | MAE | MAPE (%) | gRMSE |", "|---|---|---|---|---|"]
    rows = sorted(
        ((n, m) for n, m in methods.items() if h in m["summary"]), key=lambda r: _rmse(r[1], h)
    )
    for name, m in rows:
        label = f"{name} †" if m["kind"] == "reference" else name
        if name == MAIN:
            label = f"**{label}**"
        s = m["summary"][h]
        lines.append(f"| {label} | " + " | ".join(_cell(s[k]) for k in METRICS) + " |")
    return lines


def _coverage_table(methods: Mapping[str, Mapping[str, Any]], horizons: list[str]) -> list[str]:
    head = "| Method | " + " | ".join(
        f"{h} min coverage (%) | {h} min width (mg/dL) | {h} min below / above (%)"
        for h in horizons
    )
    lines = [head + " |", "|---|" + "---|---|---|" * len(horizons)]
    for name, m in methods.items():
        cov = m.get("coverage")
        if not cov:
            continue
        cells = []
        for h in horizons:
            c = cov[h]
            cells += [
                _cell(c["coverage"]),
                _cell(c["width"]),
                f"{c['below']['mean']:.1f} / {c['above']['mean']:.1f}",
            ]
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    return lines


def _significance_table(sig: Mapping[str, Mapping[str, Any]], horizons: list[str]) -> list[str]:
    lines = [
        "| Horizon | Method | n | mean Δ RMSE (EPS-TFT − method) | Shapiro p | t-test p"
        " | Wilcoxon p | significant (paper criterion) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for h in horizons:
        for name, by_h in sig.items():
            s = by_h[h]
            lines.append(
                f"| {h} min | {name} | {s['n']} | {s['mean_difference']:+.2f} |"
                f" {s['shapiro_p']:.3g} | {s['t_p']:.3g} | {s['wilcoxon_p']:.3g} |"
                f" {s['significant']} |"
            )
    return lines


def _findings(results: Mapping[str, Any]) -> list[str]:
    methods: Mapping[str, Mapping[str, Any]] = results["methods"]
    sig: Mapping[str, Mapping[str, Any]] = results["significance"]
    horizons = [str(h) for h in results["horizons_min"]]
    tsfm = [n for n, m in methods.items() if m["kind"] == "tsfm"]
    out: list[str] = []
    if not tsfm:
        return out
    for h in horizons:
        main = _rmse(methods[MAIN], h)
        best = min(tsfm, key=lambda n: _rmse(methods[n], h))
        diff = _rmse(methods[best], h) - main
        s = sig[best][h]
        worse = sum(sig[n][h]["mean_difference"] < 0 and sig[n][h]["wilcoxon_p"] < 0.05
                    for n in tsfm)
        better = sum(sig[n][h]["mean_difference"] > 0 and sig[n][h]["wilcoxon_p"] < 0.05
                     for n in tsfm)
        criterion = (
            "met" if s["significant"] else
            "not met, paired differences not normal" if not s["differences_normal"]
            else "not met"
        )
        out.append(
            f"{h} min: the best zero-shot model is {best} with RMSE {_rmse(methods[best], h):.2f}"
            f" mg/dL vs {main:.2f} for EPS-TFT ({abs(diff):.2f} mg/dL"
            f" {'lower' if diff < 0 else 'higher'}; paired per-patient Wilcoxon p ="
            f" {s['wilcoxon_p']:.3g}, t-test p = {s['t_p']:.3g}; paper criterion {criterion})."
            f" Across all {len(tsfm)} foundation-model rows, {worse}"
            f" are significantly worse than EPS-TFT and {better} significantly better"
            " (Wilcoxon p < 0.05)."
        )
    last = horizons[-1]
    best = min(tsfm, key=lambda n: _rmse(methods[n], last))
    n_windows = results["n_test_windows"]
    ms = {n: 1000.0 * methods[n]["runtime"]["predict_s"] / n_windows for n in (MAIN, best)}
    out.append(
        f"Cost: {best} has {_params(methods[best].get('params'))} parameters and needs"
        f" {ms[best]:.2f} ms per forecast on {methods[best]['device']}, vs"
        f" {_params(methods[MAIN].get('params'))} and {ms[MAIN]:.2f} ms for EPS-TFT, and it"
        f" reads {context_label(int(methods[best]['context_min']))} of history instead of"
        f" {context_label(int(methods[MAIN]['context_min']))}."
    )
    naive = [n for n, m in methods.items() if m["kind"] == "naive"]
    if naive:
        p = _rmse(methods[naive[0]], last)
        beat = sum(_rmse(methods[n], last) < p for n in tsfm)
        out.append(
            f"Persistence (last value) scores {p:.2f} mg/dL RMSE at {last} min; {beat} of"
            f" {len(tsfm)} foundation-model rows beat it."
        )
    by_model: dict[str, dict[int, float]] = {}
    for n in tsfm:
        m = methods[n]
        by_model.setdefault(n.rsplit(", ", 1)[0], {})[int(m["context_min"])] = _rmse(m, last)
    deltas = [
        f"{base} {r[max(r)] - r[min(r)]:+.2f}" for base, r in by_model.items() if len(r) > 1
    ]
    if deltas:
        lengths = [int(m) for m in results["contexts"]]
        out.append(
            f"Longest vs shortest context ({context_label(max(lengths))} vs"
            f" {context_label(min(lengths))}) changes {last}-min RMSE by: "
            + "; ".join(deltas) + " mg/dL."
        )
    lookback = int(methods[MAIN]["context_min"])
    short = [n for n in tsfm if int(methods[n]["context_min"]) == lookback]
    if short:
        worse_short = sum(
            sig[n][h]["mean_difference"] < 0 and sig[n][h]["wilcoxon_p"] < 0.05
            for n in short for h in horizons
        )
        out.append(
            f"With EPS-TFT's own {context_label(lookback)} context, {worse_short} of"
            f" {len(short) * len(horizons)} foundation-model/horizon pairs are significantly"
            " worse than EPS-TFT (Wilcoxon p < 0.05)."
        )
    beats = sig[best][last]["mean_difference"] > 0 and sig[best][last]["wilcoxon_p"] < 0.05
    if beats and int(methods[best]["context_min"]) > lookback:
        restricted = "Non-Commercial" in str(methods[best]["licence"])
        out.append(
            f"Reading: glucose history beyond {context_label(lookback)} carries signal that"
            f" EPS-TFT's {context_label(lookback)} look-back discards. Retraining EPS-TFT with a"
            " longer look-back is the cheaper experiment before considering a foundation model"
            " in the product"
            + (f" (whose licence would not allow {best.rsplit(', ', 1)[0]} there anyway)."
               if restricted else ".")
        )
    open_rows = [n for n in tsfm if "Non-Commercial" not in str(methods[n]["licence"])]
    if open_rows and best not in open_rows:
        ob = min(open_rows, key=lambda n: _rmse(methods[n], last))
        out.append(
            f"Best permissively licensed model at {last} min: {ob} ({methods[ob]['licence']}),"
            f" RMSE {_rmse(methods[ob], last):.2f} vs {_rmse(methods[MAIN], last):.2f} mg/dL for"
            f" EPS-TFT (Wilcoxon p = {sig[ob][last]['wilcoxon_p']:.3g})."
        )
    cov = {n: m["coverage"][last]["coverage"]["mean"] for n, m in methods.items()
           if m.get("coverage") and m["kind"] in ("tsfm", "eps-tft")}
    if MAIN in cov and best in cov:
        others = [v for n, v in cov.items() if n != MAIN]
        out.append(
            f"The nominal 80% interval (q0.1–q0.9) covers {cov[MAIN]:.1f}% of {last}-min targets"
            f" for EPS-TFT and {cov[best]:.1f}% for {best} (range over all foundation-model"
            f" rows {min(others):.1f}–{max(others):.1f}%)."
        )
    ref = {n: _rmse(m, last) for n, m in methods.items() if m["kind"] == "reference"}
    if ref:
        b = min(ref, key=lambda n: ref[n])
        out.append(
            f"For context, the best trained model in `{results['reference_source']}` at {last}"
            f" min is {b} ({ref[b]:.2f} mg/dL)."
        )
    return out


def context_label(minutes: int) -> str:
    return f"{minutes // 60} h" if minutes >= 240 and minutes % 60 == 0 else f"{minutes} min"


def _caveats(results: Mapping[str, Any]) -> list[str]:
    interval = results["interval_min"]
    lookback = results["lookback_min"]
    steps = [h // interval for h in results["horizons_min"]]
    return [
        "EPS-TFT and the trained baselines were fit on the training split of the same dataset;"
        " the foundation models are zero-shot and see glucose only (no time of day, no static"
        " covariates). Fine-tuned foundation models could do better; that is not tested here.",
        f"Rows with a context longer than {context_label(lookback)} see history EPS-TFT never"
        " sees (the longest reach into the train/validation part of the same series). That"
        " favours the foundation models; it is still causal (nothing after the forecast"
        " origin).",
        "ShanghaiDM is public (2023). Whether it is in any model's pretraining corpus is not"
        " documented, so leakage in favour of the foundation models cannot be ruled out.",
        f"{interval}-min sampling and a {min(steps)}–{max(steps)}-step horizon are short for"
        f" these models; the {lookback}-min context is only {lookback // interval} points, below"
        " their input patch sizes (16–32), so they rely on padding there.",
        "Per-patient means weight every patient equally; STD is across patients (sample STD),"
        " as in the evaluation report. The paper's significance criterion needs normal paired"
        " differences (Shapiro–Wilk); when that fails, read the Wilcoxon p.",
        "Runtime is wall-clock inference over all test windows on the listed device, excluding"
        " data preparation; load time includes reading cached weights (first run also downloads"
        " them).",
        "Research only: none of these models is used by the app, and TimesFM 3.0 weights are"
        " licensed for non-commercial, non-production use only.",
    ]


def render_report(results: Mapping[str, Any]) -> str:
    horizons = [str(h) for h in results["horizons_min"]]
    methods: Mapping[str, Mapping[str, Any]] = results["methods"]
    lookback = results["lookback_min"]
    out = [
        f"# Zero-shot foundation-model benchmark: {results['dataset']} ({results['artifact']})",
        "",
        "Research prototype; not a medical device. Nothing here is used by the app.",
        "",
        f"- Data: {results['dataset']} ({results['interval_min']}-min CGM), the test split of"
        f" the evaluation report: {results['n_test_windows']} windows from"
        f" {results['n_test_patients']} patients, targets restricted to real CGM observations."
        f" Data hash matches the artifact: {results['data_hash_matches']}.",
        f"- Every model forecasts from the same origin as EPS-TFT. Context = the prepared glucose"
        f" series (mg/dL) ending at the origin: {lookback} min (EPS-TFT's look-back) and a longer"
        " context, cut at the most recent unimputed gap.",
        "- Point forecast = 0.5 quantile for every probabilistic model. Metrics are computed per"
        " patient and reported as mean ± sample STD across patients (same code as the evaluation"
        " report).",
        f"- EPS-TFT re-run from the artifact on CPU; |RMSE − stored report| ="
        f" {_fmt_diff(results.get('eps_tft_vs_stored_rmse_abs_diff', {}))}.",
        f"- Generated {results['evaluated_at']} on {results['machine']['platform']}; packages:"
        f" {', '.join(f'{k} {v}' for k, v in results['packages'].items())}.",
        "",
        "## Models and runtime",
        "",
        *_models_table(methods, results["n_test_windows"]),
        "",
    ]
    for h in horizons:
        out += [f"## {h}-minute prediction horizon", "", *_metric_table(methods, h), ""]
    if any(m["kind"] == "reference" for m in methods.values()):
        out += [
            f"† Trained baselines copied from `{results['reference_source']}` (same split and"
            " windows) for context; not re-run here.",
            "",
        ]
    out += [
        "## 80% prediction interval (q0.1–q0.9)",
        "",
        "Nominal coverage 80%; below / above = % of targets under q0.1 / over q0.9 (nominal 10"
        " each). Persistence has no interval.",
        "",
        *_coverage_table(methods, horizons),
        "",
        "## Paired test vs EPS-TFT (per-patient RMSE)",
        "",
        "Shapiro–Wilk on the paired differences, paired two-sided t-test and Wilcoxon"
        " signed-rank, as in the evaluation report. Negative Δ means EPS-TFT has the lower error.",
        "",
        *_significance_table(results["significance"], horizons),
        "",
        "## Context actually used",
        "",
        "| Context | Steps | Min length | Median length | Full length (%) |",
        "|---|---|---|---|---|",
    ]
    for minutes, c in results["contexts"].items():
        out.append(
            f"| {context_label(int(minutes))} | {c['steps']} | {c['length_min']} |"
            f" {c['length_median']:.0f} | {c['full_length_pct']:.1f} |"
        )
    out += ["", "## Not run", "", "| Model | Source | Licence / weights | Why not |",
            "|---|---|---|---|"]
    for item in results["not_run"]:
        out.append(f"| {item['name']} | {item['source']} | {item['licence']} | {item['reason']} |")
    out += ["", "## Discussion", ""]
    out += [f"- {line}" for line in _findings(results)]
    out += ["", "Caveats:", ""]
    out += [f"- {line}" for line in _caveats(results)]
    return "\n".join(out) + "\n"


def _fmt_diff(diff: Mapping[str, float]) -> str:
    if not diff:
        return "no stored report to compare"
    return ", ".join(f"{d:.3f} mg/dL at {h} min" for h, d in diff.items())
