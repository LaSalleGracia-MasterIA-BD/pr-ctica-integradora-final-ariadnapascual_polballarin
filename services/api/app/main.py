"""API HTTP del Sistema de Soporte Hospitalario.

Endpoints (SDD-05):
  - GET  /health                         -> liveness
  - POST /patients                       -> ficha del formulario -> triaje online
  - POST /batch-runs                     -> upload CSV -> pipeline batch async
  - GET  /batch-runs/{run_id}/events     -> eventos de dominio del run (polling)
  - GET  /docs                           -> OpenAPI auto (FastAPI)
"""
from __future__ import annotations

import io
import logging
import uuid
from datetime import datetime, timezone

import pandas as pd
from fastapi import (
    BackgroundTasks,
    FastAPI,
    File,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import text

# --- Código del pipeline (montado en /app/app/ por el Dockerfile) ----------
from app.logging_setup import set_correlation_id, setup_logging
from app.online import process_patient_ficha
from app.orchestrator import new_run_id, run_batch
from app.phases.validation import load_rules
from app.storage import mongo as mongo_store
from app.storage import postgres as pg_store
from app.storage.raw_source import make_raw_source

# --- Código de la API -------------------------------------------------------
from api_app.config import settings as api_settings
from api_app.pdf_generator import build_patient_pdf
from api_app.schemas import (
    AdmissionDetail,
    BatchRunStarted,
    DiseaseDifferentialItem,
    DiseaseSuspicion,
    DiseaseSuspicionDetail,
    DomainEvent,
    DomainEventsResponse,
    PatientDetail,
    PatientFicha,
    PatientListItem,
    PatientResponse,
    PatientsListResponse,
    PredictionDetail,
)


setup_logging(service="api", level=api_settings.api_log_level)
logger = logging.getLogger("api")

app = FastAPI(
    title="Hospital laSalle — API",
    version="1.0.0",
    description="Backend del Sistema de Soporte Hospitalario (SDD-05).",
)


# Cargar reglas una sola vez al arrancar.
_rules_cache: dict | None = None


def get_rules() -> dict:
    global _rules_cache
    if _rules_cache is None:
        _rules_cache = load_rules(api_settings.validation_rules_path)
    return _rules_cache


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# POST /patients — formulario web online (SDD-05 RF-2bis)
# ---------------------------------------------------------------------------

@app.post("/patients", response_model=PatientResponse)
def post_patient(ficha: PatientFicha, response: Response) -> PatientResponse:
    """Procesa una ficha del formulario y devuelve la predicción de triaje.

    - 200 + {status: completed, ...} si el triaje fue exitoso.
    - 202 + {status: pending_triage, ...} si ml-triage no respondió a tiempo.
    - 400 + {status: rejected, reasons: [...]} si la validación interna falla
      (aunque Pydantic haya pasado; el YAML es más estricto).
    """
    correlation_id = f"online-{uuid.uuid4().hex[:12]}"
    set_correlation_id(correlation_id)

    result = process_patient_ficha(
        ficha=ficha.model_dump(),
        rules=get_rules(),
        correlation_id=correlation_id,
        apply_triage=True,
    )

    if result["status"] == "rejected":
        response.status_code = status.HTTP_400_BAD_REQUEST
    elif result["status"] == "pending_triage":
        response.status_code = status.HTTP_202_ACCEPTED

    disease_block: DiseaseSuspicion | None = None
    disease_raw = result.get("disease") or {}
    if disease_raw.get("differential"):
        disease_block = DiseaseSuspicion(
            differential=[
                DiseaseDifferentialItem(
                    label=d["label"], probability=float(d["probability"])
                )
                for d in disease_raw.get("differential", [])
            ],
            low_confidence=disease_raw.get("low_confidence"),
            model_version=disease_raw.get("model_version"),
        )

    return PatientResponse(**{
        "status": result["status"],
        "run_id": result["run_id"],
        "pseudo_id": result.get("pseudo_id"),
        "prediction": result.get("prediction"),
        "disease": disease_block,
        "reasons": result.get("reasons"),
    })


# ---------------------------------------------------------------------------
# POST /batch-runs — upload CSV + disparo async (SDD-05 RF-2ter)
# ---------------------------------------------------------------------------

def _run_batch_background(key: str, apply_triage: bool, run_id: str) -> None:
    """Ejecuta el pipeline batch. Se llama desde BackgroundTasks."""
    try:
        rules = get_rules()
        source = make_raw_source("s3")
        run_batch(
            source=source, key=key, rules=rules,
            apply_triage=apply_triage, run_id=run_id,
        )
    except Exception:
        logger.exception("fallo en pipeline batch background")


@app.post("/batch-runs", response_model=BatchRunStarted)
async def post_batch_run(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    apply_triage: bool = True,
) -> BatchRunStarted:
    """Recibe un CSV multipart, lo sube a S3 y dispara el pipeline en background."""
    if not (file.filename or "").endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Se espera un fichero .csv",
        )

    raw = await file.read()
    # Cuenta rápida de filas (excluye cabecera)
    try:
        df = pd.read_csv(io.BytesIO(raw), encoding="utf-8")
        rows = int(len(df))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"CSV no legible: {exc}",
        )

    # run_id anticipado; se usará como correlation_id en el orquestador
    run_id = new_run_id()
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    key = f"patients/upload-{ts}-{run_id}.csv"

    # Subir a S3
    source = make_raw_source("s3")
    source.put(key, raw, content_type="text/csv")

    background_tasks.add_task(_run_batch_background, key, apply_triage, run_id)

    return BatchRunStarted(
        run_id=run_id,
        status="started",
        key=key,
        rows_in_csv=rows,
    )


