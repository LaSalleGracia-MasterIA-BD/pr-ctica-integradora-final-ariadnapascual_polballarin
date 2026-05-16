"""Configuración del servicio ml-triage leída de variables de entorno."""
from __future__ import annotations

import os
from pathlib import Path


def _getenv(name: str, default: str | None = None) -> str | None:
    val = os.getenv(name)
    return val if val is not None and val != "" else default


class Settings:
    """Variables de entorno consumidas por el servicio."""

    # Ruta al artefacto del modelo de triaje (directorio con model.joblib).
    # Si apunta al symlink/fichero `current`, se resuelve a la versión activa.
    model_path: Path = Path(
        _getenv("ML_TRIAGE_MODEL_PATH", "/app/models/triage/current") or ""
    )

    # Ruta al artefacto del modelo de enfermedad (DESIGN-08b §6.3).
    disease_model_path: Path = Path(
        _getenv("ML_DISEASE_MODEL_PATH", "/app/models/disease/current") or ""
    )

    # Umbral bajo el cual la predicción de triaje se marca como low_confidence
    # (DESIGN-08 §2).
    low_confidence_threshold: float = float(
        _getenv("ML_TRIAGE_LOW_CONFIDENCE_THRESHOLD", "0.50") or "0.50"
    )

    # Umbral bajo el cual la sospecha de enfermedad se marca como
    # low_confidence (DESIGN-08b §6.2): primary < 0.40.
    disease_low_confidence_threshold: float = float(
        _getenv("ML_DISEASE_LOW_CONFIDENCE_THRESHOLD", "0.40") or "0.40"
    )

    # Ratio mínimo respecto a la probabilidad principal para incluir una
    # clase secundaria/terciaria en el diagnóstico diferencial
    # (DESIGN-08b §6.2): cand.prob >= ratio * primary.prob.
    disease_differential_ratio: float = float(
        _getenv("ML_DISEASE_DIFFERENTIAL_RATIO", "0.70") or "0.70"
    )


settings = Settings()
