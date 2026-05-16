# DESIGN-03 — Almacenamiento: diseño técnico

> Diseño de implementación del subsistema de persistencia especificado en [`SDD-03-almacenamiento.md`](SDD-03-almacenamiento.md). Complementa el DDL ya existente en `init/postgres/init.sql` y `init/mongo/init.js` con los esquemas concretos de cada colección Mongo, el formato de `pseudo_id`, la estrategia de reconciliación PG↔Mongo y los índices por consulta típica.

---

**Versión:** 1.0
**Fecha:** 2026-04-21
**Autor:** Pol Ballarín
**Estado:** `ready-for-implementation`

---

## 1. Contexto

Spec base: SDD-03 — persistencia en **PostgreSQL** (estructurados) + **MongoDB con GridFS** (no estructurados y semiestructurados). El DDL de PG y los scripts de inicialización de Mongo ya están en `init/postgres/init.sql` e `init/mongo/init.js` (commit `c64a0f4`, anonimizados por diseño).

Este DESIGN cierra **2 de las 4 dudas** de SDD-03 §7 y documenta el esquema detallado de cada colección Mongo.

## 2. Decisiones cerradas

| Duda de SDD-03 §7 | Decisión |
|---|---|
| Formato `pseudo_id` | **`PAT-NNNNNN`** (string, prefijo `PAT-` + 6 dígitos con zero-padding). Legible en logs, ordenable, 7 bytes vs 16 de un UUID binario. Contador persistido en colección Mongo `counters` para unicidad cross-run. |
| Estrategia de reconciliación `awaiting_patient_sync` | **Doble vía**: (a) **job periódico** en `automation` (cada 60 s) que recorre docs marcados y reintenta enlace; (b) **check lazy** al leer un doc con ese flag desde la API (si el paciente ya existe en PG, limpiar flag en caliente). Detalle completo en `DESIGN-04-automatizacion.md` cuando se escriba. |
| Umbrales concretos de rendimiento (RNF-1, RNF-2) | Sigue `[NEEDS CLARIFICATION]` — se fijan tras la primera medición real del dashboard sobre una base poblada (fin Sprint 2). |
| Tamaño del subset del dataset (RNF-6) | Sigue `[NEEDS CLARIFICATION]` — se decide en `DESIGN-06-modelo-dl.md` cuando se escriba. |

**Pendiente externo** (no de SDD-03): decisión S3 vs MinIO para la capa raw. La colección `radiographs` (GridFS) sigue siendo el destino **canónico** de los bytes de imagen en ambos casos — si S3 entra, se usa como **landing zone** previo a la ingesta; no sustituye a GridFS.

## 3. PostgreSQL — schema

### 3.1 Referencia al DDL existente

El esquema vive en `init/postgres/init.sql` (commit `c64a0f4`, anonimizado). Cubre:

- `pacientes (pseudo_id TEXT PK, edad, sexo, peso_kg, altura_cm, fumador, embarazo, enfermedades_cronicas TEXT[], source, ingested_at, processed_by, created_at)`
- `ingresos (id SERIAL PK, paciente_pseudo_id FK, fecha_ingreso, motivo, motivo_principal, duracion_sintomas, intensidad_dolor, fiebre_subjetiva, dificultad_respiratoria_subjetiva, tos, contacto_covid_reciente, hora_envio, source, ingested_at, processed_by)`

### 3.2 Índices adicionales (sobre el init.sql actual)

El init ya crea tres índices. Añadiremos con migración manual en Sprint 2 si los tiempos de consulta lo exigen:

| Índice | Motivación |
|---|---|
| `ix_pacientes_edad_sexo` sobre `pacientes(edad, sexo)` | Filtros del listado de pacientes (SDD-05 RF-1) |
| `ix_ingresos_motivo_principal` sobre `ingresos(motivo_principal)` | Dashboards agregados por motivo |
| `ix_ingresos_rango_fecha` sobre `ingresos(fecha_ingreso DESC, paciente_pseudo_id)` | Composite para listados paginados por fecha |

Creados solo si los tiempos de consulta superan el umbral — principio "no optimizar sin medir".

### 3.3 Vista materializada (opcional, Sprint 3)