# ---------------------------------------------------------------------------
# GET /batch-runs/{run_id}/events — timeline para el dashboard (SDD-05 RF-2quater)
# ---------------------------------------------------------------------------

@app.get("/batch-runs/{run_id}/events", response_model=DomainEventsResponse)
def get_batch_events(run_id: str) -> DomainEventsResponse:
    cursor = mongo_store.system_events().find(
        {"correlation_id": run_id},
    ).sort("timestamp", 1)

    events: list[DomainEvent] = []
    finished = False
    for doc in cursor:
        ev = DomainEvent(
            timestamp=doc["timestamp"].isoformat() if hasattr(doc["timestamp"], "isoformat") else str(doc["timestamp"]),
            service=doc.get("service", ""),
            event=doc.get("event", ""),
            level=doc.get("level", "info"),
            correlation_id=doc.get("correlation_id", ""),
            message=doc.get("message", ""),
            payload=doc.get("payload", {}) or {},
        )
        events.append(ev)
        if ev.event in ("pipeline.run.end", "pipeline.online.end", "pipeline.online.rejected"):
            finished = True

    return DomainEventsResponse(
        run_id=run_id,
        events=events,
        total=len(events),
        finished=finished,
    )


# ---------------------------------------------------------------------------
# Helpers internos de composición paciente + último ingreso + triaje
# ---------------------------------------------------------------------------

def _iso(v) -> str | None:
    if v is None:
        return None
    return v.isoformat() if hasattr(v, "isoformat") else str(v)


def _latest_triage_by_pseudo_id(pseudo_ids: list[str]) -> dict[str, dict]:
    """Devuelve {pseudo_id: doc_predicción_más_reciente}. Una query agregada."""
    if not pseudo_ids:
        return {}
    pipeline = [
        {"$match": {"patient_pseudo_id": {"$in": pseudo_ids}}},
        {"$sort": {"ingested_at": -1}},
        {"$group": {
            "_id": "$patient_pseudo_id",
            "doc": {"$first": "$$ROOT"},
        }},
    ]
    out: dict[str, dict] = {}
    for row in mongo_store.predictions_triage().aggregate(pipeline):
        out[row["_id"]] = row["doc"]
    return out


