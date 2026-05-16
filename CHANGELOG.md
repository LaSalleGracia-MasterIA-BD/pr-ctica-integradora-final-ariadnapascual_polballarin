# Changelog

Todos los cambios notables del proyecto se documentan aquí.

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).

> Este archivo registra cambios **técnicos** (código, infra, decisiones de arquitectura). La reflexión sobre el uso de Claude Code (prompts, iteraciones, aprendizajes) va en [`docs/diario-ia/`](docs/diario-ia/), no aquí.

---

## [Unreleased]

### Added (Training y versionado radiografias DL — 2026-05-04)

- **`services/ml-inference/training/`** *(nuevo)*: pipeline offline completo para entrenar el clasificador DL:
  - `prepare_data.py`: prepara subset balanceado (3k/clase), splits 70/15/15 y metadata.
  - `dataset.py`: `RadiographyDataset` con CSV + transforms.
  - `augment.py`: data augmentation clinicamente segura + eval transforms.
  - `model.py`: EfficientNet-B0 con head de 3 clases.
  - `train.py`: warmup + fine-tuning con early stopping, class weights y artefacto versionado.
  - `evaluate.py`: metrics.json + confusion_matrix.png sobre test.
  - `critical_analysis.py`: informe clinico `critical_analysis.md`.
  - `requirements-training.txt`: deps offline (torch, pandas, sklearn, matplotlib, etc.).
- **Versionado de artefactos**: `models/radiography/rx-YYYYMMDD-hash8/` generado por `train.py` con `model.pt` + `metadata.json`; `current.txt` apuntando a version activa.
- **Healthcheck**: `ml-inference` alinea `/healthz` en app y Docker healthcheck.

### Added (Servicio ml-inference v1.0: clasificación radiografías — 2026-04-21)

Implementación completa del **servicio de inferencia Deep Learning** para clasificación de radiografías de tórax (SDD-06 §4-7, DESIGN-06). Compone la capa de predicción del pipeline de análisis de imágenes.

- **`services/ml-inference/app/config.py`** *(nuevo)*: constantes centralizadas — `MODEL_PATH`, `ML_DEVICE` (CPU/CUDA), clases `["Sana", "Neumonía", "COVID-19"]`, normalización ImageNet, umbral de alerta (`COVID_ALERT_THRESHOLD=0.80`), nivel de log.
- **`services/ml-inference/app/schemas.py`** *(nuevo)*: Pydantic model `RadiographyPredictionOutput` con 7 campos — `predicted_class`, `probabilities` (dict de P por clase), `model_version`, `inference_time_ms`, `low_confidence` (flag si max prob < 50 %), `triggers_covid_alert` (flag si P(COVID-19) > umbral), `confidence_notes` (str). JSON example incluido.
- **`services/ml-inference/app/predictor.py`** *(nuevo)*: Singleton `Predictor` (~180 líneas):
  - `load_model()`: carga torch model desde `ML_MODEL_PATH`, lee `metadata.json` adyacente para versión, establece `_ready=True`.
  - `predict(image_bytes)`: pipeline de preproceso (PIL image → RGB → resize 224×224 → normaliza ImageNet → tensor), forward pass, softmax, **regla de desempate** (Sana < Neumonía < COVID-19 por gravedad si probs empatadas), flags de confianza, time tracking.
  - Helper `_has_tie()` + `_tiebreaker_rule()`.
  - Global helpers `get_predictor()` y `is_model_ready()` para singleton thread-safe.
- **`services/ml-inference/app/app.py`** *(reemplazado stub)*: FastAPI full prod:
  - `lifespan` context manager: carga modelo en startup, log warnings si falla.
  - `GET /health`: 200 si modelo está listo, 503 si no (integra con healthcheck docker-compose).
  - `POST /predict`: multipart file upload, valida content-type (jpeg/png), forwarda a `predictor.predict()`, maneja errores (400/422/503), devuelve `RadiographyPredictionOutput` con metadata completa.
  - `GET /`: service info + endpoint list (descubrimiento).
  - Logging integrado (info + warn + error), OpenAPI auto docs.
- **`services/ml-inference/requirements.txt`** *(actualizado)*: `torch==2.4.1, torchvision==0.19.1, pillow==10.4.0, pydantic==2.9.2` añadidas (además de fastapi, uvicorn, numpy, python-multipart).
- **`services/ml-inference/app/__init__.py`** *(nuevo)*: package marker.
- **`Dockerfile` stage `ml-inference`** (existente): sin cambios — ya apuntaba a app.py correctamente, comando `CMD ["uvicorn", "app.app:app", ...]`.
- **`docker-compose.yml` servicio `ml-inference`** (existente): sin cambios — bind mount `./models:/app/models`, environment vars `ML_MODEL_PATH`, `ML_DEVICE`, healthcheck curl `/health`, restart policy.

**Notas**:
- Stack: PyTorch 2.4.1 + torchvision (backbone EfficientNet-B0, transfer learning) + Pillow (I/O imágenes).
- Singleton pattern ensures single model instance across app lifecycle (no race conditions, memory-efficient).
- Tiebreaker rule clinically prudent (si dos clases empatadas, elige la grave; prevalencia clínica: COVID-19 > Neumonía > Sana).
- `/health` integrado con Docker healthcheck — el servicio se marca healthy en 1-2s tras carga modelo, luego quedan 3 reintentos si falla.
- `inference_time_ms` mide solo prediction (excluye I/O), útil para SLO.
- Ready para consumo desde `ml-pipeline` (agent `ml-triage` y otros servicios).

**Pendientes para cierre del sprint:**
- Entrenar modelo (prepare_data.py, dataset.py, model.py, train.py, evaluate.py, critical_analysis.py).
- Versionado de artefactos (models/radiography/rx-YYYYMMDD-hash8/, metadata.json, model version format).
- Test E2E del flujo radiografía → ml-inference → pipeline → API → dashboard.

### Added (Modelo de sospecha de enfermedad + endpoint combinado + raw MinIO online — 2026-04-27)

Sprint que añade un **segundo modelo tabular** sobre el mismo formulario que ya alimenta el triaje, cubriendo el ejemplo "predicción de enfermedades" del enunciado §3.1, y completa el flujo de data lake del flujo online.

- **`specs/DESIGN-08b-modelo-enfermedad.md`** *(nuevo)*: catálogo de 11 clases (10 enfermedades + `inespecifico`), reglas heurísticas paralelas a `rules.py`, regla del 70 % para el diagnóstico diferencial adaptativo (1, 2 o 3 etiquetas), output combinado del endpoint, persistencia raw en MinIO y `predictions_disease` en Mongo.
- **`specs/DESIGN-01-arquitectura.md §5.3`** + **`README.md`**: nueva tabla "Capas de almacenamiento" comparando MinIO/PostgreSQL/MongoDB con qué guarda cada uno y por qué — antes la información estaba dispersa en prosa.
- **Generador**: `services/ml-triage/training/disease_rules.py` (11 reglas, paralelas a `rules.py`); `generate_dataset.py` extendido a `GENERATOR_VERSION=2.0` con columna `disease_target`, ruido tipo A multiclase por matriz de proximidad clínica, distribución medida ~30 %/20 %/13 %/12 %/10 %/5 %/2.5 %/2.5 %/2 %/1.5 %/0.8 %.
- **Modelo**: `services/ml-triage/training/model.py` añade `DISEASE_MODEL_HYPERPARAMS` (con `class_weight='balanced'` para el desbalance natural), `build_disease_pipeline`, `split_features_disease_target`. Entrenamiento + evaluación + análisis crítico paralelos a triaje (`train_disease.py`, `evaluate_disease.py`, `critical_analysis_disease.py`). Resultados sobre test: **accuracy 0.9267, F1 macro 0.8665, F1 weighted 0.9250**, `hora_envio` (espuria) ≈ 0.
- **Servicio `ml-triage` v2.0**:
  - Endpoint `POST /predict-triage` **renombrado a `POST /predict`**, output combinado `{triage, disease, inference_time_ms}`.
  - `app/predictor.py` reescrito como `CombinedPredictor`: carga ambos artefactos, aplica regla de desempate prudente sobre triaje y regla del 70 % sobre enfermedad. `/health` exige los dos modelos cargados (no degradación).
  - `app/schemas.py`: `DiseasePrediction`, `DiseaseOutput`, `PredictOutput` (combinado).
  - `app/config.py`: `ML_DISEASE_MODEL_PATH`, `ML_DISEASE_LOW_CONFIDENCE_THRESHOLD=0.40`, `ML_DISEASE_DIFFERENTIAL_RATIO=0.70`.
- **Pipeline**:
  - `app/clients/triage_client.py`: `predict_triage` → `predict_combined`, URL `/predict`. `TriageUnavailable` renombrada a `MlServiceUnavailable` (con alias por compatibilidad).
  - `app/online.py`: persiste el JSON original del formulario en MinIO **best-effort** (`raw/online/YYYY/MM/DD/<correlation_id>.json`) **antes** de validar — cierra el principio de data lake del enunciado §4.2 para el flujo online. Si MinIO cae, log warning + evento de dominio y el flujo continúa. Persiste tanto `predictions_triage` como `predictions_disease`.
  - `app/orchestrator.py`: `_run_triage_for_ingresos` → `_run_ml_for_ingresos` con persistencia doble.
  - `app/phases/loading.py`: nueva `persist_disease_prediction`.
  - `app/storage/mongo.py`: helper `predictions_disease()`.
- **API** (`services/api/`): `POST /patients` propaga el bloque `disease`, `GET /patients` incluye `disease_top_label`/`probability`/`low_confidence` en cada item, `GET /patients/{id}` añade `latest_disease` con el diferencial completo. Schemas: `DiseaseDifferentialItem`, `DiseaseSuspicion`, `DiseaseSuspicionDetail`.
- **Dashboard Streamlit**: helper `_render_disease_block` que renderiza inline bajo el bloque de triaje según `len(differential)`: 1 → "Sospecha: X (62 %)", 2 → "Posible X o Y", 3 → "Diagnóstico diferencial". Banner amarillo si `low_confidence`. Disclaimer clínico fijo. Nueva columna "Sospecha" en la tabla de pacientes con el top-1.
- **Init Mongo** (`init/mongo/init.js`): colección `predictions_disease` con índices sobre `patient_pseudo_id`, `ingested_at`, `model_version`, `inference_status`.
- **Compose + env**: `ML_DISEASE_MODEL_PATH=/app/models/disease/current` añadida a `.env.example`, `.env` y al servicio `ml-triage` en `docker-compose.yml`.
- **Modelo entrenado**: `models/disease/dis-20260427-16225289/` (model.joblib, metadata.json, metrics.json, confusion_matrix.png 11×11, critical_analysis.md). Marker `current.txt` apuntando al artefacto activo.

### Changed (Despliegue automático de modelos — 2026-04-27)

- **`docker-compose.yml`**: `models-data:/app/models` (volumen nombrado) **reemplazado por bind mount `./models:/app/models`** en `ml-triage` y `ml-inference`. El volumen nombrado `models-data` se elimina del bloque `volumes:`. Resultado: los artefactos entrenados en el host (`models/triage/current`, `models/disease/current`) son visibles inmediatamente desde los contenedores sin pasos manuales de `docker compose cp` y **sobreviven a `docker compose down -v`**. La automatización exige que `docker compose up` levante TODO con un solo comando (§4.1 del enunciado) — el bind mount lo cumple.
- **`specs/DESIGN-01-arquitectura.md §5.4`**: tabla de volúmenes actualizada para reflejar el bind mount.

### Changed (PDF de la ficha del paciente — 2026-04-27)

