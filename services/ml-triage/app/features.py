"""Contrato de features del modelo de triaje (compartido entre training y runtime).

Fuente única de verdad para: nombres de columnas, orden, clases y expansión
de la multi-categoría `enfermedades_cronicas`. Importado tanto por
`training/model.py` como por `app/predictor.py` para evitar divergencias.
"""
from __future__ import annotations

from typing import Iterable

import pandas as pd

NUMERIC_COLS: list[str] = [
    "edad",
    "peso_kg",
    "altura_cm",
    "intensidad_dolor",
    "hora_envio",
]

CATEGORICAL_COLS: list[str] = [
    "sexo",
    "fumador",
    "embarazo",
    "motivo_principal",
    "duracion_sintomas",
    "fiebre_subjetiva",
    "dificultad_respiratoria_subjetiva",
    "tos",
    "contacto_covid_reciente",
]

CHRONIC_LABELS: list[str] = [
    "diabetes",
    "hipertension",
    "asma_epoc",
    "cardiopatia",
    "inmunosupresion",
]
CHRONIC_BOOL_COLS: list[str] = [f"has_{x}" for x in CHRONIC_LABELS]

ALL_FEATURE_COLS: list[str] = NUMERIC_COLS + CATEGORICAL_COLS + CHRONIC_BOOL_COLS
TARGET_COL = "target"

CLASSES: list[str] = ["Alta", "Media", "Baja"]


def expand_chronic_from_list(cronicas: Iterable[str] | None) -> dict[str, bool]:
    """Dada la lista de `enfermedades_cronicas`, devuelve el diccionario
    {has_<label>: bool} con las 5 booleanas."""
    items = set(cronicas or [])
    return {f"has_{lbl}": (lbl in items) for lbl in CHRONIC_LABELS}


def expand_chronic_from_string(s: str | None) -> dict[str, bool]:
    """Variante para CSV: acepta 'diabetes|hipertension'."""
    if not s:
        return {f"has_{lbl}": False for lbl in CHRONIC_LABELS}
    items = set(str(s).split("|"))
    return {f"has_{lbl}": (lbl in items) for lbl in CHRONIC_LABELS}


def ficha_to_feature_row(ficha: dict) -> pd.DataFrame:
    """Convierte una ficha (dict con los 15 campos del formulario SDD-08 RF-1)
    en un DataFrame de 1 fila lista para pasar al pipeline sklearn.

    Expande `enfermedades_cronicas` (lista) a las 5 booleanas; preserva
    el orden de columnas en `ALL_FEATURE_COLS`; no altera tipos ni imputa."""
    row = {col: ficha.get(col) for col in NUMERIC_COLS + CATEGORICAL_COLS}
    row.update(expand_chronic_from_list(ficha.get("enfermedades_cronicas")))
    return pd.DataFrame([[row[c] for c in ALL_FEATURE_COLS]], columns=ALL_FEATURE_COLS)


__all__ = [
    "NUMERIC_COLS",
    "CATEGORICAL_COLS",
    "CHRONIC_LABELS",
    "CHRONIC_BOOL_COLS",
    "ALL_FEATURE_COLS",
    "TARGET_COL",
    "CLASSES",
    "expand_chronic_from_list",
    "expand_chronic_from_string",
    "ficha_to_feature_row",
]
