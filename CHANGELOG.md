# Changelog

## 0.5.0 — 2026-10-07
- **Wear OS watch app and Android phone app** (`android/`). Design: `docs/superpowers/specs/2026-10-06-glucorag-wear-design.md`; set-up: `android/README.md`.
  - The phone receives readings live from Juggluco (`glucodata.Minute`) or xDrip+ (`BgEstimate`), uploads about one every 5 minutes, queues them while the server is out of reach, posts alerts for predicted lows and highs (medium or high severity, once each), and sends the watch a snapshot.
  - The watch (Wear OS 3+, tested on Wear OS 6 at the Galaxy Watch4 Classic's 450 and 396 px) shows "Glucose now" and "Next hour" complications, a tile and an app. Ages and low/high countdowns are counted by the watch face itself, so they stay right between updates.
  - Phone screens: Connect, Where your readings come from, Keep readings flowing, Today, Settings.
- **Server:**
  - Device sign-in: `POST /auth/token` returns a one-year bearer token for a phone; `GET /me/devices` and `DELETE /me/devices/{id}` list and disconnect phones; `POST /auth/logout` with the bearer token signs a phone out.
  - `POST /me/readings/batch` uploads many readings at once (offset-aware times) through the backfill; `GET /me/alerts?after_id=` returns only newer alerts.
  - Database schema versions (`PRAGMA user_version`), applied on start.
- **Website:** Settings gains Connected devices (with Disconnect); Add data gains "Live from your phone".
- **Fixed:**
  - With readings every 1–5 minutes, the forecast used readings up to 5 minutes away from each 15-minute slot; each slot now takes the reading nearest its time (15-minute data is unchanged).
  - With readings every 1–5 minutes, the trend arrow was missing; it now compares with the reading nearest one interval earlier.
  - The sample CSV file was left open after loading sample data.

## 0.4.0 — 2026-10-06
- **Personal app.** People can now sign up, add their own readings and see their next hour forecast. Spec: `docs/superpowers/specs/2026-10-05-glucorag-personal-app-design.md`.
  - Pages: welcome, sign-up (research acknowledgement required), sign-in, two-step setup (about you; add your data), Today, History, Add data, Settings.
  - Today leads with one sentence ("In range for the next hour", "Low predicted in 25 min", "High now"), the current value and trend, the 30 and 60 min forecast, and the last 3 h with the next hour's band.
  - mmol/L and mg/dL throughout, stored per user; BMI from height and weight in metric or imperial.
  - Alert sensitivity per person: standard (q0.25/q0.75), cautious (q0.10/q0.90), very cautious (q0.02/q0.98).
  - Export as CSV; delete readings; delete the account (password required).
- **Accounts.** `POST /auth/register|login|logout|password`, `GET /auth/me`. Sessions are HttpOnly `SameSite=Strict` cookies, stored as SHA-256 hashes; cookie writes must be same-origin; failed logins are throttled. Passwords are hashed with scrypt.
  - Self-signup creates person accounts only. `glucorag-admin create-clinician | list-users | reset-password` manages staff.
  - The website no longer takes an API key. API keys are optional and remain for devices and scripts.
  - Staff pages moved: the ward is at `/ui/ward`; people who open a staff page get a 403 page.
- **Personal API** under `/me` (status, history, alerts, readings, import, sample, export, deletes); its times carry a UTC offset.
- **Imports.** FreeStyle LibreView, Dexcom Clarity and generic CSV, with time zone, unit and date order (`dates=auto|dmy|mdy`). When a file's dates fit both orders, the order whose span is plausible and ends nearest to now wins, and the result says so.
  - Imports backfill: readings earlier than ones already stored are merged, and forecasts and alerts are recalculated from the earliest new reading. Previously, an import after a few manual readings added nothing.
  - A 48-hour sample trace (CC BY 4.0, see `glucorag/data/sample/README.md`) can be loaded into an empty account.
- **Settings:** `GLUCORAG_ALLOW_SIGNUP`, `GLUCORAG_COOKIE_SECURE`, `GLUCORAG_SESSION_DAYS`, `GLUCORAG_IMPORT_MAX_DAYS`.
- **Fixed:** signing in while the account was being deleted returned 500; it now returns 401.

## 0.3.0 — 2026-10-05
- **Dashboard redesign** in the Ambulatory Glucose Profile (AGP) report language, aimed at ward clinicians.
  - Patients are grouped into Needs attention, Not reporting, Warming up, Stable and No readings yet, so at-risk patients are no longer listed below sensor gaps.
  - Every patient row shows the current value, the trend arrow, and a range strip: the next hour's forecast band drawn across the five consensus glucose zones on a log scale.
  - The patient page leads with Now / In 30 min / In 60 min readings, an AGP-style percentile chart and a time-in-ranges bar.
  - The model page leads with the release verdict and the comparison against the paper.
  - Self-hosted Atkinson Hyperlegible Next with tabular numerals; drawn icons (lucide) replace Unicode glyphs.
  - Design records: `web/PRODUCT.md`, `web/DESIGN.md`, `docs/superpowers/specs/2026-10-05-dashboard-agp-redesign-design.md`.
- **API:** `GET /cohort/risk` rows gain three fields, added without changing existing ones:
  - `last_glucose_mg_dl`;
  - `trend_mg_dl_per_min` (over the latest sampling interval; null across a gap);
  - `forecast`: the latest fresh forecast reduced to the patient's own alert band (low and high quantiles plus the median, at each horizon).

## 0.2.0 — 2026-10-05
- **Monitoring website** (`web/`): React + TypeScript single-page app served by the API at `/ui/`.
  - Pages: cohort overview, patient detail with forecast fan chart, alert feed with CSV export, model/evaluation/release page, system health page.
  - Login with the API key, which is kept in session storage only.
- **API:** new `GET /model` and `GET /stats` for the dashboard; SPA serving with immutable asset caching; security headers (CSP, frame and nosniff) on every response.
- **Ops:**
  - multi-stage Docker build (Node stage builds the website);
  - `docker/compose.yaml`;
  - CI job for web lint, type-check, test and build;
  - the website ships inside the Python wheel.

## 0.1.0 — 2026-10-05
- **Data:**
  - ShanghaiDM and OhioT1DM loaders;
  - regular-grid resampling, causal imputation with a 60-min gap limit, clipping to the sensor range;
  - chronological splits per segment; normalizers fitted on training data only.
- **Model:** EPS-TFT (VSN, GRN/GLU, static covariate encoder, LSTM encoder and decoder, interpretable causal attention, 7-quantile head). Covariate-encoder outputs can be precomputed. Ablation switches.
- **Training:**
  - training CLI;
  - Optuna HyperBand tuner;
  - versioned registry with a SHA-256 weights check;
  - `shanghai-v1` trained, plus two ablation models.
- **Evaluation:**
  - RMSE, MAE, MAPE, gRMSE (Del Favero 2012);
  - LR, SVR, XGBoost, LSTM, N-BEATS, N-HiTS baselines;
  - Shapiro–Wilk and paired t-test;
  - 5-fold cross-individual CV;
  - VSN and attention explainability.
- **Runtime:**
  - `ForecastEngine` (parity with offline predictions);
  - ingest validation, window buffer, risk engine (quantile bands, gap guard, watchdog), alert de-duplication;
  - SQLite storage;
  - FastAPI service with API-key auth and Prometheus metrics;
  - dataset replay adapter.
- **In-silico:** predictive low-glucose suspend trial on simglucose, with CVGA.
- **Release:** gate CLI (integrity, accuracy, significance, parity, in-silico) and a promotion pointer `models/CURRENT`.
- **Ops:** CI workflow, pre-commit hooks, Docker image, model card, risk register.