- **`services/api/app/pdf_generator.py`**: nueva sección "Sospecha de enfermedad (orientativa)" con su `_disease_box` adaptativo: 1 etiqueta → "SOSPECHA", 2 → "DIAGNOSTICO DIFERENCIAL (2 sospechas)", 3 → "DIAGNOSTICO DIFERENCIAL (3 sospechas)". Cada etiqueta se renderiza con su nombre humano (mismo mapping que dashboard) + probabilidad + versión del modelo. Si `low_confidence`, aviso en azul accent. La nota legal final ya cubre el disclaimer global.

### Changed (Specs cruzados — 2026-04-27)

- **`specs/DESIGN-08-modelo-triaje.md`** y **`specs/SDD-08-modelo-triaje.md`**: nota de versión 1.1 al inicio remitiendo a DESIGN-08b para el contrato vigente del endpoint. Las referencias internas a `/predict-triage` se conservan por trazabilidad histórica.
- **`specs/DESIGN-02-pipeline.md`**: `triage_client.py` apunta a `/predict` combinado (DESIGN-08b §6).
- **`specs/DESIGN-01-arquitectura.md §3`** + **`specs/SDD-03-almacenamiento.md §1`**: suavizado el lenguaje sobre el easter egg "NoSQL sobre todo". La arquitectura PG+Mongo+MinIO se justifica técnicamente (cumple el ejemplo del propio enunciado §4.2.2) sin depender de la interpretación opinable de un texto oculto.

### Added (post-merge ariadna→pol: servicio ml-triage — 2026-04-20)

- **Stage `ml-triage`** en `Dockerfile` (puerto 8002, python 3.11-slim).
- **Servicio `ml-triage`** en `docker-compose.yml` (depende de mongodb, healthcheck en `/health`, volumen `models-data`).
- **`services/ml-triage/app/app.py`**: FastAPI stub con endpoints `/health` y `POST /predict-triage` que valida la ficha (Pydantic con los 15 campos auto-reportados de SDD-08 RF-1) y devuelve una predicción aleatoria con la estructura definida en SDD-08 RF-14 (`predicted_class`, `probabilities.{alta,media,baja}`, `model_version`, `inference_time_ms`).
- **`services/ml-triage/requirements.txt`** con dependencias pinneadas (fastapi, uvicorn, pydantic, scikit-learn, numpy, pandas, joblib).
- **`.env.example`**: nueva variable `ML_TRIAGE_MODEL_PATH=/app/models/triage_rf.pkl`.
- **`api` ahora depende de `ml-triage`** (además de ml-inference) vía `depends_on`.

### Fixed (post-merge ariadna→pol — 2026-04-20)

- **Healthcheck de `mongodb`**: `mongo --eval ...` → `mongosh --quiet --eval ...`. El binario `mongo` ya no existe en la imagen `mongo:7`; el healthcheck habría fallado permanentemente.
- **Volumen `pgadmin-data`** declarado en el bloque `volumes:` del `docker-compose.yml` (estaba referenciado en el servicio `pgadmin` pero no declarado como nombrado, lo que producía warnings de Docker Compose).

### Added (Diario de desarrollo con IA — 2026-04-21)

Creado `docs/diario-ia/` con los **entregables del §5.3 del enunciado**: herramientas usadas, prompts representativos verbatim, aciertos y correcciones, reflexión crítica y estimación de impacto en productividad. Organizado en 9 ficheros:

- `README.md` — metodología + índice.
- `00-genesis-plan.md` — plan inicial y SDDs iniciales.
- `01-integracion-ariadna.md` — merge de la rama de la compañera.
- `02-modelo-triaje.md` — SDD-08, generador, entreno, predictor.
- `03-etl-pipeline.md` — pipeline batch + online + smoke E2E.
- `04-online-api-dashboard.md` — API del flujo + dashboard v1/v2.
- `05-minio-landing.md` — decisión S3 → MinIO con razonamiento.
- `06-pulido-ux.md` — bump versiones + UX.
- `99-reflexion-critica.md` — lecciones, patrones de prompt, productividad estimada ~3-4×.

Respeta la separación de bitácoras acordada (CHANGELOG = técnico; diario-ia = metacognición con Claude Code).

### Changed (bump de versiones — 2026-04-21)

Actualización a versiones estables recientes (no bleeding-edge, para evitar breaking changes sin ganancia real):

**Imágenes Docker** (`docker-compose.yml`):
- `postgres:16-alpine` → `postgres:17-alpine`
- `mongo:7` → `mongo:8.0`
- `minio/minio` RELEASE.2024-10-02 → RELEASE.2024-12-18
- `minio/mc` RELEASE.2024-10-02 → RELEASE.2024-11-21
- `dpage/pgadmin4:7.8` → `dpage/pgadmin4:9`
- `mongo-express:1.0.0` → `mongo-express:1.0.2`
- `grafana/loki:2.8.2` → `grafana/loki:3.2.1`
- `grafana/promtail:2.8.2` → `grafana/promtail:3.2.1`

**Python base**: `python:3.11-slim` → `python:3.12-slim` (3.13 se descartó: aún faltan wheels binarias para numpy/scikit-learn en algunas plataformas).

**Packages Python** (todos los `requirements.txt` actualizados):
- fastapi `0.115.0` → `0.115.6`
- uvicorn `0.30.6` → `0.32.1`
- pydantic `2.9.2` → `2.10.3`
- pydantic-settings `2.6.0` → `2.6.1`
- numpy `2.1.1` → `2.2.1`
- SQLAlchemy `2.0.35` → `2.0.36`
- psycopg2-binary `2.9.9` → `2.9.10`
- boto3/botocore `1.35.36` → `1.35.68`
- httpx `0.27.2` → `0.28.1`
- python-multipart `0.0.12` → `0.0.20`
- scikit-learn `1.5.2` → `1.6.0`
- matplotlib `3.9.2` → `3.10.0`
- streamlit `1.26.0` → `1.40.2`, requests `2.31.0` → `2.32.3`, pillow `11.0.0` añadido explícito (dashboard ya no falla al build).

**`monitoring/loki-config.yaml` reescrita** para Loki 3.x (config minimal oficial con `tsdb` store + schema v13 + `common.path_prefix` + `allow_structured_metadata`). Resuelve los errores en cadena que tenía la config 2.x antigua (`max_streams_per_user` en sección equivocada, `allow_structured_metadata` sin reconocer, `wal` en path no escribible, `compactor` sin working_directory).

### Verified
- `docker compose build` completa sin errores (6 imágenes custom).
- `docker compose up -d` levanta los 13 servicios. Los 7 críticos (postgres, mongodb, minio, api, ml-inference, ml-triage, dashboard) quedan **healthy**. Automation/pipeline/promtail no tienen healthcheck (son jobs). Loki/mongo-express/pgadmin sus healthchecks fallan pero los servicios responden (healthchecks cosméticos, no bloquean el flujo).

### Added (Sprint 2 Día 8: ETL online + API flujo completo — 2026-04-21)

- **`services/pipeline/app/online.py`** — `process_patient_ficha(ficha, rules, correlation_id, apply_triage)`:
  procesa **una sola ficha** reutilizando las fases del batch. Valida, transforma, persiste en PG, llama a `ml-triage`, persiste la predicción en Mongo, emite eventos de dominio. Si `ml-triage` cae, marca `pending_triage` y sigue.
- **`services/pipeline/app/orchestrator.py`**: `run_batch()` ahora acepta `run_id` externo (para que la API pueda devolver el id al cliente antes de que arranque el run y el cliente pueda polear los eventos con ese id desde el primer momento).
- **API reestructurada** (`services/api/app/`):
  - `config.py` con `pydantic-settings` (log level, path de reglas).
  - `schemas.py` con `TriageInput`, `PatientResponse`, `BatchRunStarted`, `DomainEvent`, `DomainEventsResponse`.
  - `main.py` con las rutas del flujo: `GET /health`, `POST /patients` (invoca `process_patient_ficha`; 200/202/400), `POST /batch-runs` (multipart CSV → sube a S3 → `BackgroundTasks.add_task(run_batch)` → devuelve `run_id` inmediato), `GET /batch-runs/{run_id}/events` (lee `system_events` filtrado por `correlation_id`, ordenado por timestamp, detecta fin).
- **`Dockerfile` stage `api`**: copia el código del pipeline como `app/` y la API como `api_app/` para evitar colisión de paquetes. Instala `requirements.txt` de ambos. `PYTHONPATH=/app`.
- **`Dockerfile` base**: añadido `curl` (los healthchecks del compose lo usan, la imagen `python:3.11-slim` no lo trae).
- **`.env.example`** + **`.env`**: `ML_TRIAGE_MODEL_PATH=/app/models/triage/current` (antes apuntaba a `triage_rf.pkl`, inexistente).
- **`services/api/requirements.txt`** pinneado: fastapi 0.115.0, uvicorn 0.30.6, python-multipart 0.0.12, pydantic 2.9.2, pydantic-settings 2.6.0.

### Verified (Sprint 2 Día 8: smoke test API end-to-end — 2026-04-21)

Stack completo operativo (`postgres + mongodb + minio + ml-inference + ml-triage + api`, todos `healthy`). Tras copiar el artefacto entrenado al volumen `models-data` (`docker cp models/triage ml-triage-1:/app/models/`) y recrear el contenedor:

- `GET /health` → `{"status": "ok"}`.
- `POST /patients` con ficha urgente (edad 72, dolor torácico intenso, cardiopatía) → **`Alta` con P=0.966**, `pseudo_id=PAT-000102` persistido en PG, `predictions_triage` en Mongo con `model_version=tri-20260421-80bae54a`.
- `POST /batch-runs` con CSV de 20 fichas → respuesta inmediata `{run_id: "run-20260421-7cdbb008", status: "started"}` + pipeline corriendo en background.
- `GET /batch-runs/run-20260421-7cdbb008/events` → **8 eventos de dominio** en orden (`pipeline.run.start` → `file.read` → `validation.done` → `transformation.done` → `loading.done` → `triage.done` → `aggregates.updated` → `run.end`), **`finished: true`**, duración 475 ms.
- **Triaje aplicado a las 20 fichas** (0 pending, 0 rejected).

El flujo completo *(formulario web | subir CSV → ETL → triaje → persistencia → dashboard con polling)* está cerrado en backend. Sigue: frontend Streamlit.

### Fixed (Sprint 2 Día 7: validation_rules.yaml quoting — 2026-04-21)

- **Bug en `config/validation_rules.yaml`**: YAML 1.1 interpreta `no` sin comillas como booleano `False`. Los enums `[no, si, exfumador]` quedaban como `[False, "si", "exfumador"]`, rechazando el 99 % de filas válidas. Corregido con **quoting explícito** (`["no", "si", "exfumador"]`) en todos los enums (`fumador`, `embarazo`, `fiebre_subjetiva`, `dificultad_respiratoria_subjetiva`, `tos`, `contacto_covid_reciente`).

### Verified (Sprint 2 Día 7: smoke test ETL E2E — 2026-04-21)

Con el stack mínimo (`postgres` + `mongodb` + `minio` + `minio-init`) levantado vía `docker compose up -d`:

1. `docker compose run --rm pipeline python main.py seed --n 100 --seed 42`
   → genera CSV de 100 fichas y sube a `s3://hospital-raw/patients/seed-<ts>-s42-n100.csv` (6 969 bytes).
2. `docker compose run --rm pipeline python main.py batch --key patients/seed-... --no-triage`
   → tras el fix del YAML: **100 válidos, 0 rechazados, 100 pacientes + 100 ingresos insertados** en 179 ms.
