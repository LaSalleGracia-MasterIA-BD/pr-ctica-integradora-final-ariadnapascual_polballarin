"""Pipeline sklearn y loader compartidos por train / evaluate / cross_validate.

Las constantes de features viven en `app/features.py` para tener una única
fuente de verdad compartida con el servicio HTTP.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder

try:
    from app.features import (
        ALL_FEATURE_COLS,
        CATEGORICAL_COLS,
        CHRONIC_BOOL_COLS,
        CHRONIC_LABELS,
        CLASSES,
        NUMERIC_COLS,
        TARGET_COL,
        expand_chronic_from_string,
    )
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.features import (  # type: ignore
        ALL_FEATURE_COLS,
        CATEGORICAL_COLS,
        CHRONIC_BOOL_COLS,
        CHRONIC_LABELS,
        CLASSES,
        NUMERIC_COLS,
        TARGET_COL,
        expand_chronic_from_string,
    )


MODEL_HYPERPARAMS: dict = {
    "max_iter": 300,
    "learning_rate": 0.05,
    "max_depth": 6,
    "min_samples_leaf": 30,
    "l2_regularization": 0.1,
    "early_stopping": True,
    "validation_fraction": 0.1,
    "n_iter_no_change": 20,
    "random_state": 42,
}

DISEASE_MODEL_HYPERPARAMS: dict = {
    "max_iter": 400,
    "learning_rate": 0.05,
    "max_depth": 6,
    "min_samples_leaf": 20,
    "l2_regularization": 0.1,
    "early_stopping": True,
    "validation_fraction": 0.1,
    "n_iter_no_change": 25,
    "class_weight": "balanced",
    "random_state": 42,
}

DISEASE_TARGET_COL = "disease_target"


def load_dataset(csv_path: Path | str) -> pd.DataFrame:
    """Lee un CSV generado por `generate_dataset.py` y expande enfermedades crónicas."""
    df = pd.read_csv(csv_path)
    df["enfermedades_cronicas"] = df["enfermedades_cronicas"].fillna("").astype(str)

    expanded = (
        df["enfermedades_cronicas"]
        .apply(expand_chronic_from_string)
        .apply(pd.Series)
    )

    df = pd.concat([df.drop(columns=["enfermedades_cronicas"]), expanded], axis=1)
    return df


def split_features_target(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    missing = [c for c in ALL_FEATURE_COLS + [TARGET_COL] if c not in df.columns]
    if missing:
        raise KeyError(f"Columnas faltantes en dataset: {missing}")

    X = df[ALL_FEATURE_COLS].copy()
    y = df[TARGET_COL].copy()
    return X, y


def split_features_disease_target(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    missing = [c for c in ALL_FEATURE_COLS + [DISEASE_TARGET_COL] if c not in df.columns]
    if missing:
        raise KeyError(f"Columnas faltantes en dataset: {missing}")

    X = df[ALL_FEATURE_COLS].copy()
    y = df[DISEASE_TARGET_COL].copy()
    return X, y


def _build_preprocessor() -> ColumnTransformer:
    return ColumnTransformer(
        transformers=[
            (
                "num",
                SimpleImputer(strategy="median"),
                NUMERIC_COLS,
            ),
            (
                "cat",
                OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1),
                CATEGORICAL_COLS,
            ),
            (
                "bool",
                "passthrough",
                CHRONIC_BOOL_COLS,
            ),
        ],
        remainder="drop",
    )


def build_pipeline(random_state: int = 42) -> Pipeline:
    hp = dict(MODEL_HYPERPARAMS)
    hp["random_state"] = random_state

    clf = HistGradientBoostingClassifier(**hp)
    return Pipeline(
        [
            ("preprocessor", _build_preprocessor()),
            ("clf", clf),
        ]
    )


def build_disease_pipeline(random_state: int = 42) -> Pipeline:
    hp = dict(DISEASE_MODEL_HYPERPARAMS)
    hp["random_state"] = random_state

    clf = HistGradientBoostingClassifier(**hp)
    return Pipeline(
        [
            ("preprocessor", _build_preprocessor()),
            ("clf", clf),
        ]
    )


__all__ = [
    "NUMERIC_COLS",
    "CATEGORICAL_COLS",
    "CHRONIC_LABELS",
    "CHRONIC_BOOL_COLS",
    "ALL_FEATURE_COLS",
    "TARGET_COL",
    "CLASSES",
    "MODEL_HYPERPARAMS",
    "DISEASE_MODEL_HYPERPARAMS",
    "DISEASE_TARGET_COL",
    "load_dataset",
    "split_features_target",
    "split_features_disease_target",
    "build_pipeline",
    "build_disease_pipeline",
]