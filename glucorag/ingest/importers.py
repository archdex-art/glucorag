"""Parse CGM exports into time-ordered ``(aware timestamp, mg/dL)`` readings.

Supported layouts:

* **LibreView** (FreeStyle Libre): a metadata line, then a header containing
  ``Device Timestamp``, ``Record Type`` and ``Historic Glucose mg/dL`` (or ``mmol/L``).
  Historic rows (record type 0, every 15 min) are used; scan rows only when no historic
  rows exist.
* **Dexcom Clarity**: header with ``Timestamp (YYYY-MM-DDThh:mm:ss)``, ``Event Type`` and
  ``Glucose Value (mg/dL)``; ``EGV`` rows; the sensor's ``Low`` / ``High`` become values just
  outside the 40-400 mg/dL range so ingest clips and flags them.
* **Generic**: any header with a time column and a glucose column.

Exports store naive local device times; they are interpreted in the uploader's IANA time
zone. Day/month order is resolved, unless the caller fixes it, by:

1. the order that parses the most rows;
2. the order whose readings span the shortest period (a contiguous recording read with
   day and month swapped scatters across months);
3. when that still ties (e.g. every row on one day), the order whose newest reading is
   not in the future and is closest to now: an export someone just made ends near today.

``ParsedImport.date_order`` says which order was used and ``date_ambiguous`` whether
another order would also have read the whole file, so callers can tell the user.
"""

import csv
import io
import re
import statistics
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, tzinfo
from typing import Literal

MMOL_TO_MG_DL = 18.0182
LOW_SENTINEL = 39.0
HIGH_SENTINEL = 401.0
MAX_BYTES = 10 * 1024 * 1024

Unit = Literal["mg/dL", "mmol/L"]
Format = Literal["libreview", "dexcom", "generic"]
DateOrder = Literal["iso", "dmy", "mdy", "ymd"]

# (strptime format, date order). ISO is tried separately and labelled "iso".
_DATE_FORMATS: tuple[tuple[str, DateOrder], ...] = (
    ("%d-%m-%Y %H:%M", "dmy"), ("%m-%d-%Y %H:%M", "mdy"),
    ("%d/%m/%Y %H:%M", "dmy"), ("%m/%d/%Y %H:%M", "mdy"),
    ("%d.%m.%Y %H:%M", "dmy"),
    ("%m-%d-%Y %I:%M %p", "mdy"), ("%m/%d/%Y %I:%M %p", "mdy"),
    ("%Y/%m/%d %H:%M", "ymd"), ("%Y-%m-%d %H:%M", "ymd"),
)
# Spans within this of the shortest one count as equally contiguous.
_SPAN_TIE_S = 3600.0
_TIME_COLS = ("device timestamp", "timestamp", "datetime", "date time", "time", "date")
_VALUE_COLS = ("glucose", "sgv", "value", "bg", "mg/dl", "mmol/l")


class ImportFormatError(ValueError):
    """The file is not a recognisable CGM export; the message says what was expected."""


@dataclass(frozen=True)
class ParsedImport:
    format: Format
    unit: Unit
    readings: list[tuple[datetime, float]]  # ascending, unique timestamps, mg/dL
    skipped_rows: int  # data rows without a usable time or value
    date_order: DateOrder
    # True when a different day/month order would also have read every dated row.
    date_ambiguous: bool


def parse_cgm_csv(
    text: str,
    tz: tzinfo,
    unit: Unit | None = None,
    date_order: Literal["dmy", "mdy"] | None = None,
    now: datetime | None = None,
) -> ParsedImport:
    """``date_order`` forces day-first or month-first numeric dates; ``now`` (aware)
    is the reference for the recency tie-break and defaults to the current time."""
    rows = list(csv.reader(io.StringIO(text.lstrip("\ufeff"))))
    header_i, fmt = _find_header(rows)
    header = [h.strip() for h in rows[header_i]]
    lower = [h.lower() for h in header]
    data = [r for r in rows[header_i + 1 :] if any(c.strip() for c in r)]

    if fmt == "libreview":
        t_col = lower.index("device timestamp")
        v_col = _first(lower, "historic glucose")
        rtype = _first(lower, "record type")
        picked = [r for r in data if _cell(r, rtype) == "0" and _cell(r, v_col)]
        if not picked:
            v_col = _first(lower, "scan glucose")
            picked = [r for r in data if _cell(r, rtype) == "1" and _cell(r, v_col)]
        data = picked
    elif fmt == "dexcom":
        t_col = _first(lower, "timestamp")
        v_col = _first(lower, "glucose value")
        etype = _first(lower, "event type")
        data = [r for r in data if _cell(r, etype).upper() == "EGV"]
    else:
        t_col = next((lower.index(c) for c in _TIME_COLS if c in lower), -1)
        v_col = next((i for i, h in enumerate(lower) if any(k in h for k in _VALUE_COLS)), -1)
        if t_col < 0 or v_col < 0 or t_col == v_col:
            raise ImportFormatError(
                "Could not find a time column and a glucose column. Expected a LibreView or "
                "Dexcom Clarity export, or a CSV with columns like 'timestamp,glucose'."
            )

    times_raw = [_cell(r, t_col) for r in data]
    values_raw = [_cell(r, v_col) for r in data]
    stamps, order, ambiguous = _parse_times(times_raw, tz, date_order, now)
    values = [_parse_value(v) for v in values_raw]
    if unit is None:
        unit = _detect_unit(header[v_col], values)
    factor = MMOL_TO_MG_DL if unit == "mmol/L" else 1.0

    by_time: dict[datetime, float] = {}
    skipped = 0
    for t, v in zip(stamps, values, strict=True):
        if t is None or v is None:
            skipped += 1
            continue
        mg = v if v in (LOW_SENTINEL, HIGH_SENTINEL) else round(v * factor, 1)
        by_time[t] = mg  # duplicate timestamps keep the last row
    readings = sorted(by_time.items())
    if not readings:
        raise ImportFormatError("The file has no glucose readings with a usable time.")
    return ParsedImport(fmt, unit, readings, skipped, order, ambiguous)