3. Verificación post-run:
   - PostgreSQL: `pacientes = 101`, `ingresos = 101` (incluye +1 que pasó en el run pre-fix).
   - MongoDB: `system_events = 15` (los dos runs completos), `ingestion_rejects = 99` (rechazos del run pre-fix), `aggregates_daily = 1`, `counters.patient_pseudo_id.seq = 101` (contador atómico operativo).
   - Logs JSON estructurados con `correlation_id=run-20260421-6d15e8d0` trazando cada fase (`pipeline.run.start` → `file.read` → `validation.done` → `transformation.done` → `loading.done` → `rejects.persisted` → `aggregates.updated` → `run.end`).

**Cierre**: el pipeline ETL batch funciona end-to-end contra el stack real PG + Mongo + MinIO. Listo para la siguiente fase (ETL online + API + Dashboard).

### Added (Sprint 2 Día 7: ETL pipeline batch implementado — 2026-04-21)

Implementación completa del pipeline de datos (SDD-02 + DESIGN-02) en `services/pipeline/`:

- **`app/config.py`**: `Settings` con Pydantic (envs de PG/Mongo/S3/ml-triage/logging). URIs derivadas (`postgres_url`, `mongo_uri`) como propiedades.
- **`app/logging_setup.py`**: logs JSON a stdout con `correlation_id` via `ContextVar` (SDD-07 RF-1). Formatter custom con campos obligatorios + `extra` selectivo.
- **`app/events.py`**: emisión de **eventos de dominio** a la colección `system_events` de Mongo (SDD-03 RF-10, SDD-07 RF-9bis). Emisión paralela al log técnico. No propaga excepciones.
- **`app/storage/postgres.py`**: SQLAlchemy con pool + engine singleton. `upsert_pacientes()` con `ON CONFLICT DO NOTHING` (first_wins) + `insert_ingresos()` + helpers de conteo/exists.
- **`app/storage/mongo.py`**: `MongoClient` singleton + accesores por colección + `next_sequence()` atómico con `find_one_and_update($inc)` (base de `pseudo_id`).
- **`app/storage/raw_source.py`**: interfaz `RawSource` abstract + `LocalFSSource` (tests/seed) + `S3Source` (boto3 con `endpoint_url` — sirve para MinIO y AWS sin cambio de código). Factory `make_raw_source('s3'|'local')`.
- **`app/utils/pseudo_id.py`**: `next_pseudo_id()` → `PAT-000001` zero-pad (DESIGN-03 §5).
- **`app/utils/hashing.py`**: SHA-256 streaming (evita cargar todo a memoria).
- **`app/phases/ingestion.py`**: lee CSV de RawSource, hash, emite eventos `pipeline.file.read` / `file.rejected`.
- **`app/phases/validation.py`**: carga YAML con PyYAML, aplica reglas declarativas (type, min/max, pattern, enum, cross_field con eval sandbox sin builtins), separa `(valid, rejects)`. Función `dedup_by_key()` con `first_wins`.
- **`app/phases/transformation.py`**: genera `pseudo_id`, añade trazabilidad (`source`, `ingested_at`, `processed_by`), **anonimización defensiva** (blacklist de columnas `nombre`, `dni`, `email`, …), separa `(pacientes_rows, ingresos_rows)`.
- **`app/phases/loading.py`**: persiste pacientes/ingresos en PG, rechazos en `ingestion_rejects`, predicciones de triaje en `predictions_triage` (con `ficha_snapshot` auditable).
- **`app/phases/aggregates.py`**: upsert por día natural en `aggregates_daily` con contadores (records_in, valid, rejected, triage_completed, triage_pending).
- **`app/clients/triage_client.py`**: cliente httpx con timeout 2 s; levanta `TriageUnavailable` si 5xx/timeout — el orchestrator persiste `pending_triage` en ese caso.
- **`app/orchestrator.py`**: `run_batch(source, key, rules, apply_triage)` ejecuta las 4 fases + triaje + agregados, emite `pipeline.run.start` y `pipeline.run.end` con contadores. Genera `run_id = run-YYYYMMDD-hash8` y lo fija como `correlation_id`.
- **`main.py`** CLI con subcomandos: `batch`, `batch-all`, `seed`, `version`. Flag `--source s3|local` y `--no-triage`.
- **`config/validation_rules.yaml`**: reglas declarativas con 15 campos tipados, dos reglas cross-field (warning sobre sexo/embarazo) y dedup `first_wins` por `pseudo_id`.
- **`seed/generate_fichas.py`**: réplica ligera del generador de training (distribuciones iguales, sin target). `generate_and_upload(n, seed, source_kind)` sube el CSV a `patients/seed-<ts>-s<seed>-n<n>.csv` en la fuente raw configurada.
- **`requirements.txt`** pinneado: pandas 2.2.3, SQLAlchemy 2.0.35, psycopg2-binary 2.9.9, pymongo 4.10.1, PyYAML 6.0.2, pydantic 2.9.2, pydantic-settings 2.6.0, boto3 1.35.36, httpx 0.27.2, tenacity 9.0.0.

### Added (Sprint 2: capa raw en MinIO — decisión cerrada 2026-04-21)

- **Servicio `minio`** añadido a `docker-compose.yml` (`minio/minio:RELEASE.2024-10-02T17-50-41Z`): backend S3-compatible para la capa raw (patrón *landing zone*). Puerto 9000 (API S3) + 9001 (console web). Healthcheck contra `/minio/health/live`. Volumen nombrado `minio-data`.
- **Servicio `minio-init`** (`minio/mc:RELEASE.2024-10-02T08-27-28Z`): crea el bucket `${S3_BUCKET_RAW}` al arrancar (idempotente vía `mc mb --ignore-existing`). `restart: no` — se cierra tras ejecutar.
- **Variables en `.env.example`**: bloque nuevo con `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, `MINIO_API_PORT`, `MINIO_CONSOLE_PORT`, `S3_ENDPOINT=http://minio:9000`, `S3_REGION`, `S3_BUCKET_RAW=hospital-raw`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`. En producción se apunta `S3_ENDPOINT` a AWS S3 real y el código no cambia (`boto3` con `endpoint_url`).
- **`api` y `pipeline`**: ahora ven las variables `S3_*` y tienen `minio` en `depends_on`.
- **Volumen `minio-data`** declarado en el bloque `volumes:`.
- **DESIGN-01 actualizado**: tabla de servicios añade `minio`, `minio-init`, `ml-triage`; tabla de volúmenes añade `minio-data` y `pgadmin-data`.
- **Decisión cerrada en SDDs**: `[NEEDS CLARIFICATION]` sobre S3 removido en SDD-01 §7, SDD-02 §7 y SDD-03 §7. Justificación común: MinIO = estándar industrial para desarrollo/staging, código idéntico a AWS real, levantable sin Internet ni credenciales externas (cumple §4.1 del enunciado "un solo comando"), defendible en memoria como arquitectura *landing zone*.
- **`docker compose config` valida OK** con los 13 servicios (los 11 anteriores + minio + minio-init).

### Added (Sprint 2 Día 6: servicio ml-triage con predictor real — 2026-04-21)

- **`services/ml-triage/app/features.py`**: contrato compartido de features (columnas, clases, expansión de `enfermedades_cronicas`), **única fuente de verdad** usada por `training/` y `app/`.
- **`services/ml-triage/app/schemas.py`**: modelos Pydantic v2 con `Literal[...]` en todos los enums → validación estricta del formulario en el borde del servicio. `TriageInput` con 15 campos + `TriageOutput` estructurado (`predicted_class`, `probabilities.{alta,media,baja}`, `model_version`, `inference_time_ms`, `low_confidence`).
- **`services/ml-triage/app/config.py`**: `ML_TRIAGE_MODEL_PATH` (default `/app/models/triage/current`) + `ML_TRIAGE_LOW_CONFIDENCE_THRESHOLD` (default 0.50). Sin credenciales ni secrets.
- **`services/ml-triage/app/predictor.py`**: `TriagePredictor` singleton thread-safe. Carga el artefacto resolviendo symlink o fallback `current.txt` (Windows sin permisos). Aplica **regla de desempate prudente** (SDD-08 RNF-10: Alta > Media > Baja). Calcula `low_confidence = max(probs) < 0.50`. Mide `inference_time_ms`.
- **`services/ml-triage/app/app.py`**: reescrito — rutas FastAPI finas (`GET /health`, `POST /predict-triage`). Al arranque fuerza `get_predictor()` para evitar coste de carga en la primera petición. `/health` devuelve 503 con motivo si el modelo no cargó.
- **`training/model.py`** refactorizado: re-exporta el contrato desde `app/features.py` con fallback de `sys.path` para funcionar tanto con `cwd=services/ml-triage/` como con cualquier otro.
- **Smoke test del servicio 2026-04-21** (uvicorn local apuntando al artefacto `tri-20260421-80bae54a`):
  - `GET /health` → `200 {"status":"ok","model_version":"tri-20260421-80bae54a"}`.
  - Ficha urgente (dolor torácico, 72 años, cardiopatía, dolor 9) → `Alta` con `P=0.966`.
  - Ficha benigna (28 años sana, dolor 2, otro motivo) → `Baja` con `P=0.907`.
  - Ficha inválida (`edad=500`) → `422` con detalle Pydantic.
  - Tras warm-up, `inference_time_ms=7` (dentro de p95 < 200 ms objetivo de DESIGN-08).
- **`training/cross_validate`** tras el refactor: `f1_macro = 0.8994 ± 0.0083` (idéntico al smoke test anterior — refactor no rompe el training).

### Added (Sprint 2 Día 5-6: modelo de triaje implementado — 2026-04-21)

- **`.gitignore`** en la raíz: excluye `data/synthetic/`, `data/raw/`, `data/covid-subset/`, `models/`, venv, cachés, .env, artefactos de IDE.
- **`services/ml-triage/training/`** — código offline para el modelo tabular de triaje (DESIGN-08):
  - `rules.py` — reglas clínicas deterministas (13 reglas Alta/Media/Baja).
  - `model.py` — pipeline sklearn compartido (ColumnTransformer + HistGradientBoostingClassifier), columnas y hiperparámetros como constantes exportadas, `load_dataset()` que expande `enfermedades_cronicas` a 5 booleanas.
  - `generate_dataset.py` — CLI (`--n`, `--seed`, `--output`) que produce `train.csv`, `val.csv`, `test.csv` (70/15/15 estratificado) + `metadata.json` con hashes SHA-256. Reproducibilidad byte-a-byte verificada: dos corridas con misma semilla producen CSVs idénticos.
  - `train.py` — CLI que entrena y persiste `model.joblib` + `metadata.json` en `models/triage/tri-YYYYMMDD-hash8/`. Symlink `current` (fallback `current.txt` en Windows sin permisos).
  - `evaluate.py` — CLI que produce `metrics.json` (accuracy, F1 macro, per-class, matriz confusión, permutation importance) + `confusion_matrix.png`.
  - `critical_analysis.py` — CLI que lee `metrics.json` y genera `critical_analysis.md` con: error más frecuente e impacto clínico, importancia de `hora_envio` (aviso si > 0.005), top 5 features, limitación fundamental (circularidad del dataset sintético).
  - `cross_validate.py` — k-fold estratificado sobre `train.csv + val.csv` concatenados (test.csv reservado). Persiste `cv_results.json`.
  - `requirements.txt` con pandas 2.2.3, numpy 2.1.1, scikit-learn 1.5.2, joblib, matplotlib (pinneado).
