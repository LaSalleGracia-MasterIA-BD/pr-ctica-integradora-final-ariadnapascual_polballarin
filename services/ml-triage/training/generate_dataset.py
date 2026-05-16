"""Generador del dataset sintético de triaje (DESIGN-08 §4).

Produce:
  - {output}/train.csv, val.csv, test.csv (splits 70/15/15 estratificados)
  - {output}/metadata.json (semilla, conteos, hashes SHA-256, versión)

Uso:
    python -m training.generate_dataset --n 10000 --seed 42 \
        --output data/synthetic/triage/

Reproducibilidad: misma semilla → CSVs byte-idénticos (SDD-08 RF-7).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

try:
    from .rules import assign_triage_from_rules
    from .disease_rules import assign_disease_from_rules, DISEASE_CLASSES
except ImportError:  # ejecución directa `python training/generate_dataset.py`
    from rules import assign_triage_from_rules  # type: ignore
    from disease_rules import (  # type: ignore
        DISEASE_CLASSES,
        assign_disease_from_rules,
    )


GENERATOR_VERSION = "2.0"  # v2: añade columna disease_target (DESIGN-08b)

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

NOISE_TYPE_A_FRAC = 0.05  # etiqueta movida a clase adyacente
NOISE_TYPE_B_FRAC = 0.05  # síntomas contradictorios manteniendo target

MIN_CLASS_FRACTION_TRIAGE = 0.10   # 3 clases — todas por encima del 10 %
MIN_CLASS_FRACTION_DISEASE = 0.005  # 11 clases — protege de degeneración severa.
# Las minoritarias clínicas (asma_epoc, neumonia, apendicitis) son ~1-2 % por
# construcción de las reglas (producto de probabilidades de features). Es
# realista: en un servicio de admisión real, asma_epoc exacerbada es raro
# vs gastroenteritis. El desbalance se compensa con class_weight='balanced'
# en el entrenamiento, no manipulando la generación.

# Matriz de proximidad clínica para ruido tipo A sobre `disease_target`
# (DESIGN-08b §4.4). Cada origen lista sus destinos plausibles equiprobables.
DISEASE_NOISE_NEIGHBORS: dict[str, tuple[str, ...]] = {
    "gripe_resfriado": ("covid_sospecha", "neumonia_sospecha"),
    "neumonia_sospecha": ("covid_sospecha", "gripe_resfriado"),
    "covid_sospecha": ("gripe_resfriado", "neumonia_sospecha"),
    "gastroenteritis": ("apendicitis_sospecha", "inespecifico"),
    "apendicitis_sospecha": ("gastroenteritis",),
    "cefalea_migrana": ("ictus_sospecha", "inespecifico"),
    "ictus_sospecha": ("cefalea_migrana",),
    "cardiopatia_aguda_sospecha": ("inespecifico",),
    "asma_epoc_exacerbacion": ("neumonia_sospecha",),
    "traumatismo": ("inespecifico",),
    # `inespecifico` se trata como caso especial: random uniforme entre las 10 enfermedades
}


def _pick(rng: np.random.Generator, values: list[str], weights: list[float]) -> str:
    return str(rng.choice(values, p=weights))


def _sample_ficha(rng: np.random.Generator) -> dict[str, Any]:
    """Genera una ficha sintética con las distribuciones de DESIGN-08 §4.3."""
    mix = rng.random()
    if mix < 0.70:
        edad = int(rng.integers(18, 86))
    elif mix < 0.80:
        edad = int(rng.integers(0, 18))
    else:
        edad = int(rng.integers(86, 111))

    sexo = _pick(rng, ["M", "F", "Otro"], [0.48, 0.50, 0.02])

    peso_kg: int | None = (
        None
        if rng.random() < 0.10
        else int(np.clip(rng.normal(75, 15), 40, 150))
    )
    altura_cm: int | None = (
        None
        if rng.random() < 0.10
        else int(np.clip(rng.normal(170, 10), 140, 205))
    )

    # Multi-selección independiente de enfermedades crónicas
    ec: list[str] = [e for e, p in CRONICAS_PROBS.items() if rng.random() < p]
    if not ec:
        ec = ["ninguna"] if rng.random() < 0.5 else []

    fumador = _pick(rng, ["no", "si", "exfumador"], [0.65, 0.22, 0.13])

    if sexo == "F" and 15 <= edad <= 55:
        embarazo = _pick(rng, ["si", "no"], [0.05, 0.95])
    else:
        embarazo = "na"

    motivos, weights = zip(*MOTIVO_WEIGHTS)
    motivo_principal = _pick(rng, list(motivos), list(weights))

    duracion_sintomas = _pick(
        rng, ["<24h", "1-3d", "4-7d", ">1sem"], [0.35, 0.35, 0.18, 0.12]
    )

    # Geométrica truncada [0, 10], sesgada hacia bajos
    intensidad_dolor = min(int(rng.geometric(0.25)) - 1, 10)
    intensidad_dolor = max(intensidad_dolor, 0)

    fiebre_subjetiva = _pick(rng, ["no", "leve", "alta"], [0.55, 0.30, 0.15])
    dificultad_respiratoria_subjetiva = _pick(
        rng, ["no", "leve", "moderada", "grave"], [0.60, 0.22, 0.13, 0.05]
    )
    tos = _pick(rng, ["no", "seca", "con_flema"], [0.55, 0.28, 0.17])
    contacto_covid_reciente = _pick(
        rng, ["no", "no_se", "si"], [0.55, 0.30, 0.15]
    )
    hora_envio = int(rng.integers(0, 24))

    return {
        "edad": edad,
        "sexo": sexo,
        "peso_kg": peso_kg,
        "altura_cm": altura_cm,
        "enfermedades_cronicas": ec,
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


def _noisify_disease(label: str, rng: np.random.Generator) -> str:
    """Aplica una transición de ruido tipo A a la etiqueta de enfermedad.

    Para `inespecifico` elige uniformemente entre las 10 enfermedades
    (DESIGN-08b §4.4); para el resto, elige uniformemente uno de los
    vecinos clínicamente plausibles definidos en `DISEASE_NOISE_NEIGHBORS`.
    """
    if label == "inespecifico":
        diseases = [d for d in DISEASE_CLASSES if d != "inespecifico"]
        return str(rng.choice(diseases))
    neighbors = DISEASE_NOISE_NEIGHBORS.get(label)
    if not neighbors:
        return label  # sin transición definida — no toca
    return str(rng.choice(neighbors))


def _apply_noise(df: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Ruido tipo A (etiqueta adyacente, **afecta a ambos targets**) +
    tipo B (síntomas contradictorios) sobre muestras disjuntas. Total ~10 %.

    El ruido tipo A mueve `target` (Alta/Media/Baja) a una clase adyacente y
    `disease_target` según la matriz de proximidad clínica. Las filas
    afectadas son las mismas para ambos targets — coherencia interna.
    """
    n = len(df)
    n_a = int(n * NOISE_TYPE_A_FRAC)
    n_b = int(n * NOISE_TYPE_B_FRAC)

    all_idx = np.arange(n)
    rng.shuffle(all_idx)
    idx_a = all_idx[:n_a]
    idx_b = all_idx[n_a : n_a + n_b]

    # Tipo A: etiqueta adyacente, sobre ambos targets
    for i in idx_a:
        current = df.at[i, "target"]
        if current == "Alta":
            df.at[i, "target"] = "Media"
        elif current == "Baja":
            df.at[i, "target"] = "Media"
        else:  # Media → aleatoriamente Alta o Baja
            df.at[i, "target"] = "Alta" if rng.random() < 0.5 else "Baja"

        df.at[i, "disease_target"] = _noisify_disease(
            df.at[i, "disease_target"], rng
        )

    # Tipo B: contradecir síntomas, ambos targets originales se quedan
    for i in idx_b:
        dolor = df.at[i, "intensidad_dolor"]
        df.at[i, "intensidad_dolor"] = 0 if dolor > 5 else 10
        df.at[i, "fiebre_subjetiva"] = "no"

    return df


