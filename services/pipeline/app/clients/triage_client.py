"""Cliente HTTP para el servicio ml-triage.

Normaliza la ficha antes de enviarla al modelo para evitar errores 422 por:
- NaN de pandas/Dask.
- Campos numéricos vacíos.
- Enfermedades crónicas serializadas como string.
- Diferencias menores entre valores humanos y valores internos.

Endpoint vigente:
    POST http://ml-triage:8002/predict

Respuesta:
    {
      "triage": {...},
      "disease": {...},
      "inference_time_ms": int
    }
"""
from __future__ import annotations

import logging
import math
import os
from datetime import datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class MlServiceUnavailable(RuntimeError):
    """Error controlado cuando el servicio ML no responde o rechaza la ficha."""


# Alias histórico para compatibilidad con código anterior.
TriageUnavailable = MlServiceUnavailable


def _ml_triage_url() -> str:
    base = os.getenv("ML_TRIAGE_URL", "http://ml-triage:8002").rstrip("/")
    if base.endswith("/predict"):
        return base
    return f"{base}/predict"


def _is_missing(value: Any) -> bool:
    """Detecta None, NaN, pd.NA, strings vacíos y variantes textuales de null."""
    if value is None:
        return True

    try:
        if isinstance(value, float) and math.isnan(value):
            return True
    except TypeError:
        pass

    text = str(value).strip()
    return text == "" or text.lower() in {"nan", "none", "null", "<na>"}


def _as_int_or_none(value: Any) -> int | None:
    if _is_missing(value):
        return None
    return int(float(value))


def _as_required_int(value: Any, default: int = 0) -> int:
    if _is_missing(value):
        return default
    return int(float(value))


def _as_str(value: Any, default: str) -> str:
    if _is_missing(value):
        return default
    return str(value).strip()


def _normalize_sexo(value: Any) -> str:
    raw = _as_str(value, "Otro")
    mapping = {
        "masculino": "M",
        "hombre": "M",
        "m": "M",
        "M": "M",
        "femenino": "F",
        "mujer": "F",
        "f": "F",
        "F": "F",
        "otro": "Otro",
        "otros": "Otro",
        "na": "Otro",
    }
    return mapping.get(raw, mapping.get(raw.lower(), "Otro"))


def _normalize_binary_si_no(value: Any, default: str = "no") -> str:
    raw = _as_str(value, default).lower()
    mapping = {
        "sí": "si",
        "si": "si",
        "s": "si",
        "true": "si",
        "1": "si",
        "yes": "si",
        "no": "no",
        "n": "no",
        "false": "no",
        "0": "no",
    }
    return mapping.get(raw, default)


def _normalize_fumador(value: Any) -> str:
    raw = _as_str(value, "no").lower()
    mapping = {
        "no": "no",
        "si": "si",
        "sí": "si",
        "fumador": "si",
        "exfumador": "exfumador",
        "ex-fumador": "exfumador",
        "ex fumador": "exfumador",
    }
    return mapping.get(raw, "no")


def _normalize_embarazo(value: Any) -> str:
    raw = _as_str(value, "na").lower()
    mapping = {
        "si": "si",
        "sí": "si",
        "no": "no",
        "na": "na",
        "n/a": "na",
        "no_aplica": "na",
        "no aplica": "na",
        "ninguno": "na",
        "ninguna": "na",
    }
    return mapping.get(raw, "na")


def _normalize_motivo(value: Any) -> str:
    raw = _as_str(value, "otro").lower()
    mapping = {
        "dolor torácico": "dolor_toracico",
        "dolor_toracico": "dolor_toracico",
        "dolor toracico": "dolor_toracico",
        "dificultad respiratoria": "dificultad_respiratoria",
        "dificultad_respiratoria": "dificultad_respiratoria",
        "fiebre": "fiebre",
        "dolor abdominal": "dolor_abdominal",
        "dolor_abdominal": "dolor_abdominal",
        "traumatismo": "traumatismo",
        "síntomas neurológicos": "sintomas_neurologicos",
        "sintomas neurologicos": "sintomas_neurologicos",
        "sintomas_neurologicos": "sintomas_neurologicos",
        "otro": "otro",
    }
    return mapping.get(raw, "otro")


def _normalize_duracion(value: Any) -> str:
    raw = _as_str(value, "<24h").lower()
    mapping = {
        "<24h": "<24h",
        "menos de 24 h": "<24h",
        "menos de 24h": "<24h",
        "1-3d": "1-3d",
        "1-3 días": "1-3d",
        "1-3 dias": "1-3d",
        "4-7d": "4-7d",
        "4-7 días": "4-7d",
        "4-7 dias": "4-7d",
        ">1sem": ">1sem",
        "más de 1 semana": ">1sem",
        "mas de 1 semana": ">1sem",
    }
    return mapping.get(raw, "<24h")


def _normalize_fiebre(value: Any) -> str:
    raw = _as_str(value, "no").lower()
    mapping = {
        "no": "no",
        "ninguna": "no",
        "leve": "leve",
        "alta": "alta",
    }
    return mapping.get(raw, "no")


def _normalize_dificultad_respiratoria(value: Any) -> str:
    raw = _as_str(value, "no").lower()
    mapping = {
        "no": "no",
        "ninguna": "no",
        "leve": "leve",
        "moderada": "moderada",
        "grave": "grave",
    }
    return mapping.get(raw, "no")


