# Risk register (ISO 14971-style, research use)

**Status: RESEARCH USE ONLY — not a medical device, not cleared for clinical decisions.**
Any clinical deployment requires an IEC 62304 software lifecycle, a full ISO 14971 risk
management file, clinical validation, and regulatory clearance. Insulin-suspend logic
(`glucorag.sim`) exists only for simulation.

Severity: 1 negligible … 5 catastrophic. Probability: 1 improbable … 5 frequent.
Residual ratings assume the listed controls are in place.

| ID | Hazard / failure | Cause | Harm | S | P | Controls (implemented) | Residual |
|----|------------------|-------|------|---|---|------------------------|----------|
| R1 | Missed hypoglycaemia alert | Point forecast overestimates falling BG | Untreated hypo | 5 | 3 | Alert on lower quantile band (configurable), not the median; quantiles sorted before use; hypo threshold inclusive (≤ 70) | S5 P2 |
| R2 | Prediction from stale/insufficient data | CGM dropout, sensor warm-up | Wrong forecast | 4 | 4 | Gap guard: gaps > 60 min suspend prediction and raise `data_gap`; watchdog for silent sensors; causal imputation only for short gaps | S4 P2 |
| R3 | Train/serve skew | Different preprocessing online vs offline | Silent accuracy loss | 4 | 3 | Single `ForecastEngine` reusing training normalizers from the artifact; parity check vs dataset windows (< 0.005 mg/dL) | S4 P1 |
| R4 | Wrong or corrupted model loaded | Manual file edits, partial copy | Arbitrary output | 5 | 2 | Immutable versioned artifacts, SHA-256 weight check on load, model version pinned on every stored prediction | S5 P1 |
| R5 | Out-of-population use | Model applied to cohorts/sensors it was not trained on (e.g. 5-min sensors with 15-min model) | Degraded accuracy | 4 | 4 | Artifact pins dataset + sampling interval; model card states scope; engine requires matching interval | S4 P3 |
| R6 | Invalid sensor values | Spikes, non-numeric, out-of-range | Spurious alerts | 3 | 3 | Ingest validation; clipping to 40–400 mg/dL sensor range; non-finite rejected | S3 P2 |
| R7 | Alert fatigue | Repeated identical alerts | Alerts ignored | 3 | 4 | De-duplication with cooldown; quantile choice is a configuration knob | S3 P2 |
| R8 | Data exposure | Unauthenticated access, one person seeing another's data, stolen session, logs with PHI | Privacy breach | 4 | 3 | Every route except `/healthz` authenticated (API key, or account session); people reach only `/me` (their own patient id, never client-supplied); staff routes need a clinician account created server-side; scrypt password hashes; session tokens stored only as SHA-256; HttpOnly `SameSite=Strict` cookie, plus same-origin `Origin` check on cookie writes; login throttling; strict CSP; export and full deletion available to every person; local inference only; data/ and models/ excluded from VCS | S4 P2 |
| R9 | Overfitting / optimistic evaluation | Leakage across splits | Overstated accuracy | 3 | 3 | Chronological per-series splits; normalizers fit on train only; val/test scored only on real (non-imputed) targets; cross-individual CV | S3 P1 |
| R10 | Forecast used to make treatment decisions | A person doses insulin or carbohydrate from the forecast | Hypo/hyperglycaemia | 5 | 3 | Research notice on every screen; acknowledgement required at sign-up; the forecast is shown as a band, not a single number; alert sensitivity explained in plain words; no dosing features | S5 P2 |
| R11 | Wrong units or times on import | mmol/L read as mg/dL, day/month swapped, wrong time zone | Nonsense forecasts | 4 | 3 | Unit detected from the header, then from value magnitude, and overridable; day/month resolved by the most contiguous reading; time zone sent from the browser and editable; import report shows format, unit, first/last time and every skipped count | S4 P2 |
| R12 | Stale or historic data read as current | An old export is imported | False reassurance | 4 | 3 | Status computed against wall-clock time; a past forecast is labelled with when it was made; no "now" claims without a reading inside the gap limit | S4 P1 |