```sql
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_pacientes_con_ultimo_ingreso AS
SELECT p.pseudo_id,
       p.edad,
       p.sexo,
       p.enfermedades_cronicas,
       i.fecha_ingreso AS ultimo_ingreso,
       i.motivo_principal AS ultimo_motivo
FROM   pacientes p
LEFT JOIN LATERAL (
  SELECT * FROM ingresos
  WHERE  paciente_pseudo_id = p.pseudo_id
  ORDER  BY fecha_ingreso DESC
  LIMIT  1
) i ON true;
```

Se refresca tras el informe diario (SDD-04 RF-5) si acelera el dashboard. No es obligatoria en Sprint 2.

## 4. MongoDB — schemas de colecciones

> Mongo no impone schema, pero documentamos el **contrato** de cada colección con ejemplo, tipos y campos obligatorios. Los servicios escritores respetan este contrato; la capa de lectura tolera campos extras (evolución hacia adelante).

### 4.1 `radiographs.files` / `radiographs.chunks` (GridFS)

**Propósito**: bytes de cada radiografía JPG/PNG (SDD-03 RF-2).

**Ejemplo de documento en `radiographs.files`**:

```json
{
  "_id": ObjectId("6625aa..."),
  "filename": "PAT-000042_1.jpg",
  "length": 523412,
  "chunkSize": 261120,
  "uploadDate": ISODate("2026-04-21T10:12:34Z"),
  "metadata": {
    "content_hash": "d7f9c3...64hex",
    "patient_pseudo_id": "PAT-000042",
    "admission_id": 17,
    "content_type": "image/jpeg",
    "source": "kaggle_covid_radiography",
    "ingested_at": ISODate("2026-04-21T10:12:34Z"),
    "processed_by": "pipeline-batch:run-20260421-a1b2c3d4",
    "width_px": 1024,
    "height_px": 1024
  }
}
```

**Índices** (ya en init.js):
- `filename: 1`
- `{files_id: 1, n: 1}` UNIQUE (en chunks, obligatorio para GridFS)

**Índice adicional** (añadir en migración Sprint 2):
- `"metadata.content_hash": 1` UNIQUE — **deduplicación por hash** (RF-4 de SDD-01, RF-12 de SDD-03).
- `"metadata.patient_pseudo_id": 1` — lookup por paciente.

### 4.2 `predictions_radiography`

**Propósito**: predicción del modelo DL de radiografías (SDD-06) sobre una imagen de `radiographs`.

```json
{
  "_id": ObjectId("..."),
  "radiograph_id": ObjectId("6625aa..."),        // ref a radiographs.files._id
  "patient_pseudo_id": "PAT-000042",
  "predicted_class": "Neumonía",
  "probabilities": {
    "sana": 0.12,
    "neumonia": 0.71,
    "covid": 0.17
  },
  "model_version": "rx-20260425-9f8e7d6c",
  "inference_time_ms": 340,
  "low_confidence": false,                        // si max(probs) < umbral (DESIGN-06)
  "source": "ml-inference",
  "ingested_at": ISODate("2026-04-25T08:45:11Z"),
  "processed_by": "ml-inference:rx-20260425-9f8e7d6c",
  "correlation_id": "req-abc123"
}
```

**Campos obligatorios**: `radiograph_id`, `predicted_class`, `probabilities` (3 keys, floats en [0,1] que suman 1±1e-6), `model_version`, `source`, `ingested_at`, `processed_by`.

**Índices** (ya en init.js): `radiograph_id`, `patient_pseudo_id`, `created_at` (renombrar a `ingested_at` para coherencia), `model_version`.

### 4.3 `predictions_triage`

**Propósito**: predicción del modelo tabular de triaje (SDD-08) sobre una ficha de paciente/ingreso.

