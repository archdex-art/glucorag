# Dashboard redesign: AGP report language

- **Status:** approved by the user on 2026-10-05.
- **Direction:** "AGP report language".
- **Primary user:** ward clinicians.
- **Mode:** impeccable *Operate*, a redesign that replaces the visual world.
- **Product truth:** `web/PRODUCT.md`.

This spec is a development contract. Its wording, and above all the direction contract below, must never be copied into shipped source, comments, DOM, data attributes or bundles.

## Direction contract
- **THESIS.** The ward reads as a stack of Ambulatory Glucose Profile strips. Each patient's next hour is drawn as a percentile band across the five consensus glucose zones, so "who is heading out of range" shows up as position and colour before any text is read. This rejects the category default of KPI tiles above a status table.
- **OWN-WORLD.**
  - **Ground and ink:** clinical white paper on a cool blue-grey ground; navy ink.
  - **Forecast colours:** the AGP percentile blues (light outer ribbon, mid ribbon, deep inner band, ink median line).
  - **Status colours:** the five consensus zone colours (very low dark red, low red, target green, high yellow, very high orange) are the only status palette.
  - **Type and icons:** one hyperlegible sans with tabular numerals; drawn line icons.
  - **Structure:** flat print-like sheets divided by hairline rules, not floating cards.
- **STORY.** A clinician opens the ward and immediately sees the one patient who needs attention, their value now, the direction they are heading and the band they will land in. One click opens the patient's AGP-style chart and time-in-ranges bar.
- **FIRST VIEWPORT.**
  - **Desktop:** a quiet tinted left rail (wordmark, four nav items, the research notice at the bottom).
  - **Header:** the page title, the replay/data-time status and the refresh state.
  - **Toolbar:** search, a type filter and the zone legend.
  - **Body:** the "Needs attention" section at the top, its rows at full strip width. "Not reporting" comes below. Empty sections collapse to a single line.
- **FORM.** A standard product shell: side rail, page header, list rows, a disclosure for details. The world contributes only type, palette, density and the strip.
- **SIGNATURE.** The **range strip**: a log-scaled 40–400 mg/dL track with five zone segments, the next-hour forecast envelope as a blue band, the current value as an ink dot, and a thin line from that dot to the 60-minute median tick.

## Tokens (light; dark follows `prefers-color-scheme`)

### Neutrals and shell
| Token | Light | Dark | Role |
|---|---|---|---|
| `--ground` | #EEF2F6 | #0B1625 | Page ground |
| `--paper` | #FFFFFF | #102136 | Content sheet |
| `--wash` | #F5F8FB | #15293F | Row hover, table head |
| `--rail` | #E1EAF4 | #081221 | Shell rail |
| `--line` | #DCE3EB | #22364D | Hairlines |
| `--line-strong` | #B6C4D3 | #34506E | Strong rules, input borders |
| `--ink` | #0E2742 | #E6EDF5 | Primary text, median |
| `--ink-2` | #4A6079 | #A7B8CB | Secondary text (≥ 4.5:1 on paper) |
| `--action` | #1D5FA8 | #7EB0EC | Links, primary button, focus, selection |

### Percentile blues (AGP ribbons)
| Token | Light | Dark | Quantiles |
|---|---|---|---|
| `--p-outer` | #D6E4F4 | #1C324C | q0.02–0.98 |
| `--p-mid` | #AFCAEA | #284A72 | q0.10–0.90 |
| `--p-inner` | #5B8FCB | #4F86C8 | q0.25–0.75 / alert band |
| `--p-median` | #0E2742 | #E6EDF5 | q0.50 |

### Consensus zones
Every zone token comes in three forms:
- `-fill`: strip segments and bars.
- `-text`: text on paper, ≥ 4.5:1.
- `-tint`: chart background bands.

| Zone | fill (L / D) | text (L / D) | tint (L / D) |
|---|---|---|---|
| very low < 54 | #8E1B1B / #E0605C | #7A1616 / #FF9A94 | #F7E3E3 / #3A1A1F |
| low 54–69 | #D7372A / #F07A6E | #B3261E / #FFA49B | #FCEAE7 / #3D2022 |
| target 70–180 | #3C9A55 / #5CC27A | #1E6B35 / #8FDCA6 | #E9F5EC / #15322A |
| high 181–250 | #F0C232 / #E8C24A | #7A5900 / #F2D27A | #FDF5D7 / #362E14 |
| very high > 250 | #E8772E / #F09A5A | #9E430E / #FFB988 | #FCEBDE / #3A2516 |

