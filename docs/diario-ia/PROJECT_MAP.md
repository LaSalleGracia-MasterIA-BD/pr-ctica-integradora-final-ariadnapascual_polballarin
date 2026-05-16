# Mapa técnico completo del proyecto — laSalle Health Center

Este documento explica el proyecto de extremo a extremo: qué hace cada carpeta, qué hace cada servicio, cómo fluyen los datos, qué modelos existen, qué artefactos se generan y cómo se conectan todos los módulos.

El objetivo es que cualquier persona pueda entender el sistema sin tener que leer todo el código archivo por archivo.

---

## 1. Idea general del sistema

El proyecto simula un sistema hospitalario de soporte a la decisión clínica.

Permite:

- registrar pacientes;
- procesar formularios individuales;
- procesar lotes CSV;
- validar calidad de datos;
- clasificar urgencia clínica mediante modelos tabulares;
- estimar sospecha de enfermedad;
- clasificar radiografías de tórax mediante Deep Learning;
- guardar datos estructurados y no estructurados;
- visualizar resultados en dashboard;
- generar eventos de pipeline;
- centralizar logs;
- crear alertas automáticas ante eventos anómalos.

El sistema no sustituye al personal médico. Actúa como sistema de apoyo y priorización.

---

## 2. Flujo funcional global

```text
Entrada de datos
    ├── Formulario individual desde dashboard
    ├── CSV batch con múltiples pacientes
    └── Radiografía de tórax PNG/JPG

        ↓

Servicios de entrada
    ├── dashboard
    └── api

        ↓

Pipeline de datos
    ├── ingesta
    ├── validación
    ├── transformación
    ├── carga
    ├── predicción tabular
    └── emisión de eventos

        ↓

Almacenamiento
    ├── MinIO: datos raw / landing zone
    ├── PostgreSQL: datos estructurados
    └── MongoDB: predicciones, eventos, rechazos, alertas e imágenes

        ↓

Modelos IA
    ├── ml-triage: triaje Alta / Media / Baja
    ├── ml-triage: sospecha de enfermedad
    └── ml-inference: radiografías Sana / Neumonía / COVID-19

        ↓

Salida
    ├── Dashboard Streamlit
    ├── API REST
    ├── PDF de paciente
    ├── métricas de modelos
    ├── matrices de confusión
    ├── análisis crítico
    └── alertas operativas
```

---

## 3. Servicios Docker Compose

El sistema está containerizado con Docker Compose. Cada servicio tiene una responsabilidad separada.

| Servicio | Tipo | Responsabilidad |
|---|---|---|
| `postgres` | Base de datos relacional | Guarda pacientes, ingresos y datos estructurados. |
| `pgadmin` | UI administración | Permite inspeccionar PostgreSQL. |
| `mongodb` | Base documental | Guarda predicciones, eventos, rechazos, alertas e información flexible. |
| `mongo-express` | UI administración | Permite inspeccionar MongoDB. |
| `minio` | S3-compatible object storage | Guarda datos raw, CSVs originales, JSONs online y posibles imágenes. |
| `minio-init` | Inicialización | Crea buckets necesarios en MinIO. |
| `dask-scheduler` | Procesamiento escalable | Scheduler de Dask para pipeline batch. |
| `dask-worker` | Procesamiento escalable | Worker que ejecuta tareas Dask. |
| `pipeline` | Procesamiento de datos | Ejecuta ingesta, validación, transformación, carga y eventos. |
| `api` | Servicio REST | Expone endpoints para dashboard y consumo externo. |
| `dashboard` | Visualización | Interfaz Streamlit para pacientes, triaje, radiografías y estado. |
| `ml-triage` | IA tabular | Predice urgencia y sospecha de enfermedad. |
| `ml-inference` | Deep Learning | Clasifica radiografías de tórax. |
| `automation` | Automatización | Escanea eventos warning/error y crea alertas. |
| `loki` | Logging centralizado | Almacén centralizado de logs. |
| `promtail` | Logging centralizado | Recolector de logs Docker hacia Loki. |

---

## 4. Estructura general del repositorio

