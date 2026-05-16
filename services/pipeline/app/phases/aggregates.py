"""Fase análisis — Agregados diarios por run (SDD-02 RF-13)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.events import emit_event
from app.storage import mongo

logger = logging.getLogger(__name__)


def upsert_daily_aggregate(date_str: str, run_id: str, metrics: dict) -> None:
    """Upsert por día natural. `metrics` contiene contadores y distribuciones."""
    now = datetime.now(timezone.utc)
    update_doc = {
        "$set": {
            "report_date": date_str,
            "pipeline_run_id": run_id,
            "generated_at": now,
            **{f"metrics.{k}": v for k, v in metrics.items()},
        }
    }
    mongo.aggregates_daily().update_one(
        {"_id": date_str}, update_doc, upsert=True
    )
    emit_event(
        "pipeline.aggregates.updated",
        message=f"Agregados diarios actualizados ({date_str})",
        payload={"date": date_str, **metrics},
    )
