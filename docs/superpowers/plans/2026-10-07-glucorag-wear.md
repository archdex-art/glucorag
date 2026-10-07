# GlucoRAG Wear OS + phone companion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Readings flow from Juggluco or xDrip+ on the phone to the GlucoRAG server, and the forecast flows back to the phone and onto a Galaxy Watch4 Classic: complications, tile and app.

**Architecture:**
- The **phone app** receives explicit CGM broadcasts, queues readings in Room and uploads them with a bearer token. It then fetches status, history and new alerts, posts alert notifications, and writes an urgent Data Layer snapshot.
- The **watch app** renders that snapshot, computing ages and countdowns itself. It never talks to the server.
- The **server** gains device tokens, batch upload, `after_id` alerts, a schema-version mechanism, and two dense-feed fixes.

**Tech Stack:**
- Server: Python 3.12, FastAPI, SQLite, pytest.
- Website: React 18 + TS, Vitest.
- Android:
  - Gradle 9.5.1, AGP 9.3.1 (built-in Kotlin), Kotlin 2.4.20, KSP 2.3.12;
  - Compose BOM 2026.09.00, Wear Compose material3 1.7.0, protolayout 1.4.2, tiles 1.6.2, watchface-complications-data-source-ktx 1.3.0, play-services-wearable 20.0.1;
  - WorkManager 2.12.0, Room 2.8.5, DataStore 1.2.1, OkHttp/mockwebserver3 5.5.0, kotlinx-serialization 1.11.0, coroutines 1.11.0.

**Spec:** `docs/superpowers/specs/2026-10-06-glucorag-wear-design.md`. Read it first; its §1 platform rules bind every Android task.

## Global Constraints
- **App identity:**
  - `applicationId` is `org.glucorag.app` for **both** apps.
  - Namespaces: phone `org.glucorag.app`, watch `org.glucorag.wear`, shared `org.glucorag.shared`.
  - One keystore, `android/keystore/glucorag-dev.jks`, for debug in both apps (Data Layer requires the same signature).
