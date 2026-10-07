"""SQLite store for profiles, readings, predictions and alerts (architecture L1).

Event timestamps (reading time, forecast origin ``t0``, ``t_raised``) are naive local
wall-clock times stored in a fixed-width ISO format so lexical order equals time order.
``created_at`` / ``received_at`` are UTC audit times. Every prediction row pins the model
version that produced it.
"""

import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from glucorag.core.schemas import Alert, PatientProfile, Prediction

_TS = "%Y-%m-%dT%H:%M:%S.%f"

SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
    patient_id TEXT PRIMARY KEY,
    profile_json TEXT NOT NULL,
    hypo_quantile REAL,
    hyper_quantile REAL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS readings (
    patient_id TEXT NOT NULL REFERENCES profiles(patient_id),
    timestamp TEXT NOT NULL,
    glucose_mg_dl REAL NOT NULL,
    raw_mg_dl REAL NOT NULL,
    flag TEXT NOT NULL,
    received_at TEXT NOT NULL,
    PRIMARY KEY (patient_id, timestamp)
);
CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id TEXT NOT NULL REFERENCES profiles(patient_id),
    t0 TEXT NOT NULL,
    model_version TEXT NOT NULL,
    horizons_json TEXT NOT NULL,
    quantiles_json TEXT NOT NULL,
    values_json TEXT NOT NULL,
    latency_ms REAL NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_predictions_patient_t0 ON predictions(patient_id, t0);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id TEXT NOT NULL REFERENCES profiles(patient_id),
    type TEXT NOT NULL,
    horizon_min INTEGER,
    severity TEXT,
    t_raised TEXT NOT NULL,
    t0 TEXT,
    model_version TEXT,
    details_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_alerts_patient_t ON alerts(patient_id, t_raised);
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('person', 'clinician')),
    patient_id TEXT NOT NULL UNIQUE,
    unit TEXT NOT NULL DEFAULT 'mg/dL' CHECK (unit IN ('mg/dL', 'mmol/L')),
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_sessions_user ON sessions(user_id);
"""

Role = Literal["person", "clinician"]
Unit = Literal["mg/dL", "mmol/L"]


class StoredUser(BaseModel):
    id: int
    email: str
    role: Role
    patient_id: str
    unit: Unit
    created_at: datetime


class UserGoneError(LookupError):
    """The account no longer exists (deleted between lookup and use)."""


class StoredProfile(BaseModel):
    profile: PatientProfile
    hypo_quantile: float | None = None
    hyper_quantile: float | None = None
    updated_at: datetime


class StoredReading(BaseModel):
    patient_id: str
    timestamp: datetime
    glucose_mg_dl: float
    raw_mg_dl: float
    flag: str


class StoredPrediction(Prediction):
    id: int
    latency_ms: float
    created_at: datetime


class StoredAlert(Alert):
    id: int
    t0: datetime | None = None
    model_version: str | None = None
    details: dict[str, Any] = {}


def _ts(t: datetime) -> str:
    if t.tzinfo is not None:
        t = t.astimezone().replace(tzinfo=None)
    return t.strftime(_TS)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


class Storage:
    """Thread-safe wrapper over one SQLite connection (``":memory:"`` for tests)."""

    def __init__(self, path: str | Path) -> None:
        path = str(path)
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            if path != ":memory:":
                self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.executescript(SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Group writes atomically (re-entrant within one thread)."""
        with self._lock:
            if self._conn.in_transaction:
                yield
                return
            self._conn.execute("BEGIN")
            try:
                yield
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            self._conn.execute("COMMIT")

    def _rows(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def _exec(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        with self._lock:
            cur = self._conn.execute(sql, params)
            return int(cur.lastrowid or 0)

    # profiles ---------------------------------------------------------------------------
    def upsert_profile(
        self, profile: PatientProfile, hypo_quantile: float | None, hyper_quantile: float | None
    ) -> None:
        self._exec(
            "INSERT INTO profiles VALUES (?,?,?,?,?) ON CONFLICT(patient_id) DO UPDATE SET "
            "profile_json=excluded.profile_json, hypo_quantile=excluded.hypo_quantile, "
            "hyper_quantile=excluded.hyper_quantile, updated_at=excluded.updated_at",
            (profile.patient_id, profile.model_dump_json(), hypo_quantile, hyper_quantile,
             _utc_now()),
        )

    def profiles(self) -> list[StoredProfile]:
        return [
            self._profile(r) for r in self._rows("SELECT * FROM profiles ORDER BY patient_id")
        ]

    def profile(self, patient_id: str) -> StoredProfile | None:
        rows = self._rows("SELECT * FROM profiles WHERE patient_id=?", (patient_id,))
        return self._profile(rows[0]) if rows else None

    @staticmethod
    def _profile(r: sqlite3.Row) -> StoredProfile:
        return StoredProfile(
            profile=PatientProfile.model_validate_json(r["profile_json"]),
            hypo_quantile=r["hypo_quantile"],
            hyper_quantile=r["hyper_quantile"],
            updated_at=datetime.fromisoformat(r["updated_at"]),
        )

    # readings ---------------------------------------------------------------------------
    def insert_reading(
        self, patient_id: str, timestamp: datetime, glucose: float, raw: float, flag: str
    ) -> None:
        self._exec(
            "INSERT INTO readings VALUES (?,?,?,?,?,?)",
            (patient_id, _ts(timestamp), glucose, raw, flag, _utc_now()),
        )

    def readings(
        self,
        patient_id: str,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int | None = None,
    ) -> list[StoredReading]:
        """Readings in ``[since, until]`` ascending; with ``limit``, the most recent ones."""
        where, params = self._range("patient_id=?", [patient_id], "timestamp", since, until)
        sql = f"SELECT * FROM readings WHERE {where} ORDER BY timestamp DESC"
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        rows = self._rows(sql, tuple(params))
        return [
            StoredReading(
                patient_id=r["patient_id"],
                timestamp=datetime.fromisoformat(r["timestamp"]),
                glucose_mg_dl=r["glucose_mg_dl"],
                raw_mg_dl=r["raw_mg_dl"],
                flag=r["flag"],
            )
            for r in reversed(rows)
        ]

    def reading_bounds(self) -> dict[str, tuple[datetime, datetime]]:
        """``patient_id -> (first, last)`` reading time for every patient with readings."""
        rows = self._rows(
            "SELECT patient_id, MIN(timestamp) AS first, MAX(timestamp) AS last "
            "FROM readings GROUP BY patient_id"
        )
        return {
            r["patient_id"]: (
                datetime.fromisoformat(r["first"]), datetime.fromisoformat(r["last"])
            )
            for r in rows
        }

    # predictions ------------------------------------------------------------------------
    def insert_prediction(self, prediction: Prediction, latency_ms: float) -> int:
        return self._exec(
            "INSERT INTO predictions (patient_id, t0, model_version, horizons_json, "
            "quantiles_json, values_json, latency_ms, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (
                prediction.patient_id, _ts(prediction.t0), prediction.model_version,
                json.dumps(prediction.horizons), json.dumps(prediction.quantiles),
                json.dumps(prediction.values), latency_ms, _utc_now(),
            ),
        )

    def predictions(
        self,
        patient_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int | None = None,
        latest_first: bool = False,
    ) -> list[StoredPrediction]:
        base, params = ("patient_id=?", [patient_id]) if patient_id else ("1=1", [])
        where, params = self._range(base, params, "t0", since, until)
        order = "DESC" if latest_first else "ASC"
        sql = f"SELECT * FROM predictions WHERE {where} ORDER BY t0 {order}, id {order}"
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        return [
            StoredPrediction(
                id=r["id"],
                patient_id=r["patient_id"],
                t0=datetime.fromisoformat(r["t0"]),
                horizons=json.loads(r["horizons_json"]),
                quantiles=json.loads(r["quantiles_json"]),
                values=json.loads(r["values_json"]),
                model_version=r["model_version"],
                latency_ms=r["latency_ms"],
                created_at=datetime.fromisoformat(r["created_at"]),
            )
            for r in self._rows(sql, tuple(params))
        ]

    def latest_prediction(self, patient_id: str) -> StoredPrediction | None:
        found = self.predictions(patient_id, limit=1, latest_first=True)
        return found[0] if found else None

    def recent_latencies_ms(self, limit: int = 1000) -> list[float]:
        """Inference latency of the most recent ``limit`` stored forecasts."""
        rows = self._rows(
            "SELECT latency_ms FROM predictions ORDER BY id DESC LIMIT ?", (int(limit),)
        )
        return [float(r["latency_ms"]) for r in rows]

    def table_counts(self) -> dict[str, int]:
        return {
            t: int(self._rows(f"SELECT COUNT(*) AS n FROM {t}")[0]["n"])
            for t in ("profiles", "readings", "predictions", "alerts")
        }

    # alerts -----------------------------------------------------------------------------
    def insert_alert(
        self,
        alert: Alert,
        t0: datetime | None = None,
        model_version: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> StoredAlert:
        details = details or {}
        row_id = self._exec(
            "INSERT INTO alerts (patient_id, type, horizon_min, severity, t_raised, t0, "
            "model_version, details_json, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                alert.patient_id, alert.type, alert.horizon_min, alert.severity,
                _ts(alert.t_raised), _ts(t0) if t0 else None, model_version,
                json.dumps(details), _utc_now(),
            ),
        )
        return StoredAlert(
            **alert.model_dump(), id=row_id, t0=t0, model_version=model_version, details=details
        )

    def alerts(
        self,
        patient_id: str | None = None,
        alert_type: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int | None = None,
    ) -> list[StoredAlert]:
        """Alerts ascending by ``t_raised``; with ``limit``, the most recent ones."""
        clauses, params = ["1=1"], []
        if patient_id:
            clauses.append("patient_id=?")
            params.append(patient_id)
        if alert_type:
            clauses.append("type=?")
            params.append(alert_type)
        where, params = self._range(" AND ".join(clauses), params, "t_raised", since, until)
        sql = f"SELECT * FROM alerts WHERE {where} ORDER BY t_raised DESC, id DESC"
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        rows = self._rows(sql, tuple(params))
        return [
            StoredAlert(
                id=r["id"],
                patient_id=r["patient_id"],
                type=r["type"],
                horizon_min=r["horizon_min"],
                severity=r["severity"],
                t_raised=datetime.fromisoformat(r["t_raised"]),
                t0=datetime.fromisoformat(r["t0"]) if r["t0"] else None,
                model_version=r["model_version"],
                details=json.loads(r["details_json"]),
            )
            for r in reversed(rows)
        ]

    @staticmethod
    def _range(
        where: str,
        params: list[Any],
        column: str,
        since: datetime | None,
        until: datetime | None,
    ) -> tuple[str, list[Any]]:
        if since is not None:
            where += f" AND {column} >= ?"
            params = [*params, _ts(since)]
        if until is not None:
            where += f" AND {column} <= ?"
            params = [*params, _ts(until)]
        return where, params

    # accounts ---------------------------------------------------------------------------
    def create_user(
        self, email: str, password_hash: str, role: Role, patient_id: str
    ) -> StoredUser:
        """Raises ``ValueError`` when the email (case-insensitive) is already registered."""
        try:
            user_id = self._exec(
                "INSERT INTO users (email, password_hash, role, patient_id, created_at) "
                "VALUES (?,?,?,?,?)",
                (email, password_hash, role, patient_id, _utc_now()),
            )
        except sqlite3.IntegrityError as e:
            raise ValueError("email already registered") from e
        user = self.user_by_id(user_id)
        assert user is not None
        return user

    def user_by_id(self, user_id: int) -> StoredUser | None:
        rows = self._rows("SELECT * FROM users WHERE id=?", (user_id,))
        return self._user(rows[0]) if rows else None

    def user_credentials(self, email: str) -> tuple[StoredUser, str] | None:
        """User plus stored password hash, looked up case-insensitively."""
        rows = self._rows("SELECT * FROM users WHERE email=?", (email,))
        return (self._user(rows[0]), rows[0]["password_hash"]) if rows else None

    def users(self) -> list[StoredUser]:
        return [self._user(r) for r in self._rows("SELECT * FROM users ORDER BY id")]

    def set_password_hash(self, user_id: int, password_hash: str) -> None:
        self._exec("UPDATE users SET password_hash=? WHERE id=?", (password_hash, user_id))

    def set_unit(self, user_id: int, unit: Unit) -> None:
        self._exec("UPDATE users SET unit=? WHERE id=?", (unit, user_id))

    def delete_user(self, user_id: int) -> None:
        with self.transaction():
            self._exec("DELETE FROM sessions WHERE user_id=?", (user_id,))
            self._exec("DELETE FROM users WHERE id=?", (user_id,))

    @staticmethod
    def _user(r: sqlite3.Row) -> StoredUser:
        return StoredUser(
            id=r["id"], email=r["email"], role=r["role"], patient_id=r["patient_id"],
            unit=r["unit"], created_at=datetime.fromisoformat(r["created_at"]),
        )

    # sessions (only a SHA-256 of the bearer token is stored) -----------------------------
    def create_session(self, token_hash: str, user_id: int, expires_at: datetime) -> None:
        """Raises ``UserGoneError`` if the account was deleted concurrently (e.g. while a
        sign-in was checking its password)."""
        try:
            self._exec(
                "INSERT INTO sessions VALUES (?,?,?,?)",
                (token_hash, user_id, _utc_now(), expires_at.astimezone(UTC).isoformat()),
            )
        except sqlite3.IntegrityError as e:
            raise UserGoneError(user_id) from e

    def session_user(self, token_hash: str, now: datetime) -> StoredUser | None:
        """User for an unexpired session; expired sessions are deleted on sight."""
        rows = self._rows(
            "SELECT u.*, s.expires_at AS s_exp FROM sessions s JOIN users u ON u.id=s.user_id "
            "WHERE s.token_hash=?",
            (token_hash,),
        )
        if not rows:
            return None
        if datetime.fromisoformat(rows[0]["s_exp"]) <= now.astimezone(UTC):
            self.delete_session(token_hash)
            return None
        return self._user(rows[0])

    def delete_session(self, token_hash: str) -> None:
        self._exec("DELETE FROM sessions WHERE token_hash=?", (token_hash,))

    def delete_user_sessions(self, user_id: int, keep: str | None = None) -> None:
        self._exec(
            "DELETE FROM sessions WHERE user_id=? AND token_hash IS NOT ?", (user_id, keep)
        )

    # patient data removal ---------------------------------------------------------------
    def delete_patient_data(self, patient_id: str, include_profile: bool) -> None:
        """Remove readings, predictions and alerts (and optionally the profile) atomically."""
        with self.transaction():
            for table in ("readings", "predictions", "alerts"):
                self._exec(f"DELETE FROM {table} WHERE patient_id=?", (patient_id,))
            if include_profile:
                self._exec("DELETE FROM profiles WHERE patient_id=?", (patient_id,))

    def delete_derived_since(self, patient_id: str, since: datetime) -> None:
        """Drop forecasts (t0 >= since) and alerts (t_raised >= since) so they can be replayed
        after older readings were merged in. Readings are kept."""
        with self.transaction():
            self._exec(
                "DELETE FROM predictions WHERE patient_id=? AND t0 >= ?", (patient_id, _ts(since))
            )
            self._exec(
                "DELETE FROM alerts WHERE patient_id=? AND t_raised >= ?",
                (patient_id, _ts(since)),
            )

    def reading_summary(self, patient_id: str) -> tuple[int, datetime | None, datetime | None]:
        """``(count, first, last)`` reading time for one patient."""
        r = self._rows(
            "SELECT COUNT(*) AS n, MIN(timestamp) AS first, MAX(timestamp) AS last "
            "FROM readings WHERE patient_id=?",
            (patient_id,),
        )[0]
        first = datetime.fromisoformat(r["first"]) if r["first"] else None
        last = datetime.fromisoformat(r["last"]) if r["last"] else None
        return int(r["n"]), first, last
