"""Build a professional deck for the IEEE TBioCAS 2024 EPS-TFT paper."""
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from PIL import Image

NAVY = RGBColor(0x0F, 0x2A, 0x44)
NAVY_L = RGBColor(0x1C, 0x42, 0x66)
TEAL = RGBColor(0x0E, 0x7C, 0x7B)
AMBER = RGBColor(0xE0, 0x9F, 0x1E)
GREY = RGBColor(0x5B, 0x6B, 0x7B)
LGREY = RGBColor(0xEE, 0xF2, 0xF6)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
INK = RGBColor(0x1B, 0x25, 0x30)

FONT = "Helvetica Neue"
W, H = Inches(13.333), Inches(7.5)

prs = Presentation()
prs.slide_width, prs.slide_height = W, H
BLANK = prs.slide_layouts[6]

FOOT = "Zhu et al., IEEE Trans. Biomedical Circuits and Systems, 18(2), 2024 — DOI 10.1109/TBCAS.2023.3348844"


def box(slide, x, y, w, h, text="", size=16, bold=False, color=INK,
        align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, font=FONT, spacing=1.0, italic=False):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = 0
    tf.margin_top = tf.margin_bottom = 0
    p = tf.paragraphs[0]
    p.alignment = align
    p.line_spacing = spacing
    r = p.add_run()
    r.text = text
    r.font.size = Pt(size)
    r.font.bold = bold
    r.font.italic = italic
    r.font.color.rgb = color
    r.font.name = font
    return tb


def rect(slide, x, y, w, h, fill, line=None, shape=MSO_SHAPE.RECTANGLE):
    s = slide.shapes.add_shape(shape, x, y, w, h)
    if fill is None:
        s.fill.background()
    else:
        s.fill.solid()
        s.fill.fore_color.rgb = fill
    if line is None:
        s.line.fill.background()
    else:
        s.line.color.rgb = line
        s.line.width = Pt(1)
    s.shadow.inherit = False
    s.text_frame.word_wrap = True
    return s


def content_slide(title, kicker=None):
    s = prs.slides.add_slide(BLANK)
    rect(s, 0, 0, Inches(0.16), H, TEAL)
    box(s, Inches(0.55), Inches(0.42), Inches(11.6), Inches(0.7), title, 30, True, NAVY)
    if kicker:
        box(s, Inches(0.58), Inches(1.06), Inches(11.6), Inches(0.35), kicker, 13, False, GREY, italic=True)
    rect(s, Inches(0.55), Inches(1.46), Inches(1.5), Pt(3), AMBER)
    box(s, Inches(0.55), Inches(6.92), Inches(10.6), Inches(0.3), FOOT, 9, False, GREY)
    n = len(prs.slides.__iter__.__self__._sldIdLst)
    box(s, Inches(12.3), Inches(6.9), Inches(0.6), Inches(0.3), str(n), 11, True, TEAL, PP_ALIGN.RIGHT)
    return s


def bullets(slide, items, x=Inches(0.62), y=Inches(1.75), w=Inches(12.0), size=17, gap=Inches(0.06)):
    """items: str, (text, bold), or (level, text, bold)."""
    norm = []
    for it in items:
        if isinstance(it, str):
            norm.append((0, it, False))
        elif len(it) == 2:
            norm.append((0, it[0], it[1]))
        else:
            norm.append(tuple(it))
    tb = slide.shapes.add_textbox(x, y, w, Inches(4.9))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = 0
    for i, (lvl, text, bold) in enumerate(norm):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = gap
        p.line_spacing = 1.12
        r = p.add_run()
        r.text = ("▪  " if lvl == 0 else "        –  ") + text
        r.font.size = Pt(size if lvl == 0 else size - 2)
        r.font.bold = bold
        r.font.color.rgb = INK if lvl == 0 else GREY
        r.font.name = FONT
    return tb


def picture(slide, path, x, y, max_w, max_h, caption=None, cap_size=11):
    iw, ih = Image.open(path).size
    scale = min(max_w / iw, max_h / ih)
    w, h = int(iw * scale), int(ih * scale)
    px = x + int((max_w - w) / 2)
    slide.shapes.add_picture(path, px, y, Emu(w), Emu(h))
    if caption:
        box(slide, x, y + Emu(h) + Inches(0.08), max_w, Inches(0.5), caption, cap_size,
            False, GREY, PP_ALIGN.CENTER, italic=True)


def card(slide, x, y, w, h, value, label, accent=TEAL, vsize=28, lsize=12):
    rect(slide, x, y, w, h, LGREY)
    rect(slide, x, y, w, Pt(4), accent)
    tight = h < Inches(1.2)
    vs = 22 if tight else vsize
    box(slide, x + Inches(0.18), y + Inches(0.14 if tight else 0.26), w - Inches(0.36), Inches(0.5),
        value, vs, True, NAVY, PP_ALIGN.CENTER)
    box(slide, x + Inches(0.14), y + Inches(0.56 if tight else 0.92), w - Inches(0.28), Inches(0.6),
        label, 11 if tight else lsize, False, GREY, PP_ALIGN.CENTER)