```json
{
  "_id": ObjectId("..."),
  "patient_pseudo_id": "PAT-000042",
  "admission_id": 17,                              // FK lógica a PG.ingresos.id
  "ficha_snapshot": {                              // copia exacta del input (SDD-08 RF-14, auditable)
    "edad": 67,
    "sexo": "M",
    "peso_kg": 82,
    "altura_cm": 172,
    "enfermedades_cronicas": ["hipertension", "cardiopatia"],
    "fumador": "exfumador",
    "embarazo": "na",
    "motivo_principal": "dolor_toracico",
    "duracion_sintomas": "<24h",
    "intensidad_dolor": 9,
    "fiebre_subjetiva": "no",
    "dificultad_respiratoria_subjetiva": "leve",
    "tos": "no",
    "contacto_covid_reciente": "no",
    "hora_envio": 14
  },
  "predicted_class": "Alta",
  "probabilities": { "alta": 0.78, "media": 0.18, "baja": 0.04 },
  "model_version": "tri-20260421-a1b2c3d4",
  "inference_time_ms": 42,
  "low_confidence": false,
  "triage_status": "completed",                    // "completed" | "pending_triage" | "prediction_failed"
  "source": "formulario_web",
  "ingested_at": ISODate("2026-04-21T14:02:05Z"),
  "processed_by": "pipeline-online",
  "correlation_id": "req-xyz789"
}
```

**Campos obligatorios**: `patient_pseudo_id`, `predicted_class`, `probabilities`, `model_version`, `triage_status`, `source`, `ingested_at`, `processed_by`.

**Por qué incluir `ficha_snapshot`**: permite auditar **exactamente** qué entrada produjo qué predicción, incluso si luego cambian los campos del paciente/ingreso en PG (p. ej. corrección manual). Coste en almacenamiento despreciable (< 1 KB por doc).

**Índices** (ya en init.js): `patient_pseudo_id`, `created_at`→renombrar a `ingested_at`, `model_version`.

**Índice adicional**:
- `"triage_status": 1` — permite listar pendientes de reconciliación en O(log n).

### 4.4 `reports`

**Propósito**: informe diario generado automáticamente por SDD-04 (PDF binario en GridFS + JSON inline).

```json
{
  "_id": "2026-04-21",                             // fecha del día natural como PK (SDD-04 RF-7 idempotencia)
  "report_date": ISODate("2026-04-21T00:00:00Z"),
  "generated_at": ISODate("2026-04-21T23:59:45Z"),
  "pipeline_run_id": "run-20260421-a1b2c3d4",
  "pdf_file_id": ObjectId("..."),                  // ref a radiographs.files (o colección reports_pdf dedicada)
  "json_summary": {
    "radiographs_ingested": 123,
    "clinical_records_ingested": 456,
    "rejects_count": 12,
    "predictions_triage_distribution": { "Alta": 30, "Media": 50, "Baja": 40 },
    "predictions_radiography_distribution": { "Sana": 80, "Neumonía": 30, "COVID-19": 13 },
    "cross_model_agreement": 0.78,
    "alerts_emitted": 4
  },
  "version": 1                                     // incrementable si se regenera
}
```

> **Nota**: el PDF vive en GridFS en su propio bucket `reports_pdf` (no reutilizamos `radiographs`). Añadir al `init.js` la creación del bucket.

**Índice** (ya en init.js): `report_date: -1` UNIQUE.

### 4.5 `alerts`

**Propósito**: alertas clínicas (SDD-04 RF-8) y operativas (SDD-07 RF-13).

```json
{
  "_id": ObjectId("..."),
  "type": "covid_high_confidence",                 // ej. 'covid_high_confidence', 'ml_inference_unhealthy', 'high_reject_rate'
  "severity": "clinical",                          // 'clinical' | 'operational'
  "message": "Radiografía PAT-000042 con P(COVID-19)=0.94",
  "correlation_id": "req-abc123",
  "correlated_ids": {                              // referencias flexibles
    "patient_pseudo_id": "PAT-000042",
    "radiograph_id": ObjectId("6625aa..."),
    "prediction_id": ObjectId("...")
  },
  "emitted_at": ISODate("2026-04-25T08:45:12Z"),
  "status": "new",                                 // 'new' | 'seen' | 'resolved'
  "dedup_key": "covid_high_confidence:PAT-000042:2026-04-25",
  "source": "automation",
  "processed_by": "automation:daemon"
}
```

**Índices** (ya en init.js): `emitted_at: -1`, `{type, correlation_id}`, `{severity, status}`.

**Índice adicional**:
- `dedup_key: 1` UNIQUE — clave lógica para deduplicación (SDD-04 RF-14). `update_one(upsert=True)` sobre esta clave garantiza que una misma alerta no se duplique en la ventana temporal.

### 4.6 `system_events`

