"""Fase 4 — Carga. Persiste filas en PG + rechazos en Mongo.

SDD-02 RF-12. Incluye helpers para persistir eventos/predicciones/rechazos.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Iterable

import pandas as pd

from app.events import emit_event
from app.storage import mongo, postgres

logger = logging.getLogger(__name__)


def load_pacientes_ingresos(
    pacientes: list[dict],
    ingresos: list[dict],
) -> dict[str, int]:
    """Carga pacientes (first_wins) e ingresos (nuevos siempre)."""
    pac_inserted = postgres.upsert_pacientes(pacientes)
    ing_inserted = postgres.insert_ingresos(ingresos)

    emit_event(
        "pipeline.loading.done",
        message=f"Cargados {pac_inserted} pacientes y {ing_inserted} ingresos",
        payload={
            "pacientes_insertados": pac_inserted,
            "ingresos_insertados": ing_inserted,
            "pacientes_total_intentados": len(pacientes),
        },
    )
    return {
        "pacientes_insertados": pac_inserted,
        "ingresos_insertados": ing_inserted,
    }


def load_rejects(rejects_df: pd.DataFrame, correlation_id: str, source_file: str) -> int:
    """Persiste rechazos en la colección `ingestion_rejects` de Mongo."""
    if rejects_df.empty:
        return 0
    now = datetime.now(timezone.utc)
    docs: list[dict[str, Any]] = []
    for _, row in rejects_df.iterrows():
        docs.append({
            "entity": row["entity"],
            "source_file": source_file,
            "row_index": int(row["row_index"]) if not pd.isna(row["row_index"]) else -1,
            "raw_record": row["raw_record"],
            "reject_reason": row["reject_reasons"][0] if row["reject_reasons"] else "unknown",
            "reject_reasons": list(row["reject_reasons"]),
            "severity": row.get("severity", "error"),
            "correlation_id": correlation_id,
            "ingested_at": now,
            "processed_by": f"pipeline:{correlation_id}",
        })
    mongo.ingestion_rejects().insert_many(docs)
    emit_event(
        "pipeline.rejects.persisted",
        level="warning",
        message=f"{len(docs)} rechazos persistidos en ingestion_rejects",
        payload={"count": len(docs)},
    )
    return len(docs)


def persist_triage_prediction(
    patient_pseudo_id: str,
    admission_id: int | None,
    ficha_snapshot: dict,
    prediction: dict,
    correlation_id: str,
    source: str,
    triage_status: str = "completed",
) -> None:
    """Inserta un documento en `predictions_triage` (SDD-03 §4.3)."""
    now = datetime.now(timezone.utc)
    doc = {
        "patient_pseudo_id": patient_pseudo_id,
        "admission_id": admission_id,
        "ficha_snapshot": ficha_snapshot,
        "predicted_class": prediction.get("predicted_class"),
        "probabilities": prediction.get("probabilities"),
        "model_version": prediction.get("model_version"),
        "inference_time_ms": prediction.get("inference_time_ms"),
        "low_confidence": bool(prediction.get("low_confidence", False)),
        "triage_status": triage_status,
        "source": source,
        "ingested_at": now,
        "processed_by": f"pipeline:{correlation_id}",
        "correlation_id": correlation_id,
    }
    mongo.predictions_triage().insert_one(doc)


def persist_disease_prediction(
    patient_pseudo_id: str,
    admission_id: int | None,
    ficha_snapshot: dict,
    prediction: dict,
    correlation_id: str,
    source: str,
    inference_status: str = "completed",
) -> None:
    """Inserta un documento en `predictions_disease` (DESIGN-08b §8.4)."""
    now = datetime.now(timezone.utc)
    doc = {
        "patient_pseudo_id": patient_pseudo_id,
        "admission_id": admission_id,
        "ficha_snapshot": ficha_snapshot,
        "differential": prediction.get("differential", []),
        "low_confidence": bool(prediction.get("low_confidence", False)),
        "model_version": prediction.get("model_version"),
        "inference_time_ms": prediction.get("inference_time_ms"),
        "inference_status": inference_status,
        "source": source,
        "ingested_at": now,
        "processed_by": f"pipeline:{correlation_id}",
        "correlation_id": correlation_id,
    }
    mongo.predictions_disease().insert_one(doc)