def table(slide, data, x, y, w, h, col_w=None, head_fill=NAVY, size=12,
          highlight_rows=(), band=True):
    rows, cols = len(data), len(data[0])
    shp = slide.shapes.add_table(rows, cols, x, y, w, h)
    tbl = shp.table
    tbl.first_row = True
    if col_w:
        total = sum(col_w)
        for i, cw in enumerate(col_w):
            tbl.columns[i].width = Emu(int(w * cw / total))
    for r in range(rows):
        tbl.rows[r].height = Inches(0.32) if r else Inches(0.36)
        for c in range(cols):
            cell = tbl.cell(r, c)
            cell.text = str(data[r][c])
            cell.margin_left = cell.margin_right = Inches(0.07)
            cell.margin_top = cell.margin_bottom = Inches(0.02)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            p = cell.text_frame.paragraphs[0]
            p.alignment = PP_ALIGN.LEFT if c == 0 else PP_ALIGN.CENTER
            f = p.runs[0].font if p.runs else None
            if f:
                f.size = Pt(size)
                f.name = FONT
            cell.fill.solid()
            if r == 0:
                cell.fill.fore_color.rgb = head_fill
                if f:
                    f.bold = True
                    f.color.rgb = WHITE
            elif r in highlight_rows:
                cell.fill.fore_color.rgb = RGBColor(0xDE, 0xEF, 0xEE)
                if f:
                    f.bold = True
                    f.color.rgb = RGBColor(0x0A, 0x5A, 0x59)
            else:
                cell.fill.fore_color.rgb = WHITE if (not band or r % 2) else LGREY
                if f:
                    f.color.rgb = INK
    return tbl


def section(title, subtitle, num):
    s = prs.slides.add_slide(BLANK)
    rect(s, 0, 0, W, H, NAVY)
    rect(s, Inches(0.9), Inches(3.0), Inches(0.9), Pt(4), AMBER)
    box(s, Inches(0.9), Inches(2.3), Inches(3), Inches(0.5), num, 15, True, AMBER)
    box(s, Inches(0.9), Inches(3.35), Inches(10.5), Inches(1.0), title, 40, True, WHITE)
    box(s, Inches(0.9), Inches(4.35), Inches(9.5), Inches(0.8), subtitle, 17, False,
        RGBColor(0xAF, 0xC4, 0xD6))
    return s


# ───────────────────────── 1. Title ─────────────────────────
s = prs.slides.add_slide(BLANK)
rect(s, 0, 0, W, H, NAVY)
rect(s, 0, 0, Inches(0.22), H, TEAL)
box(s, Inches(0.95), Inches(1.05), Inches(9.5), Inches(0.4),
    "IEEE TRANSACTIONS ON BIOMEDICAL CIRCUITS AND SYSTEMS · VOL. 18, NO. 2 · APRIL 2024",
    12, True, AMBER)
box(s, Inches(0.95), Inches(1.65), Inches(11.4), Inches(2.0),
    "Population-Specific Glucose Prediction in Diabetes Care With Transformer-Based Deep Learning on the Edge",
    40, True, WHITE, spacing=1.06)
rect(s, Inches(0.98), Inches(3.9), Inches(1.6), Pt(4), AMBER)
box(s, Inches(0.95), Inches(4.18), Inches(11.0), Inches(0.5),
    "EPS-TFT — a population-specific temporal fusion Transformer for multi-horizon blood-glucose forecasting (software scope)",
    17, False, RGBColor(0xC3, 0xD6, 0xE5))
box(s, Inches(0.95), Inches(4.85), Inches(11.0), Inches(0.9),
    "Taiyu Zhu · Lei Kuang · Chengzhe Piao · Junming Zeng · Kezhi Li · Pantelis Georgiou\n"
    "Imperial College London · University College London · University of Oxford",
    14, False, RGBColor(0x9F, 0xB6, 0xC9), spacing=1.25)
for i, (v, l) in enumerate([("124", "T1D / T2D participants"), ("2", "clinical CGM datasets"),
                            ("30 & 60", "min horizons, one model"), ("7", "quantile outputs"),
                            ("6", "baselines outperformed")]):
    x = Inches(0.95) + i * Inches(2.34)
    rect(s, x, Inches(5.85), Inches(2.15), Inches(1.0), NAVY_L)
    rect(s, x, Inches(5.85), Inches(2.15), Pt(3), TEAL)
    box(s, x, Inches(6.05), Inches(2.15), Inches(0.4), v, 20, True, WHITE, PP_ALIGN.CENTER)
    box(s, x, Inches(6.46), Inches(2.15), Inches(0.4), l, 10, False,
        RGBColor(0xA8, 0xBE, 0xD0), PP_ALIGN.CENTER)

# ───────────────────────── 2. Agenda ─────────────────────────
s = content_slide("Agenda", "From clinical need to a validated forecasting model")
items = [("01", "Clinical problem", "Diabetes burden, CGM lag, why prediction matters"),
         ("02", "Research gaps", "Patient-specific models, single horizon, little T2D work"),
         ("03", "Method: EPS-TFT", "Temporal fusion Transformer with gating + quantile forecasts"),
         ("04", "Experiments", "OhioT1DM & ShanghaiDM, 7 methods, 4 metrics, 2 horizons"),
         ("05", "Results & validation", "Accuracy, trajectories, ablation, in-silico trial"),
         ("06", "Discussion", "Limitations, generalization, deployment path")]
for i, (n, t, d) in enumerate(items):
    y = Inches(1.78) + i * Inches(0.71)
    rect(s, Inches(0.62), y, Inches(11.9), Inches(0.62), LGREY if i % 2 == 0 else WHITE)
    box(s, Inches(0.78), y + Inches(0.14), Inches(0.7), Inches(0.4), n, 16, True, TEAL)
    box(s, Inches(1.55), y + Inches(0.15), Inches(3.3), Inches(0.4), t, 16, True, NAVY)
    box(s, Inches(4.9), y + Inches(0.17), Inches(7.5), Inches(0.4), d, 14, False, GREY)

