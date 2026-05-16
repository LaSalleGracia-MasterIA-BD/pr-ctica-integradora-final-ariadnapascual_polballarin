"""Servicio HTTP ml-triage: aloja los dos modelos tabulares (DESIGN-08b §6).

Endpoints:
  - GET  /health    -> 200 si ambos modelos cargados, 503 si no
  - POST /predict   -> predicción combinada {triage, disease, inference_time_ms}

El servicio aloja **dos modelos**:
  - Triaje (`tri-...`):    Alta/Media/Baja
  - Enfermedad (`dis-...`): 11 clases de sospecha clínica

El nombre `ml-triage` se mantiene por estabilidad de la infra (Docker,
compose, env vars), pero el contenido del servicio es ahora doble.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Response, status

from app.predictor import get_predictor
from app.schemas import PredictOutput, TriageInput

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ml-triage")

app = FastAPI(title="ml-triage", version="2.0.0")


@app.on_event("startup")
def _startup() -> None:
    # Fuerza la carga al arranque para evitar latencia en el primer /predict.
    predictor = get_predictor()
    if predictor.is_healthy():
        logger.info(
            "ml-triage listo (triage=%s, disease=%s)",
            predictor.triage_version,
            predictor.disease_version,
        )
    else:
        logger.error("ml-triage arrancó UNHEALTHY: %s", predictor.load_error)


@app.get("/health")
def health(response: Response) -> dict:
    predictor = get_predictor()
    if not predictor.is_healthy():
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "unhealthy",
            "reason": str(predictor.load_error) if predictor.load_error else "model not loaded",
        }
    return {
        "status": "ok",
        "triage_version": predictor.triage_version,
        "disease_version": predictor.disease_version,
    }


@app.post("/predict", response_model=PredictOutput)
def predict(ficha: TriageInput) -> PredictOutput:
    predictor = get_predictor()
    if not predictor.is_healthy():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Predictor no disponible: uno o ambos modelos no cargados.",
        )
    result = predictor.predict(ficha.model_dump())
    return PredictOutput(**result)
