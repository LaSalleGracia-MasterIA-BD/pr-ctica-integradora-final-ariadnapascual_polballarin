"""Dashboard Streamlit — Sistema de Soporte Hospitalario laSalle (SDD-05).

Estilo: hospital / clínico, paleta blanco + grises + azules.
Navegación: header horizontal (streamlit-option-menu).
Vistas:
  1. Pacientes: tabla, filtros, ficha clicable, descarga PDF.
  2. Triaje: tabs (Formulario | Lote CSV), logs embebidos al ejecutar.
  3. Estado: salud del sistema.
"""
from __future__ import annotations

import os
import time
from datetime import datetime

import pandas as pd
import requests
import streamlit as st
from streamlit_option_menu import option_menu

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000")
POLL_INTERVAL_SEC = 1.5
POLL_MAX_SECONDS = 120

# Paleta hospital (azules + grises + blanco)
PRIMARY_BLUE = "#1E3A8A"   # navy
ACCENT_BLUE = "#2563EB"    # brand
LIGHT_BLUE = "#DBEAFE"     # pastel
GREY_BG = "#F8FAFC"
GREY_BORDER = "#E2E8F0"
GREY_TEXT = "#475569"
TEXT_DARK = "#0F172A"
WHITE = "#FFFFFF"

TRIAGE_COLORS = {
    "Alta": "#DC2626",
    "Media": "#D97706",
    "Baja": "#16A34A",
    None: "#64748B",
}

ML_INFERENCE_URL = os.getenv("ML_INFERENCE_URL", "http://ml-inference:8001")

# Mapping etiqueta interna → nombre humano para la sospecha de enfermedad
# (DESIGN-08b §9.2). Espejo del dashboard y del informe crítico.
DISEASE_LABELS_HUMAN = {
    "gripe_resfriado": "Gripe / resfriado",
    "neumonia_sospecha": "Sospecha de neumonía",
    "covid_sospecha": "Sospecha de COVID-19",
    "asma_epoc_exacerbacion": "Exacerbación asma/EPOC",
    "cardiopatia_aguda_sospecha": "Sospecha cardiopatía aguda",
    "gastroenteritis": "Gastroenteritis",
    "apendicitis_sospecha": "Sospecha de apendicitis",
    "traumatismo": "Traumatismo",
    "cefalea_migrana": "Cefalea / migraña",
    "ictus_sospecha": "Sospecha de ictus",
    "inespecifico": "Cuadro inespecífico",
}