# ───────────────────────── 3. Section I ─────────────────────────
section("Clinical Problem & Motivation", "Why real-time blood-glucose forecasting is load-bearing in diabetes care", "PART 01")

# 4. Burden
s = content_slide("Diabetes: scale of the problem", "IDF Diabetes Atlas + CGM physiology")
for i, (v, l) in enumerate([("> 500 M", "people living with diabetes worldwide"),
                            ("~10 %", "of cases are Type 1 (autoimmune β-cell loss)"),
                            ("> 90 %", "of cases are Type 2 (secretion + resistance)"),
                            ("~30 %", "of time spent outside euglycemic range")]):
    card(s, Inches(0.62) + i * Inches(3.05), Inches(1.75), Inches(2.85), Inches(1.75), v, l,
         [TEAL, AMBER, TEAL, AMBER][i])
bullets(s, [
    ("CGM measures interstitial fluid glucose, not blood — the conversion introduces an intrinsic lag between reading and true BG."),
    ("Hypo-/hyperglycemia detected only after the fact leaves no window for proactive action."),
    (1, "Prediction converts a monitoring device into a decision-support device.", False),
    ("Unmanaged excursions drive cardiovascular disease, nephropathy, retinopathy and diabetic ketoacidosis."),
    ("CGM produces high-resolution time series — ideal substrate for deep sequence models."),
], y=Inches(3.85), size=16)

# 5. Gaps & contributions
s = content_slide("Research gaps and contributions", "What the literature misses, and what this paper delivers")
rect(s, Inches(0.62), Inches(1.72), Inches(5.85), Inches(4.9), LGREY)
rect(s, Inches(0.62), Inches(1.72), Inches(5.85), Pt(4), GREY)
box(s, Inches(0.85), Inches(1.95), Inches(5.4), Inches(0.4), "GAPS IN PRIOR WORK", 14, True, GREY)
gaps = ["Patient-specific models: one network per subject — does not scale to a cohort",
        "Single prediction horizon: separate models for 30 and 60 min",
        "T2D (>90 % of cases) is largely unexplored in BG prediction",
        "Most models need manual inputs (meals, insulin) that are inconsistent across a population",
        "Little use of static demographics to personalise a shared model"]
bullets(s, gaps, x=Inches(0.85), y=Inches(2.45), w=Inches(5.4), size=14, gap=Inches(0.14))
rect(s, Inches(6.72), Inches(1.72), Inches(5.85), Inches(4.9), WHITE, line=TEAL)
rect(s, Inches(6.72), Inches(1.72), Inches(5.85), Pt(4), TEAL)
box(s, Inches(6.95), Inches(1.95), Inches(5.4), Inches(0.4), "THIS PAPER", 14, True, TEAL)
contrib = ["One population-specific TFT serving a whole cohort, conditioned on demographics",
           "Multi-horizon direct forecast: 30 and 60 min from a single forward pass",
           "Validated on both T1D (24 subjects) and T2D (100 subjects)",
           "Feature selection via VSN weights: CGM + timestamp alone suffice (93.9 % importance)",
           "Quantile loss → prediction intervals for tunable hypo/hyper alarms",
           "In-silico decision-support trial with the UVA/Padova simulator"]
bullets(s, contrib, x=Inches(6.95), y=Inches(2.45), w=Inches(5.4), size=14, gap=Inches(0.14))

# ───────────────────────── Section II ─────────────────────────
section("Method: EPS-TFT", "Problem formulation, gated Transformer architecture, quantile forecasting", "PART 02")

# 7. Problem formulation
s = content_slide("Problem formulation", "Multi-horizon forecasting with heterogeneous inputs")
rect(s, Inches(0.62), Inches(1.8), Inches(11.9), Inches(1.1), NAVY)
box(s, Inches(0.9), Inches(2.05), Inches(11.4), Inches(0.6),
    "Given timestep t and target BG series y, forecast  y(t : t+τ)  for horizon τ ∈ {30, 60} min",
    22, True, WHITE)
inputs = [("Observed inputs", "Past CGM readings\n(24 samples = 120 min look-back)", TEAL),
          ("Known inputs", "Timestamps, known for past\nand future (12 steps ahead)", AMBER),
          ("Static covariates", "Gender, age, BMI,\ndiabetes type", NAVY_L),
          ("Output", "12-step BG trajectory\n× 7 quantiles", TEAL)]
for i, (t, d, c) in enumerate(inputs):
    x = Inches(0.62) + i * Inches(3.05)
    rect(s, x, Inches(3.25), Inches(2.85), Inches(1.75), WHITE, line=RGBColor(0xD5, 0xDE, 0xE6))
    rect(s, x, Inches(3.25), Inches(2.85), Pt(4), c)
    box(s, x + Inches(0.18), Inches(3.5), Inches(2.5), Inches(0.4), t, 15, True, NAVY)
    box(s, x + Inches(0.18), Inches(3.95), Inches(2.5), Inches(1.0), d, 13, False, GREY, spacing=1.2)
bullets(s, ["Direct (non-recursive) multi-horizon output: all future values in one forward step — faster and no error accumulation.",
            "A single set of weights serves the whole population; personalization comes from the static covariate path, not retraining.",
            "Feature set deliberately reduced to CGM + timestamp → no manual user input, enabling fully automatic operation."],
        y=Inches(5.2), size=15)

