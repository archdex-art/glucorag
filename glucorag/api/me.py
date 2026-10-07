"""A signed-in person's own data: profile, readings, import, forecast, alerts, export, deletion,
the phones signed in with a device token, and the pairing codes that sign a phone in.

Times are stored as naive server-local wall-clock times. Every response here carries
them as offset-aware ISO strings, so a browser in any time zone shows the user's own
local time. Request timestamps may be offset-aware (preferred) or naive server-local.
"""

import csv
import io
import ipaddress
import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import segno
from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from glucorag.api.deps import SESSION_COOKIE, CurrentPrincipal, CurrentUser, Service
from glucorag.core.accounts import (
    format_pairing_code,
    new_pairing_code,
    token_hash,
    verify_password,
)
from glucorag.core.schemas import PatientProfile
from glucorag.core.storage import DeviceSession, UserGoneError
from glucorag.ingest.importers import (
    MAX_BYTES,
    MMOL_TO_MG_DL,
    ImportFormatError,
    parse_cgm_csv,
)
from glucorag.ingest.validate import to_local_naive
from glucorag.risk.detectors import AlertPolicy

router = APIRouter(prefix="/me")

SAMPLE_CSV = Path(__file__).resolve().parents[1] / "data" / "sample" / "sample_cgm.csv"

Sensitivity = Literal["standard", "cautious", "very_cautious"]
# Alert sensitivity is the forecast quantile each alert reads: a wider band warns earlier
# and more often. Values must be quantiles the model produces.
SENSITIVITY: dict[Sensitivity, tuple[float, float]] = {
    "standard": (0.25, 0.75),
    "cautious": (0.10, 0.90),
    "very_cautious": (0.02, 0.98),
}
Unit = Literal["mg/dL", "mmol/L"]


class ProfileIn(BaseModel):
    age: int = Field(ge=1, le=120)
    gender: Literal["F", "M"]
    bmi: float = Field(ge=10, le=80)
    diabetes_type: Literal["T1D", "T2D"]
    sensitivity: Sensitivity = "standard"
    unit: Unit = "mg/dL"


class ReadingIn(BaseModel):
    timestamp: datetime
    glucose: float = Field(gt=0)
    unit: Unit = "mg/dL"


class BatchReading(BaseModel):
    timestamp: datetime
    glucose_mg_dl: float = Field(gt=0)

    @field_validator("timestamp")
    @classmethod
    def _offset_required(cls, t: datetime) -> datetime:
        if t.tzinfo is None:
            raise ValueError("timestamp needs a UTC offset")
        return t


class BatchIn(BaseModel):
    readings: list[BatchReading]


# Plausible CGM range; values outside it are sensor or transfer errors, not clipped.
BATCH_MIN_MG_DL, BATCH_MAX_MG_DL = 20.0, 600.0


class DeleteAccountIn(BaseModel):
    password: str = Field(max_length=256)