```text
.
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── .env
├── .gitignore
├── README.md
├── CHANGELOG.md
├── CONTEXT.md
├── Enunciado-Hospital.pdf
├── init/
├── monitoring/
├── scripts/
├── services/
├── specs/
├── docs/
├── data/
├── models/
└── COVID-19_Radiography_Dataset/
```

---

## 5. Archivos raíz

| Archivo | Función |
|---|---|
| `docker-compose.yml` | Orquesta todos los servicios del sistema. |
| `Dockerfile` | Imagen multietapa para construir los servicios Python. |
| `.env.example` | Plantilla de variables de entorno. Se versiona. |
| `.env` | Configuración local real. No debe versionarse. |
| `.gitignore` | Excluye datasets, pesos, entornos, temporales y secretos. |
| `README.md` | Guía principal de instalación, ejecución y demo. |
| `CHANGELOG.md` | Registro técnico de cambios. |
| `CONTEXT.md` | Contexto funcional del proyecto. |
| `Enunciado-Hospital.pdf` | Enunciado académico original. |

---

## 6. Carpeta `init/`

Contiene scripts de inicialización de bases de datos.

```text
init/
├── mongo/
│   └── init.js
└── postgres/
    └── init.sql
```

### `init/postgres/init.sql`

Inicializa la base relacional.

Suele contener:

- tablas de pacientes;
- tablas de ingresos;
- índices;
- restricciones;
- datos mínimos;
- relaciones entre entidades.

PostgreSQL se usa para datos estructurados porque permite integridad referencial, consultas SQL y consistencia.

### `init/mongo/init.js`

Inicializa MongoDB.

MongoDB se usa para:

- predicciones;
- eventos de sistema;
- rechazos de calidad;
- alertas;
- documentos flexibles;
- posibles imágenes vía GridFS.

---

## 7. Carpeta `monitoring/`

```text
monitoring/
├── loki-config.yaml
└── promtail-config.yaml
```

### `loki-config.yaml`

Configura Loki como sistema de almacenamiento centralizado de logs.

Loki permite consultar logs por labels como:

- `compose_project`;
- `compose_service`;
- `container`;
- `logstream`.

Ejemplo de consulta LogQL usada:

```text
{compose_service="pipeline"} |= "pipeline.run.end"
```

### `promtail-config.yaml`

Configura Promtail para recoger logs de los contenedores Docker y enviarlos a Loki.

Este módulo cubre el requisito:

> Logging centralizado de los procesos del pipeline.

La validación real no fue solo que Loki estuviera `healthy`, sino que una consulta a Loki devolvió logs reales del pipeline.

---

## 8. Carpeta `scripts/`

```text
scripts/
├── train_tabular_models.ps1
└── evaluate_tabular_models.ps1
```

### `train_tabular_models.ps1`

Automatiza entrenamiento de modelos tabulares dentro de Docker.

Entrena:

- modelo de triaje;
- modelo de enfermedad.

Genera artefactos en:

```text
models/triage/
models/disease/
```

### `evaluate_tabular_models.ps1`

Evalúa modelos tabulares dentro de Docker.

Genera:

- `metrics.json`;
- `confusion_matrix.png`;
- `critical_analysis.md`.

Sirve para dejar trazabilidad de métricas y análisis clínico.

---

## 9. Carpeta `data/`

```text
data/
├── covid-subset/
├── synthetic/
├── tmp/
└── raw/
```

Esta carpeta contiene datos generados o temporales. No debe versionarse.

### `data/covid-subset/`

Contiene los CSV generados para radiografías:

```text
data/covid-subset/
├── train.csv
├── val.csv
├── test.csv
└── metadata.json
```

Se genera con:

```powershell
docker compose run --rm ml-inference python -m training.prepare_data `
  --raw-dir /app/COVID-19_Radiography_Dataset `
  --output-dir /app/data/covid-subset `
  --limit-per-class 1000 `
  --seed 42
```

En la versión corregida:

- solo se usan imágenes dentro de `images/`;
- se excluyen `masks/`;
- se balancea a 1000 imágenes por clase final;
- se hace split estratificado train/val/test;
- se guarda metadata.

Clases finales:

| Clase final | Origen |
|---|---|
| `Sana` | `Normal/images` |
| `Neumonía` | `Viral Pneumonia/images` + `Lung_Opacity/images` |
| `COVID-19` | `COVID/images` |

