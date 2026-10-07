"""Builds GlucoRAG_Architecture.pptx — software reference architecture for the EPS-TFT system (hardware out of scope)."""
from pptx import Presentation
from pptx.util import Inches as I, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
from pptx.oxml.ns import qn

NAVY = RGBColor(0x0B, 0x22, 0x3F); BLUE = RGBColor(0x1F, 0x5F, 0xA8); TEAL = RGBColor(0x00, 0x96, 0x7D)
ORANGE = RGBColor(0xE0, 0x72, 0x14); PURPLE = RGBColor(0x6A, 0x4C, 0x93); GREEN = RGBColor(0x2E, 0x7D, 0x4F)
RED = RGBColor(0xC0, 0x39, 0x2B); GREY = RGBColor(0x55, 0x5F, 0x6B); WHITE = RGBColor(0xFF, 0xFF, 0xFF)
BG = RGBColor(0xF5, 0xF7, 0xFA); PALE = RGBColor(0xE3, 0xEC, 0xF6); SLATE = RGBColor(0x3E, 0x4C, 0x5E)

prs = Presentation()
prs.slide_width, prs.slide_height = I(13.333), I(7.5)
SW = prs.slide_width
N = [0]


def rect(s, x, y, w, h, fill=WHITE, line=None, lw=1.0, r=None, dash=False):
    sp = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if r else MSO_SHAPE.RECTANGLE, I(x), I(y), I(w), I(h))
    if r:
        sp.adjustments[0] = r
    if fill is None:
        sp.fill.background()
    else:
        sp.fill.solid(); sp.fill.fore_color.rgb = fill
    if line is None:
        sp.line.fill.background()
    else:
        sp.line.color.rgb = line; sp.line.width = Pt(lw)
        if dash:
            ln = sp.line._get_or_add_ln(); ln.append(ln.makeelement(qn('a:prstDash'), {'val': 'dash'}))
    sp.shadow.inherit = False
    return sp


def text(s, t, x, y, w, h, sz=11, c=NAVY, b=False, it=False, al=PP_ALIGN.LEFT, anc=MSO_ANCHOR.TOP, ls=1.0, font="Calibri"):
    tb = s.shapes.add_textbox(I(x), I(y), I(w), I(h)); tf = tb.text_frame; tf.word_wrap = True
    tf.vertical_anchor = anc
    for m in ('margin_left', 'margin_right', 'margin_top', 'margin_bottom'):
        setattr(tf, m, Pt(2))
    for i, line in enumerate(t.split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = line; p.alignment = al; p.line_spacing = ls
        for r in p.runs:
            r.font.size = Pt(sz); r.font.color.rgb = c; r.font.bold = b; r.font.italic = it; r.font.name = font
    return tb


def box(s, x, y, w, h, t, fill, c=WHITE, sz=10, b=True, r=0.08, line=None):
    rect(s, x, y, w, h, fill=fill, r=r, line=line)
    text(s, t, x, y, w, h, sz=sz, c=c, b=b, al=PP_ALIGN.CENTER, anc=MSO_ANCHOR.MIDDLE)


def comp(s, x, y, w, h, title, sub, color, ts=10.5, ss=8.5):
    rect(s, x, y, w, h, fill=WHITE, line=color, lw=1.25, r=0.05)
    rect(s, x, y + 0.04, 0.07, h - 0.08, fill=color)
    text(s, title, x + 0.12, y + 0.03, w - 0.16, 0.28, sz=ts, b=True)
    if sub:
        text(s, sub, x + 0.12, y + 0.28, w - 0.16, h - 0.3, sz=ss, c=GREY)


def zone(s, x, y, w, h, label, color):
    rect(s, x, y, w, h, fill=None, line=color, lw=1.5, r=0.02, dash=True)
    lw_ = 0.08 * len(label) + 0.35
    box(s, x + 0.15, y - 0.15, lw_, 0.3, label, color, sz=9, r=0.3)


def arrow(s, x1, y1, x2, y2, c=NAVY, w=1.5, dash=False, both=False):
    cn = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, I(x1), I(y1), I(x2), I(y2))
    cn.line.color.rgb = c; cn.line.width = Pt(w)
    ln = cn.line._get_or_add_ln()
    if dash:
        ln.append(ln.makeelement(qn('a:prstDash'), {'val': 'dash'}))
    if both:
        ln.append(ln.makeelement(qn('a:headEnd'), {'type': 'triangle', 'w': 'med', 'len': 'med'}))
    ln.append(ln.makeelement(qn('a:tailEnd'), {'type': 'triangle', 'w': 'med', 'len': 'med'}))