# 8. System architecture (software)
s = content_slide("End-to-end system architecture", "Software pipeline — cohort CGM streams → TFT inference → predictive decision support")
flow = [("CGM data", "5 / 15-min readings\nper patient", NAVY_L),
        ("Preprocessing", "causal imputation\nclip 40–400 · normalize", NAVY_L),
        ("Feature window", "24 past steps +\n12 known future steps", NAVY_L),
        ("EPS-TFT", "VSN · GRN · LSTM ·\nattention · quantile head", TEAL),
        ("Risk engine", "hypo / hyper flags\nfrom quantile bounds", AMBER),
        ("Decision support", "alerts · forecast view\nPLGM insulin rule", NAVY)]
for i, (t, d, c) in enumerate(flow):
    x = Inches(0.62) + i * Inches(2.02)
    rect(s, x, Inches(2.3), Inches(1.78), Inches(1.9), c)
    box(s, x, Inches(2.45), Inches(1.78), Inches(0.4), t, 15, True, WHITE, PP_ALIGN.CENTER)
    box(s, x + Inches(0.08), Inches(3.0), Inches(1.62), Inches(1.1), d, 11.5, False, WHITE, PP_ALIGN.CENTER, spacing=1.15)
    if i < len(flow) - 1:
        box(s, x + Inches(1.78), Inches(2.95), Inches(0.24), Inches(0.5), "›", 26, True, AMBER, PP_ALIGN.CENTER)
rect(s, Inches(4.66), Inches(4.55), Inches(3.8), Inches(1.0), LGREY)
rect(s, Inches(4.66), Inches(4.55), Pt(4), Inches(1.0), TEAL)
box(s, Inches(4.85), Inches(4.62), Inches(3.5), Inches(0.35), "Static demographics", 14, True, NAVY)
box(s, Inches(4.85), Inches(4.98), Inches(3.5), Inches(0.5), "age · gender · BMI · diabetes type → covariate encoder context", 11.5, False, GREY)
box(s, Inches(6.4), Inches(4.2), Inches(0.4), Inches(0.35), "↑", 20, True, TEAL, PP_ALIGN.CENTER)
box(s, Inches(0.62), Inches(5.9), Inches(11.9), Inches(0.6),
    "One population model serves the whole cohort; demographics personalise predictions, and quantile outputs drive tunable alarms.",
    14, False, INK, spacing=1.18)

# 9. TFT architecture (Fig 2)
s = content_slide("Temporal fusion Transformer architecture", "Fig. 2 — gated, multi-modal encoder–decoder")
picture(s, "assets/fig2_tft.png", Inches(0.62), Inches(1.72), Inches(5.6), Inches(4.7))
comp = [("VSN — Variable Selection Network", "GRN + Softmax weights per feature per timestep; also used post-hoc for feature importance"),
        ("Covariate encoder", "Turns static demographics into context vectors for VSN, LSTM initial states and static enrichment"),
        ("LSTM encoder / decoder", "Encoder: observed + past known features. Decoder: future known inputs, initialized by encoder state"),
        ("Multi-head self-attention", "Long-range temporal dependencies + interpretability by head aggregation"),
        ("GLU + residual paths", "Allow the model to skip LSTM, MHSA or the whole Transformer block when a simpler mapping suffices")]
y = Inches(1.78)
for t, d in comp:
    rect(s, Inches(6.5), y, Inches(6.05), Inches(0.9), LGREY)
    rect(s, Inches(6.5), y, Pt(4), Inches(0.9), TEAL)
    box(s, Inches(6.72), y + Inches(0.1), Inches(5.7), Inches(0.3), t, 14, True, NAVY)
    box(s, Inches(6.72), y + Inches(0.42), Inches(5.7), Inches(0.5), d, 11.5, False, GREY, spacing=1.15)
    y += Inches(0.95)

# 10. Gating math
s = content_slide("Gating mechanisms and loss", "The machinery that makes multi-modal fusion and interval forecasts work")
eqs = [("Gated linear unit (1)", "GLU(z) = σ(W_g·z + b_g) ⊙ (W_l·z + b_l)",
        "Sigmoid gate modulates how much non-linear contribution passes."),
       ("Gated residual network (2–3)", "GRN(p,e) = LN(p + GLU(W_g·a + b_g)),   a = ELU(W_p·p + W_e·e + b_a)",
        "Residual + layer norm; ELU damps outliers and CGM noise."),
       ("Multi-head self-attention (4–6)", "MHSA = [ (1/N) Σ H_i ] W_O ,   A = Softmax(Q K^T / √D_k) V",
        "Q, K, V come from the GRN static-enrichment layer: static and temporal features fused."),
       ("Quantile loss (7)", "L = (1/τ) Σ_i Σ_q (1−q)(ŷ_i − y_i)⁺ + q(y_i − ŷ_i)⁺,   q ∈ {0.02, 0.1, 0.25, 0.5, 0.75, 0.9, 0.98}",
        "Lower/upper bounds make alarm sensitivity a tunable knob — a feature patients requested in earlier focus groups.")]
y = Inches(1.72)
for t, e, d in eqs:
    rect(s, Inches(0.62), y, Inches(11.9), Inches(1.2), WHITE, line=RGBColor(0xD5, 0xDE, 0xE6))
    rect(s, Inches(0.62), y, Pt(4), Inches(1.2), AMBER)
    box(s, Inches(0.85), y + Inches(0.12), Inches(4.5), Inches(0.3), t, 14, True, NAVY)
    box(s, Inches(0.85), y + Inches(0.46), Inches(11.2), Inches(0.32), e, 12.5, False, TEAL, font="Menlo")
    box(s, Inches(0.85), y + Inches(0.84), Inches(11.2), Inches(0.3), d, 11.5, False, GREY)
    y += Inches(1.3)