Zone classification for a value `v` (mg/dL):
- very low: `v < 54`
- low: `54 ≤ v < 70`
- target: `70 ≤ v ≤ 180`
- high: `180 < v ≤ 250`
- very high: `v > 250`

Alert sentences come from backend flags, never from the zone. An exact 70 colours as target while the backend may still alert "hypo" (rule: ≤ 70). That is intended.

### Shape, depth, motion
- **Radius:** 4px on chips, strips, inputs and buttons; 8px on the page sheet; 999px only on the dot and the toggle.
- **Depth:** the page sheet has `0 1px 2px rgb(14 39 66 / 6%), 0 6px 20px rgb(14 39 66 / 5%)`. Nothing else casts a shadow.
- **Motion:** state transitions take 150–200 ms, ease-out. The strip band and dot animate position on data change. There is no page-load choreography, and `prefers-reduced-motion` turns transitions off.

### Type
- **Face:** `@fontsource-variable/atkinson-hyperlegible-next` (latin subsets, self-hosted by Vite), with a system sans fallback. Reason: it was designed for character differentiation (0/O, 1/l/I), which suits glance-reading of clinical values.
- **Scale (rem; base 16px; ratio about 1.2):**

  | Size | Use |
  |---|---|
  | 0.75 | Captions, legend |
  | 0.8125 | Meta |
  | 0.875 | Table and row text |
  | 1 | Body |
  | 1.25 | h2 |
  | 1.5 | h1 |
  | 2 | Readout values |
  | 2.75 | Patient's current value |

- **Weights:** 400 body, 600 headings, labels and IDs, 700 values.
- **Numbers:** every number uses `font-variant-numeric: tabular-nums` (class `.num`).
- **Case:** sentence case everywhere. No all-caps labels, eyebrows or kickers, no `·`-joined meta strings, no "Label — fragment" constructions, no "→" on links.

### Icons
- `lucide-react`, stroke 1.75, 16px inline and 18px in nav. Colour is `currentColor`.
- No Unicode glyphs or emoji as icons (▲▼⚠○✓↕ etc. are all replaced).
- Trend arrows:

  | Rate (mg/dL per min) | Icon | Label |
  |---|---|---|
  | `r > 2` | ArrowUp | "rising quickly" |
  | `1 < r ≤ 2` | ArrowUpRight | "rising" |
  | `−1 ≤ r ≤ 1` | ArrowRight | "steady" |
  | `−2 ≤ r < −1` | ArrowDownRight | "falling" |
  | `r < −2` | ArrowDown | "falling quickly" |

  These are the FreeStyle Libre conventions, matching the 15-min sensor.

### Browser surfaces
- `::selection` uses the `--p-mid` background.
- `caret-color` is `--action`.
- `scrollbar-color` is `--line-strong` on transparent.
- `:focus-visible` gets a 2px `--action` outline at 2px offset.
- `text-underline-offset` is 0.18em; links are underlined only on hover/focus, except inside body prose.

## Copy dictionary (user language, not system language)
| System value | UI text |
|---|---|
| Cohort page | **Ward** |
| status `at_risk` | Needs attention |
| status `data_gap` | Not reporting |
| status `warming_up` | Warming up (forecast starts after 2 h of readings) |
| status `ok` | Stable |
| status `no_data` | No readings yet |
| severity high / medium / low | **Urgent / Soon / Watch** (never "low": it collides with low glucose) |
| flag hyper, horizon h | "Hyper predicted in h min" |
| flag hypo, horizon h | "Hypo predicted in h min" |
| data gap | "No reading for 2 h 10 min" / "No reading for 49 days" |
| logout | Sign out |
| research notice | "Research use only. Not for clinical decisions." |

Errors name the problem and the fix: "The service rejected this API key. Check the key and sign in again."

## Components (new or rebuilt)
- **`RangeStrip`** (signature).
  - Props: `current?`, `band?: {low[], median[], high[]}`, `size: 'row' | 'compact'`.
  - Scale: `x = (ln v − ln 40) / (ln 400 − ln 40)`, clamped to [0, 1].
  - Drawing:
    - five zone tint segments separated by 1px paper gaps;
    - the envelope band from `min(low)` to `max(high)` at 10px height in `--p-inner` (opacity 0.75);
    - the 60-min median as a 2px ink tick;
    - the current value as an 8px ink dot, joined to the median tick by a 1.5px ink line.
  - No forecast: a muted track and a hollow dot at the last value, if there is one.
  - Rendered as inline SVG with `role="img"` and a full sentence `aria-label` (now, zone, band range, 60-min median).
  - The strip has no text labels; one shared `ZoneLegend` explains it: zone swatches, threshold numbers and "log scale".
