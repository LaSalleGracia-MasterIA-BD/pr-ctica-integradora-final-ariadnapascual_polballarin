"""Genera un PDF con la ficha del paciente (estilo hospitalario minimal).

Uso:
    pdf_bytes = build_patient_pdf(patient_detail_dict)
"""
from __future__ import annotations

from datetime import datetime
from io import BytesIO

from fpdf import FPDF


PRIMARY_BLUE = (30, 58, 138)       # #1E3A8A
ACCENT_BLUE = (59, 130, 246)       # #3B82F6
GREY_DARK = (17, 24, 39)           # #111827
GREY_MED = (107, 114, 128)         # #6B7280
GREY_LIGHT = (243, 244, 246)       # #F3F4F6
WHITE = (255, 255, 255)


# Mapping etiqueta interna → nombre humano para la sospecha de enfermedad
# (DESIGN-08b §9.2). Espejo del dashboard.
DISEASE_LABELS_HUMAN = {
    "gripe_resfriado": "Gripe / resfriado",
    "neumonia_sospecha": "Sospecha de neumonia",
    "covid_sospecha": "Sospecha de COVID-19",
    "asma_epoc_exacerbacion": "Exacerbacion asma/EPOC",
    "cardiopatia_aguda_sospecha": "Sospecha cardiopatia aguda",
    "gastroenteritis": "Gastroenteritis",
    "apendicitis_sospecha": "Sospecha de apendicitis",
    "traumatismo": "Traumatismo",
    "cefalea_migrana": "Cefalea / migrania",
    "ictus_sospecha": "Sospecha de ictus",
    "inespecifico": "Cuadro inespecifico",
}


def _human_disease(label: str) -> str:
    return DISEASE_LABELS_HUMAN.get(label, label.replace("_", " ").capitalize())


class _HospitalPDF(FPDF):
    def header(self):  # noqa: D401
        self.set_fill_color(*PRIMARY_BLUE)
        self.rect(0, 0, 210, 22, "F")
        self.set_xy(12, 6)
        self.set_text_color(*WHITE)
        self.set_font("Helvetica", "B", 14)
        self.cell(0, 6, "laSalle Health Center", ln=1)
        self.set_x(12)
        self.set_font("Helvetica", "", 9)
        self.cell(0, 4, "Sistema de Soporte Hospitalario - Ficha clinica", ln=1)
        self.ln(12)
        self.set_text_color(*GREY_DARK)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*GREY_MED)
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.cell(0, 4, f"Documento generado automaticamente el {stamp}", align="L")
        self.cell(0, 4, f"Pagina {self.page_no()}", align="R")


def _section_title(pdf: FPDF, text: str) -> None:
    pdf.set_fill_color(*PRIMARY_BLUE)
    pdf.set_text_color(*WHITE)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, f" {text}", ln=1, fill=True)
    pdf.set_text_color(*GREY_DARK)
    pdf.set_font("Helvetica", "", 10)
    pdf.ln(2)


def _kv_row(pdf: FPDF, label: str, value: str) -> None:
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*GREY_MED)
    pdf.cell(55, 6, label)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*GREY_DARK)
    pdf.cell(0, 6, value, ln=1)


def _triage_box(pdf: FPDF, predicted_class: str | None, probs: dict | None, model_version: str | None) -> None:
    COLOR_BY_CLASS = {
        "Alta": (220, 38, 38),    # rojo
        "Media": (217, 119, 6),   # naranja
        "Baja": (22, 163, 74),    # verde
    }
    if not predicted_class:
        return
    color = COLOR_BY_CLASS.get(predicted_class, PRIMARY_BLUE)
    pdf.ln(1)
    pdf.set_fill_color(*GREY_LIGHT)
    pdf.rect(pdf.l_margin, pdf.get_y(), 210 - 2 * pdf.l_margin, 26, "F")
    x0 = pdf.l_margin
    y0 = pdf.get_y()
    # Franja de color a la izquierda
    pdf.set_fill_color(*color)
    pdf.rect(x0, y0, 3, 26, "F")
    pdf.set_xy(x0 + 6, y0 + 3)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*GREY_MED)
    pdf.cell(0, 4, "NIVEL DE TRIAJE", ln=1)
    pdf.set_x(x0 + 6)
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(*color)
    pdf.cell(0, 9, predicted_class, ln=1)
    if probs:
        pdf.set_x(x0 + 6)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*GREY_MED)
        probs_txt = "  ·  ".join(f"{k}: {v:.1%}" for k, v in probs.items())
        pdf.cell(0, 4, probs_txt, ln=1)
    pdf.set_y(y0 + 26 + 4)
    pdf.set_text_color(*GREY_MED)
    pdf.set_font("Helvetica", "I", 8)
    if model_version:
        pdf.cell(0, 4, f"Modelo: {model_version}", ln=1)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*GREY_DARK)


