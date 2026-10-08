# GlucoRAG: design system

This describes what is built, for both the personal app and the clinician pages. Source of truth for
values: `src/styles/tokens.css` (tokens and browser surfaces) and `src/styles/app.css` (components,
class-based, at most one level of nesting).

## Colour tokens

Light is the default; dark applies under `prefers-color-scheme: dark`.

### Shell and text

| Token | Light | Dark | Use |
|---|---|---|---|
| `--ground` | #EEF2F6 | #0B1625 | Page background |
| `--paper` | #FFFFFF | #102136 | The page sheet, inputs, chips |
| `--wash` | #F5F8FB | #15293F | Row hover, table and column heads, skeletons |
| `--rail` | #E1EAF4 | #081221 | Side rail, mobile top bar and notice |
| `--line` | #DCE3EB | #22364D | Hairlines between sections and rows |
| `--line-strong` | #B6C4D3 | #34506E | Input and button borders, axis lines |
| `--ink` | #0E2742 | #E6EDF5 | Text, readings line, strip marks |
| `--ink-2` | #4A6079 | #A7B8CB | Secondary text, old values, axis labels |
| `--action` | #1D5FA8 | #7EB0EC | Links, primary button, focus ring, caret |
| `--on-action` | #FFFFFF | #0B1625 | Text on a filled `--action` surface |

### Forecast ribbons

| Token | Light | Dark | Quantiles |
|---|---|---|---|
| `--p-outer` | #D6E4F4 | #1C324C | q0.02–q0.98 |
| `--p-mid` | #AFCAEA | #284A72 | q0.10–q0.90 |
| `--p-inner` | #5B8FCB | #4F86C8 | q0.25–q0.75; the strip's next-hour band |
| `--p-median` | #0E2742 | #E6EDF5 | Median line, strip dot and tick |

### Glucose zones

Each zone has `--zone-<name>-fill` (strip baselines, bars, urgent chips), `-text` (text on paper,
at least 4.5:1) and `-tint` (chart and strip backgrounds). The zones are the only status palette.

| Zone (mg/dL) | Fill L / D | Text L / D | Tint L / D |
|---|---|---|---|
| Very low, under 54 | #8E1B1B / #E0605C | #7A1616 / #FF9A94 | #F7E3E3 / #3A1A1F |
| Low, 54–69 | #D7372A / #F07A6E | #B3261E / #FFA49B | #FCEAE7 / #3D2022 |
| Target, 70–180 | #3C9A55 / #5CC27A | #1E6B35 / #8FDCA6 | #E9F5EC / #15322A |
| High, 181–250 | #F0C232 / #E8C24A | #7A5900 / #F2D27A | #FDF5D7 / #362E14 |
| Very high, over 250 | #E8772E / #F09A5A | #9E430E / #FFB988 | #FCEBDE / #3A2516 |