- **SDK levels:** compileSdk 37; targetSdk 36; minSdk phone 28, watch 30. JDK 17 (`JAVA_HOME=/Library/Java/JavaVirtualMachines/jdk-17.jdk/Contents/Home`).
- **Glucose units and thresholds:**
  - mg/dL = mmol/L × 18.0182; mmol/L shows 1 decimal, mg/dL none; never show "-0".
  - Thresholds 54 / 70 / 180 / 250 mg/dL; scale 40–400.
  - "Past threshold" is inclusive: value ≤ 70 is low and ≥ 180 is high (the backend's alert rule).
- **Trend** (mg/dL/min): > 2 rising quickly `↑`; > 1 rising `↗`; ≥ −1 steady `→`; ≥ −2 falling `↘`; else falling quickly `↓`.
- **Staleness and update rates:**
  - A reading is old after 15 min.
  - A forecast expires at `t0 + 60 min`.
  - Complication pushes: ≤ 1 per 5 min, except on a status change. Tile: ≤ 1 per min.
- **Snapshot:** `/glucorag/snapshot`, written with `setUrgent()`, < 2 KB, JSON `v: 1` as in spec §3.
- **Broadcasts:**
  - Accept 20–600 mg/dL; times no more than 2 min in the future.
  - Thinning: queue a reading only if ≥ 4.5 min after the last queued one.
- **Notifications:** only for hypo/hyper alerts with severity `high` or `medium`, one per alert id. Title "Low predicted in N min" / "High predicted in N min"; body "Research forecast. Your CGM app's alarms still apply."
- **Copy:** people read "low"/"high", never "hypo"/"hyper". Research notice text: "Research prototype. Not a medical device. Don't use it to make treatment decisions."
- **No VCS:** the repo is not a git repository, so each task ends with a green test run instead of a commit.
- **Final checks:**
  - Python: `ruff check . && pyright && pytest -q`.
  - Web: `cd web && npm run lint && npm run typecheck && npm test && npm run build`.
  - Android: `cd android && ./gradlew :shared:testDebugUnitTest :phone:testDebugUnitTest :wear:testDebugUnitTest :phone:lintDebug :wear:lintDebug :phone:assembleDebug :wear:assembleDebug`.

## Review Focus
1. **Phone clock ahead of the server.** A reading stamped 1–2 min in the future must be accepted by both, and one 3 min ahead must be rejected by both. The phone must not retry it forever. Tests: Task 5 `test_batch_future_reading_rejected_with_reason`; Task 10 `futureBeyondTwoMinutesDropped`; Task 12 `rejectedReadingsLeaveQueue`.
2. **Timestamps sent as UTC (`Z`) from the phone** must land at the right local time on the server and in website History. Test: Task 5 `test_batch_utc_timestamps_stored_as_local_time`.
3. **A long offline backlog** (e.g. 1,200 readings after a weekend away) uploads in several batches of ≤ 500, in time order, and the backfill replays alerts. Test: Task 12 `drainsBacklogInBatchesOf500`.
4. **A token revoked while readings are queued:** uploads stop and the queue is **kept** until sign-in, never silently deleted. Test: Task 12 `unauthorizedKeepsQueueAndSignsOut`.
5. **An alert already notified** is not posted again after a process restart. The last-seen alert id is persisted. Test: Task 12 `alertNotifiedOnceAcrossRestart`.

---

## Phase A: Server

### Task 1: Grid alignment for dense feeds

**Files:**
- Modify: `glucorag/inference/engine.py` (`ForecastEngine.build_inputs`, lines 64–89)
- Test: `tests/test_dense_feeds.py`

**Interfaces:**
- Produces: `build_inputs` unchanged in signature. Each slot holds the reading **nearest** to `t0 − k·step` within `step/2`; on an exact tie the later reading wins.

- [ ] **Step 1: Write the failing test.** Build a `ForecastEngine` the way `tests/test_backfill.py` does (via `tiny_artifact` + `ForecastEngine.from_artifact`). Each value encodes its own age (`glucose = 100 + age_min`).
```python
@pytest.mark.parametrize("step_min", [15, 5, 1])
def test_slots_hold_reading_nearest_grid_time(engine, step_min):
    hist = [Reading(T0 - timedelta(minutes=a), 100.0 + a) for a in range(0, 180, step_min)]
    x_enc, _, t0 = engine.build_inputs(hist)
    ages = decode_ages(engine, x_enc)          # inverse-normalise column 0, minus 100
    assert ages == [15 * k for k in range(engine.meta.lookback_steps - 1, -1, -1)]
```
- [ ] **Step 2:** Run `pytest tests/test_dense_feeds.py -q`. Expected: the 5- and 1-min cases FAIL (ages 100, 85 … 10, 0).
- [ ] **Step 3:** In `build_inputs`, track the best `|offset|` per slot and keep a reading only if `|t0 − r.timestamp − k·step| ≤ step/2` and it is nearer than the current holder (ties: later). Leave gap imputation untouched.
- [ ] **Step 4:** Run `pytest tests/test_dense_feeds.py tests/test_service.py tests/test_backfill.py -q`. Expected: PASS. Then the parity gate's unit tests: `pytest -q -k parity`. Expected: PASS.

### Task 2: Trend on dense feeds

**Files:**
- Modify: `glucorag/service.py` (`_trend`, lines 599–611)
- Test: `tests/test_dense_feeds.py`

**Interfaces:**
- Produces: `_trend(history: list[Reading], interval_min: int) -> float | None`, using the reading nearest `last − interval`, accepted within `[0.5, 1.5]·interval`.

- [ ] **Step 1: Write the failing test.**
```python
@pytest.mark.parametrize("step_min", [15, 5, 1])
def test_trend_on_rising_feed(step_min):
    hist = [Reading(T0 - timedelta(minutes=a), 200.0 - a) for a in range(120, -1, -step_min)]  # +1 mg/dL/min
    assert _trend(hist, 15) == pytest.approx(1.0)

def test_trend_none_across_gap():
    hist = [Reading(T0 - timedelta(minutes=40), 100.0), Reading(T0, 120.0)]
    assert _trend(hist, 15) is None
```
- [ ] **Step 2:** Run it. Expected: the 5/1-min cases FAIL (`None`).
- [ ] **Step 3:** Implement as above. `history` is sorted ascending; scan backwards from the end.
- [ ] **Step 4:** Run `pytest tests/test_dense_feeds.py tests/test_service.py -q`. Expected: PASS.

### Task 3: Schema versions and session device columns

**Files:**
- Modify: `glucorag/core/storage.py` (`Storage.__init__` ≈ line 140; the sessions methods ≈ line 388)
- Test: `tests/test_migrations.py`

**Interfaces:**
- Produces:
  - `Storage.SCHEMA_VERSION = 1`, and `_migrate()` run after `executescript(SCHEMA)`. Version 0→1: `ALTER TABLE sessions ADD COLUMN device TEXT; ALTER TABLE sessions ADD COLUMN last_used_at TEXT`, then `PRAGMA user_version = 1`.
  - `create_session(token_hash, user_id, expires_at, device: str | None = None) -> None`
  - `device_sessions(user_id: int) -> list[DeviceSession]`, where `DeviceSession(id: int, device: str, created_at: datetime, last_used_at: datetime | None)` and `id` is the sessions `rowid`; only rows with `device IS NOT NULL`.
  - `delete_device_session(user_id: int, session_id: int) -> bool`
  - `touch_session(token_hash: str, now: datetime) -> None`, which writes `last_used_at` only if it is null or ≥ 10 min old.

- [ ] **Step 1: Write the failing tests.**
  - `test_v0_database_upgrades`: create a file with the current `SCHEMA` text and `user_version` 0, plus one session row. Open `Storage`. Assert `user_version == 1`, the new columns exist and the old row survives.
  - `test_fresh_database_is_current`: a fresh database has `user_version == 1`.
  - `test_device_sessions_list_and_delete_scoped_to_user`: two users with one device each. User A can't delete B's row (returns False).
  - `test_touch_session_throttled`: two touches 5 min apart keep the first time; 11 min apart update it.
- [ ] **Step 2:** Run `pytest tests/test_migrations.py -q`. Expected: FAIL.
- [ ] **Step 3:** Implement. `SCHEMA` keeps the v0 `sessions` definition so step 1 applies uniformly; new columns arrive only via migrations.
- [ ] **Step 4:** Run `pytest tests/test_migrations.py tests/test_accounts.py -q`. Expected: PASS.

### Task 4: Device tokens and the devices API

**Files:**
- Modify: `glucorag/api/auth.py` (add `POST /auth/token`), `glucorag/api/deps.py` (`optional_principal`), `glucorag/api/me.py` (devices routes)
- Test: `tests/test_device_tokens.py` (reuse the `make_client`, `_register`, `PASSWORD`, `PROFILE` helpers; copy them or move them to `tests/conftest.py` if shared by ≥ 2 files)

**Interfaces:**
- Consumes: Task 3's `create_session(..., device=)`, `device_sessions`, `delete_device_session`, `touch_session`.
- Produces:
  - `POST /auth/token` with body `TokenIn(email: str, password: str, device: str = Field(min_length=1, max_length=64))`, returning `TokenOut(token: str, expires_at: datetime, account: AccountOut)`.
    - 401 "Email or password is incorrect."; 429 with the same throttle as login; 403 "Device sign-in is for personal accounts." for clinicians.
    - Lifetime 365 days.
  - `Authorization: Bearer <token>` resolves to `Principal("session", user, hashed)`. Precedence: `X-API-Key`, then Bearer, then cookie; an invalid or expired bearer token → 401 (not a fall-through to the cookie). The same-origin check is skipped for bearer requests, and each bearer request calls `touch_session`.
  - `GET /me/devices` → `[{id, device, created_at, last_used_at}]`; `DELETE /me/devices/{id}` → 204, or 404 if not the caller's.

- [ ] **Step 1: Write the failing tests.**
  - `test_token_issue_and_use`: register, then `POST /auth/token` with no cookies (use a fresh `TestClient` or clear `c.cookies`); `GET /auth/me` with the bearer header → 200.
  - `test_token_wrong_password_401_and_throttled_after_5`: the fifth failure → the next attempt gets 429.
  - `test_token_refused_for_clinician`: 403.
  - `test_bearer_write_needs_no_origin_and_cross_origin_header_is_ignored`: `POST /me/readings` with a bearer token and `Origin: https://evil.example` → 200 (no cookie involved).
  - `test_devices_list_revoke_then_401`: create the token, list it (device name shown), delete it, then bearer `GET /me/status` → 401.
  - `test_cookie_sessions_not_listed_as_devices`.
- [ ] **Step 2:** Run `pytest tests/test_device_tokens.py -q`. Expected: FAIL (404s).
- [ ] **Step 3:** Implement. Share the credential check with `login` by extracting `_check_credentials(body, service, throttle) -> StoredUser` in `auth.py`; keep `UserGoneError → 401`.
- [ ] **Step 4:** Run `pytest tests/test_device_tokens.py tests/test_accounts.py -q`. Expected: PASS.

### Task 5: Batch readings and new-alert polling

**Files:**
- Modify: `glucorag/api/me.py` (add `POST /me/readings/batch`; `GET /me/alerts` gains `after_id`), plus the `glucorag/core/storage.py` alerts query if it can't filter by id
- Test: `tests/test_batch_readings.py`

**Interfaces:**
- Consumes: `service.backfill(patient_id, readings: list[tuple[datetime, float]]) -> BackfillResult(outcomes, added)`; `to_local_naive` (as used by `/me/import`).
- Produces:
  - `POST /me/readings/batch` with body `BatchIn(readings: list[BatchReading])`, where `BatchReading(timestamp: datetime, glucose_mg_dl: float = Field(gt=0))`. More than `request.app.state.max_batch` → 413. Returns `{accepted: int, already_present: int, rejected: [{timestamp, reason}]}`.
  - Rejections:
    - future beyond `max_future_skew` → `"future"`;
    - outside 20–600 → `"out_of_range"`;
    - a naive timestamp → 422 for the whole request (offset required).
  - `GET /me/alerts?after_id=N` → alerts with `id > N`, **oldest first**, capped by `limit`.

- [ ] **Step 1: Write the failing tests.**
  - `test_batch_out_of_order_and_duplicates`: 12 readings shuffled, then the same batch again → `accepted == 12`, then `already_present == 12`.
  - `test_batch_future_reading_rejected_with_reason`: +90 s accepted, +3 min rejected with `"future"`.
  - `test_batch_utc_timestamps_stored_as_local_time`: post `Z` times; `/me/history` returns the same instants with an offset.
  - `test_batch_413_over_max_batch` (use `make_client(max_batch=3)`).
  - `test_batch_requires_offset_aware_times` → 422.
  - `test_alerts_after_id_returns_only_newer_oldest_first`: drive a rising series to raise ≥ 2 alerts (reuse the reading helper from `test_accounts.py`).
- [ ] **Step 2:** Run `pytest tests/test_batch_readings.py -q`. Expected: FAIL.
- [ ] **Step 3:** Implement. Validate ranges and the future limit in the handler (with `service.now()` or the clock the service uses), then pass survivors to `backfill`.
- [ ] **Step 4:** Run `pytest -q`, then `ruff check . && pyright`. Expected: all pass, 0 errors.

### Task 6: Website — Connected devices and "Live from your phone"

**Files:**
- Modify: `web/src/api/types.ts` (`Device`), `web/src/api/client.ts` (`devices()`, `revokeDevice(id)`), `web/src/api/hooks.ts` (`useDevices`), `web/src/pages/SettingsPage.tsx` (new `DevicesSection` after `DataSection`), `web/src/components/AddDataChoices.tsx` (fourth choice)
- Create: `web/src/lib/devices.ts` (`describeDevice(d: Device, now: number): string`)
- Test: `web/src/lib/devices.test.ts`

**Interfaces:**
- Consumes: Task 4's `GET/DELETE /me/devices`.
- Produces:
  - `type Device = { id: number; device: string; created_at: string; last_used_at: string | null }`.
  - `describeDevice` → "Connected 6 Oct 2026. Last used 4 min ago." / "Connected 6 Oct 2026. Not used yet."

- [ ] **Step 1: Write the failing test.** Cover `describeDevice` for null `last_used_at`, under 1 min ("Last used just now"), minutes, and another day ("Last used 5 Oct, 14:05"). Reuse the existing time formatters from `src/lib/time.ts`.
- [ ] **Step 2:** `npm test -- devices`. Expected: FAIL.
- [ ] **Step 3:** Implement the lib function, client, hook and section:
  - **Section:** heading "Connected devices"; each row shows the device name and `describeDevice`, with a **Disconnect** button opening `ConfirmDialog`: "Disconnect Pixel 8? It stops uploading readings until you sign in on it again."
  - **Empty state:** "No phone connected. Install the GlucoRAG phone app to stream readings from Juggluco or xDrip+."
  - **AddDataChoices:** "Live from your phone", text "Readings stream from Juggluco or xDrip+ on your Android phone, and your watch shows the forecast. Install the GlucoRAG phone app and sign in with this account." A button "See connected devices" goes to `/settings#devices` (the `DevicesSection` root gets `id="devices"`). There is no link to repo files; the website doesn't serve them.
- [ ] **Step 4:** `npm run lint && npm run typecheck && npm test && npm run build`. Expected: all pass, and still exactly one `<script>` tag in `glucorag/api/static/index.html`.

## Phase B: Android

### Task 7: Gradle project skeleton, keystore, CI

**Files:**
- Create:
  - `android/settings.gradle.kts`, `android/build.gradle.kts`, `android/gradle.properties`, `android/gradle/libs.versions.toml`;
  - the Gradle 9.5.1 wrapper (`gradle wrapper --gradle-version 9.5.1`, using the cached 9.0.0 distribution to bootstrap, or download the wrapper jar);
  - `android/{shared,phone,wear}/build.gradle.kts` and minimal `AndroidManifest.xml` files;
  - `android/keystore/glucorag-dev.jks` (`keytool -genkeypair -alias glucorag -keyalg RSA -validity 10000`, store/key password `glucorag-dev`), plus `android/.gitignore`.
- Modify: `.github/workflows/ci.yml` (add an `android` job: `actions/setup-java@v4` with Java 17 and `android-actions/setup-android@v3`, then the final Android check command)

**Interfaces:**
- Produces: modules `:shared` (Android library, namespace `org.glucorag.shared`), `:phone`, `:wear`, and the version catalog aliases used by later tasks (`libs.androidx.work.runtime`, `libs.room.runtime`, `libs.room.compiler`, `libs.wear.compose.material3`, `libs.protolayout.material3`, `libs.tiles`, `libs.complications.datasource`, `libs.play.services.wearable`, `libs.okhttp`, `libs.mockwebserver3`, `libs.kotlinx.serialization.json`, `libs.kotlinx.coroutines.play.services`, `libs.datastore.preferences`, `libs.compose.bom`).
  - Both apps use `signingConfigs.debug` → the shared keystore.
  - On AGP 9: built-in Kotlin, apply `org.jetbrains.kotlin.plugin.compose` and `org.jetbrains.kotlin.plugin.serialization` at 2.4.20, Room via `com.google.devtools.ksp` 2.3.12. No `kotlin-android`, no kapt.

- [ ] **Step 1:** Run `./gradlew --version` with JDK 17. Expected: Gradle 9.5.1.
- [ ] **Step 2:** Run `./gradlew :phone:checkDebugAarMetadata :wear:checkDebugAarMetadata :phone:assembleDebug :wear:assembleDebug`. Expected: BUILD SUCCESSFUL.
- [ ] **Step 3:** `apksigner verify --print-certs` on both debug APKs shows the **same** SHA-256 certificate digest, and `aapt2 dump badging` shows `package: name='org.glucorag.app'` for both.

### Task 8: Shared rules — units, zones, trend, status

**Files:**
- Create: `android/shared/src/main/kotlin/org/glucorag/shared/{Glucose.kt,Status.kt}`
- Test: `android/shared/src/test/kotlin/org/glucorag/shared/{GlucoseTest.kt,StatusTest.kt}`

**Interfaces:**
- Produces:
  - `enum class GlucoseUnit(val label: String) { MG_DL("mg/dL"), MMOL_L("mmol/L") }`, with `fun GlucoseUnit.Companion.parse(s: String): GlucoseUnit`.
  - `fun formatGlucose(mgdl: Double, unit: GlucoseUnit): String` (no "-0"; mmol 1 decimal).
  - `enum class Zone { VERY_LOW, LOW, TARGET, HIGH, VERY_HIGH }`, with `fun zoneOf(mgdl: Double): Zone` (website boundaries: < 54, < 70, ≤ 180, ≤ 250, else).
  - `enum class Trend(val arrow: String, val label: String)`, with `fun trendOf(ratePerMin: Double?): Trend?` (null or NaN → null).
  - `enum class StatusKind { WAITING, OPEN_PHONE, NO_RECENT, COLLECTING, NEEDS_SERVER, NO_FORECAST, LOW_NOW, HIGH_NOW, LOW_SOON, HIGH_SOON, IN_RANGE }`, with table rows 1–12 mapping in order to WAITING, OPEN_PHONE, NO_RECENT, COLLECTING, NEEDS_SERVER, NO_FORECAST, LOW_NOW/HIGH_NOW, LOW_SOON/HIGH_SOON, LOW_SOON/HIGH_SOON, HIGH_NOW, LOW_NOW, IN_RANGE.
  - `data class StatusLine(val kind: StatusKind, val sentence: String, val shortText: String, val shortTitle: String, val urgent: Boolean)`.
  - `fun statusOf(s: Snapshot?, nowMs: Long): StatusLine` (`Snapshot` comes from Task 9; write Task 9's model first if implementing in order, or define the data classes here and the JSON in Task 9).
- Status rules, in order. The first match wins; `fresh` means `now.t` is within 15 min.

  | # | Condition | sentence | short text / title |
  |---|---|---|---|
  | 1 | snapshot null | "Waiting for your phone" | `--` / `Next 1h` |
  | 2 | `server.state` in {signed_out, needs_setup} | "Open GlucoRAG on your phone" | `--` / `Phone` |
  | 3 | not fresh | "No recent reading" | `--` / `Next 1h` |
  | 4 | `server.state == warming_up` | "Collecting readings" | `--` / `Next 1h` |
  | 5 | forecast null or expired, state unreachable | "Forecast needs your GlucoRAG server" | `--` / `Next 1h` |
  | 6 | forecast null or expired, otherwise | "No current forecast" | `--` / `Next 1h` |
  | 7 | risk set and value past its threshold | "Low now" / "High now" | `now` / `Low`, `now` / `High` |
  | 8 | risk set, `at > now` | "Low predicted in N min" (N = ceil((at−now)/60 000)) | `Nm` / `Low` |
  | 9 | risk set, `at ≤ now` | "Low predicted for 14:20" (local HH:mm of `at`) | `now` / `Low` |
  | 10 | no risk, value ≥ 180 | "High now, back in range within 15 min" (first horizon) | `now` / `High` |
  | 11 | no risk, value ≤ 70 | "Low now, back in range within 15 min" | `now` / `Low` |
  | 12 | otherwise | "In range for the next hour" | `OK` / `Next 1h` |

  `urgent` = risk severity `high`.

- [ ] **Step 1:** Write tests for:
  - every row of the table, including the boundaries (exactly 70 and 180 count as past; 15:00 old vs 14:59; `t0 + 60 min` expiry);
  - every `shortText` and `shortTitle` ≤ 7 characters, over a generated sweep of N = 1..60;
  - `formatGlucose(70.0, MMOL_L) == "3.9"`, `formatGlucose(-0.04, MMOL_L) == "0.0"`, `formatGlucose(142.4, MG_DL) == "142"`;
  - `trendOf` at 2.0, 2.01, 1.0, −1.0, −1.01, −2.0, −2.01 and NaN.
- [ ] **Step 2:** `./gradlew :shared:testDebugUnitTest`. Expected: FAIL to compile, then FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run again. Expected: PASS.

### Task 9: Snapshot model, JSON and complication values

**Files:**
- Create: `android/shared/src/main/kotlin/org/glucorag/shared/{Snapshot.kt,Complications.kt}`
- Test: `SnapshotTest.kt`, `ComplicationsTest.kt`

**Interfaces:**
- Produces:
  - `@Serializable data class Snapshot(v, unit, now: Now?, recent: List<List<Double>>, forecast: Forecast?, risk: Risk?, server: Server, written: Long)`, with fields exactly as in spec §3. Also `Now(t, mgdl, rate: Double?, from: String)`, `Forecast(t0, horizons, median, low, high)`, `Risk(type: String, at: Long, severity: String)` and `Server(state: String, since: Long)`.
  - `object SnapshotCodec { fun encode(s: Snapshot): ByteArray; fun decode(b: ByteArray): Snapshot? }`. `decode` returns null for unknown `v` or malformed input, and ignores unknown keys.
  - `fun rangedFraction(mgdl: Double): Float`: `(ln v − ln 40)/(ln 400 − ln 40)`, clamped to [0, 1].
  - `fun nowShortText(s: Snapshot): String`, e.g. `"142↗"` / `"7.9↗"`, ≤ 7 characters.
  - `fun nowLongText(s: Snapshot, nowMs: Long): String`, e.g. `"142 mg/dL, rising, 4 min ago"`.

- [ ] **Step 1:** Write tests:
  - a round-trip of the spec §3 example;
  - the encoded size of a full snapshot with 37 recent points < 2,048 bytes;
  - `decode` of `{"v":2}` → null and of garbage → null;
  - `rangedFraction(20.0) == 0f`, `(600.0) == 1f`, `(126.49) ≈ 0.5f`;
  - `nowShortText` ≤ 7 for 39–401 mg/dL in both units with every arrow.
- [ ] **Step 2–4:** Fail → implement → pass (`./gradlew :shared:testDebugUnitTest`).

### Task 10: Broadcast parsing, thinning, server-address rule

**Files:**
- Create: `android/shared/src/main/kotlin/org/glucorag/shared/{Broadcasts.kt,Thinning.kt,ServerAddress.kt}`
- Test: `BroadcastsTest.kt`, `ThinningTest.kt`, `ServerAddressTest.kt`

**Interfaces:**
- Produces:
  - `data class CgmReading(val t: Long, val mgdl: Double, val ratePerMin: Double?, val from: String)`.
  - `fun parseCgm(action: String?, extras: Map<String, Any?>, nowMs: Long): CgmReading?`: a pure function. The Android receiver converts the `Bundle` into a map.
    - **Juggluco:** `glucodata.Minute.mgdl` Int, `glucodata.Minute.Time` Long, `glucodata.Minute.Rate` Float (NaN → null); `from = "juggluco"`.
    - **xDrip+:** `com.eveningoutpost.dexdrip.Extras.BgEstimate` Double (missing → null result), `com.eveningoutpost.dexdrip.Extras.Time` Long, `com.eveningoutpost.dexdrip.Extras.BgSlope` Double × 60 000; `from = "xdrip"`.
    - Drop values outside 20–600 and times more than 120 000 ms after `nowMs`.
  - `class Thinner(var lastQueuedT: Long?) { fun shouldQueue(t: Long): Boolean }`, true when `lastQueuedT == null || t − lastQueuedT ≥ 270_000`.
  - `fun checkServerUrl(url: String): ServerUrlCheck`, with `sealed interface ServerUrlCheck { data class Ok(val base: String); data class Rejected(val reason: String) }`.
    - `https://` is always Ok.
    - `http://` is Ok only for 10/8, 172.16/12, 192.168/16, 169.254/16, 127/8, 100.64/10, `::1`, `fe80::/10`, `fd7a:115c:a1e0::/48`, `*.local`, `*.ts.net`.
    - Otherwise Rejected: "Use https:// for addresses outside your home network or Tailscale."
    - The trailing slash and path are stripped; a missing scheme → Rejected "Start the address with http:// or https://".

- [ ] **Step 1:** Write tests:
  - each format, including a missing BgEstimate, NaN rate, slope conversion (6.7e-6 → 0.402), `futureBeyondTwoMinutesDropped`, 19.9 / 600.1 dropped, and an unknown action → null;
  - thinning at 1-min input → one in 5 queued; exactly 270 s → queued;
  - the address rule for 172.15.0.1 (rejected), 172.16.0.1 (ok), 100.63.255.255 (rejected), 100.64.0.1 (ok), `mac.local`, `mac.tail1234.ts.net`, `http://example.com` (rejected), `https://example.com` (ok).
- [ ] **Step 2–4:** Fail → implement (parse IPv4/IPv6 literals with `java.net.InetAddress` only when the host is a literal; never resolve DNS) → pass.

### Task 11: Phone API client and session store

**Files:**
- Create: `android/phone/src/main/kotlin/org/glucorag/app/net/{GlucoApi.kt,Dto.kt}`, `.../data/SessionStore.kt`
- Test: `android/phone/src/test/kotlin/org/glucorag/app/net/GlucoApiTest.kt` (MockWebServer)

**Interfaces:**
- Consumes: `checkServerUrl`, the `Snapshot` types.
- Produces:
  - `class GlucoApi(base: String, client: OkHttpClient, token: () -> String?)` with suspend functions:
    - `health(): Health` (`GET /healthz`);
    - `signIn(email, password, device): TokenOut`;
    - `account(): AccountOut` (`GET /auth/me`);
    - `status(): StatusDto`;
    - `history(hours = 3): List<ReadingDto>`;
    - `alertsAfter(id: Long): List<AlertDto>`;
    - `uploadBatch(readings: List<CgmReading>): BatchResult`.
  - The bearer header is added when the token is present. Results are `ApiResult<T> = Ok(T) | Unauthorized | NeedsSetup | Http(code, message) | Network(cause)`, mapping 401 → `Unauthorized`, 409 → `NeedsSetup`, and an `IOException` → `Network`.
  - `class SessionStore(context)` (DataStore + app-private file): `server`, `token`, `email`, `lastAlertId`, `lastQueuedT`; `clear()`. `android:allowBackup="false"` and `dataExtractionRules` exclude everything.

- [ ] **Step 1:** Tests against MockWebServer:
  - each endpoint's path, method and JSON;
  - the bearer header is present after sign-in;
  - 401 / 409 / 413 / timeout mapping;
  - the batch body uses offset-aware ISO times in UTC (`2026-10-06T08:00:00Z`).
- [ ] **Step 2–4:** `./gradlew :phone:testDebugUnitTest`. Fail → implement → pass.

### Task 12: Phone pipeline — receiver, queue, sync, notifications, snapshot

**Files:**
- Create:
  - `android/phone/src/main/kotlin/org/glucorag/app/source/GlucoseReceiver.kt`
  - `.../data/{QueueDb.kt (Room: QueuedReading(t PK, mgdl, from)),LocalState.kt}`
  - `.../sync/{SyncEngine.kt,SyncWorker.kt,SnapshotPublisher.kt,AlertNotifier.kt}`
  - manifest entries
- Test: `android/phone/src/test/kotlin/org/glucorag/app/sync/SyncEngineTest.kt`

**Interfaces:**
- Consumes: Tasks 9–11.
- Produces:
  - `class SyncEngine(api: GlucoApi, queue: QueueDao, store: SessionStore, publish: suspend (Snapshot) -> Unit, notify: (AlertDto) -> Unit, clock: () -> Long)`, with `suspend fun run(): SyncOutcome`. It is pure Kotlin, so all logic is testable without Android.
    - Uploads oldest-first in batches of ≤ 500 until the queue is empty.
    - Deletes accepted, already-present and rejected readings.
    - Then calls `account()`, `status()`, `history(3)` and `alertsAfter(lastAlertId)`.
    - Notifies hypo/hyper alerts with severity high or medium whose id > `lastAlertId`, then persists the max id. If `lastAlertId` is unset (first sync after sign-in), it is set to the current max id **without notifying**, so past alerts never buzz. Test `firstSyncAfterSignInDoesNotNotifyHistory`.
    - Builds a `Snapshot` and publishes it:
      - `unit` from `account().unit`.
      - `now` from the latest local CGM reading if newer than the server's `last_reading`.
      - `recent` = `history(3)` thinned to ≥ 4.5 min spacing, ≤ 37 points.
      - `forecast` from `status().prediction` when `fresh`, with `low`/`high` = the alert band (`status.forecast`).
      - `risk` = the first flag after the website's `sortFlags` order (horizon ascending, hypo before hyper), with `at = t0 + horizon_min`.
      - `server.state`: `warming_up` when `status.status == "warming_up"`, otherwise `ok`.
    - On `Unauthorized`: set `server.state = signed_out`, publish, **keep the queue**.
    - On `Network`: set `unreachable`, publish a snapshot with `forecast = null`, return `Retry`.
  - `GlucoseReceiver`:
    - Exported, with intent-filter actions `glucodata.Minute` and `com.eveningoutpost.dexdrip.BgEstimate`.
    - In `goAsync`: `parseCgm` → update `LocalState.now` → if `Thinner.shouldQueue`, insert into Room and enqueue `SyncWorker`.
    - `SyncWorker` is unique work `"sync"`, `ExistingWorkPolicy.KEEP`, expedited with `RUN_AS_NON_EXPEDITED_WORK_REQUEST`, network required, exponential backoff 30 s; `getForegroundInfo()` uses the low-importance `sync` channel.
  - The manifest declares:
    - `<queries>` for `tk.glucodata` and `com.eveningoutpost.dexdrip`;
    - `uses-permission com.eveningoutpost.dexdrip.permissions.RECEIVE_BG_ESTIMATE`, `INTERNET`, `POST_NOTIFICATIONS`;
    - `network_security_config` with `cleartextTrafficPermitted="true"` in `base-config` (the code rule from Task 10 is the guard).
  - `SnapshotPublisher`: `PutDataMapRequest.create("/glucorag/snapshot")` with `bytes = SnapshotCodec.encode(s)`, `setUrgent()`, through `Wearable.getDataClient(context)`.
  - `AlertNotifier`: the `alerts` channel at `IMPORTANCE_HIGH`, created once; one notification per alert id (`notify(id.toInt(), …)`); never ongoing or local-only; copy from Global Constraints.

- [ ] **Step 1:** SyncEngine tests, each with a fake `QueueDao` and MockWebServer:
  - `drainsBacklogInBatchesOf500`: 1,200 queued → 3 batch requests, ascending times, queue empty after.
  - `rejectedReadingsLeaveQueue`.
  - `unauthorizedKeepsQueueAndSignsOut`.
  - `networkFailurePublishesUnreachableWithoutForecast`.
  - `alertNotifiedOnceAcrossRestart`: run twice with a new engine and the same store → 1 notification.
  - `lowSeverityAndDataGapNotNotified`.
  - `snapshotUsesAccountUnitAndNewerLocalReading`.
- [ ] **Step 2:** `./gradlew :phone:testDebugUnitTest`. Expected: FAIL.
- [ ] **Step 3:** Implement the engine, then the Android wrappers (receiver, worker, publisher, notifier).
- [ ] **Step 4:** Tests PASS, and `./gradlew :phone:lintDebug` reports no errors.

### Task 13: Phone UI

**Files:**
- Create: `android/phone/src/main/kotlin/org/glucorag/app/ui/{MainActivity.kt,ConnectScreen.kt,SourceScreen.kt,ChecklistScreen.kt,TodayScreen.kt,SettingsScreen.kt,GlucoseChart.kt,Theme.kt}`
- Modify: the phone manifest

**Interfaces:**
- Consumes: `GlucoApi`, `SessionStore`, `LocalState`, `statusOf`, `formatGlucose`, `zoneOf`, `trendOf`; `SyncWorker` enqueue.
- Produces: screens and copy exactly as in spec §3 Screens, plus:
  - **Navigation:** no token → Connect; token but no reading ever received → Source; then Checklist (skippable) → Today.
  - **Samsung button:** `Intent("com.samsung.android.sm.ACTION_OPEN_CHECKABLE_LISTACTIVITY").setPackage("com.samsung.android.lool").putExtra("activity_type", 2)`; on `ActivityNotFoundException`, fall back to `Settings.ACTION_APPLICATION_DETAILS_SETTINGS` for our package.
  - **Unrestricted battery check:** `PowerManager.isIgnoringBatteryOptimizations(packageName)` (display only; the button opens app details).
  - **Notification permission:** requested with `ActivityResultContracts.RequestPermission` on API 33+.
  - **Copy app ID** puts `org.glucorag.app` on the clipboard.
  - **Watch line:** `Wearable.getNodeClient(context).connectedNodes` → "Watch: up to date" when a node exists and the last publish succeeded; "No watch connected" otherwise.
  - **Chart:** Compose `Canvas` drawing zone tints (40–400 log scale, as on the website), the readings line, and the band polygon from `forecast.low/high`.
  - Colours from the website tokens (light and dark).
- [ ] **Step 1:** `./gradlew :phone:assembleDebug :phone:lintDebug`. Expected: success with no lint errors.
- [ ] **Step 2:** On the emulator (Task 15), every screen renders in light and dark (verified there).

### Task 14: Watch app — store, complications, tile, app

**Files:**
- Create:
  - `android/wear/src/main/kotlin/org/glucorag/wear/data/{SnapshotStore.kt,SnapshotListenerService.kt}`
  - `.../complication/{NowComplicationService.kt,NextHourComplicationService.kt,ComplicationPusher.kt}`
  - `.../tile/GlucoseTileService.kt`
  - `.../ui/{MainActivity.kt,HomeScreen.kt,AcknowledgeScreen.kt,WearChart.kt}`
  - `src/debug/kotlin/org/glucorag/wear/DebugSnapshotReceiver.kt`
  - `src/main/res/font/atkinson_hyperlegible_next.ttf` (copy from `web/node_modules/@fontsource-variable/atkinson-hyperlegible-next`, or the OFL release) and `assets/licenses/OFL.txt`
- Test: `android/wear/src/test/kotlin/org/glucorag/wear/complication/ComplicationPusherTest.kt`

**Interfaces:**
- Consumes: `SnapshotCodec`, `statusOf`, `nowShortText`, `nowLongText`, `rangedFraction`, `formatGlucose`.
- Produces:
  - `SnapshotStore`: DataStore holding the latest snapshot bytes; `flow: Flow<Snapshot?>`; `suspend fun save(bytes: ByteArray): Snapshot?` (decodes, persists only if `written` is newer).
  - `SnapshotListenerService : WearableListenerService`: `onDataChanged` for path `/glucorag/snapshot` → `save` → `ComplicationPusher.onSnapshot(old, new)` → tile update request.
  - `DebugSnapshotReceiver` (**debug source set only**): action `org.glucorag.wear.DEBUG_SNAPSHOT`, extra `json` (String) → `save(json.toByteArray())`, following the same path as the listener.
  - `class ComplicationPusher(clock, lastPush: Long?, lastKind: StatusKind?)` with `fun shouldPush(newKind: StatusKind, nowMs: Long): Boolean`: true if the kind changed or ≥ 300 000 ms since the last push. The tile limit is 60 000 ms.
  - **Complication services:** `SuspendingComplicationDataSourceService`; `UPDATE_PERIOD_SECONDS=0`.
    - **Now:** SHORT_TEXT (text `nowShortText`, title `TimeDifferenceComplicationText` with a count-up from `now.t`, minute unit), LONG_TEXT `nowLongText`, RANGED_VALUE (min 0, max 1, value `rangedFraction`, text `formatGlucose`).
    - **Next hour:** SHORT_TEXT (`shortText`/`shortTitle`) and LONG_TEXT (`sentence`).
    - Each has a preview data and tap action opening `MainActivity`.
  - **Tile:** ProtoLayout Material 3 primary layout: the sentence (max 2 lines), value + arrow, "at HH:mm", "In 60 min: low–high" (when a forecast is present), and the server line when the state isn't ok; click → `MainActivity`.
  - **App:**
    - `ScalingLazyColumn` with rotary input in the order of spec §4, the Atkinson font, black background, zone colours from the dark tokens.
    - Grey value plus "Old reading" when the reading is over 15 min old.
    - The acknowledgement gate, stored in DataStore.
    - Ambient: observe the ambient state (the `AmbientLifecycleObserver` from `androidx.wear:wear`), then render outline-only text with no chart animation and pause the 30 s refresh.
  - Manifest: `com.google.android.wearable.standalone=false`; `uses-feature android.hardware.type.watch`.

- [ ] **Step 1:** Write `ComplicationPusherTest`: same kind at 299 s → false; at 300 s → true; kind change at 10 s → true.
- [ ] **Step 2–3:** Fail → implement.
- [ ] **Step 4:** `./gradlew :wear:testDebugUnitTest :wear:lintDebug :wear:assembleDebug`. Expected: success.

### Task 15: Emulator verification and screenshots

**Files:**
- Create: `android/screenshots/` (PNG files), `android/scripts/snapshots/*.json` (one fixture per status row in Task 8)

- [ ] **Step 1:** Install the Wear image and create AVDs:
  - `sdkmanager "system-images;android-36;android-wear-signed;arm64-v8a"`.
  - Create AVDs `gr_wear_450` (`wearos_large_round`) and `gr_wear_396` (`wearos_small_round`), overriding `hw.lcd.width/height` and the density in `config.ini`.
- [ ] **Step 2:** Start the server with `GLUCORAG_HOST=0.0.0.0` on port 8851 and a fresh database, and create the account with a profile on the website. Then boot `PPulse_API35` and install the phone debug APK.
  - Sign in at `http://10.0.2.2:8851`.
  - Send 30 Juggluco broadcasts one minute apart (`--el` times stepped back in time) and 10 xDrip+ broadcasts using the commands in spec §6.2.
  - Expected: about 8 readings uploaded, visible in website History.
- [ ] **Step 3:** Exercise:
  - offline queueing (stop the server, send readings, restart, see them in History);
  - an alert notification (a rising series crossing 180 → exactly one notification per id);
  - revocation (Disconnect on the website → the phone shows "Signed out on the server. Sign in again.").
  - Screenshot every phone screen in light and dark.
- [ ] **Step 4:** Boot each Wear AVD and install the watch debug APK.
  - For each fixture: `adb shell am broadcast -a org.glucorag.wear.DEBUG_SNAPSHOT -p org.glucorag.app --es json "$(cat fixture.json)"`.
  - Screenshot the app (top and scrolled), the tile, and both complications on a face (the emulator's default face with complication slots), plus the ambient state (`adb shell input keyevent KEYCODE_SLEEP` with always-on enabled).
  - Confirm on the emulator that the complication age advances without a new snapshot (two screenshots 2 min apart).
- [ ] **Step 5:** Record any failure, fix it in the owning task, and repeat.

### Task 16: Documentation and final checks

**Files:**
- Create: `android/README.md`
- Modify: `README.md`, `web/PRODUCT.md` (Who uses it / Constraints: watch and phone), `docs/RISK_REGISTER.md` (R13–R18 from spec §8), `CHANGELOG.md` (0.5.0)

- [ ] **Step 1:** `android/README.md` covers:
  - build (JDK 17, Gradle wrapper, the final Android check command);
  - running the server on the LAN (`GLUCORAG_HOST=0.0.0.0`, the macOS firewall), with Tailscale and `tailscale serve` as the option away from home;
  - phone setup, i.e. the Juggluco/xDrip+ settings paths from spec §1 and the checklist;
  - watch install on the Galaxy Watch4 Classic (spec §6.4 steps, including turning off automatic Wi-Fi);
  - adding the complications;
  - known limits (Data Layer cloud routing, Samsung face slots, time-difference rendering unverified on Samsung faces, no on-phone forecast).
- [ ] **Step 2:** Add a root README section "Phone and watch" pointing to it; the CHANGELOG lists the server bug fixes (grid alignment, trend) separately.
- [ ] **Step 3:** Run the full final checks from Global Constraints. Expected: all green.
- [ ] **Step 4:** Stop the emulators and the server; delete `/tmp` databases.
