# Sistema Inteligente de Soporte Hospitalario — laSalle Health Center

Solución integral de análisis de datos clínicos y operativos basada en IA y Big Data, containerizada con Docker Compose.

## Requisitos previos

- **Docker** 20.10+ ([descargar](https://www.docker.com/products/docker-desktop))
- **Docker Compose** v2.x (incluido en Docker Desktop)
- **Git** para clonar el repositorio
- **Espacio en disco**: mínimo 5 GB para imágenes y volúmenes

### Verificar instalación

```powershell
docker --version
docker compose version
```

## Inicio rápido

### 1. Clonar y navegar al directorio

```powershell
cd C:\Users\aripa\Downloads\Practica_Hospital_AriadnaPascualPolBallarin
```

### 2. Configurar variables de entorno

Copia el archivo `.env.example` a `.env`:

```powershell
Copy-Item -Path .env.example -Destination .env -Force
```

Edita `.env` si necesitas cambiar contraseñas o puertos (valores por defecto están listos para demo).

### 3. Levantar el sistema

```powershell
docker compose up -d
```

Esto levantará todos los servicios: bases de datos, APIs, dashboards, monitorización, etc.

### 4. Hacer seguimiento del estado

```powershell
# Ver estado de los servicios (esperar a que todos sean 'healthy')
docker compose ps

# Ver logs
docker compose logs -f api
docker compose logs -f mongodb
```

## Acceso a servicios

Una vez levantado (`docker compose up -d`), accede a:

| Servicio | URL | Credenciales | Propósito |
|----------|-----|--------------|----------|
| **API** | http://localhost:8000 | — | REST API (healthcheck: `/health`) |
| **Dashboard** | http://localhost:8501 | — | Streamlit UI con métricas |
| **pgAdmin** | http://localhost:5050 | admin@example.com / change-me | Gestor PostgreSQL |
| **Mongo Express** | http://localhost:8081 | — | Gestor MongoDB |
| **Loki** | http://localhost:3100 | — | Centralizador de logs |

## Detener el sistema

### Parar servicios (mantener datos)

```powershell
docker compose down
```

Los volúmenes (datos) se conservan. Al relanzar `docker compose up -d`, los datos persisten.

### Parar y eliminar volúmenes (reset completo)

```powershell
docker compose down -v
```

Esto elimina todos los volúmenes. La siguiente ejecución ejecutará los scripts de inicialización (`./init`) desde cero.

## Estructura del proyecto

```
.
├── Dockerfile              # Multietapa (api, pipeline, ml-inference, dashboard, automation)
├── docker-compose.yml      # Orquestación de servicios
├── .env.example            # Plantilla de variables de entorno
├── .env                    # Variables de entorno (no commiteado, generar desde .env.example)
├── README.md               # Este archivo
├── init/
│   ├── postgres/
│   │   └── init.sql        # Script de inicialización PostgreSQL (tablas, datos)
│   └── mongo/
│       └── init.js         # Script de inicialización MongoDB (colecciones, usuario)
├── monitoring/
│   ├── loki-config.yaml    # Configuración Loki
│   └── promtail-config.yaml # Configuración Promtail (recolector logs)
├── services/
│   ├── api/
│   │   ├── requirements.txt
│   │   └── app/
│   │       └── main.py
│   ├── pipeline/
│   │   ├── requirements.txt
│   │   └── main.py
│   ├── ml-inference/
│   │   ├── requirements.txt
│   │   └── app/
│   │       └── app.py
│   ├── dashboard/
│   │   ├── requirements.txt
│   │   └── app.py
│   └── automation/
│       └── [stub]
├── data/                   # Dataset inicial (imágenes médicas, CSVs, etc.)
└── specs/
    ├── DESIGN-01-arquitectura.md
    ├── SDD-02-pipeline.md
    ├── SDD-03-almacenamiento.md
    └── [otros SDDs]
```

## Arquitectura de almacenamiento

El sistema usa **tres tecnologías de almacenamiento**, cada una con un rol distinto. No es duplicación, son capas (cumple §4.2.2 del enunciado: *"al menos dos tipos"*; el ejemplo del propio enunciado cita PostgreSQL + MongoDB/MinIO).

| Capa | Tecnología | Qué guarda | Por qué |
|---|---|---|---|
| **Data lake (raw)** | MinIO (S3-compatible) | JSON original del formulario online, CSVs batch crudos, futuras radiografías originales | Patrón Big Data *bronze*: conserva la entrada exacta antes de transformar. Permite *replay* y auditoría. API S3-compatible (migrable a AWS). |
| **OLTP estructurado** | PostgreSQL | `pacientes`, `ingresos`, `personal`, logs de auditoría — datos validados y transformados | Relacional con FKs e integridad fuerte. SQL para consultas analíticas (`JOIN`s). Patrón estándar HIS hospitalario. |
| **Documental flexible** | MongoDB (+ GridFS) | `predictions_triage`, `predictions_disease`, `system_events`, radiografías (GridFS), informes diarios | Documentos schemaless: cada modelo de IA puede tener un output con forma distinta sin migraciones. GridFS para binarios grandes. |

**Flujo de un formulario online**:

```
Paciente envía → MinIO (raw) → validate+transform → PostgreSQL (paciente+ingreso)
                                                      ↓
                                               ml-triage /predict
                                                      ↓
                                MongoDB (predictions_triage + predictions_disease)
```

Detalle técnico completo en [specs/DESIGN-03-almacenamiento.md](specs/DESIGN-03-almacenamiento.md).

## Configuración avanzada

### Cambiar puertos

Edita `.env` y modifica `API_PORT`, `DASHBOARD_PORT`, `PGADMIN_DEFAULT_PASSWORD`, etc. Luego reinicia:

```powershell
docker compose down
docker compose up -d
```

### Logs centralizados

Todos los servicios fluyen logs a **Loki** (accesible en http://localhost:3100).

Prueba con curl:

```powershell
curl -s "http://localhost:3100/loki/api/v1/query?query={job=\"varlogs\"}" | ConvertFrom-Json | Select-Object -ExpandProperty data
```

### Verificar volúmenes y persistencia

```powershell
# Listar volúmenes
docker volume ls | grep hospital

# Inspeccionar contenedor
docker compose exec postgres psql -U admin -d hospital -c "SELECT * FROM pacientes;"
docker compose exec mongodb mongosh -u admin -p change-me --eval "db.pacientes.find().pretty()"
```

## Validación según SDD-01

Para verificar que el despliegue cumple con los criterios de aceptación:

```powershell
# 1. Validar YAML
docker compose config > $null

# 2. Verificar servicios saludables
docker compose ps

# 3. Verificar red
docker network inspect hospital-net

# 4. Verificar volúmenes
docker volume ls

# 5. Verificar variables .env
Get-Content .env | Where-Object {$_ -notmatch "^#|^$"}
```

## Troubleshooting

### Los servicios no alcanzan estado `healthy`

```powershell
docker compose logs <servicio>
docker compose ps  # Ver los últimos errores
```

### Puerto ya en uso

Si algún puerto (8000, 8501, 5050, 8081, 3100) ya está ocupado, edita `.env` y cambia:

```dotenv
API_PORT=8001         # en lugar de 8000
DASHBOARD_PORT=8502   # en lugar de 8501
```

### Limpiar todo y empezar desde cero

```powershell
docker compose down -v
docker system prune -a --volumes
docker compose up -d
```

## Documentación técnica

Para detalles de arquitectura, almacenamiento, pipeline, modelos de IA, etc., consulta:

- **SDD-01**: [specs/DESIGN-01-arquitectura.md](specs/DESIGN-01-arquitectura.md) — Arquitectura global y Docker Compose
- **CONTEXT.md**: [CONTEXT.md](CONTEXT.md) — Contexto y requisitos del proyecto
## Desarrollo asistido por IA y metodología SDD

El proyecto se ha desarrollado siguiendo parcialmente una metodología **Spec-Driven Development (SDD)** y utilizando herramientas de desarrollo asistido por IA.

### Herramientas de IA utilizadas

| Herramienta | Uso principal |
|---|---|
| **Claude Code** | Generación y refactorización de código dentro del repositorio, edición de servicios, documentación y apoyo en la integración Docker. |
| **ChatGPT** | Apoyo en arquitectura, depuración de errores, diseño de pruebas end-to-end, validación de requisitos y redacción técnica. |

La herramienta principal aceptada para el requisito de *Vibe Coding* ha sido **Claude Code**, complementada con ChatGPT para revisión, análisis y debugging.

### Aplicación de Spec-Driven Development

Antes de implementar los módulos principales se redactaron especificaciones en la carpeta `specs/`, incluyendo:

- `DESIGN-01-arquitectura.md`: arquitectura global y servicios Docker.
- `DESIGN-02-pipeline.md`: flujo de ingesta, validación, transformación y carga.
- `DESIGN-03-almacenamiento.md`: PostgreSQL, MongoDB y MinIO.
- `DESIGN-08-modelo-triaje.md`: modelo tabular de triaje.
- `DESIGN-08b-modelo-enfermedad.md`: modelo de sospecha clínica.
- `SDD-02-pipeline.md`: contrato funcional del pipeline.
- `SDD-07-monitorizacion.md`: eventos, logs, Loki/Promtail y alertas.

Estas especificaciones sirvieron como base para pedir a las herramientas de IA la implementación incremental de componentes.

### Diario de desarrollo con IA

El proceso se documenta en `docs/diario-ia/`, donde se recogen:

- prompts representativos,
- decisiones técnicas,
- iteraciones con la IA,
- errores detectados y correcciones,
- reflexión crítica sobre productividad y limitaciones.

Documentos principales:

- `docs/diario-ia/00-genesis-plan.md`
- `docs/diario-ia/01-integracion-ariadna.md`
- `docs/diario-ia/02-modelo-triaje.md`
- `docs/diario-ia/03-etl-pipeline.md`
- `docs/diario-ia/04-online-api-dashboard.md`
- `docs/diario-ia/05-minio-landing.md`
- `docs/diario-ia/06-pulido-ux.md`
- `docs/diario-ia/99-reflexion-critica.md`

## Licencia

Proyecto académico — Práctica final de especialidad en IA y Big Data.




| **Dask Dashboard** | http://localhost:8787 | — | Monitorización del procesamiento batch escalable |
## Procesamiento escalable con Dask

El pipeline batch incorpora Dask como framework de procesamiento escalable. Dask se utiliza en la fase de ingesta de ficheros CSV para leer y particionar datos mediante `dask.dataframe`.

En ejecución Docker Compose, el sistema levanta:

- `dask-scheduler`: planificador de tareas distribuidas.
- `dask-worker`: worker que ejecuta tareas del pipeline.
- `pipeline`: servicio que orquesta la ingesta, validación, transformación y carga.

El dashboard de Dask está disponible en:

```powershell
http://localhost:8787


1. Añade esta fila dentro de la tabla “Acceso a servicios”
| **Dask Dashboard** | http://localhost:8787 | — | Monitorización del procesamiento distribuido |

Y, si quieres dejar los puertos más correctos con tu .env, puedes cambiar API/Dashboard a:

| **API** | http://localhost:${API_PORT} | — | REST API (healthcheck: `/health`) |
| **Dashboard** | http://localhost:${DASHBOARD_PORT} | — | Streamlit UI con métricas |
2. Sustituye el fragmento final suelto por este bloque

Pégalo después de Arquitectura de almacenamiento o después de Configuración avanzada.

## Pipeline de datos a escala

El sistema implementa un pipeline completo de datos hospitalarios, desde la ingesta hasta el servicio final mediante API y dashboard.

### Flujo batch

```text
CSV sintético / CSV externo
        ↓
MinIO / S3 raw bucket
        ↓
Pipeline Dockerizado
        ↓
Dask dataframe para lectura escalable
        ↓
Validación declarativa YAML
        ↓
Transformación a entidades hospitalarias
        ↓
PostgreSQL: pacientes + ingresos
        ↓
ml-triage: triaje + sospecha de enfermedad
        ↓
MongoDB: predicciones, eventos, rechazos y alertas
        ↓
API REST + Dashboard Streamlit
Ingesta

La ingesta puede realizarse mediante generación sintética reproducible:

docker compose exec pipeline python main.py seed --n 100 --seed 42

El comando genera un CSV en el bucket raw de MinIO y devuelve una clave S3 similar a:

patients/seed-YYYYMMDDTHHMMSSZ-s42-n100.csv

Después se ejecuta el batch:

docker compose exec pipeline python main.py batch --key "patients/seed-YYYYMMDDTHHMMSSZ-s42-n100.csv"

También se puede hacer en PowerShell de forma automática:

$seed = docker compose exec -T pipeline python main.py seed --n 20 --seed 555 | ConvertFrom-Json
$key = $seed.key
docker compose exec pipeline python main.py batch --key "$key"
Resultado esperado del batch

Un batch correcto devuelve un resumen como:

{
  "records_in": 20,
  "valid": 20,
  "rejected": 0,
  "pacientes_insertados": 20,
  "ingresos_insertados": 20,
  "triage_completed": 20,
  "triage_pending": 0
}
Procesamiento escalable con Dask

El pipeline batch incorpora Dask como framework de procesamiento escalable. Se utiliza en la fase de ingesta para leer CSVs mediante dask.dataframe, particionar el fichero y ejecutar operaciones distribuidas sobre el scheduler.

Servicios implicados:

Servicio	Función
dask-scheduler	Planificador distribuido
dask-worker	Ejecutor de tareas
pipeline	Orquestador del batch

El dashboard de Dask está disponible en:

http://localhost:8787
Verificación de Dask
docker compose ps dask-scheduler dask-worker pipeline

Prueba de conexión al scheduler:

docker compose exec pipeline python -c "from dask.distributed import Client; c=Client('tcp://dask-scheduler:8786'); info=c.scheduler_info(); print('Scheduler:', info['address']); print('Workers:', len(info['workers'])); c.close()"

Prueba de procesamiento distribuido:

docker compose exec pipeline python -c "from dask.distributed import Client; import dask.dataframe as dd; import pandas as pd; import os; p='/app/data/tmp/test_dask.csv'; os.makedirs('/app/data/tmp', exist_ok=True); pd.DataFrame({'a': range(10000), 'b': range(10000)}).to_csv(p, index=False); c=Client('tcp://dask-scheduler:8786'); df=dd.read_csv(p, blocksize='16KB'); print('Partitions:', df.npartitions); print('Rows:', df.shape[0].compute()); print('Sum:', df.a.sum().compute()); print('Workers:', len(c.scheduler_info()['workers'])); c.close()"

Ejemplo de salida esperada:

Partitions: 6
Rows: 10000
Sum: 49995000
Workers: 1
Justificación de Dask

Se usa Dask porque permite escalar el procesamiento tabular manteniendo una API muy próxima a pandas. Para este proyecto es más ligero que Spark, se integra bien con Python y permite demostrar ejecución distribuida mediante scheduler y worker sin añadir la sobrecarga operativa de un clúster Spark completo.

Modelos de IA tabular: triaje y sospecha de enfermedad

El servicio ml-triage aloja dos modelos tabulares:

Modelo	Salida
Triaje	Alta, Media, Baja
Sospecha de enfermedad	Diagnóstico diferencial orientativo

El endpoint combinado es:

POST http://ml-triage:8002/predict

Desde fuera del contenedor puede verificarse el estado con:

docker compose exec ml-triage curl -s http://localhost:8002/health

Salida esperada:

{
  "status": "ok",
  "triage_version": "tri-...",
  "disease_version": "dis-..."
}
Entrenamiento reproducible

Los modelos se generan mediante scripts Dockerizados:

.\scripts\train_tabular_models.ps1

Este script genera dataset sintético, entrena los modelos y crea artefactos en:

models/triage/
models/disease/

La evaluación se ejecuta con:

.\scripts\evaluate_tabular_models.ps1

Genera:

metrics.json
confusion_matrix.png
critical_analysis.md
Monitorización y logging centralizado

El sistema usa dos capas de observabilidad:

Logs técnicos centralizados
Los servicios emiten logs a stdout.
Promtail recoge logs Docker.
Loki centraliza y permite consultar logs mediante LogQL.
Eventos de dominio
El pipeline guarda eventos estructurados en MongoDB (system_events).
Cada ejecución usa un correlation_id.
El dashboard y la automatización pueden consumir estos eventos.
Servicios de monitorización
Servicio	Función
loki	Almacenamiento y consulta de logs
promtail	Recolector de logs Docker
automation	Escaneo de warnings/errors y creación de alertas
mongodb.system_events	Eventos de dominio del pipeline
mongodb.alerts	Alertas operativas deduplicadas
Verificar Loki y Promtail
docker compose ps loki promtail
curl.exe -s http://localhost:3100/ready
docker compose logs promtail --tail=50

Salida esperada de Loki:

ready
Consultar logs del pipeline en Loki desde PowerShell
$end = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() * 1000000
$start = [DateTimeOffset]::UtcNow.AddMinutes(-30).ToUnixTimeMilliseconds() * 1000000

$query = '{compose_service="pipeline"} |= "pipeline.run.end"'
$url = "http://localhost:3100/loki/api/v1/query_range?limit=10&start=$start&end=$end&query=$([uri]::EscapeDataString($query))"

curl.exe -s $url

La respuesta debe contener logs JSON del pipeline, por ejemplo:

{
  "event": "pipeline.run.end",
  "message": "Pipeline batch completado en ... ms",
  "records_in": 20,
  "duration_ms": 2736
}
Calidad de datos y rechazos

La validación se define de forma declarativa en:

services/pipeline/config/validation_rules.yaml

Comprueba:

Campos obligatorios.
Tipos.
Rangos numéricos.
Enumeraciones válidas.
Reglas cruzadas.
Duplicados por clave lógica.

Ejemplos de reglas:

Campo	Regla
edad	entero entre 0 y 120
sexo	M, F, Otro
intensidad_dolor	entero entre 0 y 10
hora_envio	entero entre 0 y 23
Prueba de calidad con CSV inválido

Se incluye una prueba controlada con:

patients/quality-test-invalid.csv

Ejecución:

docker compose exec pipeline python main.py batch --key "patients/quality-test-invalid.csv"

Salida esperada:

{
  "records_in": 5,
  "valid": 1,
  "rejected": 4,
  "rejects_persisted": 4,
  "pacientes_insertados": 1,
  "ingresos_insertados": 1,
  "triage_completed": 1,
  "triage_pending": 0
}
Ver eventos de validación en MongoDB
docker compose exec mongodb mongosh -u admin -p change-me --authenticationDatabase admin hospital --eval "db.system_events.find({event:'pipeline.validation.done'}).sort({timestamp:-1}).limit(5).pretty()"
Ver warnings del pipeline
docker compose exec mongodb mongosh -u admin -p change-me --authenticationDatabase admin hospital --eval "db.system_events.find({level:'warning'}).sort({timestamp:-1}).limit(10).pretty()"
Ver rechazos persistidos
docker compose exec mongodb mongosh -u admin -p change-me --authenticationDatabase admin hospital --eval "db.ingestion_rejects.find().sort({ingested_at:-1}).limit(5).pretty()"

Ejemplos de motivos de rechazo:

missing_field:edad
sexo:enum
intensidad_dolor:max:10
Alertas operativas

El servicio automation revisa periódicamente system_events y crea alertas en MongoDB cuando detecta eventos warning o error.

Ejemplo de eventos que generan alertas:

pipeline.validation.done
pipeline.rejects.persisted
pipeline.ml.done
Ver logs del servicio de automatización
docker compose logs automation --tail=50

Ejemplo de salida:

Nueva alerta creada: pipeline.validation.done:run-...:warning | Validación: 1 válidos, 4 rechazados
Nueva alerta creada: pipeline.rejects.persisted:run-...:warning | 4 rechazos persistidos en ingestion_rejects
Escaneo completado: events_scanned=2 alerts_inserted=2 alerts_existing=0
Consultar alertas en MongoDB
docker compose exec mongodb mongosh -u admin -p change-me --authenticationDatabase admin hospital --eval "db.alerts.find().sort({created_at:-1}).limit(10).pretty()"

Cada alerta contiene:

Campo	Descripción
dedup_key	Clave de deduplicación
correlation_id	Run del pipeline asociado
severity	warning o error
source_event	Evento que originó la alerta
message	Mensaje legible
payload	Métricas asociadas
notification_status	simulated
Prueba end-to-end recomendada

Para validar el sistema completo:

# 1. Levantar todo
docker compose up -d --remove-orphans

# 2. Ver estado
docker compose ps

# 3. Ejecutar batch correcto
$seed = docker compose exec -T pipeline python main.py seed --n 20 --seed 555 | ConvertFrom-Json
docker compose exec pipeline python main.py batch --key "$($seed.key)"

# 4. Ejecutar batch con errores de calidad
docker compose exec pipeline python main.py batch --key "patients/quality-test-invalid.csv"

# 5. Ver eventos
docker compose exec mongodb mongosh -u admin -p change-me --authenticationDatabase admin hospital --eval "db.system_events.find().sort({timestamp:-1}).limit(10).pretty()"

# 6. Ver rechazos
docker compose exec mongodb mongosh -u admin -p change-me --authenticationDatabase admin hospital --eval "db.ingestion_rejects.find().sort({ingested_at:-1}).limit(5).pretty()"

# 7. Ver alertas
docker compose exec mongodb mongosh -u admin -p change-me --authenticationDatabase admin hospital --eval "db.alerts.find().sort({created_at:-1}).limit(10).pretty()"
Limpieza de contenedores huérfanos

Durante pruebas con docker compose run, pueden quedar contenedores temporales huérfanos. Se eliminan con:

docker compose up -d --remove-orphans
Nota sobre datasets y artefactos pesados

No se deben versionar datasets grandes ni artefactos binarios pesados en GitHub.

El repositorio ignora:

data/synthetic/
data/raw/
data/covid-subset/
models/
*.zip

Los modelos y datasets se regeneran con scripts reproducibles usando semilla fija.


## 3. Cambia también la sección “Logs centralizados”

Tu bloque actual de logs usa `{job="varlogs"}`, pero ahora estás usando labels Docker (`compose_service`, `compose_project`, etc.). Sustitúyelo por este:

```markdown
### Logs centralizados

Todos los servicios emiten logs a stdout. Promtail descubre contenedores Docker y envía sus logs a Loki.

Verificar Loki:

```powershell
curl.exe -s http://localhost:3100/ready

Consultar logs recientes del pipeline:

$end = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() * 1000000
$start = [DateTimeOffset]::UtcNow.AddMinutes(-30).ToUnixTimeMilliseconds() * 1000000
$query = '{compose_service="pipeline"} |= "pipeline.run.end"'
$url = "http://localhost:3100/loki/api/v1/query_range?limit=10&start=$start&end=$end&query=$([uri]::EscapeDataString($query))"
curl.exe -s $url

Con esto tu README ya explica bien la parte de **Dask + pipeline escalable + ML + Loki/Promtail + calidad +

El README debe explicar que el dataset se descarga aparte y se coloca en:

COVID-19_Radiography_Dataset/
## Documentación de arquitectura y notebooks

Además de este README, el proyecto incluye documentación ampliada:

| Documento | Función |
|---|---|
| [`docs/PROJECT_MAP.md`](docs/PROJECT_MAP.md) | Mapa técnico completo del repositorio, servicios, modelos, datos y flujo end-to-end. |
| [`docs/notebooks.md`](docs/notebooks.md) | Plan de notebooks de análisis, gráficas y comunicación de resultados. |
| [`services/ml-inference/README.md`](services/ml-inference/README.md) | Documentación específica del módulo Deep Learning de radiografías. |
| [`specs/SDD-09-etica-legal.md`](specs/SDD-09-etica-legal.md) | Consideraciones éticas, legales, sesgos, privacidad y limitaciones. |

Los notebooks complementan el dashboard: muestran gráficas, matrices de confusión, comparación de modelos y explicación técnica paso a paso.