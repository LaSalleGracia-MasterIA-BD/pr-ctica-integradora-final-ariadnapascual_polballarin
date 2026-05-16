# DESIGN-02 — Pipeline de datos: diseño técnico

> Diseño de implementación del pipeline especificado en [`SDD-02-pipeline.md`](SDD-02-pipeline.md). Define módulos Python, reglas de validación en YAML, flujo batch vs online, y justifica formalmente el uso de pandas. La fuente de datos crudos (local FS vs S3 AWS vs MinIO) queda abstracta tras una interfaz — decisión diferida según SDD-02 §7.

---

**Versión:** 1.0
**Fecha:** 2026-04-21
**Autor:** Pol Ballarín
**Estado:** `ready-for-implementation`

---

## 1. Contexto

Spec base: SDD-02 — pipeline de cuatro fases (ingesta → limpieza → transformación → análisis) con dos modos de operación: **batch** (CSVs + radiografías en lote) y **online** (una única ficha del formulario web que termina invocando al modelo de triaje SDD-08).

Este documento cierra **4 de los 5 `[NEEDS CLARIFICATION]`** de SDD-02 §7 (el 5º, fuente S3 vs MinIO, sigue diferido — ver SDD-03 §7) y aterriza el código listo para implementar dentro de `services/pipeline/`.

## 2. Decisiones cerradas

| Duda de SDD-02 §7 | Decisión |
|---|---|
| Volumen y tiempo objetivo (RNF-1) | **10 000 registros clínicos + 1 000 radiografías** en **< 10 min** en CPU estándar de portátil. Metric calculada por el pipeline al finalizar. |
| Orquestación del pipeline (ligada a SDD-04) | **Sprint 2: `cron` + scripts Python** (simple, 1 persona). Prefect queda documentado como mejora futura si el tribunal pide workflow visual. |
| Política de upsert por clave lógica duplicada (RF-7) | **`first_wins`**: el primer registro con una clave lógica gana. Los siguientes se persisten en `ingestion_rejects` con motivo `"duplicate_key"`. Favorece idempotencia y evita sobrescribir silenciosamente. |
| Lenguaje de reglas declarativas (RNF-10) | **YAML** (`config/validation_rules.yaml`), parseado con `PyYAML` a diccionario Python. Legible por no-programadores, versionable, sin lock-in. Validación estructural del propio YAML con un pequeño esquema Pydantic al arranque. |

Pendiente: **fuente de datos crudos** (SDD-02 §7 último bullet) — se usa una **interfaz `RawSource`** para leer tanto del filesystem local montado en `./data/` como de un bucket S3 (AWS o MinIO). El código de negocio es agnóstico; cambia solo el constructor.

## 3. Estructura de código

```
services/pipeline/
├── Dockerfile                       # stage 'pipeline' ya existe en Dockerfile raíz
├── requirements.txt                 # pandas, sqlalchemy, psycopg2-binary, pymongo, PyYAML, pydantic, boto3, loguru, tenacity
├── main.py                          # CLI entry point (argparse)
├── config/
│   └── validation_rules.yaml        # reglas declarativas (ver §5)
└── app/
    ├── __init__.py
    ├── cli.py                       # parser de argumentos + despachador
    ├── config.py                    # env vars tipadas (Pydantic BaseSettings)
    ├── logging_setup.py             # JSON structured logs + correlation_id
    ├── orchestrator.py              # ejecuta las 4 fases en orden o una sola
    ├── online.py                    # modo online: una ficha → triaje → persistencia
    │
    ├── phases/
    │   ├── ingestion.py             # Fase 1: lee crudo (RawSource) → DataFrame
    │   ├── validation.py            # Fase 2: aplica reglas YAML → (válidos, rechazos)
    │   ├── transformation.py        # Fase 3: pseudo_id, derivados, trazabilidad
    │   ├── loading.py               # Fase 4: PG (SQLAlchemy) + Mongo (pymongo)
    │   └── aggregates.py            # Métricas diarias → Mongo colección agregados
    │
    ├── storage/
    │   ├── postgres.py              # engine + sesiones + upsert helpers
    │   ├── mongo.py                 # client + GridFS + helpers
    │   └── raw_source.py            # interfaz LocalFS | S3 (boto3)
    │
    ├── clients/
    │   └── triage_client.py         # httpx a ml-triage:8002/predict (combinado)
    │
    └── utils/
        ├── pseudo_id.py             # generador "PAT-000001" reproducible
        ├── hashing.py               # SHA-256 de ficheros e imágenes
        └── retry.py                 # tenacity con backoff exponencial
```

