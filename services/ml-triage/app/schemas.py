"""Schemas Pydantic del servicio ml-triage (SDD-08 RF-1 input, RF-14 output)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


Sexo = Literal["M", "F", "Otro"]
Fumador = Literal["no", "si", "exfumador"]
Embarazo = Literal["si", "no", "na"]
MotivoPrincipal = Literal[
    "dolor_toracico",
    "dificultad_respiratoria",
    "fiebre",
    "dolor_abdominal",
    "traumatismo",
    "sintomas_neurologicos",
    "otro",
]
Duracion = Literal["<24h", "1-3d", "4-7d", ">1sem"]
FiebreSubjetiva = Literal["no", "leve", "alta"]
DifRespiratoria = Literal["no", "leve", "moderada", "grave"]
Tos = Literal["no", "seca", "con_flema"]
ContactoCovid = Literal["si", "no", "no_se"]
CronicaLabel = Literal[
    "diabetes",
    "hipertension",
    "asma_epoc",
    "cardiopatia",
    "inmunosupresion",
    "ninguna",
]
PredictedClass = Literal["Alta", "Media", "Baja"]


class TriageInput(BaseModel):
    """Ficha del paciente tal y como llega del formulario web (SDD-08 RF-1).

    Los 14 primeros campos los rellena el paciente. `hora_envio` puede llegar
    del cliente o ser rellenada por el servidor al recibir el POST.
    """

    edad: int = Field(..., ge=0, le=120)
    sexo: Sexo
    peso_kg: int | None = Field(default=None, ge=1, le=500)
    altura_cm: int | None = Field(default=None, ge=40, le=250)
    enfermedades_cronicas: list[CronicaLabel] = Field(default_factory=list)
    fumador: Fumador = "no"
    embarazo: Embarazo = "na"
    motivo_principal: MotivoPrincipal
    duracion_sintomas: Duracion
    intensidad_dolor: int = Field(..., ge=0, le=10)
    fiebre_subjetiva: FiebreSubjetiva = "no"
    dificultad_respiratoria_subjetiva: DifRespiratoria = "no"
    tos: Tos = "no"
    contacto_covid_reciente: ContactoCovid = "no_se"
    hora_envio: int = Field(..., ge=0, le=23)


class ProbabilitiesByClass(BaseModel):
    alta: float = Field(..., ge=0.0, le=1.0)
    media: float = Field(..., ge=0.0, le=1.0)
    baja: float = Field(..., ge=0.0, le=1.0)


class TriageOutput(BaseModel):
    """Bloque de triaje del endpoint POST /predict (DESIGN-08b §6.1)."""

    predicted_class: PredictedClass
    probabilities: ProbabilitiesByClass
    model_version: str
    inference_time_ms: int
    low_confidence: bool


class DiseasePrediction(BaseModel):
    """Una etiqueta del diagnóstico diferencial (DESIGN-08b §6.1)."""

    label: str
    probability: float = Field(..., ge=0.0, le=1.0)


class DiseaseOutput(BaseModel):
    """Bloque de sospecha de enfermedad del endpoint POST /predict.

    `differential` contiene 1, 2 o 3 etiquetas según la regla del 70 %
    (DESIGN-08b §6.2): se incluye una clase secundaria si su probabilidad
    es ≥ 0.70 × probabilidad de la primaria.
    """

    differential: list[DiseasePrediction] = Field(..., min_length=1, max_length=3)
    low_confidence: bool
    model_version: str
    inference_time_ms: int


class PredictOutput(BaseModel):
    """Respuesta combinada del endpoint POST /predict (DESIGN-08b §6.1).

    Devuelve triaje + sospecha de enfermedad con sus respectivas versiones
    de modelo, sobre la misma ficha.
    """

    triage: TriageOutput
    disease: DiseaseOutput
    inference_time_ms: int