def _disease_box(pdf: FPDF, disease: dict | None) -> None:
    """Bloque de sospecha de enfermedad — diferencial adaptativo (DESIGN-08b §9.2).

    Renderizado según `len(differential)`:
      - 1: "Sospecha: X (62%)"
      - 2: "Posible X (38%) o Y (32%)"
      - 3: "Diagnostico diferencial: X / Y / Z"
    Banner en azul accent si `low_confidence`. Sin disclaimer aquí (el final
    del PDF ya tiene la nota legal global).
    """
    if not disease:
        return
    diff = disease.get("differential") or []
    if not diff:
        return

    n = len(diff)
    if n == 1:
        title = "SOSPECHA"
    elif n == 2:
        title = "DIAGNOSTICO DIFERENCIAL (2 sospechas)"
    else:
        title = "DIAGNOSTICO DIFERENCIAL (3 sospechas)"

    pdf.ln(1)
    box_height = 14 + 5 * n  # cabecera + una fila por etiqueta
    pdf.set_fill_color(*GREY_LIGHT)
    x0 = pdf.l_margin
    y0 = pdf.get_y()
    pdf.rect(x0, y0, 210 - 2 * x0, box_height, "F")
    # Franja vertical accent a la izquierda
    pdf.set_fill_color(*ACCENT_BLUE)
    pdf.rect(x0, y0, 3, box_height, "F")

    pdf.set_xy(x0 + 6, y0 + 3)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*GREY_MED)
    pdf.cell(0, 4, title, ln=1)

    pdf.set_text_color(*GREY_DARK)
    for d in diff:
        pdf.set_x(x0 + 6)
        pdf.set_font("Helvetica", "B", 11)
        label = _human_disease(d.get("label", ""))
        prob = float(d.get("probability") or 0.0)
        pdf.cell(120, 5, label, ln=0)
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(*GREY_MED)
        pdf.cell(0, 5, f"{prob:.0%}", ln=1, align="L")
        pdf.set_text_color(*GREY_DARK)

    pdf.set_y(y0 + box_height + 2)

    version = disease.get("model_version")
    if version:
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(*GREY_MED)
        pdf.cell(0, 4, f"Modelo: {version}", ln=1)

    if disease.get("low_confidence"):
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(*ACCENT_BLUE)
        pdf.cell(
            0, 5,
            "Aviso: sin sospecha clara (probabilidad principal < 40%). Derivar a valoracion medica.",
            ln=1,
        )

    pdf.set_text_color(*GREY_DARK)
    pdf.set_font("Helvetica", "", 10)


def build_patient_pdf(patient: dict) -> bytes:
    """Construye el PDF a partir de un dict con forma de `PatientDetail`."""
    pdf = _HospitalPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    # --- Cabecera con pseudo_id ---
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(*PRIMARY_BLUE)
    pdf.cell(0, 8, f"Paciente {patient['pseudo_id']}", ln=1)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*GREY_MED)
    pdf.cell(0, 5, f"Registrado: {patient.get('ingested_at', '')[:19]}", ln=1)
    pdf.ln(4)

    # --- Datos basicos ---
    _section_title(pdf, "Datos basicos")
    _kv_row(pdf, "Pseudo-ID", patient["pseudo_id"])
    _kv_row(pdf, "Edad", str(patient.get("edad", "")))
    _kv_row(pdf, "Sexo", str(patient.get("sexo", "")))
    if patient.get("peso_kg"):
        _kv_row(pdf, "Peso (kg)", str(patient["peso_kg"]))
    if patient.get("altura_cm"):
        _kv_row(pdf, "Altura (cm)", str(patient["altura_cm"]))
    _kv_row(pdf, "Fumador", str(patient.get("fumador") or "-"))
    _kv_row(pdf, "Embarazo", str(patient.get("embarazo") or "-"))
    ec = ", ".join(patient.get("enfermedades_cronicas") or []) or "ninguna"
    _kv_row(pdf, "Enfermedades cronicas", ec)
    pdf.ln(3)

    # --- Ultimo ingreso ---
    admissions = patient.get("admissions") or []
    if admissions:
        adm = admissions[0]
        _section_title(pdf, "Ultimo episodio clinico")
        _kv_row(pdf, "Fecha de ingreso", str(adm.get("fecha_ingreso", ""))[:19])
        _kv_row(pdf, "Motivo principal", str(adm.get("motivo_principal") or "-"))
        _kv_row(pdf, "Duracion sintomas", str(adm.get("duracion_sintomas") or "-"))
        _kv_row(pdf, "Intensidad dolor (0-10)", str(adm.get("intensidad_dolor") if adm.get("intensidad_dolor") is not None else "-"))
        _kv_row(pdf, "Fiebre subjetiva", str(adm.get("fiebre_subjetiva") or "-"))
        _kv_row(pdf, "Dificultad respiratoria", str(adm.get("dificultad_respiratoria_subjetiva") or "-"))
        _kv_row(pdf, "Tos", str(adm.get("tos") or "-"))
        _kv_row(pdf, "Contacto COVID", str(adm.get("contacto_covid_reciente") or "-"))
        pdf.ln(3)

    # --- Triaje ---
    pred = patient.get("latest_prediction")
    if pred and pred.get("predicted_class"):
        _section_title(pdf, "Triaje (apoyo a la decision)")
        _triage_box(
            pdf,
            predicted_class=pred.get("predicted_class"),
            probs=pred.get("probabilities"),
            model_version=pred.get("model_version"),
        )
        if pred.get("low_confidence"):
            pdf.set_font("Helvetica", "I", 9)
            pdf.set_text_color(*ACCENT_BLUE)
            pdf.cell(0, 5, "Aviso: prediccion con baja confianza (max. probabilidad < 50%).", ln=1)
            pdf.set_text_color(*GREY_DARK)

    # --- Sospecha de enfermedad (diferencial adaptativo) ---
    disease = patient.get("latest_disease")
    if disease and (disease.get("differential") or []):
        _section_title(pdf, "Sospecha de enfermedad (orientativa)")
        _disease_box(pdf, disease)

    # --- Nota legal ---
    pdf.ln(6)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(*GREY_MED)
    pdf.multi_cell(
        0, 4,
        "Este documento se genera de forma automatica y tiene caracter de apoyo a la decision clinica. "
        "No sustituye al juicio del personal sanitario ni constituye un dispositivo medico validado. "
        "Los datos personales estan anonimizados por diseno: el paciente se identifica unicamente por su pseudo-ID.",
    )

    buf = BytesIO()
    pdf.output(buf)
    return buf.getvalue()
