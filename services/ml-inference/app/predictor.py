from __future__ import annotations

import json
import logging
import os
import time
from io import BytesIO
from pathlib import Path
from typing import Dict

import torch
import torch.nn.functional as F
from PIL import Image
from torchvision import transforms as T

from training.model import build_model

from .config import (
    CLASSES,
    COVID_ALERT_THRESHOLD,
    IMAGENET_MEAN,
    IMAGENET_STD,
    IMG_SIZE,
    ML_DEVICE,
    MODEL_PATH,
)

logger = logging.getLogger(__name__)


class Predictor:
    """Cargador de modelo y generador de predicciones."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "initialized"):
            self.device = torch.device(ML_DEVICE)
            self._model_version: str = "unknown"
            self._backbone: str = "unknown"
            self._model: torch.nn.Module | None = None
            self._ready: bool = False

            self.eval_transform = T.Compose(
                [
                    T.Resize((IMG_SIZE, IMG_SIZE)),
                    T.ToTensor(),
                    T.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
                ]
            )
            self.initialized = True
            logger.info("Predictor initialized with device: %s", self.device)

    def _load_metadata(self, model_path: str) -> dict:
        metadata_path = Path(model_path).parent / "metadata.json"
        if not metadata_path.exists():
            return {}

        with open(metadata_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def load_model(self) -> bool:
        """Carga el modelo del volumen. Devuelve True si es exitoso."""
        try:
            if not os.path.exists(MODEL_PATH):
                logger.error("Model not found at %s", MODEL_PATH)
                self._ready = False
                return False

            metadata = self._load_metadata(MODEL_PATH)
            self._model_version = metadata.get("version", Path(MODEL_PATH).parent.name)
            self._backbone = metadata.get("config", {}).get("backbone", "efficientnet_b0")

            logger.info(
                "Loading model from %s | version=%s | backbone=%s",
                MODEL_PATH,
                self._model_version,
                self._backbone,
            )

            checkpoint = torch.load(MODEL_PATH, map_location=self.device)

            # pretrained=False: al servir no queremos descargar ImageNet.
            model = build_model(
                num_classes=len(CLASSES),
                backbone=self._backbone,
                freeze_backbone=False,
                pretrained=False,
            )

            if isinstance(checkpoint, dict):
                state_dict = checkpoint.get("state_dict") or checkpoint.get("model_state_dict")
                if state_dict is None:
                    raise ValueError("Invalid checkpoint: state_dict not found")
                model.load_state_dict(state_dict)
            elif isinstance(checkpoint, torch.nn.Module):
                model = checkpoint
            else:
                raise ValueError("Invalid checkpoint format")

            model.to(self.device)
            model.eval()

            self._model = model
            self._ready = True

            logger.info("Model loaded successfully. Version: %s", self._model_version)
            return True

        except Exception as exc:
            logger.exception("Error loading model: %s", exc)
            self._ready = False
            self._model = None
            return False

    @property
    def is_ready(self) -> bool:
        return self._ready and self._model is not None

    def predict(self, image_bytes: bytes) -> Dict:
        start_time = time.time()

        if not self.is_ready:
            raise RuntimeError("Model is not loaded")

        try:
            image = Image.open(BytesIO(image_bytes)).convert("RGB")

            if image.width < 64 or image.height < 64:
                raise ValueError(
                    f"Image too small: {image.width}x{image.height} (min: 64x64)"
                )

            img_tensor = self.eval_transform(image).unsqueeze(0).to(self.device)

            with torch.no_grad():
                logits = self._model(img_tensor)
                probs = F.softmax(logits, dim=1)[0].cpu().numpy()

            max_prob = float(probs.max())
            pred_idx = int(probs.argmax())
            predicted_class = CLASSES[pred_idx]

            if self._has_tie(probs):
                predicted_class = self._tiebreaker_rule(probs)

            covid_prob = float(probs[CLASSES.index("COVID-19")])
            low_confidence = max_prob < 0.50
            triggers_covid_alert = covid_prob > COVID_ALERT_THRESHOLD

            inference_time_ms = int((time.time() - start_time) * 1000)

            return {
                "predicted_class": predicted_class,
                "probabilities": {
                    cls: float(probs[i]) for i, cls in enumerate(CLASSES)
                },
                "model_version": self._model_version,
                "inference_time_ms": inference_time_ms,
                "low_confidence": low_confidence,
                "triggers_covid_alert": triggers_covid_alert,
            }

        except Exception as exc:
            logger.exception("Prediction error: %s", exc)
            raise

    def _has_tie(self, probs, threshold: float = 1e-9) -> bool:
        sorted_probs = sorted([float(p) for p in probs], reverse=True)
        return abs(sorted_probs[0] - sorted_probs[1]) <= threshold

    def _tiebreaker_rule(self, probs, threshold: float = 1e-9) -> str:
        """Regla de desempate: Sana < Neumonía < COVID-19."""
        severity = {"Sana": 0, "Neumonía": 1, "COVID-19": 2}
        max_p = float(max(probs))
        tied_classes = [
            CLASSES[i]
            for i, p in enumerate(probs)
            if abs(float(p) - max_p) <= threshold
        ]
        return max(tied_classes, key=lambda c: severity.get(c, -1))


_predictor = Predictor()


def get_predictor() -> Predictor:
    return _predictor


def is_model_ready() -> bool:
    return _predictor.is_ready