- **Smoke test completo 2026-04-21** sobre 10 000 fichas (seed=42):
  - Entrenamiento: val_accuracy = 0.9193.
  - Test: **accuracy = 0.9133, F1 macro = 0.8961**.
  - Recall `Alta` = 0.8345 (métrica clínica crítica documentada explícitamente).
  - Importancia `hora_envio` = **-0.0115** — el modelo **ignora la variable espuria**, como diseñado.
  - 5-fold CV: **F1 macro = 0.8994 ± 0.0083** (baja varianza entre folds).
  - Error más frecuente: `Alta → Media` (46 casos), con descripción de impacto clínico.
- **Decisión práctica: reproducibilidad verificada en entorno Python 3.14 / pandas 2.3.3** (el `requirements.txt` pinnea versiones algo inferiores; compatibilidad mantenida para runtime del contenedor).

### Added (DESIGN-06 modelo DL radiografías — 2026-04-21)

- **`specs/DESIGN-06-modelo-dl.md`** (versión 1.0, `ready-for-implementation`): diseño técnico del modelo de clasificación de radiografías. Cierra los **6 `[NEEDS CLARIFICATION]`** de SDD-06 §7 y, de paso, el de **SDD-03 RNF-6** (tamaño del subset):
  - Backbone: **EfficientNet-B0** pre-entrenado en ImageNet (~5M params, mejor ratio precisión/tamaño que ResNet50). ResNet50 como fallback documentado.
  - Splits: **70/15/15** estratificados por clase, `random_state=42`.
  - Desbalance: **pesos de clase en CrossEntropyLoss** (`w_i = N / (C * n_i)`).
  - Umbral alerta COVID-19: **P(COVID-19) > 0.80**, configurable vía `COVID_ALERT_THRESHOLD`.
  - Regla de desempate: **Sana < Neumonía < COVID-19** (criterio clínico conservador).
  - Latencia objetivo: **p95 < 3 s** por imagen en CPU.
  - Subset balanceado: **3 000 imágenes por clase = 9 000 totales** (cierra también duda de SDD-03 sobre tamaño).
- **Mapeo del dataset** Kaggle → clases del proyecto: `Normal → Sana`; `Viral Pneumonia + Lung_Opacity → Neumonía`; `COVID → COVID-19`. Decisión documentada con justificación clínica.
- **Entrenamiento en dos fases** (warm-up con backbone congelado + fine-tuning descongelando) con hiperparámetros concretos (AdamW, lr 1e-3/1e-4, batch 32, 20 épocas max con early stopping sobre `val_f1_macro` patience 5).
- **Augmentation clínicamente realista**: random crop, flip horizontal, rotación ±10°, color jitter suave. Sin flip vertical (anatómicamente incorrecto).
- **Análisis crítico** obligatorio: recall de COVID-19 como métrica crítica, impacto clínico de cada tipo de error (falso negativo COVID = peor escenario), limitaciones del dataset.
- **Estructura de código**: `app/{app,schemas,predictor,config}.py` + `training/{prepare_data,dataset,augment,model,train,evaluate,critical_analysis}.py`.
- **Versionado**: `rx-YYYYMMDD-hash8` + symlink `current`. Estructura del artefacto con `model.pt`, métricas, matriz de confusión, análisis crítico.
- **Requirements pinneados** (torch 2.4.1, torchvision, pillow, fastapi). Aviso sobre tamaño de imagen: considerar wheel CPU-only (~200 MB vs ~800 MB).
- **Checklist de tests** unitarios, entrenamiento, servicio e integración mapeado a los CAs de SDD-06.

### Added (DESIGN-03 almacenamiento — 2026-04-21)

- **`specs/DESIGN-03-almacenamiento.md`** (versión 1.0, `ready-for-implementation`): diseño técnico de la persistencia. Cierra 2 de los 4 `[NEEDS CLARIFICATION]` de SDD-03 §7:
  - **Formato `pseudo_id`**: `PAT-NNNNNN` (prefijo + 6 dígitos zero-pad). Contador atómico en colección Mongo `counters` vía `find_one_and_update($inc, upsert=True)` — idempotente y reproducible cross-run.
  - **Reconciliación PG↔Mongo**: doble vía — job periódico cada 60 s en automation + check lazy al leer desde API. Umbral de huérfano viejo: 24 h (`RECONCILIATION_STALE_HOURS` configurable).
  - *Umbrales de rendimiento y tamaño de subset siguen `[NEEDS CLARIFICATION]`, por dependencias externas (medir, DESIGN-06).*
- **Schemas detallados de las 8 colecciones Mongo** (`radiographs.{files,chunks}`, `predictions_radiography`, `predictions_triage`, `reports`, `alerts`, `system_events`, `ingestion_rejects`, `counters`) con ejemplos de documento, campos obligatorios e índices complementarios a los ya creados en `init.js`.
- **`predictions_triage` incluye `ficha_snapshot`**: copia exacta de los 15 campos del formulario que produjeron la predicción (auditabilidad SDD-08 RF-14, coste < 1 KB/doc).
- **`alerts` con `dedup_key` UNIQUE**: dedup por clave lógica consistente con SDD-04 RF-14 — `update_one(upsert)` evita duplicados.
- **Transacciones e idempotencia**: mapa de operaciones con su garantía (`ON CONFLICT DO NOTHING` en PG, `$inc` atómico por doc en Mongo, dedup por hash en GridFS).
- **Referencia explícita al DDL existente** en `init/postgres/init.sql` e `init/mongo/init.js` (anonimizados en commit `c64a0f4`) — DESIGN-03 los complementa, no los sustituye.
- **Índices adicionales** propuestos (`metadata.content_hash`, `triage_status`, `dedup_key`) a añadir solo si las mediciones lo exigen ("no optimizar sin medir").
- **Credenciales**: Sprint 2 usa root del compose; Sprint 3 opcional mover a usuarios de aplicación con permisos mínimos.
- **Vista materializada** opcional `mv_pacientes_con_ultimo_ingreso` para acelerar el dashboard en Sprint 3.
- **Checklist de tests** con mapeo a CAs de SDD-03.

### Added (DESIGN-02 pipeline ETL — 2026-04-21)

- **`specs/DESIGN-02-pipeline.md`** (versión 1.0, `ready-for-implementation`): diseño técnico del pipeline de datos. Cierra 4 de los 5 `[NEEDS CLARIFICATION]` de SDD-02 §7:
  - **Volumen/tiempo objetivo**: 10 000 registros + 1 000 radiografías en < 10 min CPU.
  - **Orquestación**: cron + scripts en Sprint 2; Prefect diferido como mejora opcional.
  - **Política de dedup**: `first_wins` — el primer registro gana, los siguientes van a `ingestion_rejects`.
  - **Reglas declarativas**: **YAML** (`config/validation_rules.yaml`) parseado con `PyYAML` y validado estructuralmente con Pydantic al arranque.
- **Estructura de código** del pipeline definida (`app/{cli,config,orchestrator,online}.py` + `phases/{ingestion,validation,transformation,loading,aggregates}.py` + `storage/{postgres,mongo,raw_source}.py` + `clients/triage_client.py`).
- **Interfaz `RawSource`** con implementaciones `LocalFSSource` y `S3Source` (boto3 con `endpoint_url` configurable — mismo código para AWS real y MinIO local). Desbloquea implementación aunque la decisión S3 siga diferida.
- **Justificación formal de pandas** (SDD-02 RF-18) con tabla de equivalencias pandas↔Dask y estimación del coste de migración (< 1 día). Material reutilizable en la memoria técnica §9.3.8.
- **Contrato YAML de reglas** con ejemplos completos para `paciente` y `radiografia`: `required_fields`, `field_rules` (type/min/max/pattern/enum/nullable), `cross_field_rules` con severidad, `deduplication.policy`.
- **Modo online**: función sincrona `process_patient_ficha(ficha, correlation_id)` que la API importa directamente; latencia objetivo end-to-end < 1.5 s incluyendo llamada al modelo de triaje.
- **Cron jobs** sugeridos para batch diario y generación de informe (coordinado con SDD-04).
- **Requirements pinneados** (pandas, SQLAlchemy, psycopg2-binary, pymongo, PyYAML, pydantic, boto3, httpx, tenacity, loguru).
- **Checklist de validación** con tests unitarios e integración mapeados a los CA de SDD-02.

### Added (DESIGN-08 modelo triaje — 2026-04-20)

- **`specs/DESIGN-08-modelo-triaje.md`** (versión 1.0, `ready-for-implementation`): diseño técnico del modelo tabular de triaje. Cierra las 6 dudas abiertas de SDD-08:
  - Algoritmo: `HistGradientBoostingClassifier` de sklearn (sin LightGBM/XGBoost extra). Hiperparámetros concretos y justificación.
  - Ruido: 10 % total (5 % etiqueta adyacente + 5 % contradicciones síntoma-target).
  - Imputación: mediana para opcionales (`peso_kg`, `altura_cm`), calculada en training y persistida en el artefacto.
  - Servicio: dedicado `ml-triage` (ya creado, puerto 8002).
  - Latencia objetivo: p95 < 200 ms en CPU.
  - Flag `low_confidence` cuando `max(probabilities) < 0.50`.
- **Reglas concretas del generador sintético** (13 reglas clínicas en prioridad Alta → Baja) con distribuciones por feature, volumen 10 000 filas, splits estratificados 70/15/15.
- **Estructura de código del servicio** definida: `app/{app,schemas,predictor,config}.py` + `training/{generate_dataset,rules,train,evaluate,critical_analysis}.py`.
- **Contrato de versionado**: `model_version = tri-YYYYMMDD-<hash8>`, persistida en cada predicción (ligada a `predictions_triage` de Mongo por `pseudo_id`).
- **Checklist implementable** con 10 puntos verificables antes de dar por buena la implementación.

### Pending decisions (2026-04-20)

- **Capa raw en S3**: los datos crudos (radiografías + CSVs clínicos) residirán en un bucket S3. Hay credenciales AWS disponibles. Decisión diferida entre tres opciones: (a) solo AWS S3 real, (b) solo MinIO local S3-compatible, (c) AWS con fallback MinIO si `AWS_ACCESS_KEY_ID` vacío. Registrado como `[NEEDS CLARIFICATION]` en SDD-01 §7, SDD-02 §7, SDD-03 §7. Cuando se cierre: actualizar esos SDDs, `DESIGN-01-arquitectura.md`, añadir (o no) servicio MinIO al compose, añadir `boto3` a los requirements del pipeline y variables `AWS_*`/`S3_ENDPOINT` al `.env.example`.

### Changed (post-merge ariadna→pol: init scripts reescritos — 2026-04-20)

- **`init/postgres/init.sql`** reescrito para cumplir anonimización por diseño (SDD-01 RNF-8, SDD-03 RF-14):
  - Tabla `pacientes` ahora usa `pseudo_id TEXT PRIMARY KEY` en vez de `id SERIAL` + `nombre TEXT`. Se eliminan `nombre` y `fecha_nac`; se sustituyen por `edad` + atributos clínicos no identificativos (`sexo`, `peso_kg`, `altura_cm`, `fumador`, `embarazo`, `enfermedades_cronicas TEXT[]`).
  - Tabla `ingresos` referencia `paciente_pseudo_id` (FK a `pacientes.pseudo_id`, `ON DELETE RESTRICT`) y añade todos los campos del formulario de triaje (SDD-08 RF-1): `motivo_principal`, `duracion_sintomas`, `intensidad_dolor`, `fiebre_subjetiva`, `dificultad_respiratoria_subjetiva`, `tos`, `contacto_covid_reciente`, `hora_envio`.
  - **Campos de trazabilidad obligatorios** (SDD-03 RF-9): `source`, `ingested_at`, `processed_by` en ambas tablas.
  - Restricciones `CHECK` sobre dominios categóricos y rangos numéricos.
  - Índices en `ingresos(paciente_pseudo_id)`, `ingresos(fecha_ingreso DESC)`, `pacientes(ingested_at DESC)`.
  - **Eliminados los datos de ejemplo con nombres personales** ("Ana Pérez"/"Luis Gómez"). El seed sintético se carga por el pipeline (SDD-02 RF-6) con `pseudo_id` generados reproduciblemente.