def _normalize_tos(value: Any) -> str:
    raw = _as_str(value, "no").lower()
    mapping = {
        "no": "no",
        "ninguna": "no",
        "seca": "seca",
        "con flema": "con_flema",
        "con_flema": "con_flema",
    }
    return mapping.get(raw, "no")


def _normalize_contacto_covid(value: Any) -> str:
    raw = _as_str(value, "no_se").lower()
    mapping = {
        "si": "si",
        "sí": "si",
        "no": "no",
        "no_se": "no_se",
        "no sé": "no_se",
        "no se": "no_se",
        "desconocido": "no_se",
    }
    return mapping.get(raw, "no_se")


def _normalize_enfermedades(value: Any) -> list[str]:
    allowed = {
        "diabetes",
        "hipertension",
        "asma_epoc",
        "cardiopatia",
        "inmunosupresion",
        "ninguna",
    }

    if _is_missing(value):
        return []

    if isinstance(value, list):
        raw_items = value
    elif isinstance(value, tuple):
        raw_items = list(value)
    else:
        text = str(value).strip()
        if text.lower() in {"", "nan", "none", "null", "<na>"}:
            return []
        # CSV del generador: "diabetes|hipertension"
        if "|" in text:
            raw_items = text.split("|")
        elif "," in text:
            raw_items = text.split(",")
        else:
            raw_items = [text]

    normalized: list[str] = []
    for item in raw_items:
        if _is_missing(item):
            continue
        label = str(item).strip().lower()
        label = label.replace(" ", "_").replace("-", "_")
        label = label.replace("hipertensión", "hipertension")
        label = label.replace("cardiopatía", "cardiopatia")

        if label in allowed and label not in normalized:
            normalized.append(label)

    # Si hay patologías reales, no hace falta enviar "ninguna".
    if len(normalized) > 1 and "ninguna" in normalized:
        normalized.remove("ninguna")

    return normalized


def normalize_ficha_for_ml(ficha: dict[str, Any]) -> dict[str, Any]:
    """Convierte una fila del pipeline en el contrato exacto de ml-triage."""
    now_hour = datetime.now().hour

    payload = {
        "edad": _as_required_int(ficha.get("edad"), default=0),
        "sexo": _normalize_sexo(ficha.get("sexo")),
        "peso_kg": _as_int_or_none(ficha.get("peso_kg")),
        "altura_cm": _as_int_or_none(ficha.get("altura_cm")),
        "enfermedades_cronicas": _normalize_enfermedades(
            ficha.get("enfermedades_cronicas")
        ),
        "fumador": _normalize_fumador(ficha.get("fumador")),
        "embarazo": _normalize_embarazo(ficha.get("embarazo")),
        "motivo_principal": _normalize_motivo(ficha.get("motivo_principal")),
        "duracion_sintomas": _normalize_duracion(ficha.get("duracion_sintomas")),
        "intensidad_dolor": _as_required_int(
            ficha.get("intensidad_dolor"),
            default=0,
        ),
        "fiebre_subjetiva": _normalize_fiebre(ficha.get("fiebre_subjetiva")),
        "dificultad_respiratoria_subjetiva": _normalize_dificultad_respiratoria(
            ficha.get("dificultad_respiratoria_subjetiva")
        ),
        "tos": _normalize_tos(ficha.get("tos")),
        "contacto_covid_reciente": _normalize_contacto_covid(
            ficha.get("contacto_covid_reciente")
        ),
        "hora_envio": _as_required_int(ficha.get("hora_envio"), default=now_hour),
    }

    # Seguridad de rangos antes de Pydantic.
    payload["edad"] = max(0, min(120, payload["edad"]))
    payload["intensidad_dolor"] = max(0, min(10, payload["intensidad_dolor"]))
    payload["hora_envio"] = max(0, min(23, payload["hora_envio"]))

    return payload


def predict_combined(ficha: dict[str, Any], timeout_seconds: float = 5.0) -> dict:
    """Llama al endpoint combinado de ml-triage.

    Devuelve el JSON completo `{triage, disease, inference_time_ms}`.
    Lanza MlServiceUnavailable si el servicio falla o rechaza la ficha.
    """
    url = _ml_triage_url()
    payload = normalize_ficha_for_ml(ficha)

    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.post(url, json=payload)

        if response.status_code == 503:
            raise MlServiceUnavailable(f"{url} devolvió 503")

        if response.status_code == 422:
            logger.warning(
                "ml-triage rechazó ficha normalizada",
                extra={
                    "status_code": response.status_code,
                    "payload": payload,
                    "response": response.text[:1500],
                },
            )
            raise MlServiceUnavailable(f"{url} devolvió 422: {response.text[:500]}")

        response.raise_for_status()
        return response.json()

    except httpx.TimeoutException as exc:
        raise MlServiceUnavailable(f"Timeout llamando a {url}") from exc

    except httpx.HTTPError as exc:
        raise MlServiceUnavailable(str(exc)) from exc


def predict_triage(ficha: dict[str, Any], timeout_seconds: float = 5.0) -> dict:
    """Alias de compatibilidad.

    En versiones antiguas devolvía solo triaje. Ahora devuelve el contrato combinado.
    """
    return predict_combined(ficha, timeout_seconds=timeout_seconds)