## 4. Justificación formal del uso de pandas y plan de escalado

> **Sección obligatoria de entregable (SDD-02 RF-18).** También se replicará en la memoria técnica §9.3.8 "Justificaciones técnicas".

### 4.1 Autorización

El enunciado §4.2.3 exige "al menos un framework distribuido/escalable — Apache Spark/PySpark, Dask o Apache Beam". El profesor **autorizó explícitamente** el uso de pandas como excepción documentada.

### 4.2 Razones técnicas

1. **Volumen manejable en memoria**: el dataset objetivo (10 000 fichas clínicas + 1 000 radiografías de metadatos) cabe holgadamente en RAM de un portátil estándar (< 100 MB en pandas).
2. **Integración directa con PyTorch** (SDD-06): tensores se crean desde `DataFrame.values` sin coste de conversión.
3. **Simplicidad operativa**: sin cluster, sin scheduler externo, sin configuración de workers. Reduce deuda técnica para un proyecto de 3 semanas.
4. **Curva de aprendizaje**: todo el equipo domina pandas; Spark/Dask/Beam implicarían tiempo de onboarding desproporcionado al valor añadido.

### 4.3 Plan de escalado a Dask (cumple "diseñado para escalar" §4.2)

Si el volumen creciera 10× o 100×, la migración a **Dask DataFrame** sería acotada porque pandas y Dask comparten ~90 % de la API:

| Operación pandas actual | Equivalente Dask |
|---|---|
| `import pandas as pd` | `import dask.dataframe as dd` |
| `pd.read_csv(path)` | `dd.read_csv(path, blocksize="64MB")` |
| `df.groupby('col').agg(...)` | idéntico + `.compute()` al final |
| `df.merge(...)` | idéntico + `.compute()` |
| `df.apply(f, axis=1)` | evitar — sustituir por vectorización o `map_partitions` |

**Cambios esperados**:
- Importaciones y lecturas: 5-10 líneas.
- Añadir `.compute()` en los puntos donde hoy se materializa el resultado (escritura a BD o logs).
- Sustituir 2-3 `apply` por vectorización. Inventario en `DESIGN-02` anexo al arranque de la implementación.
- Sin cambios en reglas de validación (YAML), schemas, endpoints, ni contratos con SDD-03/SDD-08.

**Cómo lo documentaremos en la memoria**: tabla comparativa pandas↔Dask + estimación de tiempo de migración (< 1 día).

## 5. Reglas declarativas de validación (YAML)

### 5.1 Contrato del fichero `config/validation_rules.yaml`

```yaml
version: 1

entities:
  paciente:
    required_fields: [pseudo_id, edad, sexo, motivo_principal]
    field_rules:
      pseudo_id:
        type: string
        pattern: "^PAT-[0-9]{6}$"
      edad:
        type: int
        min: 0
        max: 120
      sexo:
        type: enum
        values: [M, F, Otro]
      peso_kg:
        type: int
        min: 1
        max: 500
        nullable: true
      altura_cm:
        type: int
        min: 40
        max: 250
        nullable: true
      fumador:
        type: enum
        values: [no, si, exfumador]
        nullable: true
      embarazo:
        type: enum
        values: [si, no, na]
        nullable: true
      motivo_principal:
        type: enum
        values: [dolor_toracico, dificultad_respiratoria, fiebre, dolor_abdominal,
                 traumatismo, sintomas_neurologicos, otro]
      hora_envio:
        type: int
        min: 0
        max: 23
    cross_field_rules:
      - rule: "sexo != 'F' implies embarazo in ('na', null)"
        severity: warning      # no invalida, solo anota evento
    deduplication:
      key: pseudo_id
      policy: first_wins

  radiografia:
    required_fields: [filename, hash_sha256, size_bytes]
    field_rules:
      filename:
        type: string
        pattern: "^.+\\.(jpg|jpeg|png)$"
        case_insensitive: true
      size_bytes:
        type: int
        min: 1
        max: 10485760     # 10 MB (SDD-01 RNF-16)
      hash_sha256:
        type: string
        pattern: "^[a-f0-9]{64}$"
    deduplication:
      key: hash_sha256
      policy: first_wins
```

### 5.2 Validación del YAML al arranque