- **`ZoneLegend`**: a compact horizontal legend (zone name plus range) shown once per page.
- **`TimeInRanges`**: the AGP stacked bar (5 segments, horizontal) with a % label per segment (hidden below 3% and shown in the legend list instead) and the consensus targets as caption text ("Target: over 70% in range, under 4% low"). Computes from readings in the visible window.
- **`Readout`**: Now, In 30 min, In 60 min. Each shows the value (700, 2rem) coloured by zone text, a unit, and the band "176–219" (`--ink-2`). Now also shows the trend icon and rate.
- **`PriorityChip`**: Urgent / Soon / Watch as a 4px-radius chip. Urgent is filled with the risk type's zone colour; Soon is outlined; Watch is plain text.
- **`StatusIcon`**: a lucide icon per status.

  | Status | Icon |
  |---|---|
  | at risk | TriangleAlert (zone-coloured by flag type) |
  | not reporting | WifiOff (ink-2) |
  | warming up | Hourglass |
  | stable | CircleCheck (target text) |
  | no data | CircleDashed |

- **Shell `Layout`.**
  - **Rail (≥ 900px, 232px wide, `--rail`):**
    - wordmark "GlucoRAG" (600) and "Glucose forecast monitor" (0.75rem);
    - nav: Ward (Activity), Alerts (Bell, with a count badge of active alerts), Model (FlaskConical), System (Server);
    - footer: research notice (Info icon) and a "Sign out" button.
    - The active nav item is a paper pill with ink text and 600 weight. No coloured left border.
  - **Below 900px:** a top bar (wordmark plus the replay chip), a one-line research notice under it, and a fixed bottom tab bar with the 4 items (icon plus label, 56px tall, safe-area inset).
  - **Page header (every page):**
    - h1 on the left;
    - on the right: the replay status. With `clock=data` it is a chip "Replay data" plus "Data time 27 Jan 2022, 11:33". With `clock=wall` it is just "Live";
    - after that, the refresh state "Updated 11:33:05" and an icon-only pause/resume toggle (`aria-pressed`, labelled).
  - **Dates:** "27 Jan 2022, 11:33". Today's times show only "11:33".

## Pages
- **Ward (`/`).**
  - **Toolbar:** search patient ID, diabetes type select, `ZoneLegend`.
  - **Sections in order:** Needs attention, Not reporting, Warming up, Stable, No readings yet.
    - Each heading is an h2 with a count.
    - A section with zero rows renders as one muted line ("Stable: none").
    - Within Needs attention, rows sort by backend rank, then earliest horizon.
    - Other sections sort by minutes since the last reading.
  - **Rows:** each row is a `<li>` holding one `<a>` (the whole row is the link). It is a CSS grid with these columns:
    - Patient: ID (600) and type (ink-2);
    - Now: value (700, 1.25rem), unit, trend icon, "4 min ago";
    - Next hour: `RangeStrip`, flexible width;
    - Assessment: StatusIcon plus sentence plus PriorityChip;
    - Alerts: small icons for active alert types, each with a label.

    Not-reporting rows show the last value in ink-2 and "No reading for …".
  - **Mobile:** each row stacks: line 1 is ID, type, value, trend and chip; line 2 is a full-width strip; line 3 is the sentence.
  - **Empty cohort:** a teaching empty state: "No patients yet. Register a patient with POST /patients, then stream readings." The text includes the replay command.
- **Patient (`/patients/:id`).**
  - Breadcrumb "Ward" / "Patient 2012".
  - Header: ID, type, status, PriorityChip, active alerts.
  - `Readout`.
  - Risk sentence from flags: "Hyper predicted in 15 min: the q0.75 forecast reaches 246 mg/dL, 66 above 180." A stale patient gets a warning line instead.
  - **Chart (restyled ForecastChart, AGP ribbons):**
    - readings as an ink line;
    - q0.02–0.98 in `--p-outer`, q0.10–0.90 in `--p-mid`, q0.25–0.75 in `--p-inner`, the median dashed ink;
    - zone tint bands across the background;
    - 70/180 rules labelled at the right edge;
    - a "now" rule at t0;
    - window segmented control: 6 h, 24 h, 3 d.
  - `TimeInRanges` for the window.
  - `<details>` "All forecast quantiles": the existing table restyled, with crossing cells marked by zone text colour plus a drawn icon.
  - Alerts list (compact, newest first).
  - 404 handling:
    - no forecast yet: "Forecast starts after 2 hours of readings";
    - unknown patient: "Patient 2012 is not registered."