- **`init/mongo/init.js`** reescrito:
  - Colecciones dedicadas alineadas con los SDDs: `predictions_radiography` (SDD-06), `predictions_triage` (SDD-08), `reports`, `alerts`, `system_events`, `ingestion_rejects` (todas SDD-02/03/04).
  - GridFS con bucket `radiographs` para binarios de imagen (SDD-03 RF-2, RF-12) + índices sobre `filename` y `{files_id, n}`.
  - Índices para consultas típicas del dashboard y reconciliación (SDD-03 RF-13, SDD-05 endpoints).
  - `getCollectionNames()` (deprecated en Mongo 7) → `getCollectionInfos()`.
  - Eliminada la colección `pacientes` con nombres personales (persiste solo en PostgreSQL como fuente de verdad relacional).
  - Usuario `appuser` con `readWrite` sobre `hospital` mantenido.

### Added (Sprint 1: Infraestructura Docker y servicios base — 2026-04-20)

**Docker & Orquestación:**
- `Dockerfile` multietapa en raíz con 5 stages: `api`, `pipeline`, `ml-inference`, `dashboard`, `automation`.
- `docker-compose.yml` v3.9+ con 11 servicios:
  - Databases: `postgres:16-alpine`, `mongo:7`
  - Aplicaciones: `api`, `pipeline`, `ml-inference`, `dashboard`, `automation` (todos build desde `Dockerfile`)
  - UIs de admin: `pgadmin:7.8`, `mongo-express:1.0.0`
  - Monitorización: `loki:2.8.2`, `promtail:2.8.2`
- Red interna `hospital-net` (bridge) con DNS por nombre de servicio.
- 5 volúmenes nombrados: `postgres-data`, `mongo-data`, `pgadmin-data`, `models-data` + bind mount `./data` para dataset.
- Healthchecks definidos en todos los servicios (< 90s para `healthy`).
- Logging JSON con límites (5-10 MB, 2-3 archivos).
- Restart policies: `on-failure` para apps, `unless-stopped` para BBDD.

**Variables de entorno & Configuración:**
- `.env.example` con 31 variables (no secrets en repo, solo placeholders).
- Todas las variables referenciadas en `docker-compose.yml` externalizadas.
- Comentarios descriptivos para cada bloque (PostgreSQL, MongoDB, API, Dashboard, ML, Admin UIs).

**Inicialización de datos:**
- `./init/postgres/init.sql`: tablas `pacientes`, `ingresos` con datos de ejemplo y timestamps.
- `./init/mongo/init.js`: colección `pacientes` en BD `hospital`, usuario de aplicación `appuser`.
- Scripts ejecutados automáticamente en primera ejecución de contenedores (via `/docker-entrypoint-initdb.d/`).

**Monitorización & Logging:**
- `./monitoring/loki-config.yaml`: almacenamiento local con boltdb-shipper + filesystem.
- `./monitoring/promtail-config.yaml`: recolector de logs desde `/var/log/` hacia Loki (puerto 3100).
- Todos los servicios emiten logs a stdout (formato json-file driver).

**Aplicaciones base:**
- `services/api/app/main.py`: FastAPI con endpoints `/health` y `/` (stub).
- `services/api/requirements.txt`: fastapi, uvicorn, psycopg2-binary, pymongo, requests.
- `services/pipeline/main.py`: script Python que simula procesamiento de datos.
- `services/pipeline/requirements.txt`: pandas, pymongo, psycopg2-binary.
- `services/ml-inference/app/app.py`: FastAPI con `/health` y `/predict` (stub con numpy).
- `services/ml-inference/requirements.txt`: fastapi, uvicorn, numpy, python-multipart.
- `services/dashboard/app.py`: Streamlit que consulta estado de API interna.
- `services/dashboard/requirements.txt`: streamlit, requests.
- `services/automation/main.py`: script de ejemplo que ejecuta tareas cada 30s (logging).
- `services/automation/requirements.txt`: (vacío, stub mínimo).

**Documentación & Referencia:**
- `README.md`: instrucciones de deploy en raíz.
  - Requisitos: Docker 20.10+, Docker Compose v2.x.
  - Pasos: `cp .env.example .env` → `docker compose up -d`.
  - Tabla de URLs de servicios (API: 8000, Dashboard: 8501, pgAdmin: 5050, Mongo Express: 8081, Loki: 3100).
  - Comandos para parar (`down`), reset (`down -v`), logs, troubleshooting.
  - Validación de criterios SDD-01.

### Changed (Sprint 1: Alineación SDD-01 con implementación)

**`specs/DESIGN-01-arquitectura.md`:**
- **Tabla 5.1 (Servicios)**: actualizada con 11 servicios reales (antes TBD para monitoring). Cada uno con: imagen/build, puerto, dependencias, SDD de detalle. Ahora especifica:
  - Stages del `Dockerfile` para apps internas.
  - Puerto en variables de entorno (`API_PORT`, `DASHBOARD_PORT`).
  - Puertos fijos para UIs (5050 pgAdmin, 8081 Mongo Express, 3100 Loki).
- **Sección 5.4 (Variables de entorno)**: especificado formato `.env`/`.env.example` con todas las 31 variables comentadas (antes solo 14). Incluye:
  - POSTGRES_HOST, POSTGRES_PORT (antes omitidos).
  - MONGO_HOST, MONGO_PORT, MONGO_GRIDFS_BUCKET (antes omitidos).
  - PGADMIN_DEFAULT_EMAIL, PGADMIN_DEFAULT_PASSWORD (actualizados).
- **Criterios de aceptación (§4)**: 10 criterios marcados como `[x] Completado` con verificación de cómo probar cada uno.
  - `docker compose config` validación YAML.
  - Healthchecks en todos los servicios.
  - Volúmenes nominados para persistencia.
  - Red `hospital-net` con DNS.
  - Scripts de init en `/docker-entrypoint-initdb.d/`.
  - `.env.example` sin variables hardcoded.
  - README en raíz (creado).
  - Puertos documentados.
  - GridFS en MongoDB (preparado en init.js).

**`CONTEXT.md`:**
- Añadida sección 3.1 con decisión explícita: **Modelo seleccionado: Clasificación de pacientes** (breve justificación técnica).

### Removed
- Dockerfiles individuales en `services/*/Dockerfile` (consolidados en `Dockerfile` raíz multietapa).

### Fixed
- Servicios sin healthcheck en compose → ahora todos los 11 servicios tienen uno.
- Variables hardcoded en compose (puertos, credenciales) → externalizadas a `.env.example`.
- Falta de documentación de deploy básico → creado `README.md` con instrucciones paso a paso.

### Verified
- `docker compose config`: valida sin errores (YAML structure).
- Red `hospital-net`: definida, todos los servicios la usan.
- Volúmenes nombrados: 4 declarados en compose (postgres-data, mongo-data, pgadmin-data, models-data).
- Dependencias entre servicios: especificadas con `depends_on`.
- Init scripts: montados correctamente en `/docker-entrypoint-initdb.d/`.
- Logging: todos los servicios con driver json-file + límites de tamaño.

### Added
- `CHANGELOG.md` (este archivo).
- Carpeta `specs/` para los Spec-Driven Design documents (§5.2 del enunciado).
- `specs/_template.md`: plantilla común de SDD (8 secciones fijas).
- `specs/SDD-01-arquitectura.md`: arquitectura global del sistema + `docker-compose.yml` (8 servicios, red `hospital-net`, 3 volúmenes nombrados, contrato de variables de entorno).

### Changed
- **Almacenamiento**: MongoDB + MinIO → **PostgreSQL + MongoDB (GridFS)**. Reparto: PG para estructurados (pacientes, ingresos, personal, logs), Mongo para no estructurados (radiografías vía GridFS, predicciones, informes, eventos). SDD-01 actualizado: tabla de servicios, diagrama, volúmenes, variables de entorno, alternativas y plan de escalado.
- **Plantilla SDD reescrita** según estructura del Master (PDF "Spec Driven Development"): secciones *Contexto y objetivo · Actores y alcance · Requisitos funcionales · Requisitos no funcionales · Casos borde / errores · Criterios de aceptación · Dudas abiertas* con tag `[NEEDS CLARIFICATION]`. Se separa spec de diseño (el diseño pasa a `DESIGN-XX-...md`).
- **Renombrado**: `SDD-01-arquitectura.md` → `DESIGN-01-arquitectura.md` (era diseño arquitectónico, no spec).
- **`SDD-01-sistema.md` completado** (versión 1.0, estado `ready-for-design`): spec raíz del sistema global con 23 RF, 17 RNF, 20 casos borde, 25 criterios de aceptación y 3 `[NEEDS CLARIFICATION]` pendientes (umbral P(COVID-19), umbrales de rendimiento, regla de desempate de probabilidades).
- **`SDD-03-almacenamiento.md` completado** (versión 1.0, estado `ready-for-design`): spec del subsistema de persistencia PostgreSQL + MongoDB (GridFS). 17 RF, 15 RNF, ~20 casos borde, 22 criterios de aceptación y 4 `[NEEDS CLARIFICATION]` (rendimiento consultas, tamaño subset dataset, reconciliación PG↔Mongo, formato pseudo_id).
- **`SDD-02-pipeline.md` completado** (versión 1.0, `ready-for-design`): pipeline de datos con pandas (autorizado por el profesor). 18 RF, 10 RNF, casos borde y 16 CA. Incluye justificación técnica y plan de escalado a Dask. 4 `[NEEDS CLARIFICATION]` (volumen/tiempo, orquestador, política upsert, lenguaje reglas).
- **`SDD-06-modelo-dl.md` completado** (versión 1.0, `ready-for-design`): clasificación triple Sana/Neumonía/COVID-19 con transfer learning (PyTorch). 17 RF, 9 RNF, casos borde y 12 CA. Evaluación con matriz de confusión y reflexión clínica obligatoria. 6 `[NEEDS CLARIFICATION]` (arquitectura backbone, splits, balance, umbral COVID, regla desempate, latencia).
- **`SDD-05-api-dashboard.md` completado** (versión 1.0, `ready-for-design`): API FastAPI + Dashboard. 21 RF, 11 RNF, casos borde y 18 CA. OpenAPI automático, sin autenticación. 4 `[NEEDS CLARIFICATION]` (Streamlit vs Grafana, upload sync/async, umbrales rendimiento, imagen inline vs endpoint).
- **`SDD-04-automatizacion.md` completado** (versión 1.0, `ready-for-design`): watchers, scheduler, alertas, reintento con backoff, reconciliación PG↔Mongo. 17 RF, 8 RNF, casos borde y 13 CA. 7 `[NEEDS CLARIFICATION]` (orquestador cron vs Prefect, mecanismo watcher, umbrales COVID y tasas, deduplicación, política huérfanos, política informe duplicado).
- **`SDD-07-monitorizacion.md` completado** (versión 1.0, `ready-for-design`): logging JSON estructurado con `correlation_id`, reglas de calidad de datos transversales, alertas operativas (coordinadas con SDD-04). 15 RF, 8 RNF, casos borde y 11 CA. 5 `[NEEDS CLARIFICATION]` (backend logs, intervalo chequeo, umbral rechazos, retención, parseo logs de BBDD).

### Added (iteración 2 — segundo modelo de IA)