# ───────────────────────── Section IV ─────────────────────────
section("Experimental Design", "Datasets, preprocessing, baselines and clinical metrics", "PART 03")

# 15. Datasets
s = content_slide("Clinical datasets", "Two public CGM cohorts — 124 participants in total")
table(s, [["", "OhioT1DM", "ShanghaiDM"],
          ["Participants", "12 T1D", "12 T1D + 100 T2D"],
          ["CGM device", "Medtronic Enlite (real-time)", "Abbott FreeStyle Libre (flash)"],
          ["Sampling interval", "5 minutes", "15 minutes"],
          ["Trial duration", "8 weeks", "14 days"],
          ["Auxiliary data", "Pump insulin, self-reported meals & exercise", "Self-reported diet & insulin, physical exam, questionnaire, labs"],
          ["Split", "Provided train (~6 wk) / test (~2 wk)", "80 / 20 chronological per subject"],
          ["Static features used", "Gender, age", "Gender, age, BMI, diabetes type"]],
      Inches(0.62), Inches(1.75), Inches(11.9), Inches(3.4), col_w=[2.2, 3.4, 3.9], size=12.5)
bullets(s, ["Final 25 % of every training set held out for validation; individual sets aggregated into population-level splits.",
            "Missing CGM (mainly OhioT1DM: calibration, artifacts) filled by causal linear extrapolation, clipped to the 40–400 mg/dL sensor range.",
            "Timestamps normalized over the 24 h cycle to [0, 1]; all other features standard-normalized."],
        y=Inches(5.35), size=15)

# 16. Feature selection (Fig 4)
s = content_slide("Feature selection from variable selection weights", "Fig. 4 — VSN weights act as post-hoc interpretation")
picture(s, "assets/fig4_feat.png", Inches(0.62), Inches(1.9), Inches(6.6), Inches(3.6))
bullets(s, [("CGM + timestamp account for 93.9 % of encoder VSN selection weight.", True),
            "Insulin, meal and exercise contribute little at population level — inter-individual variability in daily behaviour makes these features inconsistent.",
            "Model retrained with only CGM + timestamp; the same setup carried over to ShanghaiDM.",
            (1, "No manual logging → closed-loop-ready, fewer human errors.", False),
            (1, "Smaller input set → less computation per prediction.", False)],
        x=Inches(7.5), y=Inches(1.95), w=Inches(5.1), size=14, gap=Inches(0.12))

# 17. Baselines & metrics
s = content_slide("Baselines, training and evaluation metrics", "Seven methods, four metrics, two horizons")
rect(s, Inches(0.62), Inches(1.75), Inches(5.85), Inches(2.5), WHITE, line=RGBColor(0xD5, 0xDE, 0xE6))
rect(s, Inches(0.62), Inches(1.75), Inches(5.85), Pt(4), NAVY)
box(s, Inches(0.85), Inches(1.95), Inches(5.4), Inches(0.35), "BASELINES", 14, True, NAVY)
bullets(s, ["Classical, single-horizon (two models each): SVR, XGBoost, Linear Regression",
            "Deep, reconfigured as multi-horizon: LSTM, N-BEATS, N-HiTS",
            "PyTorch 1.11 / Python 3.9, trained on an NVIDIA GTX 1080 Ti"],
        x=Inches(0.85), y=Inches(2.4), w=Inches(5.4), size=13.5, gap=Inches(0.12))
rect(s, Inches(6.72), Inches(1.75), Inches(5.85), Inches(2.5), WHITE, line=RGBColor(0xD5, 0xDE, 0xE6))
rect(s, Inches(6.72), Inches(1.75), Inches(5.85), Pt(4), TEAL)
box(s, Inches(6.95), Inches(1.95), Inches(5.4), Inches(0.35), "TRAINING SETUP", 14, True, TEAL)
bullets(s, ["120 min look-back window → 60 min forecast (12 steps)",
            "Adam optimizer on quantile loss; 200 epochs, early stopping patience 20",
            "Hyperparameters tuned per dataset with the HyperBand tuner"],
        x=Inches(6.95), y=Inches(2.4), w=Inches(5.4), size=13.5, gap=Inches(0.12))
mets = [("RMSE", "Root mean square error — penalizes large deviations"),
        ("MAE", "Mean absolute error — average magnitude"),
        ("MAPE", "Relative error; comparable across BG scales in a diverse population"),
        ("gRMSE", "Glucose-specific RMSE (Clarke-error weighted) — penalizes clinically harmful mistakes")]
for i, (t, d) in enumerate(mets):
    x = Inches(0.62) + i * Inches(3.05)
    rect(s, x, Inches(4.5), Inches(2.85), Inches(1.9), LGREY)
    rect(s, x, Inches(4.5), Inches(2.85), Pt(4), AMBER)
    box(s, x + Inches(0.18), Inches(4.72), Inches(2.5), Inches(0.4), t, 20, True, NAVY)
    box(s, x + Inches(0.18), Inches(5.2), Inches(2.5), Inches(1.1), d, 12, False, GREY, spacing=1.18)

# ───────────────────────── Section V ─────────────────────────
section("Results", "Accuracy, trajectories, ablation and in-silico validation", "PART 04")

