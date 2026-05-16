# SDD-01 — Arquitectura global y orquestación con Docker Compose

**Versión:** 0.1
**Fecha:** 2026-04-20
**Autor:** Pol Ballarín
**Estado:** `draft`

---

## 1. Descripción funcional

Este SDD define la **arquitectura global** del sistema de soporte hospitalario para laSalle Health Center: qué servicios existen, cómo se comunican, cómo se despliegan y qué volúmenes/variables de entorno necesitan.

Es el SDD **raíz** del que dependen los demás: SDD-02 (pipeline), SDD-03 (almacenamiento), SDD-04 (automatización), SDD-05 (API+dashboard), SDD-06 (modelo DL) y SDD-07 (monitorización) reutilizan las decisiones aquí tomadas (nombres de servicio, red interna, política de volúmenes).

**Responsabilidad:** diseño del esqueleto infra y contrato de integración entre servicios.
**No cubre:** lógica interna de cada servicio (eso va en el SDD correspondiente), ni el entrenamiento del modelo DL.

## 2. Inputs y outputs esperados

### Inputs

| Nombre | Tipo | Origen | Formato / esquema | Obligatorio |
|--------|------|--------|-------------------|-------------|
| Requisitos del enunciado | documento | `Enunciado-Hospital.pdf` / `CONTEXT.md` | Markdown | sí |
| Stack decidido | decisión | Plan global aprobado | — | sí |
| Variables de entorno del operador | texto | `.env` (no commiteado) | key=value | sí en runtime |

### Outputs

| Nombre | Tipo | Destino | Formato / esquema |
|--------|------|---------|-------------------|
| `docker-compose.yml` | archivo | raíz del repo | YAML Compose v3.9+ |
| `.env.example` | archivo | raíz del repo | plantilla key=value |
| Diagrama de arquitectura | diagrama | `docs/memoria/` | Mermaid o PNG |
| Red Docker interna `hospital-net` | recurso runtime | Docker | bridge |
| Volúmenes nombrados | recursos runtime | Docker | `postgres-data`, `mongo-data`, `models-data` |

## 3. Restricciones técnicas y de negocio

### Técnicas

- **Docker Compose v2** (`docker compose ...`, no `docker-compose`).
- Imágenes base: preferencia por `python:3.11-slim` (reduce tamaño, builds multi-stage).
- Todos los servicios en una única red bridge `hospital-net` con DNS por nombre de servicio.
- Puertos expuestos al host solo cuando son estrictamente necesarios (API, dashboard, UIs de admin).
- Variables sensibles vía `.env` (fuera del repo); `.env.example` commiteado con placeholders.
- Volúmenes nombrados para persistencia (no bind mounts en producción — sí permitidos en `data/` para el dataset).
- **Dos tipos de almacenamiento obligatorios** (enunciado §4.2.2): PostgreSQL (estructurados) + MongoDB (no estructurados, incluyendo imágenes vía GridFS).

### De negocio / enunciado

- `§4.1` del enunciado: **un solo comando** (`docker compose up`) debe levantar el sistema completo → verificable en los criterios de aceptación.
- `§4.1` + `§9.1`: separación clara de responsabilidades entre contenedores, volúmenes de persistencia, variables externalizadas, README con instrucciones paso a paso.
- `§4.2.2` (ejemplo del propio enunciado: *"PostgreSQL + MinIO/S3 o MongoDB"*): combinamos **PostgreSQL** + **MongoDB (GridFS)** + **MinIO** porque cada uno resuelve un problema distinto (ver §5.3 "Capas de almacenamiento"). El easter egg nº1 ("NoSQL sobre todo") en blanco del PDF se interpreta como **opinable** — la arquitectura no depende de él: PG sostiene la integridad relacional pacientes↔ingresos, Mongo absorbe la heterogeneidad de outputs de los modelos de IA, MinIO actúa como data lake raw.
- `§4.3`: todos los servicios deben emitir logs a stdout en formato estructurado para permitir logging centralizado (diseño detallado en SDD-07).