`--on-low-fill` (light #FFFFFF, dark #0B1625) and `--on-high-fill` (#0E2742 / #0B1625) set the text
on filled Urgent chips. In CSS, a `.zone-<key>` class exposes `--z-fill`, `--z-text` and `--z-tint`;
`.zt-<key>` colours text; `.tone-hypo` uses the low text colour, `.tone-hyper` the high text colour.

Classification (`src/lib/zones.ts`): very low `v < 54`, low `54 ≤ v < 70`, target `70 ≤ v ≤ 180`,
high `180 < v ≤ 250`, very high `v > 250`. Zone colour is display only. Alert wording always comes
from the backend's flags, so an exact 70 is coloured as target while a hypo alert may still fire.
In mmol/L the thresholds display as 3.0 / 3.9 / 10.0 / 13.9 (`src/lib/units.ts`); classification
always runs on mg/dL.

## Shape, depth, motion

- Radius 4px on chips, inputs, buttons and strips; 8px on the page sheet; 999px only on the strip
  dot and the pause toggle.
- One shadow, on the page sheet (`--shadow-sheet`). Sections inside the sheet are divided by
  `--line` hairlines; nothing else floats.
- Transitions are 180 ms with an exponential ease-out (`--ease-out`), used for hover, toggles,
  disclosures and the strip's band, tick and dot moving when data changes. No load choreography.
  `prefers-reduced-motion: reduce` sets every transition and animation to zero.

## Type

- Face: Atkinson Hyperlegible Next (variable, latin and latin-ext, self-hosted), falling back to
  the system sans. Its 0/O and 1/l/I shapes are distinct, which suits glance reading of values.
- Scale (rem): 0.75 captions and legends; 0.8125 meta; 0.875 rows and tables; 1 body; 1.25 h2;
  1.5 h1; 2 readout values; 2.75 the patient's current value (2.25 below 480px).
- Weights: 400 body; 600 headings, labels, IDs; 700 values.
- Every number is tabular (`font-variant-numeric: tabular-nums` on the body; `.num` marks data).
- Sentence case throughout. Dates read "27 Jan 2022, 11:33"; times on the service's current day
  read "11:33".

## Browser surfaces

`::selection` uses `--p-mid`; `caret-color` is `--action`; `scrollbar-color` is `--line-strong`
on transparent; `:focus-visible` draws a 2px `--action` outline at 2px offset (inset on ward rows
and tab bar items); links underline at 0.18em only on hover and focus. `theme-color` follows the
rail colour in each scheme.

## Icons

`lucide-react` at stroke 1.75: 16px inline, 18px in navigation, always `currentColor` and
`aria-hidden` next to visible text. Trend arrows (`src/lib/trend.ts`, mg/dL per minute):

| Rate | Icon | Label |
|---|---|---|
| > 2 | ArrowUp | rising quickly |
| 1 to 2 | ArrowUpRight | rising |
| −1 to 1 | ArrowRight | steady |
| −2 to −1 | ArrowDownRight | falling |
| < −2 | ArrowDown | falling quickly |

Status icons: TriangleAlert (needs attention, zone text of the flag), WifiOff (not reporting),
Hourglass (warming up), CircleCheck (stable, target text), CircleDashed (no readings yet). Alert
types: TrendingUp (hyper), TrendingDown (hypo), WifiOff (data gap).

## The range strip

`RangeStrip` (`src/components/RangeStrip.tsx`) is the ward's signature: one inline SVG per row.

- Scale: `x = (ln v − ln 40) / (ln 400 − ln 40)`, clamped to [0, 1]. Geometry uses SVG percentages,
  so the strip fills any width without measuring.
- Track: five zone segments in `-tint`, each with a 2px `-fill` baseline so the zone reads on
  white, separated by 1px `--paper` gaps.
- Band: `min(low)` to `max(high)` of the next hour, in the patient's alert quantiles, 10px tall,
  `--p-inner` at 0.75 opacity, 2px corners.
- 60-min median: a 2px ink tick. Current value: an 8px ink dot with a paper outline, joined to the
  tick by a 1.5px ink line.
- Without a current forecast the track fades (tints 0.6, baselines 0.35) and the last value is a
  hollow dot.
- Sizes: `row` (28px tall, ward) and `compact` (20px).
- `role="img"` with a sentence label, e.g. "Now 248 mg/dL, high. Next hour forecast band 176 to
  246 mg/dL. 60-minute median 198 mg/dL." The strip itself carries no text; `ZoneLegend` explains
  it once per page (zones with thresholds, the dot, band and tick, and "Log scale").

## Components

- **Shell.** From 900px: a 232px `--rail` with the wordmark, role-specific nav (people: Today,
  History, Add data, Settings; clinicians: Ward, Alerts with an ink count badge of active alerts,
  Model and System under a "Clinical" heading, then Settings), the research notice, the account
  email and Sign out; the active item is
  a paper fill with ink 600 text. Below 900px: a top bar with the wordmark, a one-line research
  notice, and a fixed 56px bottom tab bar with safe-area padding.
- **Auth frame.** Welcome, sign-up and sign-in sit on `--ground`: the wordmark (and a switch link)
  in a top row, one centred sheet (`.auth-sheet`, wider for welcome), and the research notice below.
- **Page header.** h1 on the left; on the right the clock status ("Replay data" chip and "Data time
  …", or "Live"), "Updated hh:mm:ss" and an icon-only pause toggle (`aria-pressed`). Pausing is
  shared by every page until resumed.
- **Ward row.** One `<li>` holding one link, a grid of Patient, Now, Next hour (strip), Assessment
  and Alerts. Not-reporting rows show the last value in `--ink-2`. On phones it stacks: ID, type,
  value, trend and chip; then the strip; then the sentence.
- **Readout.** Now (2.75rem), In 30 min, In 60 min (2rem), coloured by zone text, with the band
  range under each forecast value and the trend under Now. Old values take `--ink-2`.
- **Forecast chart.** Zone tint bands behind, q0.02–0.98, q0.10–0.90 and q0.25–0.75 ribbons,
  a dashed median, readings in ink, 70 and 180 rules labelled at the right, and a dotted t0 rule
  labelled "Now" (or "Last forecast" when the patient is not reporting). Fewer ticks below 600px.
- **TimeInRanges.** A stacked bar of zone fills, percentages under segments of 3% and more, a legend
  listing every share, and the consensus targets as caption.
- **PriorityChip.** Urgent fills with the flag's zone colour (low fill for hypo, high fill for
  hyper, ink when neutral); Soon is outlined in the zone text colour; Watch is plain text.
- **States.** Skeleton blocks in the shape of the content (pulse off under reduced motion), errors
  that name the problem and the fix with a "Try again" button, and empty states that say what to
  do next.

### Personal app

- **Status sentence.** Today's h1-sized answer with a status icon, in plain words: "In range for
  the next hour.", "Heading below 70 in about 25 min (could reach 68)." (the limit in the person's
  unit, the earliest flag's first crossing, "soon" at horizon 0, then in brackets its lowest or
  highest forecast, omitted without a value), or, when the reading is already past the threshold
  (the same inclusive rule as alerts) or out of range with no flag, "198 mg/dL, steady. Likely
  about 185 in 30 min.", then "Collecting readings.", "No current forecast.", "No readings yet.". A
  high-severity flag fills it with the zone fill (`.is-urgent.tone-hypo|hyper`); otherwise it stays
  ink. Below it, `.status-detail` lists the other likely lows/highs ("High likely in about 45 min
  (could reach 205 mg/dL).") and, under the readout, one caption on how close the 30-minute forecast
  usually was. People never read "band", "edge" or quantile names; the forecast table speaks in
  chances ("1 in 4 chance below"). Wording never contradicts the coloured value
  (`src/lib/personStatus.ts`).
- **Today readout.** The readout in a stacked layout: Now across the top, then In 30 min and In 60
  min side by side, with the reading's age under Now.
- **Today chart.** The forecast chart over the last 3 h plus the next hour, so the forecast takes a
  quarter of the width. With old data it is labelled "Forecast made at …" instead of "Now".
- **Add-data choices.** One recommended path first: "Live from your phone" in a card with a 2px
  `--action` border and a Recommended chip, with Get the phone app (`/help/phone`) and Connect a
  phone, which opens the pairing panel in place. Below it, "Or start another way": Import a file,
  Type a reading and Try sample data as secondary buttons, each with one line of help (one column
  on phones). Used on setup and on an empty Today; Add data repeats the phone card and, for an
  empty account, sample data.
- **Install help.** `/help/phone` and `/help/watch`, open to everyone in the set-up frame with a
  Back link: numbered plain steps, the app file from `GET /downloads` or the releases page.
- **Connected devices.** A Settings section (`#devices`, both roles) listing each phone as a row
  between hairlines: the device name in 600, "Connected 6 Oct 2026. Last used 4 min ago." in
  `--ink-2`, and a quiet danger Disconnect button that opens the confirm dialog.
- **Drop zone.** A 1.5px dashed `--line-strong` box on `--wash` with a "Choose a file" button;
  dragging turns the border `--action` and the fill `--p-outer`; a chosen file makes the border
  solid and shows its name. Format help is a disclosure below the time zone, unit and date-order
  selects.
- **Import result.** A count list (rows read, added, already present, older than the import window,
  unusable rows, refused), each with the reason, and, when
  the file's dates fit both day-first and month-first, an `.import-note` on `--wash` saying which
  order was used and how to change it.
- **Radio cards.** Alert sensitivity as three bordered cards in a row (stacked on phones). The
  checked card gets an `--action` border, inset ring and `--wash` fill; each card shows what the
  setting does and a preview of the latest forecast's range with that setting.
- **Confirm dialog.** A modal `<dialog>` (`showModal`, backdrop) that names the exact consequence
  ("Delete 193 readings, all forecasts and alerts. Your account and settings stay."). The confirm
  button repeats the action and is ink-filled, since zone colours are reserved for glucose. Deleting
  the account requires the password and shows "This password is not correct." in the dialog.

## Do

- Let position and zone colour carry status; keep words for what the backend decided.
- Keep one sheet per page and divide it with hairlines.
- Use the copy of the ward: Needs attention, Not reporting, Warming up, Stable, No readings yet;
  Urgent, Soon, Watch; "Hyper predicted in 15 min"; "No reading for 2 h 10 min". For people say
  "low" and "high", never "hypo" and "hyper".
- Show every glucose value in the user's unit: mmol/L with one decimal, mg/dL with none.
- Give every icon a visible word beside it, and every graphic a sentence for screen readers.

## Don't

- No KPI tiles, cards inside the sheet, or coloured side bars on rows.
- No Unicode glyphs or emoji as icons; no all-caps labels, kickers above headings, or meta strings
  joined with middle dots.
- No severity word "low" on clinician pages: it reads as low glucose. People see timing, not
  severity labels.
- No colour outside the tokens, and no zone colour for anything other than glucose status.
- No inline scripts, eval or external assets: the service's CSP blocks them.