def _find_header(rows: Sequence[Sequence[str]]) -> tuple[int, Format]:
    for i, row in enumerate(rows[:20]):
        lower = [c.strip().lower() for c in row]
        joined = ",".join(lower)
        if "device timestamp" in lower and "historic glucose" in joined:
            return i, "libreview"
        if "event type" in lower and "glucose value" in joined:
            return i, "dexcom"
        has_time = any(c in lower for c in _TIME_COLS)
        has_value = any(any(k in c for k in _VALUE_COLS) for c in lower)
        if has_time and has_value:
            return i, "generic"
    raise ImportFormatError(
        "No header row found in the first 20 lines. Expected a LibreView or Dexcom Clarity "
        "export, or a CSV with columns like 'timestamp,glucose'."
    )


def _first(lower: list[str], prefix: str) -> int:
    for i, h in enumerate(lower):
        if h.startswith(prefix):
            return i
    raise ImportFormatError(f"Expected a column starting with '{prefix}'.")


def _cell(row: Sequence[str], i: int) -> str:
    return row[i].strip() if i < len(row) else ""


def _parse_value(s: str) -> float | None:
    if not s:
        return None
    if s.lower() == "low":
        return LOW_SENTINEL
    if s.lower() == "high":
        return HIGH_SENTINEL
    try:
        v = float(s.replace(",", "."))
    except ValueError:
        return None
    return v if v > 0 else None


def _detect_unit(header: str, values: list[float | None]) -> Unit:
    h = header.lower()
    if "mmol" in h:
        return "mmol/L"
    if "mg/dl" in h or "mg" in h:
        return "mg/dL"
    real = [v for v in values if v is not None and v not in (LOW_SENTINEL, HIGH_SENTINEL)]
    return "mmol/L" if real and statistics.median(real) < 35 else "mg/dL"


def _parse_times(
    raw: list[str],
    tz: tzinfo,
    forced: Literal["dmy", "mdy"] | None,
    now: datetime | None,
) -> tuple[list[datetime | None], DateOrder, bool]:
    present = [s for s in raw if s]
    if not present:
        return [None] * len(raw), "iso", False
    reference = now or datetime.now(tz)
    parsers: list[tuple[Callable[[str], datetime | None], DateOrder]] = [
        (_iso, "iso"),
        *((_fmt_parser(f), order) for f, order in _DATE_FORMATS),
    ]

    candidates: list[tuple[int, float, float, int, DateOrder]] = []
    for i, (parse, order) in enumerate(parsers):
        if forced is not None and order in ("dmy", "mdy") and order != forced:
            continue
        ok = [_localize(t, tz) for t in map(parse, present) if t is not None]
        aware = [t for t in ok if t is not None]
        if not aware:
            continue
        span = (max(aware) - min(aware)).total_seconds()
        # Seconds the newest reading lies after now (negative: in the past).
        ahead = (max(aware) - reference).total_seconds()
        candidates.append((len(aware), span, ahead, i, order))
    if not candidates:
        raise ImportFormatError(f"Unrecognised date format, for example {present[0]!r}.")

    most = max(c[0] for c in candidates)
    if most < 0.5 * len(present):
        raise ImportFormatError(f"Unrecognised date format, for example {present[0]!r}.")
    full = [c for c in candidates if c[0] == most]
    shortest = min(c[1] for c in full)
    tied = [c for c in full if c[1] <= shortest + _SPAN_TIE_S]
    # Among equally contiguous readings: not in the future (1 min of clock skew allowed),
    # then the one ending closest to now, then list order.
    best = min(tied, key=lambda c: (c[2] > 60, abs(c[2]), c[3]))
    parse, order = parsers[best[3]]
    stamps = [_localize(parse(s), tz) if s else None for s in raw]
    # Ambiguous: another day/month order was equally contiguous and reads to different
    # times, so only the recency tie-break chose. Contiguity alone is a confident answer.
    rivals = [c for c in tied if c[4] in ("dmy", "mdy") and c[4] != order]
    ambiguous = forced is None and order in ("dmy", "mdy") and any(
        parsers[c[3]][0](s) != parse(s) for c in rivals for s in present
    )
    return stamps, order, ambiguous


def _fmt_parser(fmt: str) -> Callable[[str], datetime | None]:
    return lambda s: _strptime(s, fmt)


def _iso(s: str) -> datetime | None:
    try:
        return datetime.fromisoformat(re.sub(r"Z$", "+00:00", s))
    except ValueError:
        return None


def _strptime(s: str, fmt: str) -> datetime | None:
    s = re.sub(r":\d{2}(\s*[AP]M)?$", lambda m: m.group(1) or "", s) if s.count(":") == 2 else s
    try:
        return datetime.strptime(s, fmt)
    except ValueError:
        return None


def _localize(t: datetime | None, tz: tzinfo) -> datetime | None:
    if t is None:
        return None
    return t if t.tzinfo is not None else t.replace(tzinfo=tz)