### `data/synthetic/`

Datos sintéticos del modelo tabular de triaje y enfermedad.

Se generan con scripts de `ml-triage/training`.

### `data/tmp/`

Temporales del pipeline y Dask.

### `data/raw/`

Datos raw locales. En ejecución real, el raw principal vive en MinIO.

---

## 10. Carpeta `models/`

```text
models/
├── triage/
├── disease/
├── radiography/
├── radiography_old/
└── radiography_contaminated/
```

### `models/triage/`

Artefactos del modelo de triaje.

Ejemplo:

```text
models/triage/
├── current.txt
└── tri-YYYYMMDD-hash/
    ├── model.joblib
    ├── metadata.json
    ├── metrics.json
    ├── confusion_matrix.png
    └── critical_analysis.md
```

Predice:

- `Alta`;
- `Media`;
- `Baja`.

### `models/disease/`

Artefactos del modelo de sospecha de enfermedad.

Predice etiquetas como:

- `cardiopatia_aguda_sospecha`;
- `covid_sospecha`;
- `neumonia_sospecha`;
- `gripe_resfriado`;
- `gastroenteritis`;
- `ictus_sospecha`;
- etc.

### `models/radiography/`

Artefactos del modelo de radiografías.

Contiene:

```text
models/radiography/
├── rx-simplecnn-YYYYMMDD-hash/
├── rx-resnet18-YYYYMMDD-hash/
├── rx-efficientnetb0-YYYYMMDD-hash/
└── comparison/
```

Cada modelo genera:

```text
metadata.json
metrics.json
confusion_matrix.png
critical_analysis.md
model.pt
```

No se debe subir `model.pt` a Git.

Sí se pueden subir:

- `metadata.json`;
- `metrics.json`;
- `confusion_matrix.png`;
- `critical_analysis.md`;
- `comparison.csv`;
- `comparison.md`;
- `comparison.json`.

### Resultados comparativos actuales

| Modelo | Accuracy | F1 macro | Recall COVID | Recall Neumonía |
|---|---:|---:|---:|---:|
| EfficientNet-B0 | 0.9600 | 0.9601 | 0.9800 | 0.9333 |
| ResNet18 | 0.8933 | 0.8929 | 0.9667 | 0.8333 |
| CNN simple | 0.7022 | 0.7013 | 0.7000 | 0.7733 |

Se selecciona EfficientNet-B0 porque ofrece el mejor equilibrio clínico: alto F1 macro, alto recall COVID y alto recall Neumonía.

### `models/radiography_old/`

Modelos antiguos apartados.

### `models/radiography_contaminated/`

Modelos descartados porque se entrenaron cuando el CSV incluía rutas a `masks/`. Esa versión se considera contaminada porque el modelo podía aprender máscaras binarias en lugar de radiografías reales.

---

## 11. Carpeta `services/`

Contiene todos los servicios funcionales.

```text
services/
├── api/
├── dashboard/
├── pipeline/
├── ml-triage/
├── ml-inference/
└── automation/
```

---

# 12. Servicio `api`

```text
services/api/
├── app/
└── requirements.txt
```

La API es el punto de entrada REST para dashboard y clientes externos.

## Responsabilidades

- comprobar salud del sistema;
- crear pacientes individuales;
- lanzar procesos batch;
- listar pacientes;
- consultar detalle de paciente;
- generar PDF;
- consultar eventos de ejecución;
- conectar dashboard con pipeline y bases de datos.

## Endpoints principales

```text
GET  /health
GET  /patients
GET  /patients/{pseudo_id}
GET  /patients/{pseudo_id}/pdf
POST /patients
POST /batch-runs
GET  /batch-runs/{run_id}/events
```

## Flujo de `POST /patients`

```text
Dashboard formulario
        ↓
POST /patients
        ↓
API valida entrada básica
        ↓
Guarda raw en MinIO
        ↓
Ejecuta flujo online del pipeline
        ↓
Guarda paciente e ingreso
        ↓
Llama a ml-triage
        ↓
Guarda predicción en MongoDB
        ↓
Devuelve resultado al dashboard
```

## Flujo de `POST /batch-runs`