- **`SDD-08-modelo-triaje.md`** (versión 1.0, `ready-for-design`): nuevo SDD para el **modelo tabular de triaje de pacientes** (§3.1 del enunciado, *"clasificación de pacientes"*). 21 RF, 11 RNF, casos borde y 14 CA. Target: *Alta / Media / Baja* (3 niveles). Dataset **sintético** con reglas + ruido + variables espurias (incluye `hora_envio` como espuria intencional). Formulario web de 14 campos **auto-reportados** por el paciente (sin constantes vitales — sistema autoservicio, no triaje profesional). Entrena offline, predice online al final del pipeline. 6 `[NEEDS CLARIFICATION]` (algoritmo, ruido, imputación, servicio compartido vs dedicado, umbrales).

### Changed (iteración 2 — integración del modelo de triaje)

- **`SDD-01-sistema.md`**: incorporado el flujo de **triaje web** y el segundo modelo. Se actualizan §1 Objetivo (menciona triaje y dos modelos), §2 Actores (añade *paciente* como actor humano vía formulario, *servicio de triaje tabular* como servicio interno, *dataset sintético de triaje* como fuente) y §2 Dentro del alcance (formulario web, pipeline online).
- **`SDD-02-pipeline.md`**: añadido **modo online** del pipeline (§1 Objetivo, §2 Alcance, nuevos RF-24 a RF-29) que procesa una única ficha del formulario y acaba invocando a SDD-08 para dejar el triaje persistido antes de responder al cliente.
- **`SDD-05-api-dashboard.md`**: añadido endpoint `POST /patients` (RF-2bis) para la ficha del formulario y vista **Triaje pre-consulta** (RF-19bis) con formulario y página de confirmación mostrando el nivel predicho.

---

## 2026-04-20 — Sprint 0: Planificación inicial

### Added
- `CONTEXT.md` con resumen exhaustivo del enunciado (incluye easter eggs del PDF).
- Plan global del proyecto aprobado (roadmap 3 sprints, 7 SDDs, stack definido).

### Decided
- **API**: FastAPI (tipado, async, OpenAPI automático).
- **Procesamiento**: pandas (autorizado por el profesor, aunque §4.2.3 solo liste Spark/Dask/Beam).
- **Almacenamiento**: MongoDB (documental) + MinIO (imágenes) — NoSQL predominante por indicación del profesor.
- **Modelo DL**: PyTorch + transfer learning (arquitectura concreta a cerrar en SDD-06).
- **Herramienta IA obligatoria**: Claude Code.

### Pending
- Dashboard: Streamlit vs Grafana (decisión en SDD-05).
- Orquestación de pipeline: cron+scripts vs Prefect/Airflow (decisión en SDD-04).
- Dataset radiografías: confirmar *COVID-19 Radiography Database* en SDD-06.

### Added (Dask + pipeline Big Data + modelos tabulares validados — 2026-05-14)

- **Dask integrado como framework de procesamiento escalable** para cumplir el requisito de infraestructura Big Data del enunciado:
  - Añadidos servicios `dask-scheduler` y `dask-worker` en `docker-compose.yml`.
  - Expuesto el dashboard de Dask en `http://localhost:8787/status`.
  - Añadidas variables de entorno:
    - `PIPELINE_PROCESSING_ENGINE=dask`
    - `DASK_SCHEDULER_ADDRESS=tcp://dask-scheduler:8786`
    - `DASK_DASHBOARD_PORT=8787`
    - `DASK_WORKERS`
    - `DASK_THREADS_PER_WORKER`
    - `DASK_WORKER_MEMORY`
    - `DASK_CSV_BLOCKSIZE`
    - `DASK_SHARED_TMP_DIR`
  - Añadido `services/pipeline/app/dask_runtime.py` para conectar el pipeline con el scheduler distribuido o usar fallback local.
  - Añadido `services/pipeline/app/phases/scalable_csv.py` para lectura batch de CSVs con `dask.dataframe`.
  - Añadidas dependencias de Dask y Bokeh al pipeline para habilitar procesamiento escalable y dashboard visual.

- **Pipeline batch validado end-to-end con Dask**:
  - Prueba Dask sobre 10.000 filas: `6` particiones, `10.000` filas procesadas, suma correcta `49.995.000`, `1` worker activo.
  - Ejecución batch sobre CSV generado automáticamente y almacenado en MinIO:
    - `records_in=100`
    - `valid=100`
    - `rejected=0`
    - `pacientes_insertados=100`
    - `ingresos_insertados=100`
    - `triage_completed=100`
    - `triage_pending=0`
  - Logs estructurados con `correlation_id` y eventos:
    - `pipeline.run.start`
    - `dask.connected`
    - `pipeline.file.read`
    - `pipeline.validation.done`
    - `pipeline.transformation.done`
    - `pipeline.loading.done`
    - `pipeline.ml.done`
    - `pipeline.aggregates.updated`
    - `pipeline.run.end`

- **Modelos tabulares entrenados y versionados**:
  - Generado artefacto de triaje:
    - `models/triage/tri-20260514-60eff3c2/`
    - `model.joblib`
    - `metadata.json`
    - `metrics.json`
    - `confusion_matrix.png`
    - `critical_analysis.md`
  - Generado artefacto de sospecha de enfermedad:
    - `models/disease/dis-20260514-8c9a3874/`
    - `model.joblib`
    - `metadata.json`
    - `metrics.json`
    - `confusion_matrix.png`
    - `critical_analysis.md`
  - Marcadores activos:
    - `models/triage/current.txt`
    - `models/disease/current.txt`

- **Evaluación de modelos tabulares**:
  - Modelo de triaje:
    - `accuracy=0.9180`
    - `f1_macro=0.8978`
  - Modelo de sospecha de enfermedad:
    - `accuracy=0.9267`
    - `f1_macro=0.8665`
    - `f1_weighted=0.9250`
  - Generadas matrices de confusión y análisis crítico para ambos modelos.

- **Scripts de soporte añadidos**:
  - `scripts/train_tabular_models.ps1`: entrena los modelos tabulares dentro del contenedor Docker `ml-triage`, evitando problemas de compatibilidad con Python local en Windows.
  - `scripts/evaluate_tabular_models.ps1`: genera métricas, matrices de confusión y análisis crítico dentro del contenedor Docker.

### Changed (Normalización y robustez del pipeline ML — 2026-05-14)

- **`services/pipeline/app/clients/triage_client.py`** reescrito para normalizar la ficha antes de enviarla a `ml-triage`:
  - Convierte `NaN`, `None`, strings vacíos y valores nulos en valores compatibles con el schema.
  - Normaliza enums como `sexo`, `fumador`, `embarazo`, `motivo_principal`, `duracion_sintomas`, `fiebre_subjetiva`, `dificultad_respiratoria_subjetiva`, `tos` y `contacto_covid_reciente`.
  - Convierte `enfermedades_cronicas` desde lista, string separado por `|` o string separado por `,`.
  - Limita rangos de seguridad para `edad`, `intensidad_dolor` y `hora_envio`.
  - Reduce errores `422 Unprocessable Entity` durante el batch.

- **`services/ml-triage/requirements.txt`** actualizado para incluir dependencias necesarias tanto para inferencia como para evaluación:
  - `matplotlib==3.10.0`
  - `requests==2.32.3`
  - dependencias de entrenamiento/evaluación alineadas con el runtime.

- **`docker-compose.yml`** actualizado para montar `./data:/app/data` también en servicios que necesitan acceso compartido a ficheros procesados por Dask.

### Fixed (Errores de integración detectados en pruebas — 2026-05-14)

- Corregido el problema de Dask distribuido donde el worker no podía leer ficheros temporales creados en `/tmp` por el contenedor `pipeline`; ahora se usa una ruta compartida en `/app/data/tmp/dask`.
- Corregido el problema de entrenamiento local en Windows con Python 3.14, donde `scikit-learn==1.6.0` intentaba compilar desde fuente. El entrenamiento tabular se ejecuta ahora dentro del contenedor Docker con Python 3.12.
- Corregido el estado `unhealthy` de `ml-triage`, causado por ausencia de artefactos en `models/triage/current` y `models/disease/current`.
- Corregidos errores `422` parciales del pipeline batch mediante normalización previa de payloads enviados a `ml-triage`.
- Corregido el dashboard de Dask añadiendo dependencia `bokeh`.

### Verified

- `GET http://localhost:8005/health` devuelve `{"status":"ok"}`.
- Dashboard Streamlit disponible en `http://localhost:8502`.
- Dask dashboard disponible en `http://localhost:8787/status`.
- `dask-scheduler` healthy y `dask-worker` conectado con `Workers: 1`.
- `ml-triage` healthy:
  - `triage_version=tri-20260514-60eff3c2`
  - `disease_version=dis-20260514-8c9a3874`
- Predicción directa contra `ml-triage` validada:
  - caso paciente 72 años, dolor torácico, cardiopatía, dolor 9/10
  - triaje: `Alta`
  - probabilidad Alta: ~98 %
  - sospecha: `cardiopatia_aguda_sospecha`
- Flujo online validado desde dashboard:
  - paciente `PAT-000401`
  - `ml_status=completed`
  - raw persistido en MinIO
  - eventos online visibles en dashboard.
- Flujo batch validado:
  - `100` registros procesados
  - `100` válidos
  - `0` rechazados
  - `100` pacientes cargados
  - `100` ingresos cargados
  - `100` predicciones ML completadas
  - `0` pendientes.

  ### Pending

- `ml-inference` sigue pendiente de cerrar completamente hasta disponer de un artefacto activo para radiografías en `models/radiography/` o la ruta configurada en `ML_MODEL_PATH`.


## [Unreleased] - 2026-05-15

### Added
- Añadido procesamiento escalable con Dask:
  - Servicio `dask-scheduler` con dashboard en el puerto `8787`.
  - Servicio `dask-worker` conectado al scheduler interno.
  - Integración del pipeline con `DASK_SCHEDULER_ADDRESS`.
  - Lectura CSV escalable con particionado y metadatos de ejecución (`processing_engine`, `dask_partitions`, `dask_blocksize`, `dask_scheduler`).

- Añadido servicio `ml-triage` combinado:
  - Modelo de triaje tabular: predicción `Alta`, `Media`, `Baja`.
  - Modelo de sospecha de enfermedad: diagnóstico diferencial con probabilidades.
  - Endpoint `GET /health`.
  - Endpoint `POST /predict`.
  - Carga de artefactos desde `models/triage/current` y `models/disease/current`.

- Añadido entrenamiento reproducible de modelos tabulares dentro de Docker:
  - Generación de dataset sintético con semilla.
  - Entrenamiento de modelo de triaje.
  - Entrenamiento de modelo de sospecha de enfermedad.
  - Artefactos versionados `tri-YYYYMMDD-*` y `dis-YYYYMMDD-*`.
  - Marcadores `current.txt` para compatibilidad con Windows.

- Añadida evaluación de modelos tabulares:
  - `metrics.json`.
  - `confusion_matrix.png`.
  - `critical_analysis.md`.
  - Métricas finales obtenidas:
    - Triaje: `accuracy=0.9180`, `f1_macro=0.8978`.
    - Enfermedad: `accuracy=0.9267`, `f1_macro=0.8665`, `f1_weighted=0.9250`.

- Añadida persistencia de predicciones ML en el pipeline:
  - Predicción de triaje por paciente.
  - Predicción de sospecha de enfermedad.
  - Estado `completed` / `pending` para inferencia.
  - Integración en el resumen final del batch con `triage_completed` y `triage_pending`.