def elbow(s, pts, c=NAVY, w=1.5, dash=False):
    """Orthogonal polyline through pts (inches); arrowhead on last segment."""
    for i in range(len(pts) - 1):
        (x1, y1), (x2, y2) = pts[i], pts[i + 1]
        if i == len(pts) - 2:
            arrow(s, x1, y1, x2, y2, c, w, dash)
        else:
            cn = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, I(x1), I(y1), I(x2), I(y2))
            cn.line.color.rgb = c; cn.line.width = Pt(w)
            if dash:
                ln = cn.line._get_or_add_ln(); ln.append(ln.makeelement(qn('a:prstDash'), {'val': 'dash'}))


def tag(s, t, x, y, w=1.6, c=GREY, sz=8, al=PP_ALIGN.CENTER):
    text(s, t, x, y, w, 0.25, sz=sz, c=c, it=True, al=al)


def slide(title, kicker):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    s.background.fill.solid(); s.background.fill.fore_color.rgb = BG
    rect(s, 0, 0, 13.333, 0.95, fill=NAVY); rect(s, 0, 0.95, 13.333, 0.04, fill=TEAL)
    text(s, kicker, 0.45, 0.07, 10, 0.28, sz=10, c=RGBColor(0x9F, 0xC7, 0xEF), b=True)
    text(s, title, 0.45, 0.32, 12, 0.55, sz=24, c=WHITE, b=True)
    N[0] += 1
    text(s, "GlucoRAG · EPS-TFT Reference Architecture", 0.45, 7.15, 8, 0.28, sz=8.5, c=GREY)
    text(s, str(N[0]), 12.4, 7.15, 0.5, 0.28, sz=8.5, c=GREY, al=PP_ALIGN.RIGHT)
    return s


def legend(s, items, x, y):
    for i, (lab, col) in enumerate(items):
        rect(s, x + i * 1.95, y + 0.05, 0.18, 0.14, fill=col)
        text(s, lab, x + i * 1.95 + 0.22, y, 1.7, 0.25, sz=8, c=SLATE)



# ============ 0. Cover ============
s = prs.slides.add_slide(prs.slide_layouts[6])
s.background.fill.solid(); s.background.fill.fore_color.rgb = NAVY
N[0] += 1
rect(s, 0, 4.55, 13.333, 0.05, fill=TEAL)
text(s, "SOFTWARE REFERENCE ARCHITECTURE  ·  v2.0", 0.6, 1.1, 10, 0.4, sz=13, c=RGBColor(0x7F, 0xD1, 0xC0), b=True)
text(s, "GlucoRAG / EPS-TFT", 0.6, 1.5, 12, 0.9, sz=42, c=WHITE, b=True)
text(s, "Population-specific, multi-horizon blood-glucose forecasting with a\nTemporal Fusion Transformer — data, model, inference and decision-support software",
     0.6, 2.45, 12, 1.0, sz=19, c=RGBColor(0xCF, 0xE1, 0xF6), ls=1.15)
toc = ["1  Horizontal end-to-end architecture (training pipeline → inference service → consumers)",
       "2  Vertical layered architecture (6-layer software stack with interfaces)",
       "3  TFT model architecture — tensor-level data flow",
       "4  Software module & component architecture",
       "5  Runtime sequence (one prediction cycle per CGM sample)",
       "6  Data & model lifecycle (MLOps) pipeline",
       "7  Non-functional requirements & design decisions"]
text(s, "\n".join(toc), 0.6, 4.8, 12, 2.0, sz=12.5, c=RGBColor(0xB5, 0xCB, 0xE4), ls=1.2)
text(s, "Scope: software only (hardware / wearable device excluded).   Basis: Zhu et al., IEEE TBioCAS 18(2), 2024 — DOI 10.1109/TBCAS.2023.3348844",
     0.6, 6.95, 12.5, 0.3, sz=10, c=RGBColor(0x8A, 0xA7, 0xC9))