```text
Dashboard sube CSV
        ↓
API recibe archivo
        ↓
Guarda CSV en MinIO
        ↓
Pipeline batch procesa archivo
        ↓
Eventos se guardan en MongoDB
        ↓
Dashboard consulta eventos por run_id
```

---

# 13. Servicio `dashboard`

```text
services/dashboard/
├── .streamlit/
│   └── config.toml
├── app.py
└── requirements.txt
```

Dashboard Streamlit del sistema.

## Responsabilidades

- mostrar pacientes registrados;
- filtrar por triaje;
- consultar ficha individual;
- descargar PDF;
- ejecutar formulario de triaje;
- subir CSV batch;
- mostrar eventos del pipeline en vivo;
- subir radiografías;
- llamar a `ml-inference`;
- mostrar probabilidades y alertas;
- mostrar estado de API.

## Vistas del dashboard

| Vista | Función |
|---|---|
| `Pacientes` | Tabla de pacientes, filtros, ficha y PDF. |
| `Triaje` | Formulario individual y carga CSV batch. |
| `Radiografías` | Upload PNG/JPG y clasificación DL. |
| `Estado` | Estado básico del backend. |

## Flujo de Radiografías

```text
Usuario sube imagen en dashboard
        ↓
dashboard llama a http://ml-inference:8001/predict
        ↓
ml-inference devuelve clase y probabilidades
        ↓
dashboard muestra:
    - clase predicha
    - Sana %
    - Neumonía %
    - COVID-19 %
    - alerta COVID si aplica
    - warning de baja confianza si aplica
```

Dentro de Docker, el dashboard no debe llamar a `localhost:8001`, sino a:

```text
http://ml-inference:8001
```

porque `localhost` dentro del contenedor dashboard sería el propio contenedor dashboard.

---

# 14. Servicio `pipeline`

```text
services/pipeline/
├── app/
│   ├── clients/
│   ├── phases/
│   ├── storage/
│   ├── utils/
│   ├── config.py
│   ├── dask_runtime.py
│   ├── events.py
│   ├── logging_setup.py
│   ├── online.py
│   └── orchestrator.py
├── config/
│   └── validation_rules.yaml
├── seed/
├── main.py
└── requirements.txt
```

El pipeline implementa la parte Big Data del sistema.

## Responsabilidades

- leer datos batch desde MinIO;
- usar Dask para lectura escalable;
- validar calidad de datos;
- transformar registros;
- cargar pacientes e ingresos;
- persistir rechazos;
- llamar a modelos tabulares;
- emitir eventos de dominio;
- actualizar agregados.

---

## 14.1. `main.py`

CLI del pipeline.

Ejemplos:

```powershell
docker compose exec pipeline python main.py seed --n 100 --seed 123
docker compose exec pipeline python main.py batch --key "patients/file.csv"
```

Subcomandos típicos:

| Comando | Función |
|---|---|
| `seed` | Genera CSV sintético y lo sube a MinIO. |
| `batch` | Procesa un CSV existente en MinIO. |

---

## 14.2. `orchestrator.py`

Orquesta el pipeline batch.

Flujo:

```text
run_batch()
    ↓
1. ingestion.ingest_csv()
    ↓
2. validation.validate_entity()
    ↓
3. transformation.transform()
    ↓
4. loading.load_pacientes_ingresos()
    ↓
5. loading.load_rejects()
    ↓
6. ml-triage /predict
    ↓
7. aggregates.upsert_daily_aggregate()
    ↓
8. emit_event("pipeline.run.end")
```

---

## 14.3. `phases/ingestion.py`

Lee datos desde MinIO.

Responsabilidades:

- abrir objeto raw;
- leer CSV;
- activar Dask si está configurado;
- devolver DataFrame;
- emitir evento `pipeline.file.read`.

---

## 14.4. `phases/validation.py`

Aplica reglas de calidad desde:

```text
services/pipeline/config/validation_rules.yaml
```

Detecta:

- campos obligatorios ausentes;
- tipos incorrectos;
- valores fuera de rango;
- enums inválidos;
- reglas cruzadas;
- duplicados lógicos si aplica.

Ejemplo de rechazos reales:

```text
missing_field:edad
sexo:enum
intensidad_dolor:max:10
```

---

## 14.5. `phases/transformation.py`

Transforma registros válidos a entidades internas:

- pacientes;
- ingresos;
- snapshots;
- hashes de contenido;
- pseudo_id.

---

## 14.6. `phases/loading.py`

Carga datos en almacenamiento persistente.

Responsabilidades:

- insertar pacientes en PostgreSQL;
- insertar ingresos en PostgreSQL;
- persistir rechazos en MongoDB;
- guardar predicciones de triaje;
- guardar predicciones de enfermedad.

---

## 14.7. `phases/aggregates.py`

Actualiza agregados diarios.

Ejemplo:

```json
{
  "records_in": 100,
  "valid": 100,
  "rejected": 0,
  "triage_completed": 100,
  "triage_pending": 0
}
```

---

## 14.8. `events.py`

Emite eventos de dominio a MongoDB.

Ejemplos:

```text
pipeline.run.start
pipeline.file.read
pipeline.validation.done
pipeline.transformation.done
pipeline.loading.done
pipeline.rejects.persisted
pipeline.ml.done
pipeline.aggregates.updated
pipeline.run.end
```

Estos eventos alimentan:

- dashboard;
- auditoría;
- alertas;
- notebooks;
- monitorización.

---

## 14.9. `logging_setup.py`

Configura logs JSON a stdout.

Cada log incluye:

- timestamp;
- level;
- service;
- correlation_id;
- event;
- message.

Promtail recoge estos logs y los envía a Loki.

---

## 14.10. `dask_runtime.py`

Gestiona conexión con Dask.

El pipeline registra metadatos como:

```json
{
  "processing_engine": "dask",
  "dask_partitions": 1,
  "dask_blocksize": "16MB",
  "dask_scheduler": "tcp://dask-scheduler:8786"
}
```

Dask cubre el requisito de procesamiento distribuido o escalable.

---

# 15. Servicio `ml-triage`

```text
services/ml-triage/
├── app/
├── training/
└── requirements.txt
```

Servicio de inferencia tabular.

## 15.1. Función

Predice:

1. Nivel de urgencia:
   - Alta;
   - Media;
   - Baja.

2. Sospecha de enfermedad:
   - cardiopatía aguda;
   - COVID;
   - neumonía;
   - ictus;
   - gastroenteritis;
   - etc.

---

## 15.2. `app/`

Servicio FastAPI.

Responsabilidades:

- cargar modelos desde `models/triage` y `models/disease`;
- exponer `/health`;
- exponer `/predict`;
- devolver probabilidades;
- devolver versión de modelo;
- devolver flags de baja confianza.

---

## 15.3. `training/`

Contiene entrenamiento y evaluación.

| Archivo | Función |
|---|---|
| `generate_dataset.py` | Genera dataset sintético reproducible. |
| `rules.py` | Reglas clínicas usadas para etiquetar triaje. |
| `disease_rules.py` | Reglas sintéticas para sospecha de enfermedad. |
| `model.py` | Pipeline sklearn para modelo tabular. |
| `train.py` | Entrena modelo de triaje. |
| `train_disease.py` | Entrena modelo de enfermedad. |
| `evaluate.py` | Evalúa triaje. |
| `evaluate_disease.py` | Evalúa enfermedad. |
| `critical_analysis.py` | Informe crítico de triaje. |
| `critical_analysis_disease.py` | Informe crítico de enfermedad. |
| `cross_validate.py` | Validación cruzada. |

---

## 15.4. Artefactos

```text
models/triage/tri-YYYYMMDD-hash/
├── model.joblib
├── metadata.json
├── metrics.json
├── confusion_matrix.png
└── critical_analysis.md

models/disease/dis-YYYYMMDD-hash/
├── model.joblib
├── metadata.json
├── metrics.json
├── confusion_matrix.png
└── critical_analysis.md
```

---

# 16. Servicio `ml-inference`

```text
services/ml-inference/
├── app/
├── training/
├── README.md
└── requirements.txt
```

Servicio Deep Learning para radiografías.

## 16.1. Función

Clasifica radiografías de tórax en:

- Sana;
- Neumonía;
- COVID-19.

---

## 16.2. `app/`