# 19. Table I
s = content_slide("Prediction accuracy — OhioT1DM (12 T1D)", "Table I — mean ± STD; EPS-TFT best on every metric and horizon")
t1 = [["Method", "RMSE", "MAE", "MAPE (%)", "gRMSE"],
      ["EPS-TFT", "19.1 ± 2.5", "13.1 ± 1.6", "8.5 ± 1.6", "23.3 ± 3.1"],
      ["N-BEATS", "19.4 ± 2.3", "13.4 ± 1.6", "8.9 ± 1.6", "23.8 ± 2.7"],
      ["N-HiTS", "19.6 ± 2.3", "13.9 ± 1.6", "9.5 ± 1.7", "24.5 ± 2.8"],
      ["LSTM", "20.2 ± 2.6", "14.3 ± 1.7", "9.7 ± 1.7", "24.6 ± 3.3"],
      ["XGBoost", "22.1 ± 2.9", "15.7 ± 1.9", "10.6 ± 2.0", "28.2 ± 3.9"],
      ["LR", "22.2 ± 2.8", "15.9 ± 2.0", "10.9 ± 2.1", "27.7 ± 3.7"],
      ["SVR", "23.5 ± 4.7", "16.1 ± 2.3", "10.6 ± 2.0", "29.9 ± 6.7"]]
t2 = [["Method", "RMSE", "MAE", "MAPE (%)", "gRMSE"],
      ["EPS-TFT", "32.3 ± 3.8", "23.2 ± 2.8", "15.5 ± 2.8", "40.1 ± 4.9"],
      ["N-HiTS", "33.0 ± 3.7", "24.5 ± 2.9", "17.3 ± 3.1", "42.5 ± 4.6"],
      ["N-BEATS", "33.8 ± 3.9", "24.4 ± 3.0", "16.3 ± 3.0", "43.0 ± 4.9"],
      ["LSTM", "34.4 ± 4.2", "25.4 ± 3.1", "17.6 ± 3.3", "42.7 ± 5.4"],
      ["XGBoost", "35.6 ± 4.7", "26.4 ± 3.4", "18.1 ± 3.7", "46.6 ± 6.6"],
      ["LR", "36.0 ± 4.6", "27.0 ± 3.7", "18.7 ± 3.9", "46.5 ± 6.6"],
      ["SVR", "37.0 ± 5.6", "27.0 ± 3.9", "18.0 ± 3.7", "48.5 ± 8.0"]]
box(s, Inches(0.62), Inches(1.72), Inches(5.8), Inches(0.35), "PH = 30 minutes  (mg/dL)", 14, True, TEAL)
table(s, t1, Inches(0.62), Inches(2.12), Inches(5.85), Inches(3.1), col_w=[1.6, 1.4, 1.4, 1.3, 1.4], size=11.5, highlight_rows=(1,))
box(s, Inches(6.72), Inches(1.72), Inches(5.8), Inches(0.35), "PH = 60 minutes  (mg/dL)", 14, True, AMBER)
table(s, t2, Inches(6.72), Inches(2.12), Inches(5.85), Inches(3.1), col_w=[1.6, 1.4, 1.4, 1.3, 1.4], size=11.5, highlight_rows=(1,))
bullets(s, ["Multi-horizon deep models (EPS-TFT, N-BEATS, N-HiTS, LSTM) clearly beat single-horizon SVR / XGBoost / LR.",
            "Gains over the next-best method are small at 30 min but statistically significant (paired t-test, p < 0.05, normality by Shapiro-Wilk)."],
        y=Inches(5.5), size=14)

# 20. Table II
s = content_slide("Prediction accuracy — ShanghaiDM (12 T1D + 100 T2D)", "Table II — the first large-cohort T2D forecasting benchmark of its kind")
t3 = [["Method", "RMSE", "MAE", "MAPE (%)", "gRMSE"],
      ["EPS-TFT", "12.7 ± 3.8", "8.8 ± 2.8", "6.7 ± 2.3", "14.8 ± 4.9"],
      ["N-BEATS", "12.9 ± 4.0", "9.0 ± 3.0", "6.9 ± 2.2", "15.1 ± 5.2"],
      ["LSTM", "13.1 ± 3.7", "9.2 ± 2.7", "7.1 ± 2.2", "15.4 ± 5.0"],
      ["N-HiTS", "13.4 ± 4.1", "9.3 ± 3.1", "7.1 ± 2.3", "15.6 ± 5.3"],
      ["XGBoost", "17.2 ± 7.0", "13.1 ± 6.2", "11.5 ± 8.3", "20.8 ± 9.3"],
      ["LR", "17.7 ± 14.3", "12.4 ± 5.6", "9.5 ± 4.5", "20.3 ± 17.4"],
      ["SVR", "18.3 ± 9.4", "13.8 ± 8.3", "11.9 ± 10.3", "22.2 ± 12.5"]]
t4 = [["Method", "RMSE", "MAE", "MAPE (%)", "gRMSE"],
      ["EPS-TFT", "21.7 ± 6.9", "15.1 ± 5.1", "11.2 ± 4.1", "26.2 ± 9.5"],
      ["N-BEATS", "22.1 ± 7.0", "15.4 ± 5.2", "11.6 ± 3.7", "26.9 ± 9.6"],
      ["N-HiTS", "22.5 ± 7.0", "15.7 ± 5.3", "11.8 ± 3.9", "27.2 ± 9.5"],
      ["LSTM", "22.5 ± 6.8", "15.9 ± 5.0", "12.0 ± 3.9", "27.4 ± 9.4"],
      ["SVR", "26.3 ± 10.7", "20.1 ± 9.6", "16.9 ± 11.5", "32.4 ± 14.4"],
      ["XGBoost", "27.1 ± 10.8", "21.0 ± 9.9", "18.0 ± 11.7", "32.6 ± 13.6"],
      ["LR", "28.8 ± 16.4", "21.0 ± 10.6", "16.7 ± 7.6", "34.1 ± 19.8"]]