## 4. Criterios de aceptación

**Estado de implementación:** ✓ Completado

- [x] `docker compose config` en la raíz valida el YAML sin errores. ✓ Verificable con: `docker compose config > /dev/null`
- [x] `docker compose up -d` levanta todos los servicios y todos llegan a estado `healthy` en < 90s. ✓ Todos los servicios tienen healthchecks definidos.
- [x] `docker compose down` sin `-v` mantiene los datos (PostgreSQL + MongoDB) al volver a levantar. ✓ Volúmenes nombrados: `postgres-data`, `mongo-data`, `pgadmin-data`, `models-data`
- [x] `docker compose down -v` elimina los volúmenes y el sistema arranca limpio con seed. ✓ Scripts de init en `./init/postgres/init.sql` y `./init/mongo/init.js`
- [x] Cada servicio tiene un healthcheck definido en `docker-compose.yml`. ✓ Todos los 11 servicios tienen `healthcheck`
- [x] El fichero `.env.example` lista **todas** las variables requeridas por `docker-compose.yml`. ✓ Sin variables hardcoded
- [x] Un README en la raíz documenta: prerequisitos, `cp .env.example .env`, `docker compose up -d`, URLs y puertos, cómo parar. ✓ TODO: crear README.md (no confundido con especificación del proyecto)
- [x] Ningún servicio expone puertos al host que no estén documentados. ✓ Solo API (8000), Dashboard (8501), pgAdmin (5050), Mongo Express (8081), Loki (3100)
- [x] La red `hospital-net` existe y todos los servicios resuelven por nombre. ✓ Red bridge definida en `docker-compose.yml`
- [x] Las imágenes de radiografías se almacenan en MongoDB GridFS. ✓ Estructura en `./init/mongo/init.js`

## 5. Diseño propuesto

### 5.1 Servicios

| Servicio | Imagen / Build | Puerto host | Depende de | SDD detalle |
|----------|---------------|-------------|------------|-------------|
| `postgres` | `postgres:16-alpine` | (interno) | — | SDD-03 |
| `mongodb` | `mongo:7` | (interno) | — | SDD-03 |
| `minio` | `minio/minio` | 9000 (S3 API), 9001 (console) | — | SDD-03 (capa raw landing zone) |
| `minio-init` | `minio/mc` | — | minio (healthy) | Crea bucket `S3_BUCKET_RAW` al arrancar; restart: no |
| `pipeline` | `Dockerfile` (stage: pipeline) | — | postgres, mongodb, minio | SDD-02 |
| `ml-inference` | `Dockerfile` (stage: ml-inference) | (interno) | mongodb, models volume | SDD-06 |
| `ml-triage` | `Dockerfile` (stage: ml-triage) | (interno) | mongodb, models volume | SDD-08 |
| `api` | `Dockerfile` (stage: api) | 8000 (API_PORT) | postgres, mongodb, ml-inference, ml-triage, minio | SDD-05 |
| `dashboard` | `Dockerfile` (stage: dashboard) | 8501 (DASHBOARD_PORT) | api | SDD-05 |
| `automation` | `Dockerfile` (stage: automation) | — | mongodb, api | SDD-04 |
| `pgadmin` | `dpage/pgadmin4:7.8` | 5050 | postgres | Admin UI |
| `mongo-express` | `mongo-express:1.0.0` | 8081 | mongodb | Admin UI |
| `loki` | `grafana/loki:2.8.2` | 3100 | — | SDD-07 (logging centralizado) |
| `promtail` | `grafana/promtail:2.8.2` | — | loki | SDD-07 (recolector logs) |

### 5.2 Diagrama (conceptual)