| Archivo | Función |
|---|---|
| `app.py` | Define FastAPI, `/healthz` y `/predict`. |
| `predictor.py` | Carga modelo `.pt`, preprocesa imagen y predice. |
| `config.py` | Clases, tamaño de imagen, normalización, thresholds. |
| `schemas.py` | Esquema Pydantic de respuesta. |

---

## 16.3. `training/`

| Archivo | Función |
|---|---|
| `prepare_data.py` | Genera splits limpios desde `images/`, excluye `masks/`. |
| `dataset.py` | Dataset PyTorch basado en CSV. |
| `augment.py` | Transforms de entrenamiento y evaluación. |
| `model.py` | Define `simple_cnn`, `resnet18`, `efficientnet_b0`. |
| `train.py` | Entrena modelos versionados. |
| `evaluate.py` | Genera `metrics.json` y `confusion_matrix.png`. |
| `critical_analysis.py` | Genera informe clínico del modelo. |
| `compare_models.py` | Compara modelos y genera tabla final. |

---

## 16.4. Dataset radiografías

Dataset local:

```text
COVID-19_Radiography_Dataset/
├── COVID/images/
├── Normal/images/
├── Viral Pneumonia/images/
└── Lung_Opacity/images/
```

Mapeo final:

| Origen | Clase final |
|---|---|
| `Normal` | `Sana` |
| `Viral Pneumonia` | `Neumonía` |
| `Lung_Opacity` | `Neumonía` |
| `COVID` | `COVID-19` |

---

## 16.5. Modelos comparados

| Modelo | Tipo | Justificación |
|---|---|---|
| `simple_cnn` | CNN desde cero | Baseline simple para comparar. |
| `resnet18` | Transfer learning | Arquitectura clásica, robusta y fácil de justificar. |
| `efficientnet_b0` | Transfer learning eficiente | Mejor equilibrio entre precisión y coste. |

---

## 16.6. Resultados actuales

```text
EfficientNet-B0:
accuracy = 0.9600
f1_macro = 0.9601
recall_covid = 0.9800
recall_neumonia = 0.9333

ResNet18:
accuracy = 0.8933
f1_macro = 0.8929
recall_covid = 0.9667
recall_neumonia = 0.8333

Simple CNN:
accuracy = 0.7022
f1_macro = 0.7013
recall_covid = 0.7000
recall_neumonia = 0.7733
```

Conclusión:

```text
Se selecciona EfficientNet-B0 porque consigue el mejor equilibrio clínico:
- mejor accuracy;
- mejor F1 macro;
- mejor recall COVID;
- mejor recall Neumonía.
```

---

# 17. Servicio `automation`

```text
services/automation/
├── main.py
└── requirements.txt
```

Servicio de automatización operativa.

## Función

Escanea eventos recientes de MongoDB:

```text
system_events
```

Busca:

```text
level = warning
level = error
```

Y crea alertas deduplicadas en:

```text
alerts
```

---

## Flujo

```text
system_events
    ↓
automation escanea últimos N minutos
    ↓
detecta warning/error
    ↓
genera dedup_key
    ↓
inserta o actualiza alerts
    ↓
dashboard / mongo-express pueden consultarlo
```

Ejemplo de evento:

```text
pipeline.validation.done → warning
```

Ejemplo de alerta:

```json
{
  "source_event": "pipeline.validation.done",
  "severity": "warning",
  "status": "open",
  "notification_channel": "mongo_dashboard",
  "notification_status": "simulated"
}
```

---

# 18. Carpeta `specs/`

Contiene documentación SDD y DESIGN.

| Archivo | Función |
|---|---|
| `SDD-01-sistema.md` | Sistema global. |
| `SDD-02-pipeline.md` | Pipeline de datos. |
| `SDD-03-almacenamiento.md` | Almacenamiento. |
| `SDD-04-automatizacion.md` | Automatización. |
| `SDD-05-api-dashboard.md` | API y dashboard. |
| `SDD-06-modelo-dl.md` | Deep Learning de radiografías. |
| `SDD-07-monitorizacion.md` | Monitorización. |
| `SDD-08-modelo-triaje.md` | Modelo tabular. |
| `SDD-09-etica-legal.md` | Ética, privacidad y limitaciones. |

Esta carpeta demuestra metodología Spec-Driven Development.

---

# 19. Carpeta `docs/diario-ia/`

