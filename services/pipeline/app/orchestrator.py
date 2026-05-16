"""Orquestador del pipeline batch (SDD-02 RF-6).

Flujo end-to-end sobre un CSV que reside en RawSource:
  1. ingestion.ingest_csv() → DataFrame
  2. validation (paciente) → valid/rejects
  3. dedup por pseudo_id logical — en este pipeline NO se dedupa por
     pseudo_id porque se genera en transformation; la dedup la hace
     postgres con ON CONFLICT DO NOTHING.
  4. transformation → (pacientes_rows, ingresos_rows)
  5. loading → PG + rechazos a Mongo
  6. [opcional] triaje online por cada ficha
  7. aggregates → colección `aggregates_daily`
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone

import pandas as pd

from app.clients.triage_client import MlServiceUnavailable, predict_combined
from app.config import get_settings
from app.events import emit_event
from app.logging_setup import set_correlation_id
from app.phases import aggregates, ingestion, loading, transformation, validation
from app.storage.raw_source import RawSource

logger = logging.getLogger(__name__)


def new_run_id() -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"run-{today}-{uuid.uuid4().hex[:8]}"


def _run_ml_for_ingresos(
    ingresos_rows: list[dict],
    pacientes_by_id: dict[str, dict],
    correlation_id: str,
    source: str,
) -> dict[str, int]:
    """Llama al servicio ml-triage (endpoint combinado /predict) por cada
    paciente. Persiste tanto la predicción de triaje como la sospecha
    de enfermedad (DESIGN-08b §8.3)."""
    completed = 0
    pending = 0
    for ingreso in ingresos_rows:
        pseudo = ingreso["paciente_pseudo_id"]
        pac = pacientes_by_id.get(pseudo, {})
        ficha = {
            "edad": pac.get("edad"),
            "sexo": pac.get("sexo"),
            "peso_kg": pac.get("peso_kg"),
            "altura_cm": pac.get("altura_cm"),
            "enfermedades_cronicas": pac.get("enfermedades_cronicas") or [],
            "fumador": pac.get("fumador") or "no",
            "embarazo": pac.get("embarazo") or "na",
            "motivo_principal": ingreso.get("motivo_principal"),
            "duracion_sintomas": ingreso.get("duracion_sintomas"),
            "intensidad_dolor": ingreso.get("intensidad_dolor") or 0,
            "fiebre_subjetiva": ingreso.get("fiebre_subjetiva") or "no",
            "dificultad_respiratoria_subjetiva": ingreso.get("dificultad_respiratoria_subjetiva") or "no",
            "tos": ingreso.get("tos") or "no",
            "contacto_covid_reciente": ingreso.get("contacto_covid_reciente") or "no_se",
            "hora_envio": ingreso.get("hora_envio") if ingreso.get("hora_envio") is not None else 0,
        }
        triage_pred: dict = {}
        disease_pred: dict = {}
        try:
            combined = predict_combined(ficha)
            triage_pred = combined.get("triage", {})
            disease_pred = combined.get("disease", {})
            status = "completed"
            completed += 1
        except MlServiceUnavailable:
            status = "pending"
            pending += 1
        loading.persist_triage_prediction(
            patient_pseudo_id=pseudo,
            admission_id=None,
            ficha_snapshot=ficha,
            prediction=triage_pred or {"predicted_class": None, "probabilities": {}},
            correlation_id=correlation_id,
            source=source,
            triage_status="completed" if status == "completed" else "pending_triage",
        )
        loading.persist_disease_prediction(
            patient_pseudo_id=pseudo,
            admission_id=None,
            ficha_snapshot=ficha,
            prediction=disease_pred or {"differential": []},
            correlation_id=correlation_id,
            source=source,
            inference_status="completed" if status == "completed" else "pending_disease",
        )
    return {"triage_completed": completed, "triage_pending": pending}


def run_batch(
    source: RawSource,
    key: str,
    rules: dict,
    apply_triage: bool = True,
    run_id: str | None = None,
) -> dict:
    """Ejecuta el pipeline batch end-to-end sobre un único CSV `key`.

    Si se pasa `run_id`, se usa como `correlation_id` para que la API
    pueda filtrar los `system_events` por ese mismo id (SDD-05 RF-2quater).
    Si no, se genera uno nuevo.
    """
    settings = get_settings()
    if run_id is None:
        run_id = new_run_id()
    set_correlation_id(run_id)

    emit_event(
        "pipeline.run.start",
        message=f"Pipeline batch iniciado sobre {source.describe()}/{key}",
        payload={"file": key, "source": source.describe(), "apply_triage": apply_triage},
    )
    t0 = time.perf_counter()

    # 1) INGESTA
    df, meta = ingestion.ingest_csv(source, key)

    # 2) VALIDACIÓN
    valid_df, rejects_df = validation.validate_entity(df, "paciente", rules)
    rejects_count = len(rejects_df)
    emit_event(
        "pipeline.validation.done",
        level="warning" if rejects_count else "info",
        message=f"Validación: {len(valid_df)} válidos, {rejects_count} rechazados",
        payload={"valid": len(valid_df), "rejected": rejects_count},
    )

    # 3) TRANSFORMACIÓN
    pacientes_rows, ingresos_rows = transformation.transform(
        valid_df, source_file=key, correlation_id=run_id
    )
    emit_event(
        "pipeline.transformation.done",
        message=f"Transformación: {len(pacientes_rows)} fichas preparadas",
        payload={"records": len(pacientes_rows)},
    )

    # 4) CARGA
    load_result = loading.load_pacientes_ingresos(pacientes_rows, ingresos_rows)
    rejects_loaded = loading.load_rejects(rejects_df, run_id, key)

    # 5) TRIAJE + SOSPECHA DE ENFERMEDAD (opcional)
    triage_counts = {"triage_completed": 0, "triage_pending": 0}
    if apply_triage and ingresos_rows:
        pacientes_by_id = {p["pseudo_id"]: p for p in pacientes_rows}
        triage_counts = _run_ml_for_ingresos(
            ingresos_rows, pacientes_by_id, run_id, source=f"csv_batch:{key}"
        )
        emit_event(
            "pipeline.ml.done",
            level="info" if triage_counts["triage_pending"] == 0 else "warning",
            message=(
                f"Triaje + sospecha aplicados: {triage_counts['triage_completed']} "
                f"completados, {triage_counts['triage_pending']} pendientes"
            ),
            payload=triage_counts,
        )

    # 6) AGREGADOS
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    aggregates.upsert_daily_aggregate(
        today,
        run_id,
        {
            "records_in": int(meta.get("size_bytes") is not None and len(df)) or 0,
            "valid": len(valid_df),
            "rejected": rejects_count,
            "pacientes_insertados": load_result["pacientes_insertados"],
            "ingresos_insertados": load_result["ingresos_insertados"],
            "triage_completed": triage_counts["triage_completed"],
            "triage_pending": triage_counts["triage_pending"],
        },
    )

    duration_ms = int((time.perf_counter() - t0) * 1000)
    summary = {
        "run_id": run_id,
        "file": key,
        "records_in": len(df),
        "valid": len(valid_df),
        "rejected": rejects_count,
        "rejects_persisted": rejects_loaded,
        "pacientes_insertados": load_result["pacientes_insertados"],
        "ingresos_insertados": load_result["ingresos_insertados"],
        **triage_counts,
        "duration_ms": duration_ms,
    }
    emit_event(
        "pipeline.run.end",
        message=f"Pipeline batch completado en {duration_ms} ms",
        payload=summary,
    )
    return summary
