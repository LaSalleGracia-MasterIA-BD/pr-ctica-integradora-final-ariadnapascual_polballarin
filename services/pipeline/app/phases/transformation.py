"""Fase 3 — Transformación. Genera pseudo_id, añade trazabilidad, separa
paciente vs ingreso.

SDD-02 RF-9, RF-10, RF-11. Se aplica anonimización defensiva: si aparece
alguna columna identificativa (`nombre`, `dni`, etc.), se **omite** y se
registra evento.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from app.config import get_settings
from app.events import emit_event
from app.utils.pseudo_id import next_pseudo_id

logger = logging.getLogger(__name__)


# Columnas que nunca deben persistirse (SDD-01 RNF-8).
BLACKLIST_COLS = {
    "nombre", "apellido", "apellidos", "name", "surname",
    "dni", "nie", "nif", "ssn",
    "email", "correo",
    "telefono", "telefono_movil", "phone", "mobile",
    "direccion", "address", "domicilio",
}

# Campos estables del paciente (van a la tabla `pacientes`).
PATIENT_FIELDS = [
    "edad", "sexo", "peso_kg", "altura_cm",
    "enfermedades_cronicas", "fumador", "embarazo",
]

# Campos del episodio (van a la tabla `ingresos`).
ADMISSION_FIELDS = [
    "motivo_principal", "duracion_sintomas", "intensidad_dolor",
    "fiebre_subjetiva", "dificultad_respiratoria_subjetiva",
    "tos", "contacto_covid_reciente", "hora_envio",
]


def _drop_blacklist(df: pd.DataFrame) -> pd.DataFrame:
    to_drop = [c for c in df.columns if c.lower() in BLACKLIST_COLS]
    if to_drop:
        for c in to_drop:
            emit_event(
                "anonymization.dropped_column",
                level="warning",
                message=f"Columna identificativa omitida: {c}",
                payload={"column": c},
            )
        df = df.drop(columns=to_drop)
    return df


def _coerce_enfermedades_cronicas(val: Any) -> list[str]:
    """Acepta lista, string 'a|b|c' o NaN. Devuelve lista."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return []
    if isinstance(val, list):
        return [str(x) for x in val]
    s = str(val).strip()
    if not s:
        return []
    return [p for p in s.split("|") if p]


def transform(
    df: pd.DataFrame,
    source_file: str,
    correlation_id: str,
) -> tuple[list[dict], list[dict]]:
    """Devuelve `(pacientes_rows, ingresos_rows)` listos para `loading.py`.

    Genera `pseudo_id` por fila usando el contador atómico de Mongo.
    """
    df = _drop_blacklist(df)

    now = datetime.now(timezone.utc)
    processed_by = f"{get_settings().service_name}:{correlation_id}"

    pacientes: list[dict] = []
    ingresos: list[dict] = []

    for _, row in df.iterrows():
        pseudo_id = next_pseudo_id()
        ec = _coerce_enfermedades_cronicas(row.get("enfermedades_cronicas"))

        patient_row = {
            "pseudo_id": pseudo_id,
            "edad": int(row["edad"]) if not pd.isna(row.get("edad")) else None,
            "sexo": row.get("sexo"),
            "peso_kg": int(row["peso_kg"]) if not pd.isna(row.get("peso_kg")) else None,
            "altura_cm": int(row["altura_cm"]) if not pd.isna(row.get("altura_cm")) else None,
            "enfermedades_cronicas": ec,
            "fumador": row.get("fumador"),
            "embarazo": row.get("embarazo"),
            "source": f"csv_batch:{source_file}",
            "ingested_at": now,
            "processed_by": processed_by,
        }
        pacientes.append(patient_row)

        admission_row = {
            "paciente_pseudo_id": pseudo_id,
            "fecha_ingreso": now,
            "motivo": row.get("motivo"),
            "motivo_principal": row.get("motivo_principal"),
            "duracion_sintomas": row.get("duracion_sintomas"),
            "intensidad_dolor": int(row["intensidad_dolor"])
                if not pd.isna(row.get("intensidad_dolor")) else None,
            "fiebre_subjetiva": row.get("fiebre_subjetiva"),
            "dificultad_respiratoria_subjetiva": row.get("dificultad_respiratoria_subjetiva"),
            "tos": row.get("tos"),
            "contacto_covid_reciente": row.get("contacto_covid_reciente"),
            "hora_envio": int(row["hora_envio"]) if not pd.isna(row.get("hora_envio")) else None,
            "source": f"csv_batch:{source_file}",
            "ingested_at": now,
            "processed_by": processed_by,
        }
        ingresos.append(admission_row)

    return pacientes, ingresos