- Añadido logging centralizado con Loki + Promtail:
  - Servicio `loki` persistente con volumen `loki-data`.
  - Servicio `promtail` con descubrimiento Docker.
  - Volumen `promtail-positions` para evitar relectura completa de logs.
  - Filtro de Promtail por proyecto Docker Compose.
  - Descarte de logs antiguos con `drop.older_than`.

- Añadido sistema de eventos de dominio en MongoDB:
  - Colección `system_events`.
  - Eventos estructurados del pipeline:
    - `pipeline.run.start`
    - `pipeline.file.read`
    - `pipeline.validation.done`
    - `pipeline.transformation.done`
    - `pipeline.loading.done`
    - `pipeline.ml.done`
    - `pipeline.aggregates.updated`
    - `pipeline.run.end`
  - Cada evento incluye `correlation_id`, `level`, `message` y `payload`.

- Añadido servicio `automation` para monitorización básica:
  - Escaneo periódico de eventos del sistema.
  - Preparado para generar alertas a partir de eventos `warning` y `error`.

### Changed
- Actualizado `docker-compose.yml`:
  - Añadidos servicios `dask-scheduler` y `dask-worker`.
  - Añadidos servicios `loki` y `promtail`.
  - Añadido volumen persistente `loki-data`.
  - Añadido volumen `promtail-positions`.
  - Añadidas variables de entorno para Dask.
  - Añadido bind mount `./models:/app/models` en servicios ML.
  - Añadido bind mount `./data:/app/data` donde aplica.

- Actualizado el pipeline batch:
  - Ahora conecta con Dask cuando `PIPELINE_PROCESSING_ENGINE=dask`.
  - Registra metadatos de Dask en eventos de ingesta.
  - Ejecuta inferencia ML después de cargar pacientes e ingresos.
  - Actualiza agregados diarios con métricas de triaje completado/pendiente.

- Actualizado `ml-triage`:
  - El servicio ahora exige ambos modelos cargados para devolver `healthy`.
  - Se corrigió la carga de artefactos mediante `current.txt` en Windows.
  - Se verificó `/health` con respuesta:
    - `triage_version=tri-20260514-60eff3c2`
    - `disease_version=dis-20260514-8c9a3874`

- Actualizado `.gitignore`:
  - Exclusión de datasets y artefactos reproducibles:
    - `data/synthetic/`
    - `data/raw/`
    - `data/covid-subset/`
    - `models/`
  - Exclusión de entorno local `.env`.

### Fixed
- Corregido error inicial de Dockerfile por contenido Markdown pegado accidentalmente.
- Corregido error de build por `COPY models/triage` cuando no existían artefactos locales.
- Corregido problema de variables `.env` no cargadas usando `docker compose --env-file .env`.
- Corregidos conflictos de puertos:
  - API movida a `8005`.
  - Dashboard movido a `8502`.
- Corregido error de Dask con `/tmp/test_dask.csv`, usando ruta compartida `/app/data/tmp/test_dask.csv`.
- Corregido estado `unhealthy` de `ml-triage` entrenando y montando artefactos reales.
- Corregidos errores `503` del servicio `ml-triage` provocados por modelos ausentes.
- Corregidos errores `422` en batch tras reconstruir `pipeline` y `api` con el payload actualizado.
- Corregido problema de `matplotlib` ausente en la imagen de `ml-triage` para poder generar matrices de confusión.
- Corregido `docker-compose.yml` tras duplicación de claves `build`.
- Corregido Loki/Promtail para evitar ingesta de logs antiguos de otros proyectos Docker.

### Verified
- Dask validado desde el contenedor `pipeline`:
  - Scheduler accesible en `tcp://dask-scheduler:8786`.
  - Worker registrado correctamente.
  - CSV de prueba procesado con varias particiones.

- `ml-triage` validado:
  - `GET /health` devuelve `status=ok`.
  - `POST /predict` devuelve triaje + sospecha de enfermedad.
  - Ejemplo verificado: paciente con dolor torácico y cardiopatía predicho como `Alta` y `cardiopatia_aguda_sospecha`.

- Pipeline batch validado end-to-end:
  - CSV generado en MinIO.
  - Ingesta correcta desde S3/MinIO.
  - Validación YAML correcta.
  - Carga en PostgreSQL correcta.
  - Predicción ML completada para todos los registros.
  - Última prueba:
    - `records_in=20`
    - `valid=20`
    - `rejected=0`
    - `triage_completed=20`
    - `triage_pending=0`

- MongoDB validado:
  - Eventos de dominio persistidos en `system_events`.
  - Consulta de eventos `warning/error` funcionando.
  - Eventos históricos de fallo ML disponibles para demostrar alertas y trazabilidad.

- Loki validado parcialmente:
  - Servicio `loki` en estado `healthy`.
  - Endpoint `/ready` devuelve `ready`.
  - Promtail arranca y descubre contenedores Docker del proyecto.
  - Filtro contra logs de otros proyectos aplicado.
  - Pendiente: revisar consulta final de `query_range` porque la query por `compose_service="pipeline"` todavía devuelve `result: []`.

  ### Evidence / comandos de verificación

```powershell
docker compose ps
docker compose exec pipeline python main.py seed --n 20 --seed 890
docker compose exec pipeline python main.py batch --key "<key-generada>"
docker compose exec ml-triage curl -s http://localhost:8002/health
docker compose exec mongodb mongosh -u admin -p change-me --authenticationDatabase admin hospital --eval "db.system_events.find().sort({timestamp:-1}).limit(10).pretty()"
docker compose exec mongodb mongosh -u admin -p change-me --authenticationDatabase admin hospital --eval "db.system_events.find({level:{`$in:['warning','error']}}).sort({timestamp:-1}).limit(10).pretty()"
curl.exe -s http://localhost:3100/ready

## Infraestructura Big Data, monitorización y calidad

- Integrado Loki + Promtail como sistema de logging centralizado para la infraestructura Docker Compose.
- Configurado Promtail con descubrimiento Docker (`docker_sd_configs`) y filtrado por proyecto Compose para recoger logs de los contenedores del sistema hospitalario.
- Añadidos volúmenes persistentes para Loki y posiciones de Promtail (`loki-data`, `promtail-positions`).
- Verificada la ingesta de logs del pipeline en Loki ejecutando el batch como job one-shot con `docker compose run`.
- Validada consulta LogQL sobre logs del pipeline:
  - `{compose_service="pipeline"}`
  - `{compose_service="pipeline"} |= "pipeline.run.end"`
- Confirmado que Loki devuelve eventos estructurados del pipeline con `correlation_id`, `event`, `records_in`, `duration_ms` y `file`.
- Mantenida auditoría funcional en MongoDB mediante la colección `system_events`, con eventos de dominio del pipeline: `pipeline.run.start`, `pipeline.file.read`, `pipeline.validation.done`, `pipeline.ml.done`, `pipeline.run.end`.
- Verificada trazabilidad de runs batch con Dask, MinIO, PostgreSQL, MongoDB y servicio `ml-triage`.

## 2026-05-15 — Monitorización, calidad de datos y alertas operativas

### Añadido
- Integración de Loki + Promtail para logging centralizado de contenedores Docker.
- Configuración de Promtail con descubrimiento de contenedores y filtrado por etiquetas Docker Compose.
- Servicio `automation` para escanear eventos operativos del pipeline en MongoDB.
- Colección `alerts` en MongoDB para registrar alertas simuladas ante warnings/errors del pipeline.
- Índices MongoDB para `alerts` y `system_events` (`dedup_key`, `created_at`, `status`, `timestamp`, `level`, `correlation_id`).
- Prueba de calidad de datos con CSV inválido (`patients/quality-test-invalid.csv`).

### Cambiado
- El pipeline emite eventos de dominio estructurados en MongoDB para fases críticas:
  - `pipeline.run.start`
  - `pipeline.file.read`
  - `pipeline.validation.done`
  - `pipeline.loading.done`
  - `pipeline.rejects.persisted`
  - `pipeline.ml.done`
  - `pipeline.aggregates.updated`
  - `pipeline.run.end`
- El servicio de automatización deduplica alertas por `event + correlation_id + level`.

### Corregido
- Corregido conflicto de actualización MongoDB en `automation` causado por campos repetidos entre `$setOnInsert` y `$set`.
- Corregida ejecución de Promtail para evitar ingestión accidental de logs antiguos de otros proyectos.
- Eliminados contenedores huérfanos generados por pruebas puntuales de `docker compose run`.

### Validado
- Loki y Promtail levantan correctamente y `GET /ready` devuelve `ready`.
- Consulta LogQL verificada contra Loki para recuperar logs del pipeline, incluyendo `pipeline.run.end`.
- Validación de calidad confirmada con un CSV de 5 filas:
  - `records_in: 5`
  - `valid: 1`
  - `rejected: 4`
  - `rejects_persisted: 4`
- MongoDB contiene los rechazos en `ingestion_rejects`, con motivos como:
  - `missing_field:edad`
  - `sexo:enum`
  - `intensidad_dolor:max:10`
- El servicio `automation` crea alertas en MongoDB para:
  - `pipeline.validation.done`
  - `pipeline.rejects.persisted`

  ### Monitorización y calidad de datos

El sistema incorpora dos niveles de observabilidad:

1. **Logs técnicos centralizados**
   - Todos los servicios emiten logs a stdout en Docker.
   - Promtail descubre los contenedores Docker y envía sus logs a Loki.
   - Loki permite consultar eventos del pipeline mediante LogQL.

2. **Eventos de dominio y alertas**
   - El pipeline persiste eventos de negocio en MongoDB (`system_events`) con `correlation_id`.
   - Los eventos incluyen fases de ingesta, validación, carga, ML, agregados y cierre de ejecución.
   - Un servicio de automatización revisa eventos `warning` y `error` recientes y crea alertas deduplicadas en la colección `alerts`.

La calidad de datos se valida mediante reglas declarativas YAML. En una prueba controlada con `patients/quality-test-invalid.csv`, el pipeline procesó 5 registros, aceptó 1 y rechazó 4. Los rechazos se persistieron en MongoDB (`ingestion_rejects`) con el motivo exacto de rechazo, y el servicio de automatización generó alertas operativas asociadas.

## Infraestructura Big Data y monitorización

- Se completa la arquitectura Docker Compose del sistema hospitalario con servicios independientes para almacenamiento, procesamiento, API, dashboard, modelos IA, monitorización y automatización.
- Se incorpora Dask como framework de procesamiento escalable:
  - `dask-scheduler`
  - `dask-worker`
  - integración del pipeline con `dask.dataframe`
  - dashboard disponible en `http://localhost:8787`
- Se valida el pipeline batch end-to-end:
  - generación reproducible de CSV sintético en MinIO
  - lectura desde S3/MinIO
  - validación declarativa YAML
  - transformación a entidades hospitalarias
  - carga en PostgreSQL
  - inferencia con `ml-triage`
  - persistencia de predicciones y eventos en MongoDB
- Se entrena y despliega el servicio `ml-triage` con dos modelos tabulares:
  - modelo de triaje (`Alta`, `Media`, `Baja`)
  - modelo de sospecha de enfermedad
  - endpoint combinado `/predict`
  - healthcheck correcto con versiones activas de modelo
- Se añade logging centralizado con Loki + Promtail:
  - Loki healthy en `http://localhost:3100/ready`
  - Promtail recoge logs Docker
  - consulta LogQL validada para eventos `pipeline.run.end`
- Se añade trazabilidad funcional mediante eventos de dominio en MongoDB:
  - `pipeline.run.start`
  - `pipeline.file.read`
  - `pipeline.validation.done`
  - `pipeline.loading.done`
  - `pipeline.ml.done`
  - `pipeline.run.end`