def _local(value: Any) -> Any:
    """Recursively render naive server-local datetimes as offset-aware ISO strings."""
    if isinstance(value, datetime):
        if value.year < 1900:  # an unset data clock; there is no meaningful offset
            return None
        aware = value if value.tzinfo else value.astimezone()
        return aware.isoformat()
    if isinstance(value, dict):
        return {k: _local(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_local(v) for v in value]
    return value


def local_json(payload: Any, status_code: int = 200) -> JSONResponse:
    if isinstance(payload, BaseModel):
        payload = payload.model_dump(mode="python")
    return JSONResponse(_local(payload), status_code=status_code)


def _sensitivity(hypo_q: float, hyper_q: float) -> Sensitivity | None:
    for name, qs in SENSITIVITY.items():
        if abs(qs[0] - hypo_q) < 1e-9 and abs(qs[1] - hyper_q) < 1e-9:
            return name
    return None


def _model_facts(service: Any) -> dict[str, Any]:
    meta = service.engine.meta
    return {
        "version": meta.version,
        "interval_min": meta.interval_min,
        "lookback_min": meta.lookback_min,
        "horizon_min": meta.horizon_min,
        "data_gap_min": service.config.data_gap_min,
        "hypo_mg_dl": service.config.risk.hypo_mg_dl,
        "hyper_mg_dl": service.config.risk.hyper_mg_dl,
    }


def _require_profile(user: CurrentUser, service: Service) -> None:
    if not service.is_registered(user.patient_id):
        raise HTTPException(409, "Set up your profile first.")


@router.get("")
def me(user: CurrentUser, service: Service) -> JSONResponse:
    stored = service.storage.profile(user.patient_id)
    profile: dict[str, Any] | None = None
    if stored is not None:
        hypo_q, hyper_q = service.effective_quantiles(user.patient_id)
        p = stored.profile
        profile = {
            "age": p.age, "gender": p.gender, "bmi": p.bmi, "diabetes_type": p.diabetes_type,
            "sensitivity": _sensitivity(hypo_q, hyper_q),
            "hypo_quantile": hypo_q, "hyper_quantile": hyper_q,
        }
    count, first, last = service.storage.reading_summary(user.patient_id)
    return local_json({
        "email": user.email,
        "role": user.role,
        "unit": user.unit,
        "profile": profile,
        "readings": {"count": count, "first": first, "last": last},
        "model": _model_facts(service),
    })


@router.put("/profile")
def put_profile(body: ProfileIn, user: CurrentUser, service: Service) -> JSONResponse:
    hypo_q, hyper_q = SENSITIVITY[body.sensitivity]
    profile = PatientProfile(
        patient_id=user.patient_id, age=body.age, gender=body.gender, bmi=body.bmi,
        diabetes_type=body.diabetes_type,
    )
    try:
        service.register_profile(profile, AlertPolicy(hypo_q, hyper_q))
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    service.storage.set_unit(user.id, body.unit)
    return me(service.storage.user_by_id(user.id) or user, service)


@router.get("/status")
def status(user: CurrentUser, service: Service) -> JSONResponse:
    """Current state: value, trend, freshness, risk flags and the latest forecast in full."""
    _require_profile(user, service)
    row = service.patient_status(user.patient_id)
    prediction = service.storage.latest_prediction(user.patient_id)
    hypo_q, hyper_q = service.effective_quantiles(user.patient_id)
    return local_json({
        "status": row.model_dump(mode="python"),
        "prediction": prediction.model_dump(mode="python") if prediction else None,
        "fresh": row.forecast is not None,
        "hypo_quantile": hypo_q,
        "hyper_quantile": hyper_q,
        "now": service.clock.now(),
        "model": _model_facts(service),
    })


@router.get("/history")
def history(
    user: CurrentUser,
    service: Service,
    hours: Annotated[int, Query(gt=0, le=24 * 90)] = 24,
) -> JSONResponse:
    """Readings in the ``hours`` before the latest one (so old imports still show)."""
    _require_profile(user, service)
    _, _, last = service.storage.reading_summary(user.patient_id)
    if last is None:
        return local_json({"readings": [], "since": None, "until": None})
    since = last - timedelta(hours=hours)
    readings = service.storage.readings(user.patient_id, since=since)
    return local_json({
        "readings": [{"timestamp": r.timestamp, "glucose_mg_dl": r.glucose_mg_dl,
                      "flag": r.flag} for r in readings],
        "since": since,
        "until": last,
    })


@router.get("/alerts")
def alerts(
    user: CurrentUser,
    service: Service,
    limit: Annotated[int, Query(gt=0, le=2000)] = 200,
    after_id: Annotated[int | None, Query(ge=0)] = None,
) -> JSONResponse:
    """Newest first; with ``after_id``, only newer alerts, oldest first (for polling)."""
    _require_profile(user, service)
    rows = service.storage.alerts(user.patient_id, limit=limit, after_id=after_id)
    if after_id is None:
        rows.reverse()
    return local_json([a.model_dump(mode="python") for a in rows])


@router.post("/readings")
def add_reading(body: ReadingIn, user: CurrentUser, service: Service) -> JSONResponse:
    _require_profile(user, service)
    mg = body.glucose * MMOL_TO_MG_DL if body.unit == "mmol/L" else body.glucose
    result = service.ingest(user.patient_id, body.timestamp, round(mg, 1))
    if result.status == "rejected":
        return local_json(
            {"reason": result.reason, "detail": result.detail}, status_code=422
        )
    return local_json(result)


@router.post("/readings/batch")
def add_readings_batch(
    body: BatchIn, request: Request, user: CurrentUser, service: Service
) -> JSONResponse:
    """Readings uploaded by a phone in any order; re-sent ones count as ``already_present``."""
    _require_profile(user, service)
    max_batch = request.app.state.max_batch
    if len(body.readings) > max_batch:
        raise HTTPException(413, f"Batch larger than {max_batch} readings")
    # Replay mode (data clock) has no "future": readings define time there.
    now = service.clock.now() if service.clock.checks_future else None
    rejected: list[dict[str, Any]] = []
    survivors: list[tuple[datetime, float]] = []
    for r in body.readings:
        t = to_local_naive(r.timestamp)
        if not BATCH_MIN_MG_DL <= r.glucose_mg_dl <= BATCH_MAX_MG_DL:
            rejected.append({"timestamp": t, "reason": "out_of_range"})
        elif now is not None and t > now + service.config.max_future_skew:
            rejected.append({"timestamp": t, "reason": "future"})
        else:
            survivors.append((t, r.glucose_mg_dl))
    result = service.backfill(user.patient_id, survivors)
    return local_json({
        "accepted": result.added,
        "already_present": result.outcomes.get("already_present", 0),
        "rejected": rejected,
    })


@router.post("/import")
async def import_csv(
    request: Request,
    user: CurrentUser,
    service: Service,
    tz: str = "UTC",
    unit: Literal["auto", "mg/dL", "mmol/L"] = "auto",
    dates: Literal["auto", "dmy", "mdy"] = "auto",
) -> JSONResponse:
    """Body: the export file as ``text/csv``. Times without an offset are read in ``tz``.
    ``dates`` fixes the order of numeric dates such as 06-10-2026 (day or month first)."""
    _require_profile(user, service)
    try:
        zone = ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError) as e:
        raise HTTPException(422, f"Unknown time zone {tz!r}") from e
    raw = await request.body()
    if len(raw) > MAX_BYTES:
        raise HTTPException(413, f"File larger than {MAX_BYTES // (1024 * 1024)} MB")
    try:
        parsed = parse_cgm_csv(
            raw.decode("utf-8-sig", errors="replace"), zone,
            None if unit == "auto" else unit, None if dates == "auto" else dates,
        )
    except ImportFormatError as e:
        raise HTTPException(422, str(e)) from e

    readings = [(to_local_naive(t), v) for t, v in parsed.readings]
    newest = readings[-1][0]
    keep_after = newest - timedelta(days=request.app.state.import_max_days)
    in_window = [(t, v) for t, v in readings if t >= keep_after]
    result = service.backfill(user.patient_id, in_window)
    outcomes = dict(result.outcomes)
    already_present = outcomes.pop("already_present", 0)
    return local_json({
        "format": parsed.format,
        "unit": parsed.unit,
        "date_order": parsed.date_order,
        "date_ambiguous": parsed.date_ambiguous,
        "rows_read": len(parsed.readings) + parsed.skipped_rows,
        "unusable_rows": parsed.skipped_rows,
        "older_than_window": len(readings) - len(in_window),
        "already_present": already_present,
        "accepted": result.added,
        "outcomes": outcomes,
        "first": readings[0][0],
        "last": newest,
        "window_days": request.app.state.import_max_days,
    })


