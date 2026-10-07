# GlucoRAG (EPS-TFT)

This project forecasts blood glucose 15–60 minutes ahead, with uncertainty bands (quantiles). One Temporal Fusion Transformer serves the whole patient population. It reimplements the software side of Zhu et al., *IEEE TBioCAS* 18(2), 2024, following `GlucoRAG_Architecture.pdf`.

> **Research use only.** This is not a medical device. See `docs/RISK_REGISTER.md` and `docs/MODEL_CARD.md`.

## Layout
| Package | Responsibility |
|---|---|
| `glucorag/data` | Loaders for ShanghaiDM and OhioT1DM, chronological splits, and the dataset pipeline (`load_dataset`, `make_windows`) |
| `glucorag/preprocess` | Regular time grid, causal imputation, normalizers, sliding windows |
| `glucorag/models/tft` | GLU, GRN, VSN, interpretable attention, quantile loss, `EPSTFT` |
| `glucorag/train` | Trainer, training CLI, Optuna HyperBand tuner |
| `glucorag/core` | Config, schemas, versioned model registry, SQLite storage, JSON logging |
| `glucorag/evaluate`, `glucorag/explain` | Metrics (RMSE/MAE/MAPE/gRMSE), 6 baselines, significance tests, cross-individual CV, VSN and attention importance |
| `glucorag/inference` | `ForecastEngine`: the same preprocessing as training, run on raw CGM history |
| `glucorag/ingest`, `features`, `risk`, `notify`, `service.py`, `api` | Runtime pipeline: ingest → window buffer → engine → risk → de-duplicated alerts → store → FastAPI |
| `glucorag/sim` | In-silico predictive low-glucose suspend trial (simglucose) with CVGA |
| `glucorag/release.py` | Release gates and model promotion |

## Setup
```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[dev,sim]"
```

**Data:**
- **ShanghaiDM:** public. Download it from figshare (10.6084/m9.figshare.20444397) and extract it to `data/raw/shanghai`.
- **OhioT1DM:** needs a data use agreement. Pass the XML root plus a `patient_id,age,gender` CSV (`--ohio-profiles`).
- `data/` and `models/` are never committed.

## Workflow
```bash
# Train and register a versioned model (about 7 s per epoch on CPU)
glucorag-train --dataset shanghai --data-root data/raw/shanghai --version shanghai-v1
glucorag-tune  --dataset shanghai --data-root data/raw/shanghai --trials 30   # optional HyperBand search

# Evaluate: paper-style tables, baselines, significance, explainability; 5-fold cross-individual CV
glucorag-evaluate --artifact models/shanghai-v1 --data-root data/raw/shanghai --baselines \
    --out reports/shanghai-v1
glucorag-evaluate --artifact models/shanghai-v1 --data-root data/raw/shanghai --cv 5 \
    --out reports/shanghai-v1

# In-silico trial (10 virtual adults, 90 days, about 3.5 min with 10 workers)
glucorag-sim --artifact models/shanghai-v1 --days 90 --out reports/sim

# Release gates: integrity, accuracy, significance, serving parity, in-silico result.
# Promotion writes models/CURRENT.
glucorag-release --artifact models/shanghai-v1 --data-root data/raw/shanghai \
    --sim-report reports/sim/report.json
```

## The app: serving, accounts and the website
Build the website once (output goes to `glucorag/api/static/`), then start the server:
```bash
(cd web && npm ci && npm run build)
GLUCORAG_MODEL_PATH=models/shanghai-v1 GLUCORAG_SIM_REPORT=reports/sim/report.json glucorag-serve
# GLUCORAG_MODEL_PATH=models serves whichever version models/CURRENT names
```
Open **http://127.0.0.1:8000/ui/** and choose **Create account**. Each person gets their own forecast:
1. **Sign up** with an email and a password of at least 10 characters, and confirm you understand it is a research prototype.
2. **About you:** diabetes type, age, sex and BMI (or height and weight). These are the model's static inputs. Choose mg/dL or mmol/L.
3. **Add your data** in any of three ways:
   - import a FreeStyle LibreView, Dexcom Clarity or generic CSV export (time zone detected from the browser; unit and date order auto-detected and overridable);
   - load a 48-hour sample trace;
   - type readings in one at a time.

   Forecasts start after 2 hours of readings. Imports may include earlier readings than ones already there; forecasts and alerts are recalculated from the earliest new reading.