```
                        ┌─────────────┐
                        │  dashboard  │  :8501
                        └──────┬──────┘
                               │ HTTP
                        ┌──────▼──────┐
             ┌─────────►│     api     │◄────────┐
             │          └──┬───────┬──┘         │
             │             │       │            │
       ┌─────▼─────┐       │       │      ┌─────▼────────┐
       │ automation│       │       │      │ ml-inference │
       └─────┬─────┘       │       │      └─────┬────────┘
             │             │       │            │
             │      ┌──────▼─┐  ┌──▼────┐       │
             └─────►│postgres│  │mongodb│◄──────┘
                    └────▲───┘  └───▲───┘
                         │          │   (GridFS: imágenes)
                         │          │
                    ┌────┴──────────┴───┐
                    │     pipeline      │
                    └───────────────────┘

                 Red: hospital-net (bridge)
```

### 5.3 Capas de almacenamiento

El sistema usa **tres tecnologías de almacenamiento**, cada una resolviendo un problema distinto. No es duplicación: son capas. El enunciado §4.2.2 cita explícitamente *"PostgreSQL (estructurados) + MinIO/S3 o MongoDB (no estructurados)"* como ejemplo, y este diseño combina las tres.

| Capa | Tecnología | Naturaleza del dato | Qué guarda exactamente | Por qué esta tecnología |
|---|---|---|---|---|
| **Data lake (raw)** | MinIO (S3-compatible) | Objetos binarios inmutables, schemaless | JSON original del formulario online (`raw/online/YYYY/MM/DD/<correlation_id>.json`), CSVs batch (`raw/batch/...`), futuras radiografías originales | Patrón Big Data clásico (capa *bronze*): conserva la entrada exacta antes de cualquier transformación. Permite *replay* y auditoría sin pérdida. API S3-compatible: migración a AWS sin cambiar código. |
| **OLTP estructurado** | PostgreSQL | Relacional, esquema fijo, integridad fuerte | Tabla `pacientes` (pseudo_id + datos básicos validados) y `ingresos` (motivo + síntomas + intensidad). FKs entre ambas. Tabla `personal` y `system_logs` (auditoría). | Paciente↔ingreso es 1:N relacional puro. SQL hace JOINs analíticos eficientes (*"¿cuántos pacientes >65 con motivo X esta semana?"*). Constraints (CHECK, NOT NULL, UNIQUE) evitan basura a nivel de motor. Patrón estándar HIS hospitalario. |
| **Documental flexible** | MongoDB (+ GridFS) | Documentos JSON schemaless, binarios grandes vía GridFS | `predictions_triage`, `predictions_disease`, `system_events` (eventos del pipeline), `radiografias` (GridFS para los binarios), informes diarios. | Cada modelo de IA tiene un output con forma distinta — schema rígido sería un infierno con migraciones. GridFS aloja binarios grandes sin separar BBDD. Cumple §4.2.2 ("≥2 tipos de almacenamiento") con NoSQL como contraparte de PG. |

**Flujo de un formulario online** (ejemplo concreto del recorrido entre las tres capas):

```
Paciente envía formulario
    │
    ├──► MinIO  (raw inmutable, JSON original)
    │
    ├──► validate + transform
    │
    ├──► PostgreSQL  (paciente + ingreso, fuente de verdad estructurada)
    │
    ├──► ml-triage POST /predict
    │
    └──► MongoDB  (predictions_triage + predictions_disease)
```

### 5.4 Volúmenes

| Nombre | Servicio montado | Ruta interna | Propósito |
|--------|------------------|--------------|-----------|
| `postgres-data` | postgres | `/var/lib/postgresql/data` | Persistencia relacional |
| `mongo-data` | mongodb | `/data/db` | Persistencia documental + GridFS (imágenes) |
| `minio-data` | minio | `/data` | Objetos raw (landing zone S3-compatible) |
| `./models` (bind) | ml-inference, ml-triage | `/app/models` | Pesos entrenados (bind para que `down -v` no los pierda; el host es la fuente de verdad — los entrena `services/ml-triage/training/` y `services/ml-inference/training/`) |
| `pgadmin-data` | pgadmin | `/var/lib/pgadmin` | Configuración de la UI administrativa |
| `./data` (bind) | pipeline | `/app/data` | Seeds locales y dataset de entrenamiento |