- **Alerts (`/alerts`).**
  - Toolbar: filters for type, patient and priority, plus Export CSV (secondary button, Download icon).
  - The list is grouped by day (h2 "27 Jan 2022").
  - Each row shows: time, patient link, StatusIcon plus type label ("Hyper predicted" / "Hypo predicted" / "Data gap"), detail sentence, PriorityChip.
  - Forecast t0 and the model version go into a secondary line on hover/expand, not into columns.
- **Model (`/model`).** The release verdict comes first.
  - **Verdict:** "shanghai-v1 is not promoted", followed by the reason. When evaluation significance exists and is false at any horizon, the reason reads: "Not significantly better than LSTM at 30 min (p = 0.87) and 60 min (p = 0.36)."
  - **"Accuracy against the paper" table:**
    - rows: 30-min RMSE, 60-min RMSE, cross-validation 30 and 60;
    - columns: this model, paper (Zhu et al. 2024, Table II and CV), difference.
    - Paper constants live in `lib/paper.ts` with a citation and are shown only when `dataset === 'shanghai'`. Values: RMSE 30 = 12.7 ± 3.8, RMSE 60 = 21.7 ± 6.9, CV 30 = 14.7, CV 60 = 23.5.
  - **"In-silico trial":**
    - two `TimeInRanges`-style bars (open loop, PLGM) built from `tbr_pct` / `tir_pct` / `tar_pct`. Only 3 segments are available, so use low (fill low), target and high (fill high), and say so in the legend;
    - then CVGA A+B and D+E against the paper, with an explicit "lower is better / higher is better" and a better/worse word.
  - `<details>` sections: Test metrics (MAE/MAPE/gRMSE), Significance details, Cross-validation detail, CVGA zones, Hyperparameters, Integrity (hashes).
- **System (`/system`).** One sheet with a two-column grid of small definition-list groups:
  - Service: health, model, uptime, clock;
  - Throughput;
  - Latency (p50/p95/max/mean);
  - Alerts by type;
  - Data gaps by source;
  - Rejected readings;
  - Storage;
  - Thresholds.

  No tiles.
- **Sign in.**
  - A centred narrow sheet on the ground: wordmark, one sentence ("Monitor glucose forecasts for your ward."), API key field (password type, show/hide toggle), "Sign in" primary button, error line, and the research notice below.
- **Not found.** One line and a link back to Ward.

## Data contract additions (backend already shipped)
`PatientRisk` gains:
- `last_glucose_mg_dl: number | null`
- `trend_mg_dl_per_min: number | null`
- `forecast: ForecastBand | null`, where `ForecastBand = { t0, horizons: number[], low_quantile, high_quantile, low: number[], median: number[], high: number[] }`. It is present only while fresh (status at_risk/ok) and uses the patient's own alert quantiles.

## Engineering rules
- Keep these unchanged: API client, auth, hooks, polling, error classes, time handling (`lib/time.ts`, naive-local), routing paths, CSP compliance (no inline scripts or styles injected by JS libraries that need `unsafe-eval`), session-only key, CSV export without the key in the URL.
- Styles: one tokens layer (`src/styles/tokens.css`) plus component CSS, or keep a single `styles.css` organised by layer. No CSS-in-JS. Avoid specificity clashes: class-based, at most one level of nesting.
- New pure logic goes in `src/lib/` with Vitest tests at the boundaries. Cover:
  - zone classification at exactly 54/70/180/250;
  - log-scale mapping monotonic and clamped below 40 and above 400;
  - trend buckets at exactly ±1 and ±2;
  - time-in-ranges percentages summing to 100 (rounding), the empty window, and points outside the window excluded;
  - ward sectioning (order, empty sections, within-section sort);
  - the envelope (min of low, max of high).
- Delete tests that pin old copy or old structure; keep behavioural ones.

## Acceptance
- `npm ci && npm run lint && npm run typecheck && npm test && npm run build` all green. The build output has no inline `<script>`.
- Real smoke against the backend serving `/ui/` with replayed ShanghaiDM data, including at least one at-risk patient and one data-gap patient.
- Screenshots of every page at 1440 and 390 widths, light and dark. The browser console has 0 errors and 0 CSP violations.
- WCAG AA contrast on text. Keyboard path through ward rows to the patient and back. Visible focus everywhere.
