"""Alert de-duplication (architecture notify module).

State machine per ``(patient_id, alert type)``:
  * onset (inactive -> active) raises, unless the same type was raised less than
    ``cooldown`` ago (anti-flapping): the condition then becomes active silently;
  * while active, the condition is never re-raised;
  * an explicit clear (the condition evaluated false) makes it inactive, so the next onset
    after the cooldown raises again.

Cycles that cannot evaluate a condition (e.g. no forecast during a data gap) should neither
report nor clear it, so its state is carried over unchanged.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class _State:
    active: bool = False
    last_raised: datetime | None = None


class AlertDeduplicator:
    def __init__(self, cooldown: timedelta) -> None:
        if cooldown < timedelta(0):
            raise ValueError("cooldown must be non-negative")
        self.cooldown = cooldown
        self._state: dict[tuple[str, str], _State] = {}

    def observe(self, patient_id: str, alert_type: str, present: bool, t: datetime) -> bool:
        """Record the condition at time ``t``; True when an alert should be raised now."""
        state = self._state.setdefault((patient_id, alert_type), _State())
        if not present:
            state.active = False
            return False
        if state.active:
            return False
        state.active = True
        if state.last_raised is not None and t - state.last_raised < self.cooldown:
            return False
        state.last_raised = t
        return True

    def active_types(self, patient_id: str) -> list[str]:
        return sorted(t for (p, t), s in self._state.items() if p == patient_id and s.active)

    def forget(self, patient_id: str) -> None:
        for key in [k for k in self._state if k[0] == patient_id]:
            del self._state[key]
