"""Procesamiento online de una única ficha (SDD-02 RF-24-29 + DESIGN-08b).

La función `process_patient_ficha` aplica las mismas fases del pipeline
batch pero sobre **una única fila** en memoria y termina invocando al
servicio ml-triage para dejar las predicciones (triaje + sospecha de
enfermedad) persistidas antes de responder.

Además persiste el JSON original del formulario en MinIO antes de tocar
nada (capa raw / data lake — DESIGN-08b §7), de forma best-effort:
si MinIO cae el flujo continúa y se emite un evento de aviso, no se
pierde la ficha del paciente.

Reutiliza `validation` / `transformation` / `loading` del batch — la misma
fuente de verdad para las reglas.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from app.clients.triage_client import MlServiceUnavailable, predict_combined
from app.events import emit_event
from app.logging_setup import set_correlation_id
from app.phases import loading, transformation, validation
from app.storage.raw_source import RawSource, make_raw_source

logger = logging.getLogger(__name__)


def _build_triage_ficha(pac: dict, ing: dict) -> dict:
    """Construye el dict que consume ml-triage a partir del par paciente/ingreso."""
    return {
        "edad": pac.get("edad"),
        "sexo": pac.get("sexo"),
        "peso_kg": pac.get("peso_kg"),
        "altura_cm": pac.get("altura_cm"),
        "enfermedades_cronicas": pac.get("enfermedades_cronicas") or [],
        "fumador": pac.get("fumador") or "no",
        "embarazo": pac.get("embarazo") or "na",
        "motivo_principal": ing.get("motivo_principal"),
        "duracion_sintomas": ing.get("duracion_sintomas"),
        "intensidad_dolor": ing.get("intensidad_dolor") or 0,
        "fiebre_subjetiva": ing.get("fiebre_subjetiva") or "no",
        "dificultad_respiratoria_subjetiva": ing.get("dificultad_respiratoria_subjetiva") or "no",
        "tos": ing.get("tos") or "no",
        "contacto_covid_reciente": ing.get("contacto_covid_reciente") or "no_se",
        "hora_envio": ing.get("hora_envio") if ing.get("hora_envio") is not None else 0,
    }


def _persist_raw_form(
    payload: dict, correlation_id: str, raw_source: RawSource
) -> str | None:
    """Sube el JSON original del formulario a la capa raw (DESIGN-08b §7.3).

    Best-effort: si la subida falla, log warning + evento de dominio y
    devuelve None — no debe bloquear el flujo online si MinIO está caído.
    """
    today = datetime.now(timezone.utc)
    key = f"online/{today:%Y/%m/%d}/{correlation_id}.json"
    try:
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        raw_source.put(key, body, content_type="application/json")
        emit_event(
            "pipeline.online.raw_persisted",
            message=f"Ficha raw persistida en {raw_source.describe()}/{key}",
            payload={"key": key, "bytes": len(body)},
        )
        return key
    except Exception as exc:  # noqa: BLE001 — best-effort por diseño
        logger.warning("Fallo persistiendo raw form en MinIO: %s", exc)
        emit_event(
            "pipeline.online.raw_persist_failed",
            level="warning",
            message="Raw del formulario no persistido (MinIO inaccesible)",
            payload={"key": key, "error": str(exc)},
        )
        return None


def process_patient_ficha(
    ficha: dict,
    rules: dict,
    correlation_id: str | None = None,
    apply_triage: bool = True,
) -> dict:
    """Procesa una ficha end-to-end. Devuelve el resultado con triaje y
    sospecha de enfermedad (si `apply_triage` y el servicio respondió),
    `pending_*` si el servicio cayó, o `rejected` si la validación falló."""
    run_id = correlation_id or f"online-{uuid.uuid4().hex[:12]}"
    set_correlation_id(run_id)

    # Si `hora_envio` no viene, la rellenamos desde el servidor.
    if ficha.get("hora_envio") is None:
        ficha = {**ficha, "hora_envio": datetime.now(timezone.utc).hour}

    emit_event(
        "pipeline.online.start",
        message="Procesando ficha online",
        payload={"source": "formulario_web"},
    )

    # --- Capa raw (data lake — best-effort) ---------------------------------
    raw_source = make_raw_source()
    raw_key = _persist_raw_form(ficha, run_id, raw_source)

    # --- Validación ---------------------------------------------------------
    df = pd.DataFrame([ficha])
    valid_df, rejects_df = validation.validate_entity(df, "paciente", rules)

    if len(valid_df) == 0:
        loading.load_rejects(rejects_df, run_id, source_file="formulario_web")
        reasons = list(rejects_df.iloc[0]["reject_reasons"])
        emit_event(
            "pipeline.online.rejected",
            level="warning",
            message="Ficha rechazada en validación",
            payload={"reasons": reasons, "raw_key": raw_key},
        )
        return {
            "status": "rejected",
            "run_id": run_id,
            "pseudo_id": None,
            "prediction": None,
            "disease": None,
            "raw_key": raw_key,
            "reasons": reasons,
        }

    # --- Transformación + Carga ---------------------------------------------
    pacientes_rows, ingresos_rows = transformation.transform(
        valid_df, source_file="formulario_web", correlation_id=run_id
    )
    loading.load_pacientes_ingresos(pacientes_rows, ingresos_rows)

    pseudo_id: str = pacientes_rows[0]["pseudo_id"]
    pac = pacientes_rows[0]
    ing = ingresos_rows[0]
    triage_ficha = _build_triage_ficha(pac, ing)

    # --- Triaje + sospecha de enfermedad (opcional) -------------------------
    if not apply_triage:
        emit_event(
            "pipeline.online.end",
            message=f"Ficha {pseudo_id} procesada (sin ml-triage)",
            payload={"pseudo_id": pseudo_id, "ml_status": "skipped"},
        )
        return {
            "status": "completed",
            "run_id": run_id,
            "pseudo_id": pseudo_id,
            "prediction": None,
            "disease": None,
            "raw_key": raw_key,
            "ml_status": "skipped",
        }

    triage_pred: dict[str, Any] = {}
    disease_pred: dict[str, Any] = {}
    try:
        combined = predict_combined(triage_ficha)
        triage_pred = combined.get("triage", {})
        disease_pred = combined.get("disease", {})
        ml_status = "completed"
    except MlServiceUnavailable as exc:
        logger.warning("ml-triage no disponible: %s", exc)
        ml_status = "pending"

    loading.persist_triage_prediction(
        patient_pseudo_id=pseudo_id,
        admission_id=None,
        ficha_snapshot=triage_ficha,
        prediction=triage_pred or {"predicted_class": None, "probabilities": {}},
        correlation_id=run_id,
        source="formulario_web",
        triage_status="completed" if ml_status == "completed" else "pending_triage",
    )
    loading.persist_disease_prediction(
        patient_pseudo_id=pseudo_id,
        admission_id=None,
        ficha_snapshot=triage_ficha,
        prediction=disease_pred or {"differential": []},
        correlation_id=run_id,
        source="formulario_web",
        inference_status="completed" if ml_status == "completed" else "pending_disease",
    )

    emit_event(
        "pipeline.online.end",
        message=f"Ficha {pseudo_id} procesada ({ml_status})",
        payload={"pseudo_id": pseudo_id, "ml_status": ml_status, "raw_key": raw_key},
    )

    return {
        "status": "completed" if ml_status == "completed" else "pending_triage",
        "run_id": run_id,
        "pseudo_id": pseudo_id,
        "prediction": triage_pred if triage_pred else None,
        "disease": disease_pred if disease_pred else None,
        "raw_key": raw_key,
        "ml_status": ml_status,
    }