st.set_page_config(
    page_title="laSalle Health Center",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ---------------------------------------------------------------------------
# CSS global — estilo clínico
# ---------------------------------------------------------------------------

st.markdown(
    f"""
    <style>
      /* ---------- Base ---------- */
      html, body, [class*="css"] {{
        font-family: -apple-system, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
        color: {TEXT_DARK} !important;
      }}
      .stApp {{ background: {GREY_BG} !important; }}
      .main > div {{ background: {GREY_BG} !important; }}

      /* Ocultar header nativo de Streamlit (toolbar blanco que solapa el brand) */
      header[data-testid="stHeader"] {{
        display: none !important;
      }}
      [data-testid="stToolbar"],
      [data-testid="stDecoration"],
      [data-testid="stStatusWidget"] {{
        display: none !important;
      }}
      #MainMenu {{ visibility: hidden; }}
      footer {{ visibility: hidden; }}

      .block-container {{
        padding-top: 1.2rem;
        padding-bottom: 3rem;
        max-width: 1320px;
      }}

      /* ---------- Header (responsive) ---------- */
      .hospital-brand {{
        background: linear-gradient(90deg, {PRIMARY_BLUE} 0%, {ACCENT_BLUE} 100%);
        color: {WHITE};
        padding: 14px 22px;
        border-radius: 10px;
        margin-bottom: 14px;
        display: flex;
        flex-wrap: wrap;
        gap: 10px 16px;
        align-items: center;
        justify-content: space-between;
        box-shadow: 0 1px 2px rgba(15,23,42,0.04);
      }}
      .hospital-brand .logo {{
        min-width: 0;
        flex: 1 1 auto;
      }}
      .hospital-brand .logo-title {{
        font-size: clamp(16px, 2.2vw, 22px);
        font-weight: 700;
        letter-spacing: 0.2px;
        line-height: 1.2;
        color: {WHITE};
      }}
      .hospital-brand .logo-sub {{
        display: block;
        font-size: clamp(10px, 1.1vw, 12px);
        font-weight: 400;
        opacity: 0.88;
        margin-top: 2px;
        color: {WHITE};
      }}
      .hospital-brand .status-chip {{
        flex: 0 0 auto;
        background: rgba(255,255,255,0.18);
        padding: 6px 12px;
        border-radius: 999px;
        font-size: 12px;
        white-space: nowrap;
        color: {WHITE};
      }}
      @media (max-width: 560px) {{
        .hospital-brand {{ padding: 12px 16px; }}
      }}

      /* ---------- Cards ---------- */
      .card {{
        background: {WHITE};
        border: 1px solid {GREY_BORDER};
        border-radius: 10px;
        padding: 18px 22px;
        margin-bottom: 12px;
        box-shadow: 0 1px 2px rgba(15,23,42,0.04);
      }}
      .card h3 {{ margin-top: 0; color: {PRIMARY_BLUE}; }}

      /* ---------- Triaje pill ---------- */
      .triage-pill {{
        display: inline-block; padding: 3px 10px; border-radius: 12px;
        font-weight: 600; font-size: 12px; color: {WHITE};
      }}

      /* ---------- DataFrame header navy ---------- */
      div[data-testid="stDataFrame"] thead tr th {{
        background: {PRIMARY_BLUE} !important;
        color: {WHITE} !important;
      }}

      /* ---------- Inputs (refuerzo legibilidad en tema light) ---------- */
      .stSelectbox label, .stNumberInput label, .stSlider label,
      .stMultiSelect label, .stTextInput label, .stFileUploader label,
      .stCheckbox label, .stRadio label {{
        font-weight: 600 !important;
        color: {TEXT_DARK} !important;
      }}
      /* Widgets internos */
      .stSelectbox div[data-baseweb="select"] > div,
      .stMultiSelect div[data-baseweb="select"] > div,
      .stTextInput input,
      .stNumberInput input,
      .stFileUploader section {{
        background: {WHITE} !important;
        color: {TEXT_DARK} !important;
        border-color: {GREY_BORDER} !important;
      }}
      /* Texto de opciones visibles */
      .stSelectbox span, .stMultiSelect span {{
        color: {TEXT_DARK} !important;
      }}
      /* Slider etiquetas */
      .stSlider [data-baseweb="slider"] div {{ color: {TEXT_DARK} !important; }}
      /* Markdown text dentro de columnas */
      .stMarkdown, .stMarkdown p, .stMarkdown li {{ color: {TEXT_DARK}; }}
      /* Captions */
      .stCaption, [data-testid="stCaptionContainer"] {{
        color: {GREY_TEXT} !important;
      }}

      /* ---------- Botones ---------- */
      .stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {{
        background: {PRIMARY_BLUE};
        color: {WHITE};
        border: 0;
        border-radius: 8px;
        font-weight: 600;
      }}
      .stButton > button:hover, .stDownloadButton > button:hover,
      .stFormSubmitButton > button:hover {{
        background: {ACCENT_BLUE};
        color: {WHITE};
      }}

      /* ---------- Tabs ---------- */
      .stTabs [data-baseweb="tab-list"] {{
        background: {WHITE};
        border: 1px solid {GREY_BORDER};
        border-radius: 8px;
        padding: 4px;
      }}
      .stTabs [data-baseweb="tab"] {{
        color: {GREY_TEXT} !important;
        font-weight: 600;
      }}
      .stTabs [aria-selected="true"] {{
        background: {LIGHT_BLUE} !important;
        color: {PRIMARY_BLUE} !important;
        border-radius: 6px;
      }}

      /* ---------- Timeline ---------- */
      .tl-row {{
        display: flex; gap: 10px; align-items: baseline;
        padding: 6px 10px;
        border-left: 3px solid {LIGHT_BLUE};
        background: {WHITE}; margin-bottom: 4px;
        border-radius: 0 6px 6px 0;
      }}
      .tl-row.warning  {{ border-left-color: #D97706; }}
      .tl-row.error    {{ border-left-color: #DC2626; }}
      .tl-row.critical {{ border-left-color: #7C1D1D; background: #FEE2E2; }}
      .tl-ts    {{ color: {GREY_TEXT}; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; min-width: 62px; }}
      .tl-event {{ font-weight: 600; color: {PRIMARY_BLUE}; white-space: nowrap; }}
      .tl-msg   {{ color: {TEXT_DARK}; flex: 1; }}

      /* ---------- Metric card ---------- */
      [data-testid="stMetric"] {{
        background: {WHITE};
        border: 1px solid {GREY_BORDER};
        border-radius: 8px;
        padding: 10px 14px;
      }}
      [data-testid="stMetricValue"] {{ color: {PRIMARY_BLUE}; }}
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Helpers de cliente API
# ---------------------------------------------------------------------------

def api_get(path: str, **kwargs) -> tuple[bool, dict | None, str | None]:
    try:
        r = requests.get(f"{API_BASE_URL}{path}", timeout=10, **kwargs)
        if r.status_code >= 400:
            return False, None, f"HTTP {r.status_code}: {r.text[:200]}"
        return True, r.json(), None
    except requests.RequestException as e:
        return False, None, str(e)


def api_post_json(path: str, payload: dict) -> tuple[int, dict | None, str | None]:
    try:
        r = requests.post(f"{API_BASE_URL}{path}", json=payload, timeout=15)
        try:
            body = r.json()
        except Exception:
            body = None
        return r.status_code, body, None if r.status_code < 500 else r.text[:300]
    except requests.RequestException as e:
        return 0, None, str(e)


def api_post_file(path: str, file_tuple, params: dict | None = None) -> tuple[int, dict | None, str | None]:
    try:
        r = requests.post(f"{API_BASE_URL}{path}", files={"file": file_tuple}, params=params, timeout=60)
        try:
            body = r.json()
        except Exception:
            body = None
        return r.status_code, body, None if r.status_code < 500 else r.text[:300]
    except requests.RequestException as e:
        return 0, None, str(e)


def api_get_bytes(path: str) -> tuple[int, bytes | None, str | None]:
    try:
        r = requests.get(f"{API_BASE_URL}{path}", timeout=15)
        if r.status_code >= 400:
            return r.status_code, None, r.text[:200]
        return r.status_code, r.content, None
    except requests.RequestException as e:
        return 0, None, str(e)


# ---------------------------------------------------------------------------
# Cabecera (brand + estado del backend)
# ---------------------------------------------------------------------------

def render_brand() -> None:
    ok, _, _ = api_get("/health")
    chip = ("🟢 API conectada" if ok else "🔴 API no disponible")
    st.markdown(
        f"""
        <div class="hospital-brand">
          <div class="logo">
            <div class="logo-title">🏥 laSalle Health Center</div>
            <div class="logo-sub">Sistema de Soporte Hospitalario — Apoyo a la decisión clínica</div>
          </div>
          <div class="status-chip">{chip}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Vista: Pacientes
# ---------------------------------------------------------------------------

def _triage_pill(cls: str | None) -> str:
    color = TRIAGE_COLORS.get(cls, TRIAGE_COLORS[None])
    label = cls or "—"
    return f'<span class="triage-pill" style="background:{color}">{label}</span>'


def render_patients() -> None:
    st.markdown("### Pacientes registrados")
    st.caption("Listado de pacientes triados por el sistema. Haz clic en una fila para ver la ficha completa.")

    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        f_triage = st.selectbox("Filtro de triaje", ["Todos", "Alta", "Media", "Baja"])
    with col2:
        limit = st.selectbox("Resultados por página", [25, 50, 100, 200], index=1)
    with col3:
        if st.button("🔄 Actualizar"):
            st.session_state.pop("patients_cache", None)

    params = {"limit": limit, "offset": 0}
    if f_triage != "Todos":
        params["triage_class"] = f_triage

    ok, data, err = api_get("/patients", params=params)
    if not ok:
        st.error(f"No se pudo cargar el listado: {err}")
        return

    items = data["items"]
    total = data["total"]
    st.caption(f"**{len(items)}** mostrados · **{total}** totales.")

    if not items:
        st.info("Aún no hay pacientes registrados. Sube una ficha desde **Triaje**.")
        return

    # Tabla resumen
    def _disease_cell(x: dict) -> str:
        lbl = x.get("disease_top_label")
        prob = x.get("disease_top_probability")
        if not lbl:
            return "—"
        human = _human_disease_label(lbl)
        if prob is not None:
            return f"{human} ({_format_pct(float(prob))})"
        return human

    df = pd.DataFrame([
        {
            "Pseudo-ID": x["pseudo_id"],
            "Edad": x["edad"],
            "Sexo": x["sexo"],
            "Motivo": x.get("motivo_principal") or "—",
            "Crónicas": ", ".join(x.get("enfermedades_cronicas") or []) or "—",
            "Triaje": x.get("triage_class") or "—",
            "Sospecha": _disease_cell(x),
            "Fecha ingreso": (x.get("fecha_ingreso") or "")[:19].replace("T", " "),
        }
        for x in items
    ])
    st.dataframe(df, use_container_width=True, hide_index=True, height=min(420, 46 + 36 * len(df)))

    # Selector de ficha
    st.markdown("#### Ficha del paciente")
    options = [x["pseudo_id"] for x in items]
    selected = st.selectbox("Selecciona un paciente", options, key="patient_selector")
    if selected:
        render_patient_card(selected)


def _human_disease_label(label: str) -> str:
    return DISEASE_LABELS_HUMAN.get(label, label.replace("_", " ").capitalize())


def _format_pct(p: float) -> str:
    return f"{p * 100:.0f}%"


def _render_disease_block(disease: dict | None) -> None:
    """Renderiza inline el bloque de sospecha de enfermedad bajo el triaje
    (DESIGN-08b §9.2). Acepta dicts con `differential`, `low_confidence`,
    `model_version`. Si `disease` es None o no tiene differential, no
    renderiza nada (silencioso por diseño)."""
    if not disease:
        return
    diff = disease.get("differential") or []
    if not diff:
        return

    n = len(diff)
    if n == 1:
        d = diff[0]
        title = "Sospecha"
        body = (
            f"<span style='font-weight:700;'>{_human_disease_label(d['label'])}</span>"
            f" <span style='color:{GREY_TEXT}; font-weight:500;'>"
            f"({_format_pct(float(d['probability']))})</span>"
        )
    elif n == 2:
        d1, d2 = diff[0], diff[1]
        title = "Sospecha — diagnóstico diferencial"
        body = (
            f"Posible <span style='font-weight:700;'>{_human_disease_label(d1['label'])}</span>"
            f" <span style='color:{GREY_TEXT};'>({_format_pct(float(d1['probability']))})</span>"
            f" o <span style='font-weight:700;'>{_human_disease_label(d2['label'])}</span>"
            f" <span style='color:{GREY_TEXT};'>({_format_pct(float(d2['probability']))})</span>"
        )
    else:  # 3
        d1, d2, d3 = diff[0], diff[1], diff[2]
        title = "Diagnóstico diferencial"
        body = (
            f"<span style='font-weight:700;'>{_human_disease_label(d1['label'])}</span>"
            f" <span style='color:{GREY_TEXT};'>({_format_pct(float(d1['probability']))})</span>"
            f" / <span style='font-weight:700;'>{_human_disease_label(d2['label'])}</span>"
            f" <span style='color:{GREY_TEXT};'>({_format_pct(float(d2['probability']))})</span>"
            f" / <span style='font-weight:700;'>{_human_disease_label(d3['label'])}</span>"
            f" <span style='color:{GREY_TEXT};'>({_format_pct(float(d3['probability']))})</span>"
        )

    version = disease.get("model_version") or ""
    st.markdown(
        f"""
        <div class="card" style="border-left: 6px solid {ACCENT_BLUE}; margin-top: 10px;">
            <div style="font-size:12px; color:{GREY_TEXT}; text-transform:uppercase; letter-spacing:0.5px;">
                {title}
            </div>
            <div style="font-size:18px; color:{TEXT_DARK}; margin:6px 0 8px 0;">{body}</div>
            <div style="font-size:11px; color:{GREY_TEXT}; font-style:italic;">
                Sospecha orientativa basada en síntomas auto-reportados.
                No sustituye valoración médica.
                {f"<span style='margin-left:6px;'>Modelo: {version}</span>" if version else ""}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if disease.get("low_confidence"):
        st.warning(
            "⚠️ Sin sospecha clara (probabilidad principal < 40%). "
            "Derivar a valoración médica."
        )


def render_patient_card(pseudo_id: str) -> None:
    ok, detail, err = api_get(f"/patients/{pseudo_id}")
    if not ok:
        st.error(f"No se pudo cargar el paciente: {err}")
        return

    pred = detail.get("latest_prediction") or {}
    triage = pred.get("predicted_class")
    color = TRIAGE_COLORS.get(triage, TRIAGE_COLORS[None])

    # Cabecera tipo ficha
    st.markdown(
        f"""
        <div class="card" style="border-left: 6px solid {color};">
            <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                <div>
                    <div style="color:{GREY_TEXT}; font-size:12px; letter-spacing:0.5px; text-transform:uppercase;">Paciente</div>
                    <div style="font-size:28px; font-weight:700; color:{PRIMARY_BLUE};">{detail["pseudo_id"]}</div>
                    <div style="color:{GREY_TEXT}; font-size:13px; margin-top:4px;">
                        Registrado: {detail.get("ingested_at", "")[:19].replace("T", " ")}
                    </div>
                </div>
                <div style="text-align:right;">
                    <div style="color:{GREY_TEXT}; font-size:12px; letter-spacing:0.5px; text-transform:uppercase;">Nivel de triaje</div>
                    <div style="font-size:26px; font-weight:700; color:{color};">{triage or "—"}</div>
                    {"<div style='font-size:11px; color:" + GREY_TEXT + ";'>" + (pred.get("model_version") or "") + "</div>" if pred.get("model_version") else ""}
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Columnas de info
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### 📋 Datos demográficos")
        st.markdown(
            f"""
            - **Edad**: {detail["edad"]}
            - **Sexo**: {detail["sexo"]}
            - **Peso**: {detail.get("peso_kg") or "—"} kg
            - **Altura**: {detail.get("altura_cm") or "—"} cm
            - **Fumador**: {detail.get("fumador") or "—"}
            - **Embarazo**: {detail.get("embarazo") or "—"}
            - **Crónicas**: {", ".join(detail.get("enfermedades_cronicas") or []) or "ninguna"}
            """
        )
    with c2:
        admissions = detail.get("admissions") or []
        st.markdown("#### 🩺 Último episodio clínico")
        if admissions:
            adm = admissions[0]
            st.markdown(
                f"""
                - **Fecha**: {(adm.get("fecha_ingreso") or "")[:19].replace("T", " ")}
                - **Motivo principal**: {adm.get("motivo_principal") or "—"}
                - **Duración síntomas**: {adm.get("duracion_sintomas") or "—"}
                - **Intensidad dolor**: {adm.get("intensidad_dolor") if adm.get("intensidad_dolor") is not None else "—"} / 10
                - **Fiebre subjetiva**: {adm.get("fiebre_subjetiva") or "—"}
                - **Dificultad respiratoria**: {adm.get("dificultad_respiratoria_subjetiva") or "—"}
                - **Tos**: {adm.get("tos") or "—"}
                - **Contacto COVID**: {adm.get("contacto_covid_reciente") or "—"}
                """
            )
        else:
            st.caption("Sin episodios registrados.")

    # Probabilidades de triaje
    probs = pred.get("probabilities") or {}
    if probs:
        st.markdown("#### 📊 Probabilidades de triaje")
        pcol = st.columns(3)
        pcol[0].metric("Alta",  f"{probs.get('alta', 0):.1%}")
        pcol[1].metric("Media", f"{probs.get('media', 0):.1%}")
        pcol[2].metric("Baja",  f"{probs.get('baja', 0):.1%}")
        if pred.get("low_confidence"):
            st.warning("⚠️ Predicción marcada como **baja confianza** (máx. < 50%).")

    # Sospecha de enfermedad inline (DESIGN-08b §9.2)
    _render_disease_block(detail.get("latest_disease"))

    # Descarga PDF
    st.markdown("#### 📄 Documento")
    code, pdf_bytes, err = api_get_bytes(f"/patients/{pseudo_id}/pdf")
    if code == 200 and pdf_bytes:
        st.download_button(
            label="⬇️ Descargar ficha en PDF",
            data=pdf_bytes,
            file_name=f"ficha_{pseudo_id}.pdf",
            mime="application/pdf",
            type="primary",
        )
    else:
        st.caption(f"PDF no disponible: {err or code}")


# ---------------------------------------------------------------------------
# Vista: Triaje (tabs Formulario + Lote, logs embebidos)
# ---------------------------------------------------------------------------

def _render_event_html(events: list[dict]) -> None:
    if not events:
        st.caption("Esperando eventos del pipeline…")
        return
    rows = []
    for e in events:
        lvl = (e.get("level") or "info").lower()
        klass = f"tl-row {lvl}"
        ts = (e.get("timestamp") or "")[11:19]
        ev = e.get("event") or ""
        msg = e.get("message") or ""
        rows.append(
            f'<div class="{klass}">'
            f'<span class="tl-ts">{ts}</span>'
            f'<span class="tl-event">{ev}</span>'
            f'<span class="tl-msg">{msg}</span>'
            f"</div>"
        )
    st.markdown("\n".join(rows), unsafe_allow_html=True)


def _poll_events_inline(run_id: str) -> None:
    """Polling de GET /batch-runs/{run_id}/events mostrado en línea."""
    header = st.empty()
    timeline = st.empty()
    footer = st.empty()
    start = time.time()
    while True:
        ok, data, _ = api_get(f"/batch-runs/{run_id}/events")
        if not ok or data is None:
            header.warning("No se pudo consultar la API.")
            break
        events = data.get("events") or []
        finished = bool(data.get("finished"))
        with header.container():
            c1, c2, c3 = st.columns(3)
            c1.metric("Eventos", data.get("total", 0))
            c2.metric("Estado", "✅ Terminado" if finished else "⏳ En curso")
            c3.metric("Transcurrido", f"{int(time.time() - start)} s")
        with timeline.container():
            _render_event_html(events)
            if events and finished:
                last = events[-1]
                payload = last.get("payload") or {}
                if payload:
                    st.markdown("##### Resumen final")
                    cols = st.columns(min(4, max(1, len(payload))))
                    for i, (k, v) in enumerate(payload.items()):
                        cols[i % len(cols)].metric(k, v)
        if finished or (time.time() - start) > POLL_MAX_SECONDS:
            footer.caption(
                "Polling detenido." if finished else
                "Se alcanzó el tiempo máximo — refresca para seguir viendo."
            )
            break
        time.sleep(POLL_INTERVAL_SEC)


def render_triage_form_tab() -> None:
    st.markdown("#### Ficha del paciente")
    st.caption("Rellena los campos y pulsa **Clasificar** para que el sistema calcule el nivel de urgencia.")

    with st.form("triage_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("**Datos básicos**")
            edad = st.number_input("Edad", min_value=0, max_value=120, value=45, step=1)
            sexo_lbl = st.selectbox("Sexo", ["Masculino", "Femenino", "Otro"])
            sexo = {"Masculino": "M", "Femenino": "F", "Otro": "Otro"}[sexo_lbl]
            peso_kg = st.number_input("Peso (kg)", min_value=0, max_value=500, value=0, help="0 = no informado")
            altura_cm = st.number_input("Altura (cm)", min_value=0, max_value=250, value=0, help="0 = no informado")
        with col2:
            st.markdown("**Antecedentes**")
            cron_lbl = st.multiselect(
                "Enfermedades crónicas",
                ["Diabetes", "Hipertensión", "Asma/EPOC", "Cardiopatía", "Inmunosupresión"],
            )
            cron_map = {
                "Diabetes": "diabetes", "Hipertensión": "hipertension",
                "Asma/EPOC": "asma_epoc", "Cardiopatía": "cardiopatia",
                "Inmunosupresión": "inmunosupresion",
            }
            enfermedades_cronicas = [cron_map[x] for x in cron_lbl]
            fumador_lbl = st.selectbox("Fumador", ["No", "Sí", "Ex-fumador"])
            fumador = {"No": "no", "Sí": "si", "Ex-fumador": "exfumador"}[fumador_lbl]
            embarazo_lbl = st.selectbox("Embarazo", ["No aplica", "No", "Sí"])
            embarazo = {"No aplica": "na", "No": "no", "Sí": "si"}[embarazo_lbl]
        with col3:
            st.markdown("**Síntomas actuales**")
            motivo_lbl = st.selectbox(
                "Motivo de consulta",
                ["Dolor torácico", "Dificultad respiratoria", "Fiebre",
                 "Dolor abdominal", "Traumatismo", "Síntomas neurológicos", "Otro"],
            )
            motivo_map = {
                "Dolor torácico": "dolor_toracico",
                "Dificultad respiratoria": "dificultad_respiratoria",
                "Fiebre": "fiebre", "Dolor abdominal": "dolor_abdominal",
                "Traumatismo": "traumatismo",
                "Síntomas neurológicos": "sintomas_neurologicos",
                "Otro": "otro",
            }
            motivo_principal = motivo_map[motivo_lbl]
            duracion_lbl = st.selectbox(
                "Duración", ["Menos de 24 h", "1–3 días", "4–7 días", "Más de 1 semana"],
            )
            duracion_sintomas = {
                "Menos de 24 h": "<24h", "1–3 días": "1-3d",
                "4–7 días": "4-7d", "Más de 1 semana": ">1sem",
            }[duracion_lbl]
            intensidad_dolor = st.slider("Intensidad del dolor (0–10)", 0, 10, 0)
            fiebre_lbl = st.selectbox("Fiebre subjetiva", ["No", "Leve", "Alta"])
            fiebre_subjetiva = {"No": "no", "Leve": "leve", "Alta": "alta"}[fiebre_lbl]
            dif_resp_lbl = st.selectbox("Dificultad respiratoria", ["Ninguna", "Leve", "Moderada", "Grave"])
            dificultad_respiratoria_subjetiva = {
                "Ninguna": "no", "Leve": "leve", "Moderada": "moderada", "Grave": "grave",
            }[dif_resp_lbl]
            tos_lbl = st.selectbox("Tos", ["No", "Seca", "Con flema"])
            tos = {"No": "no", "Seca": "seca", "Con flema": "con_flema"}[tos_lbl]
            contacto_lbl = st.selectbox("Contacto reciente con caso COVID-19", ["No", "No lo sé", "Sí"])
            contacto_covid_reciente = {"No": "no", "No lo sé": "no_se", "Sí": "si"}[contacto_lbl]
        submitted = st.form_submit_button("Clasificar", type="primary")

    if not submitted:
        return

    payload = {
        "edad": int(edad), "sexo": sexo,
        "peso_kg": int(peso_kg) if peso_kg else None,
        "altura_cm": int(altura_cm) if altura_cm else None,
        "enfermedades_cronicas": enfermedades_cronicas,
        "fumador": fumador, "embarazo": embarazo,
        "motivo_principal": motivo_principal,
        "duracion_sintomas": duracion_sintomas,
        "intensidad_dolor": int(intensidad_dolor),
        "fiebre_subjetiva": fiebre_subjetiva,
        "dificultad_respiratoria_subjetiva": dificultad_respiratoria_subjetiva,
        "tos": tos, "contacto_covid_reciente": contacto_covid_reciente,
        "hora_envio": datetime.now().hour,
    }

    with st.spinner("Procesando ficha…"):
        code, result, err = api_post_json("/patients", payload)
    if err:
        st.error(f"Error de conexión: {err}")
        return

    if code == 400 and (result or {}).get("status") == "rejected":
        st.error("⛔ La ficha no cumple las reglas de validación.")
        for reason in (result or {}).get("reasons") or []:
            st.write(f"- `{reason}`")
        return

    if code == 202 and (result or {}).get("status") == "pending_triage":
        st.warning(f"✅ Ficha registrada como **{result.get('pseudo_id')}**, pero el triaje queda pendiente.")
        run_id = result.get("run_id")
        if run_id:
            st.markdown("##### Seguimiento de eventos")
            _poll_events_inline(run_id)
        return

    if code != 200 or not result:
        st.error(f"Respuesta inesperada: HTTP {code}")
        return

    pred = result.get("prediction") or {}
    clase = pred.get("predicted_class")
    probs = pred.get("probabilities") or {}
    color = TRIAGE_COLORS.get(clase, TRIAGE_COLORS[None])

    st.markdown(
        f"""
        <div class="card" style="border-left: 6px solid {color};">
            <div style="font-size:12px; color:{GREY_TEXT}; text-transform:uppercase; letter-spacing:0.5px;">
                Paciente registrado — {result.get("pseudo_id")}
            </div>
            <div style="font-size:30px; font-weight:800; color:{color}; margin:4px 0;">{clase or "—"}</div>
            <div style="color:{GREY_TEXT}; font-size:12px;">Modelo: {pred.get("model_version") or "—"}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    mcols = st.columns(3)
    mcols[0].metric("Alta",  f"{probs.get('alta', 0):.1%}")
    mcols[1].metric("Media", f"{probs.get('media', 0):.1%}")
    mcols[2].metric("Baja",  f"{probs.get('baja', 0):.1%}")
    if pred.get("low_confidence"):
        st.warning("⚠️ Predicción con baja confianza.")

    # Sospecha de enfermedad inline (DESIGN-08b §9.2)
    _render_disease_block(result.get("disease"))

    # Logs embebidos del run online
    run_id = result.get("run_id")
    if run_id:
        st.markdown("##### Registro de ejecución (eventos del pipeline online)")
        _poll_events_inline(run_id)

    st.info("ℹ️ Este resultado es **apoyo a la decisión**, no un diagnóstico. El personal sanitario revisa siempre la clasificación.")


def render_triage_batch_tab() -> None:
    st.markdown("#### Carga por lotes (CSV multi-ficha)")
    st.caption(
        "Sube un CSV con una fila por paciente (mismo esquema que el formulario). "
        "El sistema validará, limpiará y triará cada fila; los eventos aparecen en vivo abajo."
    )

    uploaded = st.file_uploader("Fichero CSV", type=["csv"])
    apply_triage = st.checkbox("Aplicar triaje a cada fila", value=True)

    if uploaded and st.button("Procesar lote", type="primary"):
        code, data, err = api_post_file(
            "/batch-runs",
            file_tuple=(uploaded.name, uploaded.getvalue(), "text/csv"),
            params={"apply_triage": str(apply_triage).lower()},
        )
        if err or code != 200 or not data:
            st.error(f"Error al subir: {err or code}")
            return
        run_id = data.get("run_id")
        st.success(
            f"✅ Lote **{run_id}** iniciado con **{data.get('rows_in_csv')}** filas "
            f"— CSV guardado como `{data.get('key')}`."
        )
        st.markdown("##### Registro de ejecución")
        _poll_events_inline(run_id)


def render_triage() -> None:
    st.markdown("### Triaje")
    tab_form, tab_batch = st.tabs(["📝 Formulario individual", "📤 Lote CSV"])
    with tab_form:
        render_triage_form_tab()
    with tab_batch:
        render_triage_batch_tab()


def render_radiography_tab() -> None:
    st.header("Clasificación de radiografías")
    st.caption("Modelo DL para clasificación triple: Sana / Neumonía / COVID-19")

    uploaded = st.file_uploader(
        "Sube una radiografía de tórax",
        type=["png", "jpg", "jpeg"],
        key="radiography_upload",
    )

    if uploaded is None:
        st.info("Sube una imagen PNG/JPG para ejecutar inferencia.")
        return

    st.image(uploaded, caption="Radiografía cargada", use_container_width=True)

    if st.button("Clasificar radiografía", type="primary"):
        try:
            files = {
                "file": (
                    uploaded.name,
                    uploaded.getvalue(),
                    uploaded.type or "image/png",
                )
            }

            with st.spinner("Ejecutando inferencia en ml-inference..."):
                response = requests.post(
                    f"{ML_INFERENCE_URL}/predict",
                    files=files,
                    timeout=60,
                )

            if response.status_code != 200:
                st.error(f"Error del servicio ml-inference: {response.status_code}")
                st.code(response.text)
                return

            result = response.json()

            predicted = result["predicted_class"]
            probs = result["probabilities"]

            st.subheader(f"Resultado: {predicted}")

            c1, c2, c3 = st.columns(3)
            c1.metric("Sana", f"{probs.get('Sana', 0) * 100:.1f}%")
            c2.metric("Neumonía", f"{probs.get('Neumonía', 0) * 100:.1f}%")
            c3.metric("COVID-19", f"{probs.get('COVID-19', 0) * 100:.1f}%")

            st.progress(float(max(probs.values())))

            if result.get("triggers_covid_alert"):
                st.error("Alerta COVID-19: probabilidad superior al umbral configurado.")

            if result.get("low_confidence"):
                st.warning("Predicción de baja confianza. Requiere revisión clínica.")

            with st.expander("Respuesta completa del modelo"):
                st.json(result)

        except requests.RequestException as exc:
            st.error(f"No se pudo conectar con ml-inference: {exc}")

# ---------------------------------------------------------------------------
# Vista: Estado
# ---------------------------------------------------------------------------

def render_status() -> None:
    st.markdown("### Estado del sistema")
    ok, _, err = api_get("/health")
    if ok:
        st.success(f"API `{API_BASE_URL}` — operativa ✅")
    else:
        st.error(f"API `{API_BASE_URL}` — {err}")
    st.caption(
        "El resto de servicios (PostgreSQL, MongoDB, MinIO, ml-triage, ml-inference) "
        "se acceden a través de la API y del orquestador Docker."
    )


# ---------------------------------------------------------------------------
# Header + navegación principal
# ---------------------------------------------------------------------------

render_brand()

selected = option_menu(
    menu_title=None,
    options=["Pacientes", "Triaje", "Radiografías", "Estado"],
    icons=["people-fill", "clipboard-heart", "image", "activity"],
    default_index=0,
    orientation="horizontal",
    styles={
        "container": {
            "padding": "0 !important",
            "background-color": WHITE,
            "border": f"1px solid {GREY_BORDER}",
            "border-radius": "10px",
            "margin-bottom": "14px",
        },
        "icon": {"color": PRIMARY_BLUE, "font-size": "18px"},
        "nav-link": {
            "font-size": "14px",
            "font-weight": "600",
            "color": GREY_TEXT,
            "padding": "12px 18px",
            "margin": "0",
            "--hover-color": LIGHT_BLUE,
        },
        "nav-link-selected": {
            "background-color": LIGHT_BLUE,
            "color": PRIMARY_BLUE,
        },
    },
)

if selected == "Pacientes":
    render_patients()
elif selected == "Triaje":
    render_triage()
elif selected == "Radiografías":
    render_radiography_tab()
elif selected == "Estado":
    render_status()