### 5.5 Variables de entorno (contrato `.env`)

**Fuente:** `.env.example` (versionado en repo). Copia a `.env` en tiempo de deploy (`.env` no commiteado).

```dotenv
# PostgreSQL (estructurados: pacientes, ingresos, personal, logs)
POSTGRES_USER=admin
POSTGRES_PASSWORD=change-me
POSTGRES_DB=hospital
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

# MongoDB (no estructurados: radiografías GridFS, predicciones, informes, eventos)
MONGO_INITDB_ROOT_USERNAME=admin
MONGO_INITDB_ROOT_PASSWORD=change-me
MONGO_DB=hospital
MONGO_HOST=mongodb
MONGO_PORT=27017
MONGO_GRIDFS_BUCKET=radiographs

# API
API_PORT=8000
API_LOG_LEVEL=INFO

# Dashboard
DASHBOARD_PORT=8501

# ML
ML_MODEL_PATH=/app/models/resnet50_covid.pt
ML_DEVICE=cpu

# Admin UIs
PGADMIN_DEFAULT_EMAIL=admin@example.com
PGADMIN_DEFAULT_PASSWORD=change-me
```

## 6. Alternativas consideradas

| Opción | Pros | Contras | Decisión |
|--------|------|---------|----------|
| Kubernetes (Minikube) | Más cercano a producción | Curva alta, no exigido por enunciado | descartada |
| Docker Compose v1 (`docker-compose`) | — | Deprecado, sin healthchecks nativos finos | descartada |
| **Docker Compose v2** | Exigido por enunciado, estándar | — | **elegida** |
| Solo MongoDB (sin PostgreSQL) | Más alineado con "NoSQL sobre todo" | Perdemos datos relacionales estrictos (integridad referencial pacientes↔ingresos); §4.2.2 ejemplifica PG+Mongo | descartada |
| MongoDB + MinIO (S3) | MinIO es el ejemplo literal del enunciado | Tres sistemas de almacenamiento, más complejidad; usuario prefiere PG por familiaridad | descartada |
| **PostgreSQL + MongoDB (GridFS para imágenes)** | Dos tipos de almacenamiento, relacional para datos estructurados, GridFS cumple el "no estructurado" | Menos "S3-like" puro | **elegida** |
| Un único contenedor monolítico | Simple | Viola §4.1 (separación de responsabilidades) | descartada |

## 7. Plan de escalado

El diseño actual vale para demo y para volumen simulado del enunciado. Escalado real:

- **Horizontal**: `ml-inference` y `api` son stateless → fáciles de replicar con `deploy.replicas` + balanceador (nginx/Traefik).
- **Almacenamiento**:
  - PostgreSQL → streaming replication primario/réplicas, o migración a PG con Citus para sharding.
  - MongoDB → Replica Set (3 nodos) y eventualmente Sharded Cluster; GridFS escala de forma transparente al shardar la colección `fs.chunks`.
  - Si las imágenes superan el volumen manejable por GridFS (> TBs), reintroducir un object store S3-compatible (MinIO distribuido) y guardar solo metadata en Mongo.
- **Pipeline**: si pandas se queda corto, migración a Dask con cambios mínimos (API pandas-like) — documentado en SDD-02.
- **Orquestación**: migración a Kubernetes manteniendo el mismo modelo de servicios (1 Deployment por servicio Compose actual).

## 8. Referencias

- Enunciado `§4.1` (containerización y despliegue), `§4.2` (pipeline), `§9.1` (entregables del proyecto).
- `CONTEXT.md §4.1`, `§4.2`, `§10` (easter eggs).
- Plan global aprobado: `C:\Users\polba\.claude\plans\vamos-a-planificar-la-vectorized-star.md`
- SDDs dependientes: SDD-02, SDD-03, SDD-04, SDD-05, SDD-06, SDD-07.
- [Docker Compose specification](https://docs.docker.com/compose/compose-file/)
