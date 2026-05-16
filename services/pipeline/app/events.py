"""Emisión de **eventos de dominio** a la colección `system_events` de Mongo.

Son eventos estructurados con significado de negocio (*"5000 filas leídas"*,
*"Ingesta completada"*), distintos de los **logs técnicos** de stdout
(Loki+Promtail). Alimentan la vista "Seguimiento de run" del dashboard
(SDD-05 RF-19quater) y la auditoría (SDD-03 RF-10, SDD-07 RF-9bis).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.config import get_settings
from app.logging_setup import get_correlation_id
from app.storage.mongo import system_events

logger = logging.getLogger(__name__)


def emit_event(
    event: str,
    level: str = "info",
    message: str = "",
    payload: dict[str, Any] | None = None,
) -> None:
    """Persiste un evento de dominio y lo emite también al log técnico.

    Args:
      event: etiqueta del evento (p. ej. "pipeline.run.start", "pipeline.phase.end").
      level: "info" | "warning" | "error".
      message: texto legible humano (ES), apto para mostrar en el dashboard.
      payload: dict con contadores y metadatos (records_in, records_out, ...).
    """
    settings = get_settings()
    correlation_id = get_correlation_id()
    doc = {
        "timestamp": datetime.now(timezone.utc),
        "service": settings.service_name,
        "event": event,
        "level": level,
        "correlation_id": correlation_id,
        "message": message,
        "payload": payload or {},
    }
    try:
        system_events().insert_one(doc)
    except Exception:
        # No queremos que fallar al emitir un evento aborte la lógica principal.
        # El log técnico (stdout) sigue siendo la fuente de verdad alternativa.
        logger.exception("Fallo al persistir evento de dominio: %s", event)

    # Log técnico paralelo (SDD-07 RF-9bis: emisiones paralelas).
    extra: dict[str, Any] = {"event": event}
    if payload:
        for k, v in payload.items():
            # Solo campos simples; evitamos dicts anidados en logs stdout.
            if isinstance(v, (int, float, str, bool)):
                extra[k] = v
    py_level = {"info": logging.INFO, "warning": logging.WARNING, "error": logging.ERROR}.get(
        level.lower(), logging.INFO
    )
    logger.log(py_level, message or event, extra=extra)
