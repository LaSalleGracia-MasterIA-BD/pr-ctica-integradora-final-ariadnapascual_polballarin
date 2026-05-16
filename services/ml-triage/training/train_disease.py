"""Entrenamiento del modelo de sospecha de enfermedad (DESIGN-08b §5).

Uso:
    python -m training.train_disease \
        --data data/synthetic/triage/ \
        --output models/disease/ \
        --seed 42

Produce un directorio `models/disease/dis-<YYYYMMDD>-<hash8>/` con:
  - model.joblib
  - metadata.json (hiperparámetros, hash dataset, versión, fecha)

evaluate_disease.py se encarga de métricas + matriz confusión 11×11.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np

try:
    from .model import (
        DISEASE_MODEL_HYPERPARAMS,
        build_disease_pipeline,
        load_dataset,
        split_features_disease_target,
    )
except ImportError:  # ejecución directa
    from model import (  # type: ignore
        DISEASE_MODEL_HYPERPARAMS,
        build_disease_pipeline,
        load_dataset,
        split_features_disease_target,
    )


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _short_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:8]


def _build_version(hiperparams: dict, dataset_hash: str) -> str:
    payload = json.dumps(hiperparams, sort_keys=True) + "|" + dataset_hash
    return f"dis-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{_short_hash(payload)}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Entrena el modelo de sospecha de enfermedad."
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=Path("data/synthetic/triage/"),
        help="Directorio con train.csv / val.csv / test.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("models/disease/"),
        help="Directorio raíz donde persistir el artefacto",
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)

    np.random.seed(args.seed)

    train_csv = args.data / "train.csv"
    val_csv = args.data / "val.csv"

    print(f"[train-disease] Cargando {train_csv}")
    df_train = load_dataset(train_csv)
    print(f"[train-disease] Cargando {val_csv}")
    df_val = load_dataset(val_csv)

    X_train, y_train = split_features_disease_target(df_train)
    X_val, y_val = split_features_disease_target(df_val)

    print("[train-disease] Construyendo pipeline y entrenando…")
    pipeline = build_disease_pipeline(random_state=args.seed)
    pipeline.fit(X_train, y_train)

    val_accuracy = float(pipeline.score(X_val, y_val))
    print(f"[train-disease] Accuracy preliminar en val: {val_accuracy:.4f}")

    dataset_hash = _short_hash(
        _file_sha256(train_csv) + _file_sha256(val_csv)
    )
    model_version = _build_version(DISEASE_MODEL_HYPERPARAMS, dataset_hash)

    artifact_dir = args.output / model_version
    artifact_dir.mkdir(parents=True, exist_ok=True)

    joblib.dump(pipeline, artifact_dir / "model.joblib")

    metadata = {
        "model_version": model_version,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "seed": args.seed,
        "hiperparameters": DISEASE_MODEL_HYPERPARAMS,
        "dataset_hash": dataset_hash,
        "val_accuracy_preliminary": val_accuracy,
        "train_rows": len(df_train),
        "val_rows": len(df_val),
        "n_classes": len(pipeline.classes_),
        "classes": list(pipeline.classes_),
    }
    with open(artifact_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    current_marker = args.output / "current"
    try:
        if current_marker.is_symlink() or current_marker.exists():
            current_marker.unlink()
        current_marker.symlink_to(artifact_dir.name, target_is_directory=True)
    except (OSError, NotImplementedError):
        (args.output / "current.txt").write_text(model_version, encoding="utf-8")

    print(f"[train-disease] Artefacto: {artifact_dir}")
    print(f"[train-disease] Versión:    {model_version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