# ============ 1. Horizontal ============
s = slide("1 · Horizontal End-to-End Architecture", "SYSTEM CONTEXT  ·  LEFT → RIGHT DATA FLOW  ·  SOFTWARE SCOPE")
zone(s, 0.35, 1.35, 4.05, 5.25, "OFFLINE TRAINING PIPELINE", BLUE)
zone(s, 4.65, 1.35, 5.35, 5.25, "INFERENCE SERVICE (local, offline-capable)", ORANGE)
zone(s, 10.25, 1.35, 2.75, 5.25, "CONSUMERS", GREEN)

comp(s, 0.55, 1.65, 1.75, 1.05, "Clinical datasets", "OhioT1DM · 12 T1D · 5-min\nShanghaiDM · 12 T1D +\n100 T2D · 15-min", BLUE)
comp(s, 2.5, 1.65, 1.75, 1.05, "Preprocessing", "causal linear imputation\nclip 40–400 mg/dL\nz-norm · time→[0,1]", BLUE)
comp(s, 0.55, 3.0, 1.75, 1.05, "Windowing & split", "120-min look-back (24)\n60-min horizon (12)\n80/20 · last 25% val", BLUE)
comp(s, 2.5, 3.0, 1.75, 1.05, "TFT training", "PyTorch · Adam\nquantile loss (7 q)\nHyperBand · ES p=20", BLUE)
comp(s, 0.55, 4.35, 1.75, 1.05, "Feature selection", "VSN weights → keep\nCGM + timestamp\n(93.9% importance)", BLUE)
comp(s, 2.5, 4.35, 1.75, 1.05, "Model registry", "versioned checkpoint\n+ norm params μ/σ\n+ quantile set", BLUE)
comp(s, 0.55, 5.65, 3.7, 0.75, "Static context precompute", "covariate encoder run once per patient → context vectors c_s, c_e, c_c, c_h", PURPLE)
arrow(s, 2.3, 2.17, 2.5, 2.17); elbow(s, [(3.37, 2.7), (3.37, 2.85), (1.42, 2.85), (1.42, 3.0)])
arrow(s, 2.3, 3.52, 2.5, 3.52); arrow(s, 3.37, 4.05, 3.37, 4.35)
elbow(s, [(2.5, 3.75), (2.4, 3.75), (2.4, 4.2), (1.42, 4.2), (1.42, 4.35)], c=GREY, dash=True)
tag(s, "retrain", 0.55, 4.07, 0.8, al=PP_ALIGN.LEFT)

comp(s, 4.85, 1.65, 1.6, 1.15, "CGM data source", "live stream or\nreplayed dataset\n(5 / 15 min)", TEAL)
comp(s, 6.75, 1.65, 3.05, 1.15, "Ingestion adapter", "parse · validate range · timestamp alignment\nper-patient routing", ORANGE)
comp(s, 6.75, 3.05, 1.45, 1.25, "Window buffer", "last 24 CGM\n+ timestamps\ngap check", ORANGE)
comp(s, 8.35, 3.05, 1.45, 1.25, "EPS-TFT engine", "load model once\nforward pass\n→ 12 × 7", ORANGE)
comp(s, 6.75, 4.55, 3.05, 0.95, "Risk engine", "q0.25/q0.5/q0.75 × 12 steps → hypo (<70) /\nhyper (>180) flags · tunable quantile", RED)
comp(s, 4.85, 3.05, 1.6, 2.45, "Local store", "model artifact\n\npatient profile +\nstatic context\n\nprediction &\nevent log", SLATE)
comp(s, 4.85, 5.7, 4.95, 0.7, "Notification & API layer", "alert events · prediction query endpoint · export for review", RED)
arrow(s, 6.45, 2.22, 6.75, 2.22, w=2)
arrow(s, 7.47, 2.8, 7.47, 3.05); arrow(s, 8.2, 3.67, 8.35, 3.67)
arrow(s, 6.45, 3.67, 6.75, 3.67, c=SLATE, both=True)
elbow(s, [(6.45, 4.3), (6.6, 4.3), (6.6, 2.95), (9.07, 2.95), (9.07, 3.05)], c=SLATE, w=1)
arrow(s, 9.07, 4.3, 9.07, 4.55); arrow(s, 8.27, 5.5, 8.27, 5.7)
elbow(s, [(4.25, 4.88), (4.55, 4.88), (4.55, 4.2), (4.85, 4.2)], c=BLUE, w=2.25)
elbow(s, [(4.25, 6.02), (4.6, 6.02), (4.6, 5.0), (4.85, 5.0)], c=PURPLE, w=1.5)