@router.post("/sample")
def load_sample(user: CurrentUser, service: Service) -> JSONResponse:
    """Load a bundled 48-h CGM trace, shifted so its last reading is now."""
    _require_profile(user, service)
    count, _, _ = service.storage.reading_summary(user.patient_id)
    if count:
        raise HTTPException(
            409, "Sample data can only be loaded into an account without readings. "
            "Delete your readings first."
        )
    end = datetime.now().replace(second=0, microsecond=0)
    with SAMPLE_CSV.open() as f:
        rows = list(csv.DictReader(f))
    readings = [
        (end - timedelta(minutes=int(r["minutes_before_end"])), float(r["glucose_mg_dl"]))
        for r in rows
    ]
    result = service.backfill(user.patient_id, readings)
    return local_json({
        "loaded": result.added, "outcomes": result.outcomes,
        "first": readings[0][0], "last": end,
    })


@router.get("/export")
def export_csv(user: CurrentUser, service: Service) -> Response:
    """All of the user's readings, with offset-aware timestamps."""
    readings = service.storage.readings(user.patient_id)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["timestamp", "glucose_mg_dl", "flag"])
    for r in readings:
        w.writerow([r.timestamp.astimezone().isoformat(), f"{r.glucose_mg_dl:.1f}", r.flag])
    # Name the file by the date of the newest reading, as the reader's data shows it.
    stamp = (readings[-1].timestamp if readings else datetime.now()).strftime("%Y%m%d")
    return Response(
        buf.getvalue(), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="glucorag-readings-{stamp}.csv"'},
    )


