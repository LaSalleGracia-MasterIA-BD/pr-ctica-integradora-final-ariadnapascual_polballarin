"""Reglas clínicas del generador sintético de triaje.

Dada una ficha con los campos de SDD-08 RF-1, devuelve la clase:
Alta / Media / Baja.

La variable `hora_envio` no aparece en ninguna regla. Es la variable espuria.
"""
from __future__ import annotations

from typing import Any, Mapping

TriageLabel = str


def assign_triage_from_rules(ficha: Mapping[str, Any]) -> TriageLabel:
    motivo = ficha["motivo_principal"]
    dolor = ficha["intensidad_dolor"]
    edad = ficha["edad"]
    fiebre = ficha["fiebre_subjetiva"]
    dif_resp = ficha["dificultad_respiratoria_subjetiva"]
    tos = ficha["tos"]
    contacto = ficha["contacto_covid_reciente"]
    ec = ficha.get("enfermedades_cronicas") or []

    # Alta: condiciones clínicamente urgentes.
    if motivo == "sintomas_neurologicos" and dolor >= 7:
        return "Alta"

    if motivo == "dolor_toracico" and (
        edad >= 50 or "cardiopatia" in ec or dolor >= 8
    ):
        return "Alta"

    if dif_resp == "grave":
        return "Alta"

    if fiebre == "alta" and (edad >= 65 or "inmunosupresion" in ec):
        return "Alta"

    if motivo == "traumatismo" and dolor >= 8:
        return "Alta"

    # Media: requiere atención, pero no inmediata.
    if fiebre == "alta":
        return "Media"

    if dif_resp in ("leve", "moderada"):
        return "Media"

    if dolor >= 7:
        return "Media"

    if motivo == "dolor_abdominal" and dolor >= 6:
        return "Media"

    if contacto == "si" and (fiebre != "no" or tos != "no"):
        return "Media"

    if edad >= 65 and (
        dolor > 0 or fiebre != "no" or dif_resp != "no" or tos != "no"
    ):
        return "Media"

    if ec and ec != ["ninguna"] and (dolor > 0 or fiebre != "no"):
        return "Media"

    return "Baja"


__all__ = ["assign_triage_from_rules", "TriageLabel"]