**Propósito**: eventos de dominio para auditoría (SDD-03 RF-10). **No es logging técnico** (eso va a stdout + Loki, SDD-07).

```json
{
  "_id": ObjectId("..."),
  "timestamp": ISODate("2026-04-21T14:02:05Z"),
  "service": "pipeline",                           // pipeline | api | ml-inference | ml-triage | automation
  "event": "pipeline.run.end",
  "level": "info",                                 // info | warning | error
  "correlation_id": "run-20260421-a1b2c3d4",
  "payload": {
    "files_processed": 10,
    "records_valid": 9500,
    "records_rejected": 500,
    "duration_ms": 583000
  }
}
```

**Índices** (ya en init.js): `timestamp: -1`, `correlation_id`, `{service, event}`.

**Retención**: por ahora **indefinida** (SDD-01 decisión cerrada). Si crece demasiado, TTL index sobre `timestamp` a 90 días como mejora futura.

### 4.7 `ingestion_rejects`

**Propósito**: registros rechazados por la fase de validación del pipeline (SDD-02 RF-6).

```json
{
  "_id": ObjectId("..."),
  "entity": "paciente",                             // 'paciente' | 'ingreso' | 'radiografia'
  "source_file": "s3://raw/clinical/2026-04-21.csv",
  "row_index": 347,
  "raw_record": { /* el registro original íntegro */ },
  "reject_reason": "missing_field:sexo",
  "rule_violated": "paciente.required_fields",
  "severity": "error",                              // 'error' | 'warning'
  "correlation_id": "run-20260421-a1b2c3d4",
  "ingested_at": ISODate("2026-04-21T10:12:35Z"),
  "processed_by": "pipeline-batch"
}
```

**Índices** (ya en init.js): `ingested_at: -1`, `source: 1`→renombrar a `source_file`.

**Índice adicional**:
- `{entity: 1, rule_violated: 1}` — para el resumen de calidad de datos (SDD-07 RF-12).

### 4.8 `counters`

**Propósito**: contadores monotónicos para generar `pseudo_id` de forma reproducible cross-run (ver §5).

```json
{
  "_id": "patient_pseudo_id",
  "seq": 10042,
  "updated_at": ISODate("2026-04-21T14:02:05Z")
}
```

Solo 1-2 documentos (uno por contador). `findOneAndUpdate({_id}, {$inc: {seq: 1}}, returnNewDocument=True)` es **atómico** a nivel de documento en Mongo, seguro sin transacciones.

## 5. Formato y generación de `pseudo_id`

**Formato**: `PAT-` + 6 dígitos con zero-padding → `PAT-000001`, `PAT-000042`, `PAT-999999`.

**Rango**: 999 999 pacientes máximo. Suficiente para el proyecto; si algún día se superara, ampliar a 7 dígitos en migración.

**Generación**:

```python
# app/utils/pseudo_id.py
from pymongo.collection import Collection

def next_pseudo_id(counters: Collection) -> str:
    doc = counters.find_one_and_update(
        {"_id": "patient_pseudo_id"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True,
    )
    return f"PAT-{doc['seq']:06d}"
```

**Semilla del script sintético** (SDD-01 RF-23): el script inicializa el contador a 0 antes de generar pacientes y usa el mismo mecanismo, obteniendo `PAT-000001`, `PAT-000002`, etc. de forma **reproducible** si se parte de BD vacía con la misma semilla.

**Unicidad cross-run**: garantizada por el `$inc` atómico — nunca se asigna dos veces el mismo `pseudo_id` aunque varios procesos pidan simultáneamente.

## 6. Reconciliación PG↔Mongo

### 6.1 Escenario a cubrir

Documento en Mongo (típicamente `predictions_triage` o `predictions_radiography`) con `patient_pseudo_id` que **aún no existe** en PG.

Causas posibles:
- Ingesta online: por un fallo transitorio el paciente no llegó a PG pero la predicción se escribió en Mongo.
- Batch: desorden de orden de escritura entre pipeline y servicios consumidores.

Flag documentado: campo `reconciliation_status: "awaiting_patient_sync"` en el doc.

### 6.2 Estrategia — Doble vía