@router.delete("/readings", status_code=204)
def delete_readings(user: CurrentUser, service: Service) -> None:
    """Delete readings, forecasts and alerts; keep the account and profile."""
    service.forget_patient(user.patient_id, include_profile=False)


@router.delete("", status_code=204)
def delete_account(
    body: DeleteAccountIn, user: CurrentUser, service: Service, response: Response
) -> None:
    found = service.storage.user_credentials(user.email)
    if found is None or not verify_password(body.password, found[1]):
        raise HTTPException(403, "Password is incorrect.")
    service.forget_patient(user.patient_id, include_profile=True)
    service.storage.delete_user(user.id)
    response.delete_cookie(SESSION_COOKIE, path="/", samesite="strict", httponly=True)


@router.get("/devices")
def devices(user: CurrentUser, service: Service) -> list[DeviceSession]:
    """Phones signed in with a device token (browser sessions are not listed)."""
    return service.storage.device_sessions(user.id)


@router.delete("/devices/{session_id}", status_code=204)
def delete_device(session_id: int, user: CurrentUser, service: Service) -> None:
    """Sign one phone out; 404 for ids that aren't the caller's, without saying whose."""
    if not service.storage.delete_device_session(user.id, session_id):
        raise HTTPException(404, "No such device.")


PAIRING_MINUTES = 10


class PairingOut(BaseModel):
    code: str
    expires_at: datetime
    server_url: str
    server_url_guessed: bool
    uri: str
    qr_svg: str


def _is_loopback(host: str) -> bool:
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def _lan_ipv4() -> str | None:
    """This host's primary LAN IPv4: the source address the OS would use for an outside
    route. Connecting a UDP socket only picks the route; no packet is sent."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))  # TEST-NET-1, never contacted
            ip: str = s.getsockname()[0]
    except OSError:
        return None
    addr = ipaddress.ip_address(ip)
    return None if addr.is_loopback or addr.is_unspecified else ip


def _server_url(request: Request) -> tuple[str, bool]:
    """``(address a phone should use, whether it was guessed)``. A browser on the server
    itself (``localhost``) is no use to a phone, so that case swaps in the LAN address."""
    public: str | None = request.app.state.public_url
    if public:
        return public, False
    base = str(request.base_url).rstrip("/")
    if not _is_loopback(request.url.hostname or ""):
        return base, False
    ip = _lan_ipv4()
    if ip is None:
        return base, True
    port = request.url.port
    return f"{request.url.scheme}://{ip}{f':{port}' if port else ''}", True


def _qr_svg(data: str) -> str:
    """Black-on-white QR (with its quiet zone) as a standalone SVG document."""
    out = io.BytesIO()
    segno.make(data, error="m").save(
        out, kind="svg", xmldecl=False, svgns=True, nl=False, scale=4, dark="#000",
        light="#fff", svgclass=None, lineclass=None,
    )
    return out.getvalue().decode()


@router.post("/pairing", status_code=201)
def create_pairing(
    request: Request, principal: CurrentPrincipal, user: CurrentUser, service: Service
) -> PairingOut:
    """A single-use code (and QR) that signs a phone into this account for 10 minutes.
    A new code replaces the previous unused one."""
    if user.role != "person":
        raise HTTPException(403, "Device sign-in is for personal accounts.")
    if principal.bearer:  # a device token must not mint further devices
        raise HTTPException(403, "Make pairing codes on the website.")
    code = new_pairing_code()
    now = datetime.now(UTC)
    expires = now + timedelta(minutes=PAIRING_MINUTES)
    try:
        service.storage.create_pairing_code(token_hash(code), user.id, now, expires)
    except UserGoneError as e:
        raise HTTPException(401, "Sign in to continue") from e
    server_url, guessed = _server_url(request)
    uri = f"glucorag://pair?server={quote(server_url, safe='')}&code={code}"
    return PairingOut(
        code=format_pairing_code(code), expires_at=expires, server_url=server_url,
        server_url_guessed=guessed, uri=uri, qr_svg=_qr_svg(uri),
    )
