"""Predictor combinado: triaje + sospecha de enfermedad (DESIGN-08b §6.3).

Carga los dos artefactos al instanciar:
  - Modelo de triaje (3 clases Alta/Media/Baja) desde ML_TRIAGE_MODEL_PATH
  - Modelo de enfermedad (11 clases) desde ML_DISEASE_MODEL_PATH

Si cualquiera de los dos falla al cargar, el predictor queda unhealthy
y `/health` devuelve 503 (no se ofrece servicio degradado: simplifica el
contrato del endpoint combinado).

Uso:
    predictor = get_predictor()
    result = predictor.predict(ficha)  # dict con keys: triage, disease, inference_time_ms
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from threading import Lock
from typing import Any

import joblib

from app.config import settings
from app.features import CLASSES, ficha_to_feature_row

logger = logging.getLogger(__name__)

_CLASS_GRAVITY_ORDER = {"Baja": 0, "Media": 1, "Alta": 2}  # mayor = más grave


def _resolve_model_dir(path: Path) -> Path:
    """Resuelve el directorio del artefacto aceptando:
    - una ruta directa a un directorio con model.joblib
    - un symlink (p. ej. current -> dis-YYYYMMDD-hash8)
    - un fichero de texto `current.txt` con el nombre del directorio activo
      (fallback de Windows sin permisos de symlink).
    """
    p = path
    if p.is_symlink():
        p = p.resolve()
    if p.is_dir():
        return p
    if p.name == "current":
        candidate_txt = p.parent / "current.txt"
        if candidate_txt.is_file():
            name = candidate_txt.read_text(encoding="utf-8").strip()
            if name:
                resolved = p.parent / name
                if resolved.is_dir():
                    return resolved
    raise FileNotFoundError(f"Artefacto no encontrado o no es directorio: {path}")


def _load_artifact(model_path: Path, kind: str) -> tuple[Any, str]:
    """Carga un artefacto y devuelve (pipeline, model_version)."""
    model_dir = _resolve_model_dir(model_path)
    logger.info("[%s] Cargando modelo desde %s", kind, model_dir)
    pipeline = joblib.load(model_dir / "model.joblib")
    meta_path = model_dir / "metadata.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        model_version = meta.get("model_version", model_dir.name)
    else:
        model_version = model_dir.name
    logger.info("[%s] Modelo cargado: version=%s", kind, model_version)
    return pipeline, model_version


class CombinedPredictor:
    """Carga ambos artefactos y expone `predict(ficha) -> dict`."""

    def __init__(
        self,
        triage_model_path: Path,
        disease_model_path: Path,
        triage_low_confidence_threshold: float,
        disease_low_confidence_threshold: float,
        disease_differential_ratio: float,
    ) -> None:
        self._triage_path = triage_model_path
        self._disease_path = disease_model_path
        self._triage_low = triage_low_confidence_threshold
        self._disease_low = disease_low_confidence_threshold
        self._diff_ratio = disease_differential_ratio

        self._triage_pipeline: Any | None = None
        self._disease_pipeline: Any | None = None
        self._triage_version: str = "unknown"
        self._disease_version: str = "unknown"
        self._load_error: Exception | None = None
        self._load()

    def _load(self) -> None:
        try:
            self._triage_pipeline, self._triage_version = _load_artifact(
                self._triage_path, "triage"
            )
            self._disease_pipeline, self._disease_version = _load_artifact(
                self._disease_path, "disease"
            )
        except Exception as exc:  # pragma: no cover — queda en health 503
            logger.exception("Fallo al cargar uno o ambos modelos")
            self._load_error = exc
            self._triage_pipeline = None
            self._disease_pipeline = None

    # ---- Introspección ------------------------------------------------------

    def is_healthy(self) -> bool:
        return self._triage_pipeline is not None and self._disease_pipeline is not None

    @property
    def triage_version(self) -> str:
        return self._triage_version

    @property
    def disease_version(self) -> str:
        return self._disease_version

    @property
    def load_error(self) -> Exception | None:
        return self._load_error

    # ---- Inferencia ---------------------------------------------------------

    def _predict_triage(self, X) -> dict:  # noqa: ANN001 — DataFrame interno
        start = time.perf_counter()
        pipeline = self._triage_pipeline
        classes = list(pipeline.classes_)
        proba = pipeline.predict_proba(X)[0]

        proba_by_class: dict[str, float] = {c: float(p) for c, p in zip(classes, proba)}
        ordered = {cls: float(proba_by_class.get(cls, 0.0)) for cls in CLASSES}

        # Regla de desempate prudente (mayor gravedad ante empate).
        max_p = max(ordered.values())
        candidates = [cls for cls, p in ordered.items() if abs(p - max_p) <= 1e-9]
        predicted = (
            max(candidates, key=lambda c: _CLASS_GRAVITY_ORDER[c])
            if len(candidates) > 1
            else candidates[0]
        )

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return {
            "predicted_class": predicted,
            "probabilities": {
                "alta": ordered["Alta"],
                "media": ordered["Media"],
                "baja": ordered["Baja"],
            },
            "model_version": self._triage_version,
            "inference_time_ms": elapsed_ms,
            "low_confidence": max_p < self._triage_low,
        }

    def _predict_disease(self, X) -> dict:  # noqa: ANN001
        start = time.perf_counter()
        pipeline = self._disease_pipeline
        classes = list(pipeline.classes_)
        proba = pipeline.predict_proba(X)[0]

        # Pares (label, prob) ordenados desc por probabilidad
        pairs = sorted(
            ((c, float(p)) for c, p in zip(classes, proba)),
            key=lambda kv: kv[1],
            reverse=True,
        )
        primary_label, primary_prob = pairs[0]
        threshold = self._diff_ratio * primary_prob

        differential = [{"label": primary_label, "probability": primary_prob}]
        for cand_label, cand_prob in pairs[1:3]:
            if cand_prob >= threshold:
                differential.append({"label": cand_label, "probability": cand_prob})
            else:
                break

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return {
            "differential": differential,
            "low_confidence": primary_prob < self._disease_low,
            "model_version": self._disease_version,
            "inference_time_ms": elapsed_ms,
        }

    def predict(self, ficha: dict) -> dict:
        if not self.is_healthy():
            raise RuntimeError("Predictor unhealthy: uno o ambos modelos no cargados")
        start = time.perf_counter()

        # Una sola conversión a feature row reutilizada por ambos modelos.
        X = ficha_to_feature_row(ficha)

        triage = self._predict_triage(X)
        disease = self._predict_disease(X)

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return {
            "triage": triage,
            "disease": disease,
            "inference_time_ms": elapsed_ms,
        }


# ---- Singleton lazy --------------------------------------------------------

_predictor_lock = Lock()
_predictor: CombinedPredictor | None = None


def get_predictor() -> CombinedPredictor:
    global _predictor
    with _predictor_lock:
        if _predictor is None:
            _predictor = CombinedPredictor(
                triage_model_path=settings.model_path,
                disease_model_path=settings.disease_model_path,
                triage_low_confidence_threshold=settings.low_confidence_threshold,
                disease_low_confidence_threshold=settings.disease_low_confidence_threshold,
                disease_differential_ratio=settings.disease_differential_ratio,
            )
        return _predictor