Un pequeño modelo Pydantic (`app/phases/validation.py`) valida la estructura del YAML al cargarlo. Si el YAML es incorrecto, el pipeline **aborta con error claro** antes de procesar una sola fila. Evita errores silenciosos en runtime.

### 5.3 Semántica de cada tipo de regla

- **`required_fields`**: si falta cualquiera → registro inválido, motivo `"missing_field:<name>"`.
- **`field_rules.type`**: `int | float | string | enum | bool | date | datetime`.
- **`field_rules.min/max`**: rango numérico o lexicográfico.
- **`field_rules.pattern`**: regex (Python `re.fullmatch`).
- **`field_rules.values`**: dominio cerrado para enums.
- **`field_rules.nullable`**: default `false`. Si `true`, `None`/`NaN` pasa sin fallo.
- **`cross_field_rules`**: expresiones Python evaluadas con `eval` sobre el registro (**sandboxed**: solo accede al dict del registro). Severidad `error` o `warning`.
- **`deduplication.policy`**: `first_wins` (decisión de §2) o `last_wins` o `error`.

### 5.4 Salidas de la fase de validación

`validate(df, rules) -> (valid_df, rejects_df)` devuelve dos `DataFrame`s:
- **`valid_df`**: registros que pasaron todas las reglas `error`.
- **`rejects_df`**: con columnas adicionales `reject_reason`, `rule_violated`, `severity`, `correlation_id`, `ingested_at`. Se vuelca en la colección `ingestion_rejects` de Mongo (SDD-03).

## 6. Fase 1 — Ingestión

### 6.1 Interfaz `RawSource` (abstrae local FS vs S3)

```python
# app/storage/raw_source.py
from typing import Iterator, Protocol

class RawSource(Protocol):
    def list_csvs(self, prefix: str) -> Iterator[str]: ...
    def list_images(self, prefix: str) -> Iterator[str]: ...
    def open(self, path: str) -> BinaryIO: ...  # context manager
    def describe(self, path: str) -> dict:      # size, mtime, source_id
        ...

class LocalFSSource:
    def __init__(self, base_path: str = "/app/data"): ...

class S3Source:
    def __init__(self, bucket: str, endpoint_url: str | None = None,
                 aws_access_key_id: str | None = None,
                 aws_secret_access_key: str | None = None): ...
    # boto3 client con endpoint_url configurable (AWS real o MinIO)
```

Factory: `make_raw_source()` lee env vars y devuelve la implementación adecuada. **Mismo código de negocio para AWS S3 y MinIO**.

### 6.2 Flujo

1. Listar ficheros desde `RawSource` bajo prefijos `clinical/` y `radiographs/`.
2. Por cada fichero: calcular hash SHA-256 sin cargar todo a memoria (stream).
3. Comparar hash contra `ingestion_events` de Mongo. Si existe ya, saltar (RF-16 idempotencia).
4. Para CSVs: `pd.read_csv(stream, dtype=..., encoding='utf-8')`. Si falla encoding, rechazar el fichero completo con motivo.
5. Para imágenes: tras validación de formato, subir a GridFS con `source`, `ingested_at`, `processed_by`, `content_hash`, `patient_pseudo_id` (si se infiere del nombre o queda nulo).
6. Emitir eventos `ingestion.file_processed` con conteos.

## 7. Fase 2 — Validación

Implementada en `app/phases/validation.py`. Usa las reglas del YAML. Devuelve `(valid_df, rejects_df)` según §5.4. El pipeline **no aborta** por filas inválidas — continúa con las válidas y loguea el resumen.

## 8. Fase 3 — Transformación

1. **Generación de `pseudo_id`** si falta (script seed SDD-01 RF-23) o si viene de formulario sin ID (online). Formato: `PAT-000001`, `PAT-000002`, ... con contador persistido en Mongo (`counters` colección) para garantizar unicidad cross-run.
2. **Derivación**: calcular `imc = peso_kg / (altura_cm/100)**2` si ambos presentes. Redondeo a 1 decimal.
3. **Trazabilidad**: añadir columnas `source` (p. ej. `"seed_synthetic"`, `"csv_batch:filename"`, `"formulario_web"`), `ingested_at` (UTC ISO-8601), `processed_by` (`"pipeline-batch"` o `"pipeline-online"`).
4. **Anonimización defensiva** (SDD-02 RF-11): lista negra de columnas (`["nombre", "apellidos", "dni", "nif", "email", "telefono", "direccion"]`). Si aparece alguna, se **omite** y se loguea evento `anonymization.dropped_column`.