comp(s, 10.45, 1.65, 2.35, 1.1, "Patient app", "alert + 30/60-min\nforecast with\nuncertainty band", GREEN)
comp(s, 10.45, 3.05, 2.35, 1.1, "Clinician dashboard", "cohort view,\nrisk list, trends", GREEN)
comp(s, 10.45, 4.45, 2.35, 1.1, "Insulin decision logic", "e.g. predictive low-\nglucose suspend rule\nŷ(t+60) ≤ 70 mg/dL", GREEN)
comp(s, 10.45, 5.75, 2.35, 0.7, "Evaluation / audit", "logs → retraining data", GREEN, ss=8)
elbow(s, [(9.8, 6.05), (10.12, 6.05), (10.12, 2.2), (10.45, 2.2)], c=GREEN, w=1.75)
arrow(s, 10.12, 3.6, 10.45, 3.6, c=GREEN, w=1.75)
arrow(s, 10.12, 5.0, 10.45, 5.0, c=GREEN, w=1.75)
arrow(s, 10.12, 6.1, 10.45, 6.1, c=GREEN, w=1.5, dash=True)
legend(s, [("Training", BLUE), ("Inference", ORANGE), ("Context data", PURPLE), ("Safety / alert", RED), ("Consumer", GREEN)], 0.4, 6.75)

# ============ 2. Vertical ============
s = slide("2 · Vertical Layered Architecture", "SOFTWARE STACK  ·  TOP → BOTTOM")
layers = [
    ("L6  PRESENTATION", GREEN, ["Patient app\nalerts + forecast", "Clinician dashboard\ncohort risk view", "Prediction API\n(query / export)", "Alarm policy\nsettings (quantile)"], "UI / API contracts"),
    ("L5  DECISION SUPPORT", RED, ["Hypo detector\nŷ ≤ 70 mg/dL", "Hyper detector\nŷ ≥ 180 mg/dL", "Uncertainty gate\nq0.25 / q0.75 band", "Missing-data guard\ngap > 60 min → suspend"], "Risk flags, severity"),
    ("L4  INFERENCE (EPS-TFT)", ORANGE, ["Variable selection\nnetworks (enc/dec)", "LSTM encoder (24)\n+ decoder (12)", "Static enrichment\n+ multi-head attention", "GRN FFN + quantile\nhead (12 × 7)"], "ŷ ∈ ℝ^(12×7)"),
    ("L3  FEATURE & CONTEXT", PURPLE, ["Sliding window\n24 × {CGM, t}", "Known future\n12 × {t}", "Static context vectors\n(precomputed)", "z-normalization\nparams (μ, σ)"], "Tensors X_enc, X_dec, c"),
    ("L2  DATA INGESTION", TEAL, ["CGM source adapter\n(stream / file replay)", "Validation &\ntimestamp alignment", "Per-patient\nwindow buffer", "Causal linear\nimputation (<60 min)"], "mg/dL @ 5/15 min"),
    ("L1  PLATFORM & STORAGE", SLATE, ["Python · PyTorch\n(training & inference)", "Model registry\n(checkpoints, μ/σ)", "Patient profile &\nprediction log store", "Config, logging,\nversioning"], "Runtime services"),
]
y = 1.2; lh = 0.9; gp = 0.07
for name, col, cells, iface in layers:
    rect(s, 0.45, y, 2.2, lh, fill=col, r=0.06)
    text(s, name, 0.5, y, 2.1, lh, sz=10.5, c=WHITE, b=True, anc=MSO_ANCHOR.MIDDLE, al=PP_ALIGN.CENTER)
    cw = 2.02
    for j, c in enumerate(cells):
        cx = 2.75 + j * (cw + 0.08)
        rect(s, cx, y, cw, lh, fill=WHITE, line=col, lw=1.0, r=0.06)
        text(s, c, cx, y, cw, lh, sz=9.5, c=NAVY, anc=MSO_ANCHOR.MIDDLE, al=PP_ALIGN.CENTER)
    rect(s, 11.15, y, 1.8, lh, fill=PALE, r=0.06)
    text(s, iface, 11.15, y, 1.8, lh, sz=8.5, c=SLATE, it=True, anc=MSO_ANCHOR.MIDDLE, al=PP_ALIGN.CENTER)
    y += lh + gp
arrow(s, 13.12, 6.95, 13.12, 1.25, c=TEAL, w=2.5)
arrow(s, 0.25, 1.25, 0.25, 6.95, c=RED, w=2.5)
text(s, "data ↑", 12.9, 7.0, 0.5, 0.2, sz=7.5, c=TEAL, b=True)
text(s, "control ↓", 0.05, 7.0, 0.8, 0.2, sz=7.5, c=RED, b=True)