- Se añade prueba de calidad de datos con `patients/quality-test-invalid.csv`:
  - 5 registros procesados
  - 1 registro válido
  - 4 registros rechazados
  - rechazos persistidos en `ingestion_rejects`
- Se añade servicio `automation` para alertas operativas:
  - escaneo periódico de `system_events`
  - detección de eventos `warning` / `error`
  - creación de alertas deduplicadas en `alerts`
  - notificación simulada mediante MongoDB/dashboard

  ## Desarrollo asistido por IA y SDD

- Se documenta el uso de herramientas de IA durante el desarrollo:
  - Claude Code como asistente principal de implementación.
  - ChatGPT como asistente de arquitectura, debugging y documentación.
- Se consolida la metodología Spec-Driven Development mediante especificaciones en `specs/`.
- Se añade diario de desarrollo con IA en `docs/diario-ia/`.
- Se documentan prompts representativos, resultados obtenidos, iteraciones, errores corregidos y reflexión crítica.
- Se añade entrada específica sobre infraestructura Big Data, Dask, Loki/Promtail, calidad de datos y alertas operativas.


## Módulo Deep Learning — Clasificación de radiografías

- Iniciado el bloque de aprendizaje profundo para clasificación triple de radiografías de tórax: sana, neumonía y COVID-19.
- Definida la estrategia técnica basada en transfer learning con CNN preentrenada, evitando entrenamiento desde cero por limitaciones de dataset y riesgo de sobreajuste.
- Documentado el tratamiento de imágenes: redimensionamiento, normalización, conversión RGB, split estratificado y data augmentation moderado.
- Definida la integración del modelo dentro del servicio `ml-inference`, con endpoint `/healthz` y predicción de imágenes.
- Planificada la persistencia de artefactos en `models/radiography/` y la exclusión del dataset completo de GitHub por tamaño.
- Añadido criterio clínico de evaluación: matriz de confusión, análisis de falsos negativos COVID/neumonía y reflexión sobre limitaciones.

``markdown
## Deep Learning — Clasificación de radiografías

- Iniciado el módulo `ml-inference` para clasificación triple de radiografías: sana, neumonía y COVID-19.
- Definida una comparación entre dos arquitecturas:
  - CNN simple entrenada desde cero como baseline.
  - ResNet18 con transfer learning como modelo principal.
- Establecido el criterio de selección del modelo según F1 macro y recall clínico por clase, no únicamente accuracy.
- Definido el preprocesamiento de imágenes: conversión RGB, resize 224x224, normalización y data augmentation moderado.
- Añadida evaluación obligatoria con `metrics.json`, `confusion_matrix.png` y `critical_analysis.md`.
- Documentado el impacto clínico de errores: falso negativo COVID, neumonía clasificada como sana y falsos positivos.
- Preparada la integración con el servicio `ml-inference` mediante endpoints `/healthz` y `/predict`.
- Excluidos dataset y pesos pesados del repositorio, manteniendo versionables métricas, análisis crítico y documentación.

## ML Inference — Radiografías de tórax

- Añadido y documentado el módulo `ml-inference` para clasificación triple de radiografías: `Sana`, `Neumonía` y `COVID-19`.
- Integrado el servicio de inferencia con FastAPI mediante endpoints `/healthz` y `/predict`.
- Añadida carga de modelo versionado desde `ML_MODEL_PATH`, con soporte para inferencia en CPU mediante `ML_DEVICE=cpu`.
- Documentado el uso del dataset `COVID-19_Radiography_Dataset` y su exclusión de Git por tamaño.
- Implementado el mapeo de clases original → clase final: `Normal → Sana`, `COVID → COVID-19`, `Viral Pneumonia/Lung_Opacity → Neumonía`.
- Añadido pipeline de preparación de datos con splits estratificados `train.csv`, `val.csv`, `test.csv` y `metadata.json`.
- Añadido preprocesamiento de imágenes con resize, normalización ImageNet y data augmentation moderado.
- Justificada la arquitectura actual basada en `EfficientNet-B0` preentrenada con transfer learning.
- Añadido entrenamiento en dos fases: warmup con backbone congelado y fine-tuning completo.
- Probado smoke test con subset reducido (`limit-per-class 30`) y generación de artefacto `rx-20260515-6d3319c3`.
- Generados artefactos de evaluación del smoke test: `metrics.json` y `confusion_matrix.png`.
- Lanzado entrenamiento intermedio en CPU con `limit-per-class 500`, `batch-size 16`, `warmup-epochs 2` y `max-epochs 6`.
- Documentado el flujo de evaluación obligatorio: `metrics.json`, `confusion_matrix.png` y `critical_analysis.md`.
- Añadido análisis clínico de errores: falso negativo COVID-19, COVID confundido con neumonía, neumonía clasificada como sana y falsos positivos.
- Documentada la integración prevista con MinIO/MongoDB GridFS, API y dashboard.
- Documentada la comparación experimental futura entre CNN simple, ResNet18 y EfficientNet-B0.

## ML Inference — Radiografías de tórax

- Implementado flujo completo de Deep Learning para clasificación triple de radiografías: `Sana`, `Neumonía` y `COVID-19`.
- Preparado el dataset `COVID-19_Radiography_Dataset` con particiones estratificadas `train.csv`, `val.csv` y `test.csv`.
- Definido el mapeo de clases del dataset original: `Normal → Sana`, `COVID → COVID-19`, `Viral Pneumonia/Lung_Opacity → Neumonía`.
- Entrenado un primer modelo EfficientNet-B0 con transfer learning sobre subset de radiografías.
- Generados artefactos obligatorios de evaluación: `metrics.json`, `confusion_matrix.png` y `critical_analysis.md`.
- Validado el endpoint `/healthz` de `ml-inference` con modelo cargado correctamente.
- Validado el endpoint `/predict` con imagen real COVID del dataset, obteniendo predicción `COVID-19` y activación de alerta epidemiológica.
- Mejorado el módulo de entrenamiento para soportar comparación entre `simple_cnn`, `resnet18` y `efficientnet_b0`.
- Añadida generación de historial de entrenamiento (`history.csv`, `history.json`) para análisis posterior en notebook.
- Añadido script `compare_models.py` para comparar modelos por `accuracy`, `f1_macro`, `recall_covid` y `recall_neumonia`.
- Documentado el criterio clínico de evaluación: se prioriza reducir falsos negativos de COVID-19 y neumonía frente a maximizar únicamente accuracy.

## ML Inference — Radiografías de tórax

- Corregida la preparación del dataset para excluir carpetas `masks/` y usar únicamente radiografías dentro de `images/`.
- Documentado que las máscaras de segmentación no se usan para clasificación diagnóstica.
- Rehecho el flujo de entrenamiento de radiografías con dataset limpio y particiones estratificadas.
- Añadido soporte experimental para comparar tres arquitecturas: `simple_cnn`, `resnet18` y `efficientnet_b0`.
- Añadida evaluación común por modelo con `metrics.json`, `confusion_matrix.png` y `critical_analysis.md`.
- Añadido script de comparación de modelos con ranking por `accuracy`, `f1_macro`, `recall_covid` y `recall_neumonia`.
- Integrada una nueva pestaña `Radiografías` en el dashboard para subir una imagen y llamar al endpoint `/predict` de `ml-inference`.
- Añadida variable `ML_INFERENCE_URL` al servicio `dashboard` para comunicación interna Docker con `ml-inference`.
- Ajustado `.gitignore` para excluir pesos `.pt` y datasets pesados, pero permitir versionar métricas, matrices de confusión y análisis crítico.


## ML Inference — comparación de modelos de radiografías

- Regenerado el subset de radiografías excluyendo explícitamente las carpetas `masks/`; el entrenamiento usa únicamente imágenes reales de `images/`.
- Preparado dataset balanceado con 1000 muestras por clase final: `Sana`, `Neumonía` y `COVID-19`.
- Implementado entrenamiento configurable por arquitectura: `simple_cnn`, `resnet18` y `efficientnet_b0`.
- Añadida evaluación uniforme de modelos con `metrics.json`, `confusion_matrix.png` y `critical_analysis.md`.
- Añadida comparación agregada de modelos con métricas clínicas: `accuracy`, `f1_macro`, `recall_covid` y `recall_neumonia`.
- Integrada pestaña `Radiografías` en el dashboard para subir una imagen y consultar el endpoint `ml-inference /predict`.
- Documentado que la elección del modelo no se basa solo en accuracy, sino en matriz de confusión y riesgo clínico de falsos negativos. 

### Added — Módulo Deep Learning de radiografías

- Añadido flujo completo de clasificación triple de radiografías de tórax: `Sana`, `Neumonía` y `COVID-19`.
- Ajustado `prepare_data.py` para usar únicamente imágenes dentro de carpetas `images/`, excluyendo explícitamente `masks/`.
- Generado dataset limpio balanceado con `1000` imágenes por clase final.
- Definido mapeo clínico-operativo:
  - `Normal` → `Sana`
  - `Viral Pneumonia` → `Neumonía`
  - `Lung_Opacity` → `Neumonía`
  - `COVID` → `COVID-19`
- Añadida comparación experimental entre `simple_cnn`, `resnet18` y `efficientnet_b0`.
- Añadido script `training.compare_models` para generar tabla comparativa de métricas.
- Añadida evaluación obligatoria por modelo: `metrics.json`, `confusion_matrix.png` y `critical_analysis.md`.
- Integrado `ml-inference` con el dashboard mediante nueva pestaña `Radiografías`.
- Añadido endpoint `/predict` para inferencia HTTP sobre imágenes PNG/JPG y `/healthz` para healthcheck del modelo.

## ML Inference — Comparación de modelos radiografía

- Regenerado el dataset limpio de radiografías usando solo carpetas `images/`, excluyendo `masks/`.
- Preparado subset balanceado con 1000 imágenes por clase final: `Sana`, `Neumonía`, `COVID-19`.
- Entrenados tres modelos comparables:
  - `simple_cnn` como baseline convolucional desde cero.
  - `resnet18` con transfer learning.
  - `efficientnet_b0` con transfer learning.
- Generados artefactos de evaluación por modelo:
  - `metrics.json`
  - `confusion_matrix.png`
  - `critical_analysis.md`
  - `metadata.json`
- Generada comparación final en:
  - `models/radiography/comparison/comparison.csv`
  - `models/radiography/comparison/comparison.md`
  - `models/radiography/comparison/comparison.json`
- Seleccionado `EfficientNet-B0` como modelo final por mejor equilibrio clínico:
  - accuracy `0.9600`
  - f1_macro `0.9601`
  - recall_covid `0.9800`
  - recall_neumonia `0.9333`
- Integrado el modelo final con el servicio `ml-inference` mediante `ML_MODEL_PATH`.
- Validado endpoint `/healthz` y pruebas `/predict` con imágenes reales del dataset.

### Added — Consideraciones éticas y legales

- Añadido análisis ético y legal del sistema sanitario basado en IA.
- Documentados riesgos de sesgo en modelos tabulares y de radiografías.
- Analizados riesgos de automatización excesiva y falsos negativos clínicamente graves.
- Documentada la privacidad de datos sanitarios: pseudonimización, minimización, exclusión de `.env`, datasets y pesos del repositorio.
- Añadida reflexión sobre RGPD, datos de salud, auditoría de tratamientos con IA y necesidad de supervisión humana.
- Documentadas limitaciones técnicas, clínicas y legales del sistema: no validado clínicamente, no certificado como producto sanitario y no apto para producción real.
- Añadida tabla de mitigaciones aplicadas: logging, `correlation_id`, `system_events`, `ingestion_rejects`, alertas, métricas por clase y análisis crítico.