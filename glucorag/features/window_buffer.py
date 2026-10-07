"""Per-patient bounded CGM history feeding the forecast engine (architecture step 3).

Only the most recent ``span`` of readings is retained: enough for the look-back window plus
the slots the engine uses to bridge an imputable gap. The buffer also remembers the first
reading ever seen per patient so callers can tell "still warming up" from "data gap".
"""

from collections import deque
from collections.abc import Iterable
from datetime import datetime, timedelta

from glucorag.inference.engine import Reading


class WindowBuffer:
    def __init__(self, span: timedelta) -> None:
        if span <= timedelta(0):
            raise ValueError("span must be positive")
        self.span = span
        self._readings: dict[str, deque[Reading]] = {}
        self._first_seen: dict[str, datetime] = {}

    @classmethod
    def for_engine(cls, lookback_min: int, interval_min: int, max_gap_min: int) -> "WindowBuffer":
        """Span covering the look-back window, one imputable gap and two trend points."""
        return cls(timedelta(minutes=lookback_min + max_gap_min + 2 * interval_min))

    def __contains__(self, patient_id: str) -> bool:
        return patient_id in self._readings

    def load(
        self, patient_id: str, readings: Iterable[Reading], first_seen: datetime | None
    ) -> None:
        """(Re)hydrate a patient from persisted readings (any order)."""
        ordered = sorted(readings, key=lambda r: r.timestamp)
        self._readings[patient_id] = deque()
        for r in ordered:
            self._append(patient_id, r)
        if first_seen is not None:
            self._first_seen[patient_id] = first_seen
        elif ordered:
            self._first_seen[patient_id] = ordered[0].timestamp

    def append(self, patient_id: str, reading: Reading) -> None:
        """Append a reading strictly newer than the patient's latest one."""
        last = self.last_timestamp(patient_id)
        if last is not None and reading.timestamp <= last:
            raise ValueError(f"Reading at {reading.timestamp} is not after {last}")
        self._first_seen.setdefault(patient_id, reading.timestamp)
        self._append(patient_id, reading)

    def _append(self, patient_id: str, reading: Reading) -> None:
        buf = self._readings.setdefault(patient_id, deque())
        buf.append(reading)
        cutoff = reading.timestamp - self.span
        while buf and buf[0].timestamp < cutoff:
            buf.popleft()

    def history(self, patient_id: str) -> list[Reading]:
        return list(self._readings.get(patient_id, ()))

    def last_timestamp(self, patient_id: str) -> datetime | None:
        buf = self._readings.get(patient_id)
        return buf[-1].timestamp if buf else None

    def first_seen(self, patient_id: str) -> datetime | None:
        return self._first_seen.get(patient_id)

    def forget(self, patient_id: str) -> None:
        self._readings.pop(patient_id, None)
        self._first_seen.pop(patient_id, None)