# ============ 3. TFT tensor-level ============
s = slide("3 · Temporal Fusion Transformer — Tensor-Level Architecture", "MODEL  ·  d_model = hidden size, B = batch, 24 past + 12 future steps")
zone(s, 0.35, 1.3, 2.7, 5.4, "INPUTS", SLATE)
comp(s, 0.5, 1.6, 2.4, 0.95, "Static s", "B × 4  (gender, age,\nBMI, diabetes type)", PURPLE)
comp(s, 0.5, 2.85, 2.4, 1.1, "Past observed + known", "B × 24 × 2\n{CGM mg/dL, time-of-day}\nt−115 … t (5-min)", TEAL)
comp(s, 0.5, 4.25, 2.4, 1.0, "Future known", "B × 12 × 1\n{time-of-day}  t+5 … t+60", TEAL)
comp(s, 0.5, 5.55, 2.4, 0.95, "Target (training)", "B × 12  y(t+5 … t+60)", GREY)
zone(s, 3.3, 1.3, 2.5, 5.4, "EMBED & SELECT", PURPLE)
box(s, 3.45, 1.6, 2.2, 0.95, "Static covariate encoder\n4 × GRN → c_s, c_e, c_c, c_h", PURPLE, sz=9)
box(s, 3.45, 2.85, 2.2, 1.1, "Encoder VSN\nper-var linear embed →\nGRN(·, c_s) → softmax\nB × 24 × d", TEAL, sz=9)
box(s, 3.45, 4.25, 2.2, 1.0, "Decoder VSN\nGRN(·, c_s) → softmax\nB × 12 × d", TEAL, sz=9)
text(s, "c_s → variable selection\nc_c, c_h → LSTM (h₀, c₀)\nc_e → static enrichment", 3.45, 5.5, 2.2, 0.9, sz=8.5, c=PURPLE, it=True)
arrow(s, 2.9, 2.07, 3.45, 2.07); arrow(s, 2.9, 3.4, 3.45, 3.4); arrow(s, 2.9, 4.75, 3.45, 4.75)
zone(s, 6.05, 1.3, 2.35, 5.4, "SEQUENCE", BLUE)
box(s, 6.2, 2.85, 2.05, 1.1, "LSTM encoder\n24 steps\nh₀,c₀ ← c_h,c_c", BLUE, sz=9)
box(s, 6.2, 4.25, 2.05, 1.0, "LSTM decoder\n12 steps\ninit ← encoder state", BLUE, sz=9)
box(s, 6.2, 5.55, 2.05, 0.95, "Gate + Add & Norm\nGLU skip over LSTM\nφ ∈ B × 36 × d", SLATE, sz=9)
arrow(s, 5.65, 3.4, 6.2, 3.4); arrow(s, 5.65, 4.75, 6.2, 4.75); arrow(s, 7.22, 3.95, 7.22, 4.25, c=BLUE)
arrow(s, 7.22, 5.25, 7.22, 5.55)
elbow(s, [(5.65, 2.07), (6.0, 2.07), (6.0, 2.6), (7.22, 2.6), (7.22, 2.85)], c=PURPLE, w=1.25)
zone(s, 8.65, 1.3, 2.35, 5.4, "TEMPORAL FUSION", ORANGE)
box(s, 8.8, 5.55, 2.05, 0.95, "Static enrichment\nGRN(φ, c_e)\nB × 36 × d", PURPLE, sz=9)
box(s, 8.8, 4.1, 2.05, 1.15, "Interpretable MHSA\nN heads, causal mask\nshared V, avg heads\nQ,K,V ∈ B×36×d", ORANGE, sz=9)
box(s, 8.8, 2.85, 2.05, 0.95, "Gate + Add & Norm\n→ GRN position-wise FFN", SLATE, sz=9)
box(s, 8.8, 1.6, 2.05, 0.95, "Gate + Add & Norm\n(skip whole block)", SLATE, sz=9)
arrow(s, 8.25, 6.02, 8.8, 6.02); arrow(s, 9.82, 5.55, 9.82, 5.25); arrow(s, 9.82, 4.1, 9.82, 3.8); arrow(s, 9.82, 2.85, 9.82, 2.55)
zone(s, 11.25, 1.3, 1.8, 5.4, "OUTPUT", GREEN)
box(s, 11.4, 1.6, 1.5, 1.3, "Dense head\n12 decoder\npositions\n→ B × 12 × 7", GREEN, sz=9)
box(s, 11.4, 3.2, 1.5, 1.35, "Quantiles\nq ∈ {.02,.10,.25,\n.50,.75,.90,.98}", GREEN, sz=9)
box(s, 11.4, 4.85, 1.5, 1.65, "Quantile loss\nL = 1/τ Σᵢ Σ_q\n(1−q)(ŷ−y)⁺\n+ q(y−ŷ)⁺", RED, sz=9)
arrow(s, 10.85, 2.07, 11.4, 2.07); arrow(s, 12.15, 2.9, 12.15, 3.2); arrow(s, 12.15, 4.55, 12.15, 4.85)
elbow(s, [(2.9, 6.02), (3.15, 6.02), (3.15, 6.62), (11.3, 6.62), (11.3, 6.2), (11.4, 6.2)], c=GREY, w=1.0, dash=True)
text(s, "GLU(z) = σ(W_g z + b_g) ⊙ (W_l z + b_l)     GRN(p,e) = LN(p + GLU(W a + b)),  a = ELU(W_p p + W_e e + b)",
     0.35, 6.8, 12.7, 0.3, sz=9, c=SLATE, font="Consolas")