def _latest_disease_by_pseudo_id(pseudo_ids: list[str]) -> dict[str, dict]:
    """Análogo a `_latest_triage_by_pseudo_id` para `predictions_disease`."""
    if not pseudo_ids:
        return {}
    pipeline = [
        {"$match": {"patient_pseudo_id": {"$in": pseudo_ids}}},
        {"$sort": {"ingested_at": -1}},
        {"$group": {
            "_id": "$patient_pseudo_id",
            "doc": {"$first": "$$ROOT"},
        }},
    ]
    out: dict[str, dict] = {}
    for row in mongo_store.predictions_disease().aggregate(pipeline):
        out[row["_id"]] = row["doc"]
    return out


def _pg_array_to_list(val) -> list[str]:
    """psycopg2 devuelve arrays PG como listas Python; tolerar None/str."""
    if val is None:
        return []
    if isinstance(val, list):
        return [str(x) for x in val if x]
    return [val] if val else []


# ---------------------------------------------------------------------------
# GET /patients — listado paginado con datos enriquecidos (SDD-05 RF-1)
# ---------------------------------------------------------------------------

@app.get("/patients", response_model=PatientsListResponse)
def list_patients(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    triage_class: str | None = Query(None, description="Filtro: Alta | Media | Baja"),
) -> PatientsListResponse:
    sql = text("""
        SELECT p.pseudo_id, p.edad, p.sexo, p.fumador, p.enfermedades_cronicas,
               p.ingested_at,
               i.fecha_ingreso, i.motivo_principal
        FROM   pacientes p
        LEFT JOIN LATERAL (
            SELECT fecha_ingreso, motivo_principal
            FROM   ingresos
            WHERE  paciente_pseudo_id = p.pseudo_id
            ORDER  BY fecha_ingreso DESC
            LIMIT  1
        ) i ON true
        ORDER  BY p.ingested_at DESC
        LIMIT  :limit OFFSET :offset
    """)
    count_sql = text("SELECT COUNT(*) FROM pacientes")

    with pg_store.get_engine().begin() as conn:
        rows = conn.execute(sql, {"limit": limit, "offset": offset}).mappings().all()
        total = int(conn.execute(count_sql).scalar() or 0)

    pseudo_ids = [r["pseudo_id"] for r in rows]
    triage_by_pid = _latest_triage_by_pseudo_id(pseudo_ids)
    disease_by_pid = _latest_disease_by_pseudo_id(pseudo_ids)

    items: list[PatientListItem] = []
    for r in rows:
        triage_doc = triage_by_pid.get(r["pseudo_id"])
        pred_class = (triage_doc or {}).get("predicted_class")
        if triage_class and pred_class != triage_class:
            continue

        disease_doc = disease_by_pid.get(r["pseudo_id"])
        diff = (disease_doc or {}).get("differential") or []
        disease_top_label = diff[0]["label"] if diff else None
        disease_top_probability = (
            float(diff[0]["probability"]) if diff else None
        )

        items.append(PatientListItem(
            pseudo_id=r["pseudo_id"],
            edad=int(r["edad"]),
            sexo=str(r["sexo"]),
            fumador=r["fumador"],
            enfermedades_cronicas=_pg_array_to_list(r["enfermedades_cronicas"]),
            motivo_principal=r["motivo_principal"],
            fecha_ingreso=_iso(r["fecha_ingreso"]),
            triage_class=pred_class,
            triage_probabilities=(triage_doc or {}).get("probabilities"),
            triage_status=(triage_doc or {}).get("triage_status"),
            model_version=(triage_doc or {}).get("model_version"),
            disease_top_label=disease_top_label,
            disease_top_probability=disease_top_probability,
            disease_low_confidence=(disease_doc or {}).get("low_confidence"),
            ingested_at=_iso(r["ingested_at"]) or "",
        ))

    return PatientsListResponse(items=items, total=total, limit=limit, offset=offset)


# ---------------------------------------------------------------------------
# GET /patients/{pseudo_id} — detalle (SDD-05 RF-2)
# ---------------------------------------------------------------------------