Contiene el diario de uso de IA.

Debe demostrar:

- herramientas usadas;
- prompts;
- iteraciones;
- errores;
- correcciones;
- decisiones;
- reflexión crítica;
- impacto en productividad.

Ejemplo de contenido:

| Documento | Función |
|---|---|
| `00-genesis-plan.md` | Plan inicial. |
| `01-integracion-ariadna.md` | Integración inicial. |
| `02-modelo-triaje.md` | Desarrollo del modelo tabular. |
| `03-etl-pipeline.md` | Desarrollo del pipeline. |
| `04-online-api-dashboard.md` | API y dashboard. |
| `05-minio-landing.md` | Decisión MinIO. |
| `06-pulido-ux.md` | Dashboard y UX. |
| `99-reflexion-critica.md` | Reflexión final. |

---

# 20. Flujo demo completo

## 20.1. Levantar sistema

```powershell
Copy-Item .env.example .env -Force
docker compose --env-file .env up -d --build
docker compose ps
```

---

## 20.2. Pipeline batch

```powershell
docker compose exec pipeline python main.py seed --n 100 --seed 123
docker compose exec pipeline python main.py batch --key "patients/<archivo>.csv"
```

Resultado esperado:

```json
{
  "records_in": 100,
  "valid": 100,
  "rejected": 0,
  "triage_completed": 100,
  "triage_pending": 0
}
```

---

## 20.3. Calidad de datos

Ejemplo real:

```json
{
  "records_in": 5,
  "valid": 1,
  "rejected": 4,
  "rejects_persisted": 4
}
```

MongoDB:

```text
ingestion_rejects
```

Eventos:

```text
pipeline.validation.done
pipeline.rejects.persisted
```

Alertas:

```text
alerts
```

---

## 20.4. Modelos tabulares

```powershell
.\scripts\train_tabular_models.ps1
.\scripts\evaluate_tabular_models.ps1
```

---

## 20.5. Radiografías

Preparar dataset:

```powershell
docker compose run --rm ml-inference python -m training.prepare_data `
  --raw-dir /app/COVID-19_Radiography_Dataset `
  --output-dir /app/data/covid-subset `
  --limit-per-class 1000 `
  --seed 42
```

Entrenar modelos:

```powershell
docker compose run --rm ml-inference python -m training.train `
  --backbone simple_cnn `
  --train-csv /app/data/covid-subset/train.csv `
  --val-csv /app/data/covid-subset/val.csv `
  --models-root /app/models/radiography `
  --batch-size 32 `
  --warmup-epochs 0 `
  --max-epochs 8 `
  --num-workers 0 `
  --seed 42

docker compose run --rm ml-inference python -m training.train `
  --backbone resnet18 `
  --train-csv /app/data/covid-subset/train.csv `
  --val-csv /app/data/covid-subset/val.csv `
  --models-root /app/models/radiography `
  --batch-size 16 `
  --warmup-epochs 2 `
  --max-epochs 8 `
  --num-workers 0 `
  --seed 42

docker compose run --rm ml-inference python -m training.train `
  --backbone efficientnet_b0 `
  --train-csv /app/data/covid-subset/train.csv `
  --val-csv /app/data/covid-subset/val.csv `
  --models-root /app/models/radiography `
  --batch-size 16 `
  --warmup-epochs 2 `
  --max-epochs 8 `
  --num-workers 0 `
  --seed 42
