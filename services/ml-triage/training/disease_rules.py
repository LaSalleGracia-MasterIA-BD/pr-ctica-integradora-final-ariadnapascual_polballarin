"""Reglas clínicas del generador sintético para sospecha de enfermedad
(DESIGN-08b §4.2).

Dada una ficha (dict con los 15 campos de SDD-08 RF-1), devuelve una etiqueta
de sospecha de enfermedad. Orden de evaluación: primera regla que cumple fija
la clase.

Estas reglas son las que el modelo de enfermedad aprenderá (con el mismo
ruido del 10 % aplicado por `generate_dataset.py`). Como en `rules.py`, la
variable `hora_envio` no aparece — sigue siendo la espuria.

Las 11 clases (ver DESIGN-08b §3) son mutuamente excluyentes; el catch-all
`inespecifico` recoge todo lo que no encaja en una sospecha clínica concreta.
"""
from __future__ import annotations

from typing import Any, Mapping

DiseaseLabel = str

DISEASE_CLASSES: tuple[str, ...] = (
    "gripe_resfriado",
    "neumonia_sospecha",
    "covid_sospecha",
    "asma_epoc_exacerbacion",
    "cardiopatia_aguda_sospecha",
    "gastroenteritis",
    "apendicitis_sospecha",
    "traumatismo",
    "cefalea_migrana",
    "ictus_sospecha",
    "inespecifico",
)


def assign_disease_from_rules(ficha: Mapping[str, Any]) -> DiseaseLabel:
    """Aplica las reglas clínicas a una ficha y devuelve la etiqueta de
    sospecha de enfermedad (ver DESIGN-08b §4.2)."""
    motivo = ficha["motivo_principal"]
    edad = ficha["edad"]
    dolor = ficha["intensidad_dolor"]
    fiebre = ficha["fiebre_subjetiva"]
    dif_resp = ficha["dificultad_respiratoria_subjetiva"]
    tos = ficha["tos"]
    contacto = ficha["contacto_covid_reciente"]
    duracion = ficha["duracion_sintomas"]
    ec = ficha.get("enfermedades_cronicas") or []

    # 1. Cardiopatía aguda — dolor torácico de riesgo
    if motivo == "dolor_toracico" and (
        edad >= 50 or "cardiopatia" in ec or dolor >= 7
    ):
        return "cardiopatia_aguda_sospecha"

    # 2. Ictus — neurológico de riesgo (alta intensidad o edad)
    if motivo == "sintomas_neurologicos" and (dolor >= 7 or edad >= 65):
        return "ictus_sospecha"

    # 3. Cefalea / migraña — neurológico no urgente (resto)
    if motivo == "sintomas_neurologicos":
        return "cefalea_migrana"

    # 4. Asma/EPOC exacerbación — disnea sobre patología crónica conocida
    if motivo == "dificultad_respiratoria" and "asma_epoc" in ec:
        return "asma_epoc_exacerbacion"

    # 5. COVID-19 sospecha — contacto reciente + síntomas compatibles
    if contacto == "si" and (
        fiebre != "no"
        or tos != "no"
        or motivo == "dificultad_respiratoria"
    ):
        return "covid_sospecha"

    # 6. Neumonía sospecha — fiebre alta + tos productiva sobre cuadro respiratorio
    if (
        motivo in ("dificultad_respiratoria", "fiebre")
        and fiebre == "alta"
        and tos == "con_flema"
    ):
        return "neumonia_sospecha"

    # 7. Apendicitis sospecha — dolor abdominal severo de evolución corta
    if (
        motivo == "dolor_abdominal"
        and dolor >= 7
        and duracion in ("<24h", "1-3d")
    ):
        return "apendicitis_sospecha"

    # 8. Gastroenteritis — resto de cuadros abdominales
    if motivo == "dolor_abdominal":
        return "gastroenteritis"

    # 9. Traumatismo — sin distinguir leve/grave (el triaje ya lo hace)
    if motivo == "traumatismo":
        return "traumatismo"

    # 10. Gripe / resfriado — fiebre como motivo principal o
    #     "otro" con tos+fiebre subjetiva
    if motivo == "fiebre":
        return "gripe_resfriado"
    if motivo == "otro" and tos != "no" and fiebre != "no":
        return "gripe_resfriado"

    # 11. Inespecífico — catch-all
    return "inespecifico"


__all__ = ["assign_disease_from_rules", "DISEASE_CLASSES", "DiseaseLabel"]
