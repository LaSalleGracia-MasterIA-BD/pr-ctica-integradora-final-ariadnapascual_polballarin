from pydantic import BaseModel, Field
from typing import Literal, Dict

class RadiographyPredictionOutput(BaseModel):
    """Esquema de salida del endpoint /predict"""
    predicted_class: Literal["Sana", "Neumonía", "COVID-19"]
    probabilities: Dict[str, float] = Field(default_factory=dict)
    model_version: str
    inference_time_ms: int
    low_confidence: bool = False
    triggers_covid_alert: bool = False

    class Config:
        json_schema_extra = {
            "example": {
                "predicted_class": "COVID-19",
                "probabilities": {"Sana": 0.05, "Neumonía": 0.10, "COVID-19": 0.85},
                "model_version": "rx-20260425-a1b2c3d4",
                "inference_time_ms": 245,
                "low_confidence": False,
                "triggers_covid_alert": True,
            }
        }