def generate(n: int, seed: int) -> pd.DataFrame:
    """Genera n fichas con etiquetas por reglas (triaje + enfermedad) + ruido."""
    rng = np.random.default_rng(seed)
    fichas = [_sample_ficha(rng) for _ in range(n)]
    df = pd.DataFrame(fichas)
    df["target"] = df.apply(
        lambda r: assign_triage_from_rules(r.to_dict()), axis=1
    )
    df["disease_target"] = df.apply(
        lambda r: assign_disease_from_rules(r.to_dict()), axis=1
    )
    df = _apply_noise(df, rng)
    return df


def split_stratified(
    df: pd.DataFrame, seed: int
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """70/15/15 estratificado por `target` (triaje).

    No estratificamos también por `disease_target`: con 11 clases minoritarias
    el producto cartesiano daría grupos sin muestras suficientes. Estratificar
    por triaje y verificar manualmente la distribución de enfermedad post-split
    es el compromiso (ver `_assert_class_balance`).
    """
    train, temp = train_test_split(
        df, test_size=0.30, stratify=df["target"], random_state=seed
    )
    val, test = train_test_split(
        temp, test_size=0.50, stratify=temp["target"], random_state=seed
    )
    return (
        train.reset_index(drop=True),
        val.reset_index(drop=True),
        test.reset_index(drop=True),
    )


def save_csv(df: pd.DataFrame, path: Path) -> None:
    """Serializa con `enfermedades_cronicas` como 'a|b|c' (readers deben split)."""
    df = df.copy()
    df["enfermedades_cronicas"] = df["enfermedades_cronicas"].apply(
        lambda xs: "|".join(xs) if xs else ""
    )
    df.to_csv(path, index=False, encoding="utf-8")


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _assert_class_balance(
    name: str,
    df: pd.DataFrame,
    column: str,
    min_fraction: float,
) -> None:
    dist = df[column].value_counts(normalize=True).to_dict()
    if any(p < min_fraction for p in dist.values()):
        raise RuntimeError(
            f"Distribución degenerada en split {name} ({column}): {dist}. "
            f"Requisito: cada clase >= {min_fraction:.1%}."
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generador sintético de dataset de triaje."
    )
    parser.add_argument("--n", type=int, default=10_000, help="Número total de fichas")
    parser.add_argument("--seed", type=int, default=42, help="Semilla aleatoria")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/synthetic/triage/"),
        help="Directorio de salida",
    )
    args = parser.parse_args(argv)

    random.seed(args.seed)
    np.random.seed(args.seed)

    args.output.mkdir(parents=True, exist_ok=True)

    df = generate(args.n, args.seed)
    train, val, test = split_stratified(df, args.seed)

    for name, d in [("train", train), ("val", val), ("test", test)]:
        _assert_class_balance(name, d, "target", MIN_CLASS_FRACTION_TRIAGE)
        _assert_class_balance(
            name, d, "disease_target", MIN_CLASS_FRACTION_DISEASE
        )

    save_csv(train, args.output / "train.csv")
    save_csv(val, args.output / "val.csv")
    save_csv(test, args.output / "test.csv")

    metadata = {
        "seed": args.seed,
        "n": args.n,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "generator_version": GENERATOR_VERSION,
        "class_distribution_triage": {
            "train": train["target"].value_counts(normalize=True).to_dict(),
            "val": val["target"].value_counts(normalize=True).to_dict(),
            "test": test["target"].value_counts(normalize=True).to_dict(),
        },
        "class_distribution_disease": {
            "train": train["disease_target"].value_counts(normalize=True).to_dict(),
            "val": val["disease_target"].value_counts(normalize=True).to_dict(),
            "test": test["disease_target"].value_counts(normalize=True).to_dict(),
        },
        "rows_per_split": {
            "train": len(train),
            "val": len(val),
            "test": len(test),
        },
        "file_sha256": {
            "train.csv": file_sha256(args.output / "train.csv"),
            "val.csv": file_sha256(args.output / "val.csv"),
            "test.csv": file_sha256(args.output / "test.csv"),
        },
    }
    with open(args.output / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    print(f"[ok] Generados {args.n} registros en {args.output}")
    print(f"     Triaje (train):    {metadata['class_distribution_triage']['train']}")
    print(f"     Enfermedad (train): {metadata['class_distribution_disease']['train']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