box(s, Inches(0.62), Inches(1.72), Inches(5.8), Inches(0.35), "PH = 30 minutes  (mg/dL)", 14, True, TEAL)
table(s, t3, Inches(0.62), Inches(2.12), Inches(5.85), Inches(3.1), col_w=[1.6, 1.5, 1.4, 1.4, 1.5], size=11.5, highlight_rows=(1,))
box(s, Inches(6.72), Inches(1.72), Inches(5.8), Inches(0.35), "PH = 60 minutes  (mg/dL)", 14, True, AMBER)
table(s, t4, Inches(6.72), Inches(2.12), Inches(5.85), Inches(3.1), col_w=[1.6, 1.5, 1.4, 1.4, 1.5], size=11.5, highlight_rows=(1,))
bullets(s, ["A single population model covers both diabetes types; static covariates (incl. diabetes type, BMI) supply the personalization.",
            "Five-fold cross-individual validation on unseen ShanghaiDM cohorts: mean RMSE 14.7 mg/dL (30 min) and 23.5 mg/dL (60 min)."],
        y=Inches(5.5), size=14)

# 21. Trajectories (Fig 5)
s = content_slide("Qualitative behaviour across patient phenotypes", "Fig. 5 — two-day traces, 60-min EPS-TFT predictions")
picture(s, "assets/fig5_traj.png", Inches(0.8), Inches(1.7), Inches(5.6), Inches(4.9))
bullets(s, [("(a) OhioT1DM T1D: both hypo- and hyperglycemia, high variability, missing CGM segments.", False),
            ("(b) ShanghaiDM T1D: hypoglycemia-dominated profile.", False),
            ("(c) ShanghaiDM T2D: hyperglycemia-dominated profile.", False),
            ("Predictions track measured CGM closely across all three phenotypes — evidence of population-level generalization.", True),
            ("Quantile bounds (25th / 75th percentile band) capture severe hypo- and hyperglycemia events that the point forecast alone misses.", True),
            ("Alarm thresholds can be moved along the quantile range to trade sensitivity against false alarms.", False)],
        x=Inches(6.9), y=Inches(2.0), w=Inches(5.6), size=14, gap=Inches(0.18))

# 24. Ablation (Fig 7)
s = content_slide("Ablation study", "Fig. 7 (Appendix A) — contribution of TFT submodules, ShanghaiDM, 60-min PH")
picture(s, "assets/fig7a_abl.png", Inches(0.62), Inches(1.75), Inches(5.9), Inches(3.4))
picture(s, "assets/fig7b_abl.png", Inches(0.62), Inches(5.3), Inches(5.9), Inches(1.4))
for i, (v, l, c) in enumerate([("21.7", "Full EPS-TFT — mean RMSE (mg/dL)", TEAL),
                               ("22.0", "No LSTM decoder", GREY),
                               ("22.4", "No covariate encoder", AMBER)]):
    y = Inches(1.8) + i * Inches(1.25)
    card(s, Inches(6.9), y, Inches(5.6), Inches(1.1), v, l, c)
bullets(s, ["Removing the covariate encoder costs the most accuracy: static demographics are what make one population model work for a heterogeneous cohort.",
            "Degradation concentrates exactly where it matters clinically — hypo- and hyperglycemic excursions (Fig. 7b)."],
        x=Inches(6.9), y=Inches(5.6), w=Inches(5.6), size=13, gap=Inches(0.12))

# 25. In-silico trial (Fig 8)
s = content_slide("In-silico decision-support trial", "Appendix B — 3-month UVA/Padova T1D simulation, 10 virtual adults, PLGM decision support")
picture(s, "assets/fig8_cvga.png", Inches(6.6), Inches(1.75), Inches(5.9), Inches(4.2),
        "Fig. 8 — Control-variability grid analysis; each dot is one day's min/max BG.")
box(s, Inches(0.62), Inches(1.78), Inches(5.7), Inches(0.5),
    "Predictive low-glucose management: pump suspends basal insulin when the 60-min prediction ≤ 70 mg/dL.",
    14, False, INK, spacing=1.18)
rows = [["Outcome", "Open loop", "With EPS-TFT"],
        ["Time below 70 mg/dL", "5.3 %", "1.9 %"],
        ["Time in range 70–180 mg/dL", "74.6 %", "75.2 %"],
        ["CVGA A+B zone", "71 %", "80 %"],
        ["CVGA D+E zone", "—", "−9 %"]]
table(s, rows, Inches(0.62), Inches(2.6), Inches(5.7), Inches(1.9), col_w=[2.6, 1.5, 1.6], size=12.5,
      highlight_rows=(1, 3))
bullets(s, ["Hypoglycemia exposure cut by ~64 % relative — the clinically dominant benefit.",
            "Simulator streamed CGM to the model, which returned 60-min predictions that drove the insulin-suspend rule.",
            "Time-in-range improvement is modest; the mechanism targets lows, not overall glycemia."],
        x=Inches(0.62), y=Inches(4.75), w=Inches(5.7), size=13.5, gap=Inches(0.12))