## 9. Fase 4 — Carga

### 9.1 PostgreSQL

- Conexión vía SQLAlchemy con pool (`create_engine(..., pool_size=5)`).
- Inserciones con `INSERT ... ON CONFLICT (pseudo_id) DO NOTHING` (política `first_wins`).
- El driver `psycopg2-binary` ya está en `requirements.txt`.

### 9.2 MongoDB y GridFS

- Cliente `pymongo.MongoClient`. GridFS via `gridfs.GridFS(db, collection="radiographs")`.
- Escrituras con `update_one(..., upsert=True)` idempotentes sobre `{hash_sha256: ...}` para radiografías.
- Para colecciones de dominio (`system_events`, `ingestion_rejects`): `insert_many` en lotes de 500.

### 9.3 Transacciones y atomicidad

- PG: lote por transacción (`BEGIN; ... COMMIT;`), rollback ante cualquier fallo del lote.
- Mongo: sin transacciones cross-doc (suficiente para este caso); idempotencia garantizada por claves de deduplicación.

## 10. Fase análisis — Agregados

`app/phases/aggregates.py` produce un documento por día natural en la colección `aggregates_daily` de Mongo:

```json
{
  "_id": "2026-04-21",
  "radiographs_ingested": 123,
  "clinical_records_ingested": 456,
  "rejects_count": 12,
  "predictions_triage_distribution": {"Alta": 30, "Media": 50, "Baja": 40},
  "predictions_radiography_distribution": {"Sana": 80, "Neumonía": 30, "COVID-19": 13},
  "cross_model_agreement": 0.78,
  "generated_at": "2026-04-21T23:59:59Z",
  "pipeline_run_id": "run-20260421-a1b2c3d4"
}
```

Idempotente: `update_one({_id: date}, {$set: {...}}, upsert=True)`.

## 11. Modo online (pipeline en vivo)

`app/online.py` expone una función sincrona que la API importa directamente (SDD-05 RF-2bis → pipeline → ml-triage):

```python
def process_patient_ficha(ficha: dict, correlation_id: str) -> dict:
    """
    Aplica las 4 fases sobre una única ficha:
    1. validar con mismas reglas YAML que batch
    2. transformar (pseudo_id, trazabilidad)
    3. persistir paciente en PG + ingreso en PG
    4. llamar ml-triage:8002/predict (output combinado triaje + sospecha de enfermedad — DESIGN-08b §6)
    5. persistir predicción en predictions_triage de Mongo
    6. devolver resultado (o pending_triage si paso 4 falla)
    """
```

Latencia objetivo end-to-end (SDD-02 RF-29): **< 1 s** sin el modelo, **< 1.5 s** con el modelo (ligado a DESIGN-08 p95 < 200 ms).

### Timeout y fallback

- Llamada al servicio de triaje con `httpx.Client(timeout=2.0)`.
- Si timeout o 5xx: persistir paciente + ingreso, marcar `triage_status = pending_triage` en Mongo, devolver 202 al cliente. Automation (SDD-04) reintentará.

## 12. Orquestación

### 12.1 Sprint 2 — Cron + scripts

- **Batch diario**: entrada en `crontab` del contenedor `automation` (SDD-04):
  ```
  0 0 * * *   docker compose exec pipeline python main.py --mode batch --seed 42
  ```
- **Informe diario** (SDD-04 RF-4) tras el batch:
  ```
  15 0 * * *  docker compose exec automation python main.py --task daily_report
  ```

### 12.2 Futuro (documentar, no implementar ahora)

Migración a **Prefect** con flujos declarativos y UI en `localhost:4200`. Esfuerzo estimado: ~1 día. Beneficio: reintentos automáticos, UI de runs, paralelización. **No se implementa salvo que sobre tiempo.**

## 13. CLI

```
python main.py --mode batch [--only ingestion|validation|transformation|loading|aggregates] [--seed N]
python main.py --mode online   # (no habitual — la API llama a process_patient_ficha directamente)
python main.py --task daily_report
python main.py --version
```

`argparse` con subparsers. Todos los flags pasan por `config.py` que también lee env vars.

## 14. Observabilidad (alineado con SDD-07)