**Vía A — Job periódico (automation)**: cada 60 segundos, `automation` recorre los docs con `reconciliation_status = "awaiting_patient_sync"` (índice sobre ese campo). Para cada uno:
1. Verifica con `SELECT 1 FROM pacientes WHERE pseudo_id = %s` si existe.
2. Si existe → `update_one({_id}, {$unset: {reconciliation_status: ""}, $set: {reconciled_at: ISODate(...)}})`.
3. Si no existe y han pasado > **24 h** desde `ingested_at` → emitir alerta operativa `orphan_record_stale` (SDD-04 caso borde).
4. Si no existe y < 24 h → dejar para la próxima iteración.

**Vía B — Check lazy al leer**: cuando la API devuelve un doc con `reconciliation_status` activo, comprueba PG. Si ya existe, limpia el flag en caliente antes de responder. Oportunista, no reemplaza la Vía A.

### 6.3 Umbral de "huérfano viejo"

**24 horas** por defecto, configurable vía env var `RECONCILIATION_STALE_HOURS`. Corresponde al `[NEEDS CLARIFICATION]` de SDD-04 caso borde "orphan_record_stale".

## 7. Transacciones e idempotencia

### 7.1 Operaciones idempotentes por construcción

| Operación | Implementación | Garantía |
|---|---|---|
| Insertar paciente | `INSERT ... ON CONFLICT (pseudo_id) DO NOTHING` | Reejecutar no duplica |
| Insertar radiografía | `update_one({metadata.content_hash}, {...}, upsert=True)` | Hash único garantiza unicidad |
| Insertar predicción | `insert_one(...)` versionada por `model_version` | Historial explícito, no upsert |
| Insertar alerta | `update_one({dedup_key}, {...}, upsert=True)` | Dedup por clave lógica |
| Informe diario | `update_one({_id: date}, {...}, upsert=True)` | Un informe por día natural |
| Seed sintético | contador `counters` + `INSERT ... ON CONFLICT` | Rerun produce mismo estado |

### 7.2 Transacciones PG multi-fila

Para lotes del pipeline:

```python
with engine.begin() as conn:          # transacción: BEGIN ... COMMIT/ROLLBACK
    conn.execute(insert_pacientes, rows_pacientes)
    conn.execute(insert_ingresos, rows_ingresos)
```

Si cualquier inserción falla, todo el lote se revierte. El pipeline registra el fallo y reintenta (tenacity + backoff). En Mongo no se usan transacciones multi-doc; idempotencia por claves lógicas.

## 8. Credenciales y conexión

Los servicios aplicativos se conectan con el **usuario root del compose** en Sprint 2 (aceptado por SDD-03 RF-17 como desviación de demo local).

Como mejora futura (Sprint 3 si hay tiempo):

- Crear usuarios de aplicación en el init: `CREATE USER app_pipeline ...`, `CREATE USER app_api ...` con permisos mínimos (`GRANT SELECT, INSERT ON ... TO app_pipeline;`).
- Similar en Mongo (init.js ya crea `appuser` con `readWrite`, que se puede reutilizar).

