"""Structured JSON logging for the runtime service.

Every record becomes one JSON object per line. Event-specific fields are attached with
:func:`log_event` (``extra={"fields": {...}}``) so log shippers can index them directly.
"""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

_FIELDS = "fields"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        fields = getattr(record, _FIELDS, None)
        if isinstance(fields, dict):
            payload.update(fields)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str | int = "INFO") -> None:
    """Route the root logger to stderr as JSON lines (idempotent)."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)


def log_event(
    logger: logging.Logger, event: str, level: int = logging.INFO, **fields: Any
) -> None:
    """Emit ``event`` with structured ``fields`` (merged into the JSON object)."""
    if logger.isEnabledFor(level):
        logger.log(level, event, extra={_FIELDS: {"event": event, **fields}})
