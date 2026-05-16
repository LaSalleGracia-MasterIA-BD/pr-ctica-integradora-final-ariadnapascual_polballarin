"""Seed sintético: genera N fichas de paciente (CSV) y las sube a la fuente raw.

Intencionalmente **réplica ligera** del generador de training de ml-triage
(con sus mismas distribuciones por feature) para evitar acoplamiento cross-service.
No genera `target` (la etiqueta la predice el modelo más tarde).
"""
from __future__ import annotations

import io
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from app.storage.raw_source import make_raw_source


FICHA_COLUMNS = [
    "edad",
    "sexo",
    "peso_kg",
    "altura_cm",
    "enfermedades_cronicas",
    "fumador",
    "embarazo",
    "motivo_principal",
    "duracion_sintomas",
    "intensidad_dolor",
    "fiebre_subjetiva",
    "dificultad_respiratoria_subjetiva",
    "tos",
    "contacto_covid_reciente",
    "hora_envio",
]

CRONICAS_PROBS: dict[str, float] = {
    "diabetes": 0.10,
    "hipertension": 0.15,
    "asma_epoc": 0.08,
    "cardiopatia": 0.07,
    "inmunosupresion": 0.03,
}

MOTIVO_WEIGHTS = [
    ("dolor_toracico", 0.08),
    ("dificultad_respiratoria", 0.10),
    ("fiebre", 0.18),
    ("dolor_abdominal", 0.17),
    ("traumatismo", 0.15),
    ("sintomas_neurologicos", 0.05),
    ("otro", 0.27),
]


def _pick(rng: np.random.Generator, values: list[str], weights: list[float]) -> str:
    return str(rng.choice(values, p=weights))


def _sample_ficha(rng: np.random.Generator) -> dict:
    mix = rng.random()
    if mix < 0.70:
        edad = int(rng.integers(18, 86))
    elif mix < 0.80:
        edad = int(rng.integers(0, 18))
    else:
        edad = int(rng.integers(86, 111))

    sexo = _pick(rng, ["M", "F", "Otro"], [0.48, 0.50, 0.02])
    peso_kg = None if rng.random() < 0.10 else int(np.clip(rng.normal(75, 15), 40, 150))
    altura_cm = None if rng.random() < 0.10 else int(np.clip(rng.normal(170, 10), 140, 205))

    ec = [e for e, p in CRONICAS_PROBS.items() if rng.random() < p]
    if not ec:
        ec = ["ninguna"] if rng.random() < 0.5 else []

    fumador = _pick(rng, ["no", "si", "exfumador"], [0.65, 0.22, 0.13])
    if sexo == "F" and 15 <= edad <= 55:
        embarazo = _pick(rng, ["si", "no"], [0.05, 0.95])
    else:
        embarazo = "na"

    motivos, weights = zip(*MOTIVO_WEIGHTS)
    motivo_principal = _pick(rng, list(motivos), list(weights))
    duracion_sintomas = _pick(rng, ["<24h", "1-3d", "4-7d", ">1sem"], [0.35, 0.35, 0.18, 0.12])
    intensidad_dolor = max(min(int(rng.geometric(0.25)) - 1, 10), 0)
    fiebre_subjetiva = _pick(rng, ["no", "leve", "alta"], [0.55, 0.30, 0.15])
    dificultad_respiratoria_subjetiva = _pick(rng, ["no", "leve", "moderada", "grave"], [0.60, 0.22, 0.13, 0.05])
    tos = _pick(rng, ["no", "seca", "con_flema"], [0.55, 0.28, 0.17])
    contacto_covid_reciente = _pick(rng, ["no", "no_se", "si"], [0.55, 0.30, 0.15])
    hora_envio = int(rng.integers(0, 24))

    return {
        "edad": edad,
        "sexo": sexo,
        "peso_kg": peso_kg,
        "altura_cm": altura_cm,
        "enfermedades_cronicas": "|".join(ec) if ec else "",
        "fumador": fumador,
        "embarazo": embarazo,
        "motivo_principal": motivo_principal,
        "duracion_sintomas": duracion_sintomas,
        "intensidad_dolor": intensidad_dolor,
        "fiebre_subjetiva": fiebre_subjetiva,
        "dificultad_respiratoria_subjetiva": dificultad_respiratoria_subjetiva,
        "tos": tos,
        "contacto_covid_reciente": contacto_covid_reciente,
        "hora_envio": hora_envio,
    }


def generate_csv(n: int, seed: int) -> bytes:
    rng = np.random.default_rng(seed)
    rows = [_sample_ficha(rng) for _ in range(n)]
    df = pd.DataFrame(rows, columns=FICHA_COLUMNS)
    buf = io.StringIO()
    df.to_csv(buf, index=False, encoding="utf-8")
    return buf.getvalue().encode("utf-8")


def generate_and_upload(n: int, seed: int, source_kind: str = "s3") -> dict:
    """Genera un CSV con N fichas y lo sube a `patients/seed-<ts>-<seed>.csv`."""
    source = make_raw_source(source_kind)
    data = generate_csv(n, seed)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    key = f"patients/seed-{ts}-s{seed}-n{n}.csv"
    source.put(key, data, content_type="text/csv")
    return {
        "source": source.describe(),
        "key": key,
        "rows": n,
        "seed": seed,
        "size_bytes": len(data),
    }