```

Evaluar:

```powershell
Get-ChildItem .\models\radiography -Directory | Where-Object { $_.Name -like "rx-*" } | ForEach-Object {
  $v = $_.Name

  docker compose run --rm ml-inference python -m training.evaluate `
    --artifact-dir "/app/models/radiography/$v" `
    --test-csv /app/data/covid-subset/test.csv `
    --batch-size 16 `
    --num-workers 0

  docker compose run --rm ml-inference python -m training.critical_analysis `
    --artifact-dir "/app/models/radiography/$v"
}
```

Comparar:

```powershell
docker compose run --rm ml-inference python -m training.compare_models `
  --models-root /app/models/radiography `
  --output /app/models/radiography/comparison
```

---

## 20.6. Activar mejor modelo

```powershell
$best = "rx-efficientnetb0-20260515-2b92eec9"
$line = "ML_MODEL_PATH=/app/models/radiography/$best/model.pt"

if (Select-String -Path .env -Pattern "^ML_MODEL_PATH=" -Quiet) {
  (Get-Content .env) -replace "^ML_MODEL_PATH=.*", $line | Set-Content .env
} else {
  Add-Content .env $line
}

docker compose --env-file .env up -d --force-recreate ml-inference
docker compose exec ml-inference curl -s http://localhost:8001/healthz
```

---

## 20.7. Probar predicción radiografía

```powershell
docker compose exec ml-inference sh -lc "curl -s -X POST http://localhost:8001/predict -F 'file=@/app/COVID-19_Radiography_Dataset/COVID/images/COVID-1.png'"

docker compose exec ml-inference sh -lc "curl -s -X POST http://localhost:8001/predict -F 'file=@/app/COVID-19_Radiography_Dataset/Normal/images/Normal-1.png'"

docker compose exec ml-inference sh -lc "curl -s -X POST http://localhost:8001/predict -F 'file=@/app/COVID-19_Radiography_Dataset/Viral Pneumonia/images/Viral Pneumonia-1.png'"

docker compose exec ml-inference sh -lc "curl -s -X POST http://localhost:8001/predict -F 'file=@/app/COVID-19_Radiography_Dataset/Lung_Opacity/images/Lung_Opacity-1.png'"
```

---

## 20.8. Dashboard

```powershell
docker compose --env-file .env up -d --force-recreate dashboard
```

Abrir:

```text
http://localhost:8502
```

Pestañas:

- Pacientes;
- Triaje;
- Radiografías;
- Estado.

---

# 21. Qué explicar en defensa oral

## 21.1. Arquitectura

El sistema está dividido en microservicios para separar responsabilidades.

- API no entrena modelos.
- Dashboard no accede directamente a bases de datos.
- Pipeline valida y transforma.
- Modelos se sirven por servicios independientes.
- MongoDB guarda documentos flexibles.
- PostgreSQL guarda entidades estructuradas.
- MinIO guarda raw.
- Loki centraliza logs.
- Automation genera alertas.

---

## 21.2. Big Data

Se usa Dask para procesamiento batch escalable.

Aunque el dataset de prueba no sea masivo, el diseño permite escalar:

- scheduler;
- worker;
- particiones;
- blocksize;
- lectura distribuida.

---

## 21.3. Calidad

No solo se procesan datos buenos. Se prueba un CSV inválido.

El sistema:

- detecta errores;
- rechaza registros;
- guarda motivos;
- emite warning;
- crea alertas.

---

## 21.4. IA tabular

El sistema usa modelos tabulares para apoyar triaje.

Se evalúan con:

- accuracy;
- F1;
- matriz de confusión;
- análisis crítico.

---

## 21.5. Deep Learning

Se comparan tres arquitecturas:

- CNN simple;
- ResNet18;
- EfficientNet-B0.

No se elige solo por accuracy. Se priorizan métricas clínicas:

- F1 macro;
- recall COVID;
- recall Neumonía;
- matriz de confusión.

---

## 21.6. Ética

El sistema es apoyo a decisión, no diagnóstico.

Riesgos tratados:

- sesgos;
- privacidad;
- falsos negativos;
- automatización excesiva;
- limitaciones legales;
- no validación clínica.

---

# 22. Estado actual del proyecto

| Bloque | Estado |
|---|---|
| Docker Compose | Implementado. |
| PostgreSQL | Implementado. |
| MongoDB | Implementado. |
| MinIO | Implementado. |
| Pipeline batch | Implementado. |
| Pipeline online | Implementado. |
| Dask | Implementado. |
| API | Implementada. |
| Dashboard | Implementado. |
| Modelo triaje | Entrenado y evaluado. |
| Modelo enfermedad | Entrenado y evaluado. |
| Modelo radiografías | Entrenado y comparado. |
| EfficientNet-B0 activo | Implementado. |
| Matrix de confusión | Generada. |
| Análisis crítico | Generado. |
| Loki/Promtail | Implementado. |
| Automation alerts | Implementado. |
| Ética/legal | Documentado. |
| Diario IA | Documentado. |
| Notebooks | Pendiente de completar para comunicación visual. |