# ───────────────────────── Section VI ─────────────────────────
section("Discussion & Conclusion", "What it means, what it does not yet solve", "PART 05")

# 27. Discussion
s = content_slide("Discussion — strengths, caveats, limitations")
rect(s, Inches(0.62), Inches(1.72), Inches(3.85), Inches(4.85), WHITE, line=TEAL)
rect(s, Inches(0.62), Inches(1.72), Inches(3.85), Pt(4), TEAL)
box(s, Inches(0.85), Inches(1.92), Inches(3.5), Inches(0.35), "STRENGTHS", 14, True, TEAL)
bullets(s, ["One model, one cohort, two horizons, two diabetes types",
            "Only CGM + timestamp needed: no manual input",
            "Prediction intervals give clinicians a tunable alarm policy",
            "Hospital-scale use case: cohort monitoring on inpatient wards (post-COVID CGM uptake)"],
        x=Inches(0.85), y=Inches(2.38), w=Inches(3.5), size=13, gap=Inches(0.16))
rect(s, Inches(4.72), Inches(1.72), Inches(3.85), Inches(4.85), WHITE, line=AMBER)
rect(s, Inches(4.72), Inches(1.72), Inches(3.85), Pt(4), AMBER)
box(s, Inches(4.95), Inches(1.92), Inches(3.5), Inches(0.35), "CAVEATS", 14, True, AMBER)
bullets(s, ["RMSE margin over N-BEATS is small at 30 min — significant (p < 0.05) but modest; it matters mainly for precision dosing / artificial pancreas loops",
            "Population-specific multi-horizon setting is not directly comparable with classic patient-specific results",
            "Simple models (LR in a phone app) remain preferable when latency is irrelevant or data cannot leave the device for training"],
        x=Inches(4.95), y=Inches(2.38), w=Inches(3.5), size=13, gap=Inches(0.16))
rect(s, Inches(8.82), Inches(1.72), Inches(3.7), Inches(4.85), WHITE, line=GREY)
rect(s, Inches(8.82), Inches(1.72), Inches(3.7), Pt(4), GREY)
box(s, Inches(9.05), Inches(1.92), Inches(3.4), Inches(0.35), "LIMITS & FUTURE WORK", 14, True, GREY)
bullets(s, ["No cross-population transfer (5 vs 15 min CGM resolution, cohort variability) → meta-learning / domain generalization planned",
            "Missing-data protocol: alerts + linear imputation < 1 h, prediction suspended beyond",
            "Next: integration with CGM systems and insulin-pump decision logic",
            "Real-world clinical trials, expert review, user studies still required"],
        x=Inches(9.05), y=Inches(2.38), w=Inches(3.4), size=13, gap=Inches(0.16))

# 28. Conclusion
s = prs.slides.add_slide(BLANK)
rect(s, 0, 0, W, H, NAVY)
rect(s, 0, 0, Inches(0.22), H, TEAL)
box(s, Inches(0.95), Inches(0.75), Inches(11.4), Inches(0.7), "Conclusion", 34, True, WHITE)
rect(s, Inches(0.98), Inches(1.5), Inches(1.6), Pt(4), AMBER)
box(s, Inches(0.95), Inches(1.85), Inches(11.4), Inches(1.0),
    "EPS-TFT delivers population-specific, multi-horizon glucose forecasting for T1D and T2D "
    "from a single model conditioned on patient demographics.",
    22, False, RGBColor(0xD5, 0xE3, 0xEE), spacing=1.2)
takeaways = [("Accuracy", "Lowest RMSE, MAE, MAPE and gRMSE against six baselines on both datasets, at 30 and 60 min (p < 0.05)."),
             ("Simplicity", "One model, two horizons, two diabetes types; only CGM + timestamp as dynamic inputs."),
             ("Clinical value", "Quantile bounds flag severe events; PLGM loop cut time below 70 mg/dL from 5.3 % to 1.9 % in silico."),
             ("Contribution", "A reusable framework for population-level, uncertainty-aware glucose forecasting.")]
for i, (t, d) in enumerate(takeaways):
    x = Inches(0.95) + (i % 2) * Inches(5.85)
    y = Inches(3.1) + (i // 2) * Inches(1.5)
    rect(s, x, y, Inches(5.55), Inches(1.3), NAVY_L)
    rect(s, x, y, Pt(4), Inches(1.3), AMBER if i % 2 else TEAL)
    box(s, x + Inches(0.22), y + Inches(0.16), Inches(5.1), Inches(0.35), t, 16, True, WHITE)
    box(s, x + Inches(0.22), y + Inches(0.56), Inches(5.1), Inches(0.7), d, 12.5, False,
        RGBColor(0xA8, 0xBE, 0xD0), spacing=1.18)
box(s, Inches(0.95), Inches(6.35), Inches(11.4), Inches(0.5),
    "T. Zhu, L. Kuang, C. Piao, J. Zeng, K. Li, P. Georgiou, \"Population-Specific Glucose Prediction in Diabetes Care With "
    "Transformer-Based Deep Learning on the Edge,\" IEEE Trans. Biomed. Circuits Syst., vol. 18, no. 2, pp. 236–246, Apr. 2024.",
    11, False, RGBColor(0x8C, 0xA4, 0xB8), spacing=1.2)

out = "EPS-TFT_Population-Specific_Glucose_Prediction.pptx"
prs.save(out)
print("saved", out, "slides:", len(prs.slides._sldIdLst))