Variables de conexión en `.env.example`:
- `POSTGRES_HOST=postgres`, `POSTGRES_PORT=5432`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`
- `MONGO_HOST=mongodb`, `MONGO_PORT=27017`, `MONGO_INITDB_ROOT_USERNAME`, `MONGO_INITDB_ROOT_PASSWORD`, `MONGO_DB`, `MONGO_GRIDFS_BUCKET`

Los clientes (`services/pipeline/app/storage/postgres.py` y `mongo.py`) construyen las URIs desde estas vars, sin strings hardcodeados.

## 9. Performance y tuning (primer pase)

### 9.1 PostgreSQL

- `shared_buffers`: default de la imagen `postgres:16-alpine` (~128 MB).
- `work_mem`: default. Si el dashboard hace aggregations pesadas, subir a 16 MB vía `docker-compose.yml`.
- **Connection pooling**: SQLAlchemy `pool_size=5`, `max_overflow=10`. Suficiente para 3 servicios concurrentes.
- `EXPLAIN ANALYZE` sobre las queries del dashboard si alguna supera 1 s.

### 9.2 MongoDB

- `wiredTiger.cacheSizeGB`: default 50 % de RAM del contenedor. Sin cambio para demo.
- GridFS: chunks de 256 KB (default) — adecuado para imágenes de ~1 MB.
- Proyección explícita en lecturas (`find(query, {metadata: 1, _id: 1})`) para no traer los bytes innecesariamente.

### 9.3 Sin optimizar prematuramente

No se añaden índices ni tuning **hasta que una medición** (EXPLAIN, `db.currentOp()`, profiler de Mongo) demuestre necesidad.

## 10. Pruebas y validación

### Unitarias

- [ ] `next_pseudo_id()` devuelve `PAT-000001, PAT-000002, ...` secuencialmente. Con el contador reseteado a 0, dos llamadas en paralelo nunca devuelven el mismo id (verificar con `concurrent.futures`).
- [ ] `INSERT ... ON CONFLICT DO NOTHING` no falla al reejecutar con misma clave.
- [ ] GridFS guarda y recupera una imagen JPG **byte-idéntica** (hash SHA-256 en origen == en recuperación).

### Integración (testcontainers o servicios ya levantados)

- [ ] Toda colección de Mongo declarada en init.js existe tras arrancar.
- [ ] Todos los índices declarados existen (`db.<coll>.getIndexes()`).
- [ ] Una predicción con `patient_pseudo_id` inexistente en PG se persiste con `reconciliation_status: "awaiting_patient_sync"`. Tras crear el paciente, la vía B (check lazy al leer) limpia el flag.
- [ ] Dos inserciones de alerta con mismo `dedup_key` → un solo doc persistido (UNIQUE en `dedup_key`).

### Criterios de aceptación SDD-03 cubiertos

Mapeo CA → test:

- CA-3, CA-4: colecciones y tablas existentes tras init.
- CA-9, CA-10: tests de GridFS (byte-identidad + dedup por hash).
- CA-12, CA-13: referencias cruzadas PG↔Mongo (verifican vía join lógico).
- CA-14: test FK paciente inexistente.
- CA-15, CA-22: muestreos aleatorios de campos de trazabilidad.
- CA-17: versionado de predicciones.
- CA-18: regex sobre columnas de PG — sin datos personales.
- CA-20: búsqueda en repo — sin credenciales.

## 11. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Alguna colección Mongo se pobla sin los campos de trazabilidad | Validación en capa de escritura (helper `mongo_write(doc)` que rechaza docs sin `source/ingested_at/processed_by`). |
| `counters` se corrompe y `pseudo_id` deja de ser único | `find_one_and_update($inc)` es atómico por doc en Mongo. Sin TTL, sin replicación cruzada. Seguro mono-instancia. |
| GridFS crece sin límite | Monitorizar tamaño de `radiographs.files` + `.chunks`. Retención indefinida por decisión de SDD-01. Si supera X GB, purga manual de radiografías > N meses — fuera de alcance para Sprint 2. |
| Reconciliación nunca se ejecuta porque `automation` está caído | Vía B (check lazy al leer) cubre parcialmente. Alerta operativa si `automation` lleva > 5 min unhealthy (SDD-07). |

## 12. Referencias

- Spec base: [`SDD-03-almacenamiento.md`](SDD-03-almacenamiento.md)
- Spec raíz: [`SDD-01-sistema.md`](SDD-01-sistema.md)
- DDL PostgreSQL: [`../init/postgres/init.sql`](../init/postgres/init.sql)
- Init Mongo: [`../init/mongo/init.js`](../init/mongo/init.js)
- Pipeline consumidor: [`DESIGN-02-pipeline.md`](DESIGN-02-pipeline.md)
- Modelo triaje (predictions_triage): [`DESIGN-08-modelo-triaje.md`](DESIGN-08-modelo-triaje.md)
- Modelo DL radiografías (predictions_radiography): pendiente [`DESIGN-06-modelo-dl.md`](DESIGN-06-modelo-dl.md)
- Automatización (reconciliación, informes, alertas): pendiente [`DESIGN-04-automatizacion.md`](DESIGN-04-automatizacion.md)
- Monitorización (eventos de dominio vs logs técnicos): [`SDD-07-monitorizacion.md`](SDD-07-monitorizacion.md)
- [PostgreSQL 16 docs](https://www.postgresql.org/docs/16/) · [MongoDB 7 manual](https://www.mongodb.com/docs/manual/) · [GridFS](https://www.mongodb.com/docs/manual/core/gridfs/)
