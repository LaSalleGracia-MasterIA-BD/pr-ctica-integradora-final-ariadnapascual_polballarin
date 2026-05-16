"""Schemas Pydantic de la API (SDD-05)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ---- Formulario de paciente (POST /patients) -------------------------------

class PatientFicha(BaseModel):
    """Ficha del formulario web de triaje. Validación estricta en el borde de la API;
    el pipeline interno vuelve a validar con las reglas YAML (fuente de verdad)."""

    edad: int = Field(..., ge=0, le=120)
    sexo: Literal["M", "F", "Otro"]
    peso_kg: int | None = Field(default=None, ge=1, le=500)
    altura_cm: int | None = Field(default=None, ge=40, le=250)
    enfermedades_cronicas: list[str] = Field(default_factory=list)
    fumador: Literal["no", "si", "exfumador"] = "no"
    embarazo: Literal["si", "no", "na"] = "na"
    motivo_principal: Literal[
        "dolor_toracico", "dificultad_respiratoria", "fiebre",
        "dolor_abdominal", "traumatismo", "sintomas_neurologicos", "otro",
    ]
    duracion_sintomas: Literal["<24h", "1-3d", "4-7d", ">1sem"]
    intensidad_dolor: int = Field(..., ge=0, le=10)
    fiebre_subjetiva: Literal["no", "leve", "alta"] = "no"
    dificultad_respiratoria_subjetiva: Literal["no", "leve", "moderada", "grave"] = "no"
    tos: Literal["no", "seca", "con_flema"] = "no"
    contacto_covid_reciente: Literal["si", "no", "no_se"] = "no_se"
    # Si el cliente no la envía, el backend la rellena al recibir
    hora_envio: int | None = Field(default=None, ge=0, le=23)


class TriagePrediction(BaseModel):
    predicted_class: Literal["Alta", "Media", "Baja"] | None = None
    probabilities: dict[str, float] | None = None
    model_version: str | None = None
    low_confidence: bool | None = None


class DiseaseDifferentialItem(BaseModel):
    """Una clase del diagnóstico diferencial (DESIGN-08b §6.1)."""
    label: str
    probability: float = Field(..., ge=0.0, le=1.0)


class DiseaseSuspicion(BaseModel):
    """Sospecha de enfermedad devuelta por el endpoint combinado de ml-triage.

    `differential` contiene 1, 2 o 3 etiquetas según la regla del 70 % (ver
    DESIGN-08b §6.2). El dashboard renderiza el bloque según `len(differential)`.
    """
    differential: list[DiseaseDifferentialItem] = Field(default_factory=list)
    low_confidence: bool | None = None
    model_version: str | None = None


class PatientResponse(BaseModel):
    status: Literal["completed", "pending_triage", "rejected"]
    run_id: str
    pseudo_id: str | None = None
    prediction: TriagePrediction | None = None
    disease: DiseaseSuspicion | None = None
    reasons: list[str] | None = None


# ---- Carga por lotes (POST /batch-runs) ------------------------------------

class BatchRunStarted(BaseModel):
    run_id: str
    status: Literal["started"]
    key: str
    rows_in_csv: int


# ---- Eventos de dominio (GET /batch-runs/{id}/events) ----------------------

class DomainEvent(BaseModel):
    timestamp: str
    service: str
    event: str
    level: str
    correlation_id: str
    message: str
    payload: dict = Field(default_factory=dict)


class DomainEventsResponse(BaseModel):
    run_id: str
    events: list[DomainEvent]
    total: int
    finished: bool  # True si existe un evento 'pipeline.run.end' o similar


# ---- Listado y detalle de pacientes (GET /patients, /patients/{id}) --------

class PatientListItem(BaseModel):
    """Resumen de paciente para el listado del dashboard."""
    pseudo_id: str
    edad: int
    sexo: str
    fumador: str | None = None
    enfermedades_cronicas: list[str] = Field(default_factory=list)
    # Del último ingreso
    motivo_principal: str | None = None
    fecha_ingreso: str | None = None
    # De la última predicción de triaje
    triage_class: str | None = None
    triage_probabilities: dict[str, float] | None = None
    triage_status: str | None = None
    model_version: str | None = None
    # De la última sospecha de enfermedad (top-1 para listado, completa en detalle)
    disease_top_label: str | None = None
    disease_top_probability: float | None = None
    disease_low_confidence: bool | None = None
    ingested_at: str


class PatientsListResponse(BaseModel):
    items: list[PatientListItem]
    total: int
    limit: int
    offset: int


class AdmissionDetail(BaseModel):
    id: int
    fecha_ingreso: str
    motivo_principal: str | None = None
    duracion_sintomas: str | None = None
    intensidad_dolor: int | None = None
    fiebre_subjetiva: str | None = None
    dificultad_respiratoria_subjetiva: str | None = None
    tos: str | None = None
    contacto_covid_reciente: str | None = None
    hora_envio: int | None = None
    source: str | None = None


class PredictionDetail(BaseModel):
    predicted_class: str | None = None
    probabilities: dict[str, float] | None = None
    model_version: str | None = None
    low_confidence: bool | None = None
    triage_status: str | None = None
    ingested_at: str | None = None


class DiseaseSuspicionDetail(BaseModel):
    """Sospecha completa para la ficha del paciente (DESIGN-08b §9.1)."""
    differential: list[DiseaseDifferentialItem] = Field(default_factory=list)
    low_confidence: bool | None = None
    model_version: str | None = None
    inference_status: str | None = None
    ingested_at: str | None = None


class PatientDetail(BaseModel):
    pseudo_id: str
    edad: int
    sexo: str
    peso_kg: int | None = None
    altura_cm: int | None = None
    enfermedades_cronicas: list[str] = Field(default_factory=list)
    fumador: str | None = None
    embarazo: str | None = None
    source: str | None = None
    ingested_at: str
    created_at: str | None = None
    admissions: list[AdmissionDetail] = Field(default_factory=list)
    latest_prediction: PredictionDetail | None = None
    latest_disease: DiseaseSuspicionDetail | None = None