def _load_patient_detail(pseudo_id: str) -> PatientDetail | None:
    sql_paciente = text("""
        SELECT pseudo_id, edad, sexo, peso_kg, altura_cm,
               fumador, embarazo, enfermedades_cronicas,
               source, ingested_at, created_at
        FROM   pacientes
        WHERE  pseudo_id = :pid
    """)
    sql_ingresos = text("""
        SELECT id, fecha_ingreso, motivo_principal, duracion_sintomas,
               intensidad_dolor, fiebre_subjetiva,
               dificultad_respiratoria_subjetiva, tos,
               contacto_covid_reciente, hora_envio, source
        FROM   ingresos
        WHERE  paciente_pseudo_id = :pid
        ORDER  BY fecha_ingreso DESC
    """)

    with pg_store.get_engine().begin() as conn:
        row = conn.execute(sql_paciente, {"pid": pseudo_id}).mappings().first()
        if row is None:
            return None
        adm_rows = conn.execute(sql_ingresos, {"pid": pseudo_id}).mappings().all()

    admissions = [
        AdmissionDetail(
            id=int(a["id"]),
            fecha_ingreso=_iso(a["fecha_ingreso"]) or "",
            motivo_principal=a["motivo_principal"],
            duracion_sintomas=a["duracion_sintomas"],
            intensidad_dolor=a["intensidad_dolor"],
            fiebre_subjetiva=a["fiebre_subjetiva"],
            dificultad_respiratoria_subjetiva=a["dificultad_respiratoria_subjetiva"],
            tos=a["tos"],
            contacto_covid_reciente=a["contacto_covid_reciente"],
            hora_envio=a["hora_envio"],
            source=a["source"],
        )
        for a in adm_rows
    ]

    triage_doc = mongo_store.predictions_triage().find_one(
        {"patient_pseudo_id": pseudo_id},
        sort=[("ingested_at", -1)],
    )
    prediction = None
    if triage_doc:
        prediction = PredictionDetail(
            predicted_class=triage_doc.get("predicted_class"),
            probabilities=triage_doc.get("probabilities"),
            model_version=triage_doc.get("model_version"),
            low_confidence=triage_doc.get("low_confidence"),
            triage_status=triage_doc.get("triage_status"),
            ingested_at=_iso(triage_doc.get("ingested_at")),
        )

    disease_doc = mongo_store.predictions_disease().find_one(
        {"patient_pseudo_id": pseudo_id},
        sort=[("ingested_at", -1)],
    )
    disease_detail = None
    if disease_doc:
        disease_detail = DiseaseSuspicionDetail(
            differential=[
                DiseaseDifferentialItem(
                    label=d["label"], probability=float(d["probability"])
                )
                for d in (disease_doc.get("differential") or [])
            ],
            low_confidence=disease_doc.get("low_confidence"),
            model_version=disease_doc.get("model_version"),
            inference_status=disease_doc.get("inference_status"),
            ingested_at=_iso(disease_doc.get("ingested_at")),
        )

    return PatientDetail(
        pseudo_id=row["pseudo_id"],
        edad=int(row["edad"]),
        sexo=str(row["sexo"]),
        peso_kg=row["peso_kg"],
        altura_cm=row["altura_cm"],
        enfermedades_cronicas=_pg_array_to_list(row["enfermedades_cronicas"]),
        fumador=row["fumador"],
        embarazo=row["embarazo"],
        source=row["source"],
        ingested_at=_iso(row["ingested_at"]) or "",
        created_at=_iso(row["created_at"]),
        admissions=admissions,
        latest_prediction=prediction,
        latest_disease=disease_detail,
    )


@app.get("/patients/{pseudo_id}", response_model=PatientDetail)
def get_patient(pseudo_id: str) -> PatientDetail:
    detail = _load_patient_detail(pseudo_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")
    return detail


# ---------------------------------------------------------------------------
# GET /patients/{pseudo_id}/pdf — ficha descargable en PDF
# ---------------------------------------------------------------------------

@app.get("/patients/{pseudo_id}/pdf")
def get_patient_pdf(pseudo_id: str) -> Response:
    detail = _load_patient_detail(pseudo_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")
    pdf_bytes = build_patient_pdf(detail.model_dump())
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="ficha_{pseudo_id}.pdf"',
        },
    )
