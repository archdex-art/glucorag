# GlucoRAG (web)

The GlucoRAG website: people sign up, add their glucose readings and see the next hour forecast;
clinicians see the ward. **Research prototype. Not a medical device.** Vite + React 18 +
TypeScript; charts with Recharts, icons from `lucide-react`, data fetching and polling with TanStack
Query. The production build is served by the FastAPI app under `/ui/`. Product context lives in
`PRODUCT.md`, the visual system in `DESIGN.md`, and the binding spec in
`../docs/superpowers/specs/2026-10-05-glucorag-personal-app-design.md`.

## Commands

```sh
npm ci            # install exactly what package-lock.json pins
npm run dev       # http://localhost:5173/ui/ (API paths proxied to http://127.0.0.1:8000)
npm run lint      # eslint (flat config, typescript-eslint, react-hooks)
npm run typecheck # tsc -b (strict)
npm test          # vitest run (jsdom)
npm run build     # tsc -b && vite build → ../glucorag/api/static (index.html + hashed assets/)
```

`GLUCORAG_BACKEND=http://127.0.0.1:8765 npm run dev` points the dev proxy at another backend.

## Sign-in

The app authenticates with the server's HttpOnly session cookie (`credentials: 'same-origin'`); no
token is ever held in JavaScript or browser storage. A 401 from any request clears cached data and
goes to sign-in with "Your session ended. Sign in again." The router gates routes by role: people
reach the personal pages, clinicians the staff pages, and anyone else sees a 403 page.

## Routes

| Route | Who | Shows |
|---|---|---|
| `/welcome`, `/signup`, `/signin` | Signed out | What it does, the research notice; account forms (the sign-up acknowledgement is required) |
| `/setup`, `/setup/data` | Person | About you (diabetes type, age, sex, BMI or height and weight, units); then Import, Try sample data or Enter readings |
| `/` | Person | Today: status sentence, current value and trend, 30/60 min forecast, the last 3 h with the next hour's band, latest alerts, last 24 h in ranges |
| `/history` | Person | 24 h / 3 d / 7 d / 14 d: readings chart, time in ranges, statistics (average, GMI, CV, coverage), alerts |
| `/add` | Person | Enter a reading, or Import a file (drop zone, time zone, unit, date order, format help, result summary) |
| `/settings` | Both | Profile, alert sensitivity, units, export, password, delete readings, delete account |
| `/ward`, `/patients/:id`, `/alerts`, `/model`, `/system` | Clinician | The ward with range strips, patient detail, alert feed with CSV export, release verdict, service health |

A person without a profile is sent to `/setup`; one without readings sees the add-data choices on
Today. Today and History refresh every 30 s, staff pages every 15 s; the pause toggle in the page
header stops refreshing everywhere.

## Notes

- Units: every value, axis, threshold label and input follows the user's unit (stored per user).
  mmol/L shows one decimal and mg/dL none; mg/dL = mmol/L × 18.0182 (`src/lib/units.ts`). Body
  measures follow the locale's region (cm/kg or ft-in/lb), independent of the glucose unit.
- Times: `/me` times carry a UTC offset and show in the browser's time zone. Staff event times are
  naive server-local wall-clock strings, shown as written (`src/lib/time.ts`). With
  `GLUCORAG_CLOCK=data` (replay) the staff header shows "Replay data" and the data time.
- Imports are read in the browser and posted as `text/csv`, with the detected IANA time zone, the
  unit and the date order (`auto`, `dmy` or `mdy`). When a file's dates could be read either way
  the result says which order was used.
- The page is built for the service's CSP (`script-src 'self'`, `connect-src 'self'`,
  `font-src 'self'`): no inline scripts, no eval, no external fonts or CDNs. Atkinson Hyperlegible
  Next is bundled from `@fontsource-variable/atkinson-hyperlegible-next` (latin and latin-ext).
- Pure logic (zones, units, BMI, status wording, warm-up time, statistics, time zones, access
  rules, trend arrows, time in ranges, ward sections, forecast envelope, priorities) lives in
  `src/lib/` with Vitest tests.
- `screenshots/` holds a smoke run against a live server: every screen at 1440×900 and 390×844,
  light and dark (`<screen>-<desktop|mobile>-<light|dark>.png`), plus `state-*` files for warming
  up, an old import, high now with a band back in range, no readings, a rejected reading and an
  import error, the import result (with the ambiguous date note), the delete dialogs, a wrong
  password, a person on a staff page, and the clinician alerts, model and system pages.
