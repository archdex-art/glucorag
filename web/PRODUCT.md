# GlucoRAG: product context

## What it is
GlucoRAG predicts where your glucose will be over the next hour. One population model (EPS-TFT) reads the last two hours of continuous glucose monitoring (CGM) readings, together with four facts about the person: diabetes type, age, sex and BMI. It forecasts the next hour as seven quantiles: 0.02, 0.10, 0.25, 0.50, 0.75, 0.90 and 0.98. When the chosen edge of the forecast band crosses 70 or 180 mg/dL, the app says so and records an alert.

## Status
Research prototype. Not a medical device. It must never present itself as a basis for treatment decisions. This notice is visible on every screen, and sign-up requires acknowledging it.

## Who uses it, and where
- **Primary: a person living with diabetes who wears a CGM.**
  - They use it on a phone or laptop, at home or on the go, glancing at it a few times a day, and on a Wear OS watch (watch-face complications, a tile and an app) fed by the GlucoRAG phone app.
  - They want three things answered at a glance: where they are now, which way they are heading, and whether they will go low or high in the next hour.
  - They get data in by exporting from FreeStyle LibreView or Dexcom Clarity, by typing readings, by trying a bundled sample, or live from Juggluco or xDrip+ through the GlucoRAG phone app.
- **Secondary: clinicians.** Staff accounts monitor every registered person (ward, alerts) and check the model (accuracy against the published paper, release status, in-silico trial) and the service.
- **Devices and scripts** use API keys to stream readings.

## Jobs, in priority order (person)
1. See the next hour: current value, trend, forecast band, and any low/high warning with its timing.
2. Get data in quickly: file import, a single reading, or the sample.
3. Review recent days: chart, time in ranges, average, GMI, variability, alerts.
4. Tune it: units, alert sensitivity, profile.
5. Own the data: export everything, delete readings, delete the account.

## Vocabulary the audience already reads
- **Ambulatory Glucose Profile (AGP)** reports.
- **Consensus glucose ranges** (Battelino et al., *Diabetes Care* 2019):

  | Range | mg/dL | mmol/L |
  |---|---|---|
  | very low | < 54 | < 3.0 |
  | low | 54–69 | 3.0–3.8 |
  | target | 70–180 | 3.9–10.0 |
  | high | 181–250 | 10.1–13.9 |
  | very high | > 250 | > 13.9 |

- Targets: over 70% in range, under 4% low.
- **CGM trend arrows**, **GMI** (glucose management indicator), **CV** (coefficient of variation).

## Facts the UI must never contradict
- **Model input:** 15-minute readings. A forecast exists only after 120 minutes of readings, and gaps longer than 60 minutes suspend forecasting until 2 hours of readings follow.
- **Alert rule:** low when the chosen lower edge of the band is at or below 70 mg/dL; high when the chosen upper edge is at or above 180 mg/dL.
- **Alert sensitivity:**

  | Setting | Edges |
  |---|---|
  | standard | q0.25 / q0.75 |
  | cautious | q0.10 / q0.90 |
  | very cautious | q0.02 / q0.98 |

- The model was trained on adults in Shanghai (12 T1D, 100 T2D). Sex is recorded as F/M because those are the only values it was trained on.
- Personal times are shown in the browser's own time zone. Staff pages in replay mode show dataset time.

## Constraints
- **Serving:** a same-origin SPA served by FastAPI at `/ui/`.
- **CSP:** no inline scripts, no eval, no external hosts.
- **Sessions:** an HttpOnly SameSite=Strict cookie. No token is ever stored in JavaScript-readable storage.
- **Accessibility:** WCAG 2.1 AA.
- **Units:** mg/dL and mmol/L are both first-class.
- **Phone and watch:** the watch shows only what the phone sends; every watch surface shows the reading's age or time, values grey after 15 min, and a forecast disappears an hour after it was made. Watch alerts are the phone's notifications, mirrored; they never replace the CGM app's alarms.
