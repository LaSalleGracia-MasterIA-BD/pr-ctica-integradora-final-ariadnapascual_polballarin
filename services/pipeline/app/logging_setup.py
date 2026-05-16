"""Logging JSON estructurado a stdout con correlation_id (SDD-07 RF-1).

Un `correlation_id` identifica unívocamente un run del pipeline o una
operación online. Se pasa como argumento a `get_logger()` o se rellena
de forma ambiental con el `ContextVar` `_correlation_id`.
"""
from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="-")


def set_correlation_id(cid: str) -> None:
    _correlation_id.set(cid)


def get_correlation_id() -> str:
    return _correlation_id.get()


class JsonFormatter(logging.Formatter):
    """Formatea cada LogRecord como una línea JSON con campos fijos."""

    def __init__(self, service: str) -> None:
        super().__init__()
        self._service = service

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": self._service,
            "correlation_id": _correlation_id.get(),
            "event": getattr(record, "event", record.name),
            "message": record.getMessage(),
        }
        # Campos extra pasados por `extra={...}`
        for key in ("records_in", "records_out", "duration_ms", "file",
                    "rule_violated", "error_code"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(service: str, level: str = "INFO") -> logging.Logger:
    """Configura el root logger con el JsonFormatter. Idempotente."""
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level.upper())

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service=service))
    root.addHandler(handler)
    return root