# ============ 4. Software modules ============
s = slide("4 · Software Module & Component Architecture", "CODE ORGANISATION  ·  MODULES, RESPONSIBILITIES, DEPENDENCIES")
zone(s, 0.35, 1.3, 6.2, 2.55, "TRAINING-TIME MODULES", BLUE)
mods_t = [("data", "dataset loaders\nOhioT1DM · ShanghaiDM\nper-subject splits", BLUE),
          ("preprocess", "imputation · clipping\nnormalization · windows", BLUE),
          ("models/tft", "GLU · GRN · VSN · LSTM\nMHSA · quantile head", ORANGE),
          ("train", "Adam · quantile loss\nHyperBand · early stop", BLUE),
          ("evaluate", "RMSE · MAE · MAPE\ngRMSE · baselines", PURPLE),
          ("explain", "VSN importance\nattention weights", PURPLE)]
for k, (t, d, c) in enumerate(mods_t):
    x = 0.55 + (k % 3) * 2.0; y = 1.6 + (k // 3) * 1.1
    comp(s, x, y, 1.85, 0.95, t, d, c, ss=8.5)
zone(s, 6.8, 1.3, 6.2, 2.55, "RUN-TIME MODULES", ORANGE)
mods_r = [("ingest", "source adapters\nvalidation · alignment", TEAL),
          ("features", "window buffer · μ/σ\nstatic context lookup", PURPLE),
          ("inference", "model loader · forward\nreuses models/tft", ORANGE),
          ("risk", "thresholds · quantile\ngate · gap guard", RED),
          ("notify", "alert events\nde-duplication", RED),
          ("api", "predictions · history\nprofiles · export", GREEN)]
for k, (t, d, c) in enumerate(mods_r):
    x = 7.0 + (k % 3) * 2.0; y = 1.6 + (k // 3) * 1.1
    comp(s, x, y, 1.85, 0.95, t, d, c, ss=8.5)
zone(s, 0.35, 4.2, 12.65, 1.25, "SHARED CORE", SLATE)
shared = ["config (horizons, quantiles,\nthresholds, paths)", "registry (model + μ/σ\n+ version metadata)", "storage (profiles,\nprediction & event log)", "schemas (CGM record,\nPrediction, Alert)", "logging & metrics"]
for k, t in enumerate(shared):
    box(s, 0.55 + k * 2.48, 4.45, 2.33, 0.85, t, SLATE, sz=9)
arrow(s, 3.45, 3.85, 3.45, 4.2, c=SLATE, both=True); arrow(s, 9.9, 3.85, 9.9, 4.2, c=SLATE, both=True)
rect(s, 0.35, 5.7, 12.65, 1.3, fill=WHITE, line=NAVY, lw=0.75, r=0.04)
text(s, "Key data contracts", 0.5, 5.75, 4, 0.28, sz=10.5, b=True)
text(s, "CGMRecord {patient_id, timestamp, glucose_mg_dl}    PatientProfile {patient_id, age, gender, bmi, diabetes_type, context_vectors}\n"
        "Prediction {patient_id, t0, horizons[12], quantiles[7], values[12×7], model_version}    Alert {patient_id, type: hypo|hyper|data_gap, horizon_min, severity, t_raised}",
     0.5, 6.05, 12.4, 0.9, sz=9.5, c=SLATE, font="Consolas", ls=1.2)

# ============ 5. Runtime sequence ============
s = slide("5 · Runtime Sequence — One Prediction Cycle", "BEHAVIOUR  ·  TRIGGERED BY EACH NEW CGM SAMPLE (5 or 15 min)")
actors = [("CGM source", TEAL), ("Ingest", TEAL), ("Feature builder", PURPLE), ("EPS-TFT engine", ORANGE), ("Risk engine", RED), ("Notifier / API", GREEN), ("Store", SLATE)]
xs = []
for k, (a, c) in enumerate(actors):
    x = 0.7 + k * 1.83
    xs.append(x + 0.7)
    box(s, x, 1.2, 1.4, 0.45, a, c, sz=10)
    ln = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, I(x + 0.7), I(1.65), I(x + 0.7), I(6.75))
    ln.line.color.rgb = RGBColor(0xB0, 0xB8, 0xC4); ln.line.width = Pt(1)
    l2 = ln.line._get_or_add_ln(); l2.append(l2.makeelement(qn('a:prstDash'), {'val': 'dash'}))
steps = [(0, 1, "1  new reading {patient_id, t, mg/dL}", False),
         (1, 1, "2  validate range 40–400 · align timestamp", None),
         (1, 2, "3  append to patient window", False),
         (2, 6, "4  load profile + static context, μ/σ", False),
         (2, 2, "5  gap check · impute (<60 min) · z-norm", None),
         (2, 3, "6  infer(X_enc 24×2, X_dec 12×1, ctx)", False),
         (3, 3, "7  VSN → LSTM → MHSA → quantile head", None),
         (3, 4, "8  ŷ 12 × 7 quantiles", True),
         (4, 5, "9  alert if hypo / hyper risk", False),
         (5, 6, "10  persist prediction + alert", False),
         (5, 0, "11  push to patient app / dashboard", True)]
y = 1.9
for a, b, lab, ret in steps:
    if ret is None:
        rect(s, xs[a] - 0.08, y - 0.05, 0.16, 0.38, fill=ORANGE)
        text(s, lab, xs[a] + 0.15, y - 0.07, 5.0, 0.3, sz=9, c=NAVY)
    else:
        arrow(s, xs[a], y + 0.15, xs[b], y + 0.15, c=GREY if ret else NAVY, w=1.5, dash=ret)
        lo = min(xs[a], xs[b])
        text(s, lab, lo + 0.05, y - 0.12, abs(xs[b] - xs[a]) + 1.5, 0.25, sz=9, c=NAVY)
    y += 0.44
text(s, "If gap > 60 min at step 5: skip inference, raise data_gap alert.  Budget: whole cycle must finish well within one CGM sampling period (5 min).",
     0.45, 6.8, 12.5, 0.3, sz=9.5, c=SLATE, it=True)

# ============ 6. MLOps ============
s = slide("6 · Data & Model Lifecycle (MLOps) Pipeline", "DEVELOPMENT → VALIDATION → RELEASE → MONITORING")
stages = [("Ingest", "OhioT1DM / ShanghaiDM\nraw CGM, demographics", BLUE),
          ("Clean", "impute gaps (causal)\nclip 40–400 · align", BLUE),
          ("Engineer", "windows 24→12\nnormalize · split", PURPLE),
          ("Train", "TFT · quantile loss\nHyperBand · ES", ORANGE),
          ("Evaluate", "RMSE · MAE · MAPE\ngRMSE @30/60 min", ORANGE),
          ("Register", "checkpoint + μ/σ\n+ metadata", SLATE),
          ("Release", "load into inference\nservice (versioned)", GREEN),
          ("Monitor", "error drift · alert\nrates · data gaps", RED)]
w = 1.43; g = 0.14
for k, (t, d, c) in enumerate(stages):
    x = 0.4 + k * (w + g)
    box(s, x, 1.4, w, 0.5, t, c, sz=11)
    rect(s, x, 1.9, w, 1.05, fill=WHITE, line=c, lw=1.0)
    text(s, d, x, 1.9, w, 1.05, sz=8.5, c=NAVY, al=PP_ALIGN.CENTER, anc=MSO_ANCHOR.MIDDLE)
    if k < len(stages) - 1:
        arrow(s, x + w, 1.65, x + w + g, 1.65, w=2)
elbow(s, [(12.63, 2.95), (12.63, 3.25), (0.4 + 3 * (w + g) + w / 2, 3.25), (0.4 + 3 * (w + g) + w / 2, 2.95)], c=RED, dash=True)
tag(s, "retrain on new data / new cohort (domain shift)", 5.5, 3.27, 4.0, c=RED)
comp(s, 0.4, 3.75, 4.0, 2.9, "Validation gates", "• Held-out test: last 20% per subject\n• Paired t-test vs next-best (p < 0.05)\n• 5-fold cross-individual CV\n   (ShanghaiDM: 14.7 / 23.5 mg/dL RMSE)\n• Ablation: covariate encoder, LSTM decoder\n• Baselines: LR, SVR, XGBoost, LSTM,\n   N-BEATS, N-HiTS", ORANGE, ss=9.5)
comp(s, 4.65, 3.75, 4.0, 2.9, "Run-time safeguards", "• Missing CGM: impute gaps < 60 min;\n  longer → suspend prediction + alert\n• No-reading watchdog → data_gap alert\n• Quantile-based alarm sensitivity\n• Prediction & event log for review\n• Model version pinned per prediction", RED, ss=9.5)
comp(s, 8.9, 3.75, 4.0, 2.9, "Artifacts & versioning", "• Dataset snapshot + preprocessing config\n• Trained checkpoint + hyperparameters\n• Normalization μ/σ, quantile set\n• Precomputed static context per patient\n• Evaluation report per release\n• Model card (scope, cohorts, limits)", GREEN, ss=9.5)

# ============ 7. NFR & decisions ============
s = slide("7 · Non-Functional Requirements & Key Design Decisions", "QUALITY ATTRIBUTES  ·  ARCHITECTURE DECISION RECORD")
nfr = [("Latency", "prediction ready well within one 5-min CGM period", ORANGE),
       ("Accuracy", "lowest RMSE/MAE/MAPE/gRMSE vs 6 baselines", PURPLE),
       ("Generalization", "one model for T1D + T2D cohort; cross-individual CV", PURPLE),
       ("Privacy", "local inference; raw CGM not sent to a cloud", BLUE),
       ("Availability", "no internet dependency for predictions", BLUE),
       ("Interpretability", "VSN feature weights + attention weights", GREEN),
       ("Safety", "quantile bounds; gap guard; tunable alarms", RED)]
for k, (a, b, c) in enumerate(nfr):
    y = 1.3 + k * 0.76
    box(s, 0.4, y, 1.6, 0.64, a, c, sz=11)
    rect(s, 2.05, y, 3.6, 0.64, fill=WHITE, line=c, lw=1)
    text(s, b, 2.12, y, 3.5, 0.64, sz=9.5, c=NAVY, anc=MSO_ANCHOR.MIDDLE)
decisions = [("D1  Population model, not per-patient", "One TFT for the whole cohort; static demographics personalise via covariate encoder. Removing it raises RMSE 21.7 → 22.4 mg/dL."),
             ("D2  Direct multi-horizon output", "All 12 steps in one pass: no recursive error accumulation; one model serves 30 & 60 min."),
             ("D3  Minimal inputs: CGM + time", "VSN shows 93.9% importance; no manual meal/insulin logging, less compute."),
             ("D4  Precompute static context", "Covariate encoder runs once per patient; inference reuses stored context vectors."),
             ("D5  Quantile (probabilistic) output", "7 quantiles give an uncertainty band; alarm sensitivity is a config choice, not a retrain."),
             ("D6  Training and inference share one model package", "Same TFT code in both paths avoids train/serve skew; versioned artifacts make results reproducible.")]
for k, (h, d) in enumerate(decisions):
    y = 1.3 + k * 0.89
    rect(s, 5.95, y, 7.0, 0.8, fill=WHITE, line=NAVY, lw=0.75, r=0.05)
    rect(s, 5.95, y, 0.07, 0.8, fill=TEAL)
    text(s, h, 6.1, y + 0.02, 6.8, 0.28, sz=10.5, b=True)
    text(s, d, 6.1, y + 0.3, 6.8, 0.5, sz=9, c=GREY)

prs.save("GlucoRAG_Architecture.pptx")
print("saved", N[0], "slides")