4. **Today** shows the current value and trend, the next hour as a forecast band, and a plain sentence ("In range for the next hour", "Low predicted in 25 min", "High now"). **History** shows 24 h to 14 days, time in ranges, average, GMI and variability.
5. **Settings:** profile, alert sensitivity (standard, cautious or very cautious band), units, CSV export, password change, deleting readings, deleting the account (password required).

**Clinician accounts** see the ward, patient, alert, model and system pages instead. Self-signup never creates them; an operator does:
```bash
glucorag-admin create-clinician nurse@ward.example   # prompts for the password
glucorag-admin list-users
glucorag-admin reset-password someone@example.com
```
A person who opens a staff page gets a 403 page.

**Sessions:** the website signs in with an HttpOnly, `SameSite=Strict` session cookie; only a SHA-256 of the session token is stored. Writes made with the cookie must come from the same origin. Failed logins are throttled at 5 per 15 min per email (in process memory, so per server process). Behind TLS, set `GLUCORAG_COOKIE_SECURE=true` if the proxy does not send `X-Forwarded-Proto: https`.

**Devices and scripts** use API keys (`X-API-Key`), which are optional: set `GLUCORAG_API_KEYS` only if something should push readings without an account. To fill the ward with a recorded series:
```bash
GLUCORAG_API_KEY=change-me glucorag-replay data/raw/shanghai/Shanghai_T1DM/1001_0_20210730.xlsx \
    --url http://127.0.0.1:8000     # run the server with GLUCORAG_API_KEYS=change-me GLUCORAG_CLOCK=data
```
For frontend development: `cd web && npm run dev` (Vite on :5173, API proxied to :8000). See `web/README.md`.

**Endpoints:**
- Accounts: `POST /auth/register`, `/auth/login`, `/auth/logout`, `/auth/password`; `GET /auth/me`
- Personal (session): `GET /me`, `PUT /me/profile`, `GET /me/status`, `GET /me/history`, `GET /me/alerts`, `POST /me/readings`, `POST /me/import?tz=&unit=&dates=` (CSV body), `POST /me/sample`, `GET /me/export`, `DELETE /me/readings`, `DELETE /me`
- Staff (clinician session or API key): `POST /patients`, `POST /readings`, `GET /patients/{id}/forecast`, `GET /patients/{id}/history`, `GET /cohort/risk`, `GET /alerts`, `GET /export`, `GET /model`, `GET /stats`
- `GET /metrics` (Prometheus), `GET /healthz`, `/ui/` (website)

Everything except `/healthz`, `/ui/`, register, login and logout needs a session or an API key. `/me` times carry a UTC offset; staff routes use naive server-local times. All responses carry a strict CSP and other security headers.

**Main settings (`GLUCORAG_*`):**
- `MODEL_PATH`, `DB_PATH`, `SIM_REPORT`, `API_KEYS` (optional, comma-separated)
- `ALLOW_SIGNUP` (default true), `COOKIE_SECURE` (unset = only over HTTPS), `SESSION_DAYS` (14), `IMPORT_MAX_DAYS` (30: an import keeps the last N days of its file)
- `CLOCK` (`wall` or `data`)
- `HYPO_QUANTILE` (default 0.25), `HYPER_QUANTILE` (default 0.75): the ward default; each person's sensitivity setting overrides them for their own alerts
- `HYPO_MG_DL` (≤ 70), `HYPER_MG_DL` (≥ 180)
- `DATA_GAP_MIN` (60), `ALERT_COOLDOWN_MIN` (30)

**Docker** (builds the website and the server into one image):
```bash
docker compose -f docker/compose.yaml up --build
# then open http://localhost:8000/ui/ ; GLUCORAG_ALLOW_SIGNUP=false closes self-signup
```

## Results (`shanghai-v1`, ShanghaiDM test split)
- **RMSE:** 12.04 ± 3.02 mg/dL at 30 min and 21.21 ± 6.01 at 60 min. The paper reports 12.7 ± 3.8 and 21.7 ± 6.9.
- **Significance:** the gain over the next-best baseline (LSTM) is not statistically significant.
- **In-silico predictive suspend:** time below 70 mg/dL drops from 4.6% to 3.6%.

Full results: `docs/MODEL_CARD.md`, `reports/`.

## Development
```bash
ruff check . && pyright && pytest -q
```

CI is in `.github/workflows/ci.yml`; pre-commit hooks are in `.pre-commit-config.yaml`.