- Todos los logs en JSON a stdout.
- `correlation_id` único por run batch (`run-YYYYMMDD-<hash8>`) o por petición online (heredado de `X-Correlation-ID` de la API).
- Eventos de dominio (SDD-03 RF-10) emitidos a la colección `system_events`: `pipeline.run.start`, `pipeline.phase.start`, `pipeline.phase.end`, `pipeline.file.processed`, `pipeline.run.end`.

## 15. Pruebas y validación (checklist implementable)

### Unitarias

- [ ] Parser YAML rechaza un fichero malformado al arranque.
- [ ] `validate()` separa correctamente registros válidos e inválidos para cada tipo de regla (tipo, min/max, pattern, enum, required, cross_field).
- [ ] `first_wins` dedup funciona: dos filas con mismo `pseudo_id` → una persiste, otra en rechazos.
- [ ] `pseudo_id` generator es reproducible con la misma semilla y contador.
- [ ] Hash SHA-256 de un fichero de 10 MB se calcula en streaming sin superar 50 MB de RSS.

### Integración (con PG y Mongo reales)

- [ ] `python main.py --mode batch --seed 42` procesa un seed sintético de 10 000 filas + 10 imágenes en < 10 min. Deja los conteos esperados.
- [ ] Rerun idempotente: segunda ejecución produce `0 nuevos, N ya presentes`.
- [ ] `--only ingestion` seguido de `--only validation` da mismo estado que `batch` completo.
- [ ] Modo online: una ficha válida se persiste y su predicción aparece en `predictions_triage`.
- [ ] Modo online con `ml-triage` caído: paciente queda `pending_triage`; al rearrancar, automation completa.

### Criterios de aceptación SDD-02 cubiertos

Mapeo CA → test:

- CA-1: integración "procesa seed".
- CA-4, CA-5: unitarias de validación.
- CA-8: anonimización defensiva (lista negra de columnas).
- CA-11, CA-12: integración idempotencia.
- CA-14: el propio `DESIGN-02` es el documento de RF-18.

## 16. Requirements (pinneados)

`services/pipeline/requirements.txt`:

```
pandas==2.2.3
numpy==2.1.1
SQLAlchemy==2.0.35
psycopg2-binary==2.9.9
pymongo==4.10.1
PyYAML==6.0.2
pydantic==2.9.2
pydantic-settings==2.6.0
boto3==1.35.36
httpx==0.27.2
tenacity==9.0.0
loguru==0.7.2
```

## 17. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Decisión S3 vs MinIO se retrasa y bloquea la ingesta real | `LocalFSSource` es suficiente para Sprint 2; se puede probar todo el pipeline con `./data/` sin bucket. La abstracción `RawSource` permite cambiar después sin tocar lógica. |
| `eval` de `cross_field_rules` se usa maliciosamente | Sandbox estricto: solo se expone el dict del registro, sin builtins. Si se considera insuficiente, sustituir por `simpleeval`. |
| Volumen real supera 10 000 filas en demo | Ajustar test; plan de escalado a Dask ya documentado (§4.3). |
| Pipeline tarda > 10 min en alguna corrida | Perfilar fase por fase; la mayoría del coste suele ser I/O, no CPU. |

## 18. Referencias

- Spec base: [`SDD-02-pipeline.md`](SDD-02-pipeline.md)
- Spec raíz: [`SDD-01-sistema.md`](SDD-01-sistema.md)
- Spec almacenamiento: [`SDD-03-almacenamiento.md`](SDD-03-almacenamiento.md) (destino de la carga)
- Spec modelo triaje: [`SDD-08-modelo-triaje.md`](SDD-08-modelo-triaje.md) y [`DESIGN-08-modelo-triaje.md`](DESIGN-08-modelo-triaje.md) (consumidor en modo online)
- Spec API: [`SDD-05-api-dashboard.md`](SDD-05-api-dashboard.md) (invoca `process_patient_ficha` en modo online)
- Spec automation: [`SDD-04-automatizacion.md`](SDD-04-automatizacion.md) (dispara el batch vía cron)
- Spec monitorización: [`SDD-07-monitorizacion.md`](SDD-07-monitorizacion.md) (formato de logs)
- Memoria del profesor autorizando pandas: `project_pandas_autorizado.md` en memoria persistente
- [pandas docs](https://pandas.pydata.org/docs/) · [Dask DataFrame API](https://docs.dask.org/en/stable/dataframe-api.html) · [PyYAML](https://pyyaml.org/wiki/PyYAMLDocumentation) · [boto3 S3](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html)
