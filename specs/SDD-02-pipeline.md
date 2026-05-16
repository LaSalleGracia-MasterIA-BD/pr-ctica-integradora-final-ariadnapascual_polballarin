# SDD-02 — Pipeline de datos (ingesta → limpieza → transformación → análisis)

> Spec del subsistema de **procesamiento de datos** del Sistema de Soporte Hospitalario. Define **qué transforma el pipeline, con qué garantías de calidad y reproducibilidad**. El esquema interno, módulos Python y orquestación detallada van en `DESIGN-02-pipeline.md`.

---

**Versión:** 1.0
**Fecha:** 2026-04-20
**Autor:** Pol Ballarín
**Estado:** `ready-for-design`

---

## 1. Contexto y objetivo

### Contexto
El enunciado §4.2 exige un pipeline con cuatro fases — **ingesta, limpieza, transformación, análisis** — diseñado para escalar aunque el volumen sea simulado. El sistema ingiere dos fuentes heterogéneas: (i) **radiografías reales** del dataset público *COVID-19 Radiography Database*, y (ii) **datos clínicos sintéticos** generados por el script de RF-23 (SDD-01).

Para el procesamiento tabular se utiliza **pandas**, expresamente autorizado por el profesor en sustitución de los frameworks distribuidos listados en §4.2.3 (Spark, Dask, Beam). La decisión se justifica por el volumen simulado manejable en memoria, la simplicidad operativa y la integración directa con PyTorch (SDD-06).

### Objetivo
Proveer un pipeline **reproducible, trazable e idempotente** que opere en **dos modos complementarios**:

- **Modo batch**: procesa CSVs y lotes de radiografías en jobs programados o ejecutados a mano.
- **Modo online**: procesa **una única ficha de paciente** procedente del formulario web (SDD-05 RF nuevo de formulario) en tiempo real, con las mismas reglas de validación que el modo batch pero pensado para latencia baja, y termina invocando al modelo de triaje (SDD-08) para dejar la predicción persistida antes de responder al usuario.

En ambos modos debe:

1. **Ingerir** los datos crudos (radiografías del dataset + CSVs clínicos sintéticos en batch; ficha JSON en online), depositándolos en zonas controladas del sistema de almacenamiento.
2. **Limpiar y validar** cada registro aplicando reglas de calidad de datos (campos obligatorios, formatos, rangos), separando válidos e inválidos.
3. **Transformar** los datos limpios al modelo lógico definido en SDD-03 (pseudo-IDs, campos de trazabilidad, relaciones cruzadas PG↔Mongo, derivados como IMC).
4. **Analizar** agregados diarios (conteos, distribuciones por clase de triaje y de radiografía, tasa de rechazos) para alimentar el dashboard y los informes automáticos.
5. En **modo online**, al final del flujo, **invocar el servicio de triaje** (SDD-08) con la ficha transformada y persistir la predicción resultante, dejando al paciente con su nivel de triaje antes de que la API devuelva la respuesta al formulario.
6. **Justificar técnicamente** la elección de pandas y describir un plan de escalado a Dask manteniendo API equivalente (cumpliendo la parte "diseñado para escalar" del enunciado).

## 2. Actores y alcance

### Actores

| Actor | Dirección | Rol |
|-------|-----------|-----|
| **Dataset externo** *(COVID-19 Radiography Database)* | lectura | Fuente de imágenes de radiografía, se monta como volumen en `./data/raw/` |
| **Script de datos sintéticos** *(RF-23 SDD-01)* | lectura | Produce CSVs con pacientes/ingresos/eventos clínicos sintéticos |
| **PostgreSQL** *(SDD-03)* | escritura | Destino de datos clínicos estructurados |
| **MongoDB + GridFS** *(SDD-03)* | escritura | Destino de radiografías, rechazos de ingesta, agregados |
| **Servicio de inferencia** *(SDD-06)* | lectura | Consume radiografías ingeridas para predecir (desacoplado del pipeline) |
| **API / Dashboard** *(SDD-05)* | lectura | Consulta los datos resultantes |
| **Servicio de automatización** *(SDD-04)* | disparo | Puede disparar el pipeline o fases concretas |

### Dentro del alcance

- Las cuatro fases del pipeline en **modo batch** (ingesta, limpieza, transformación, análisis).
- **Modo online**: versión ligera del mismo flujo sobre una única ficha del formulario, terminando con invocación al modelo de triaje (SDD-08) y persistencia de la predicción.
- Reglas de validación y limpieza de datos clínicos (campos obligatorios, rangos válidos, deduplicación), **compartidas entre batch y online**.
- Preprocesado mínimo de radiografías para ingesta (validación de formato, cálculo de hash, extracción de metadatos). **No** incluye el preprocesado específico para el modelo DL — eso va en SDD-06.
- Cálculo de métricas agregadas diarias (conteos, distribuciones, tasa de rechazos, volumen ingerido, distribución de niveles de triaje, correlación entre triaje predicho y clase de radiografía si aplica).
- Justificación técnica del uso de pandas y plan de escalado teórico a Dask.
- Reproducibilidad end-to-end: con las mismas fuentes y semilla, el pipeline en modo batch produce el mismo estado final.
- Idempotencia: reejecutar el pipeline sobre datos ya cargados no los duplica ni corrompe.

### Fuera del alcance

- **Entrenamiento del modelo DL** (pertenece a SDD-06).
- **Predicción de radiografías** (el modelo, al que el pipeline no invoca directamente; lo dispara automation SDD-04).
- **Orquestación detallada** (cron, Prefect, Airflow): decisión diferida a SDD-04 y a `DESIGN-02`.
- **Streaming real-time**: el pipeline es **batch**. El streaming queda fuera del alcance.
- **Data lineage visual** con herramientas especializadas (DataHub, OpenLineage): basta con los campos de trazabilidad de SDD-03 RF-9.
- **Backfills complejos** con corrección histórica retroactiva.

## 3. Requisitos funcionales

### Fase 1 — Ingesta

- **RF-1**: El pipeline debe leer **CSVs clínicos** depositados en un directorio de entrada acordado (montado como volumen), con esquema definido (pacientes, ingresos, eventos, personal).
- **RF-2**: El pipeline debe leer **radiografías** (JPG/PNG) depositadas en un directorio de entrada acordado, o directamente del bucket de GridFS si la ingesta viene por el watcher de SDD-04.
- **RF-3**: Cada fichero o imagen ingerida debe quedar **catalogada** con metadatos de origen: ruta fuente, timestamp de detección, tamaño, hash de contenido.
- **RF-4**: La ingesta debe **no perder datos** ante fallos: un fichero procesado parcialmente queda marcado como pendiente para reintento, no se descarta.

### Fase 2 — Limpieza y validación

- **RF-5**: El pipeline debe aplicar reglas de validación a cada registro clínico: **campos obligatorios presentes**, **tipos correctos**, **valores dentro de rangos válidos** (p. ej. edad entre 0 y 120, sexo en dominio cerrado), **timestamps coherentes**.
- **RF-6**: Los registros que incumplan cualquier regla se marcan como **inválidos** y se persisten en la colección de rechazos (SDD-03 RF-3), junto con el motivo específico. El pipeline **no aborta** por registros inválidos; continúa con el resto.
- **RF-7**: El pipeline debe detectar **duplicados** por clave lógica (p. ej. mismo `pseudo_id` para un paciente, misma combinación `pseudo_id + admission_date` para un ingreso) y tratarlos como rechazo o upsert según política documentada.
- **RF-8**: Para radiografías, la limpieza verifica formato aceptado (JPG/PNG), tamaño dentro de límites (RNF-16 SDD-01) y hash no repetido (deduplicación con GridFS existente — RF-12 SDD-03).

### Fase 3 — Transformación

- **RF-9**: Los datos limpios se transforman al modelo lógico de SDD-03: generación o conservación de `pseudo_id`, enlace entre entidades (paciente ↔ ingreso ↔ evento), cálculo de campos derivados (p. ej. edad a partir de año de nacimiento si fuera el caso).
- **RF-10**: Cada registro transformado recibe los campos de trazabilidad obligatorios (`source`, `ingested_at`, `processed_by`) según SDD-03 RF-9.
- **RF-11**: La transformación respeta la **anonimización por diseño** (SDD-01 RNF-8): si detecta campos que puedan ser identificativos directos, los omite o los enmascara antes de persistir.

### Fase 4 — Análisis y carga

- **RF-12**: El pipeline debe **cargar** los datos estructurados transformados en PostgreSQL y las radiografías con sus metadatos en MongoDB/GridFS, delegando en el subsistema de almacenamiento (SDD-03).
- **RF-13**: El pipeline debe calcular **agregados diarios** y persistirlos en la colección correspondiente de MongoDB (SDD-03): número de radiografías ingeridas por día, distribución por clase predicha (si ya existe predicción), número de registros clínicos cargados, tasa de rechazos por fuente, distribución por franja etaria y sexo.
- **RF-14**: El pipeline debe emitir **eventos de dominio** (SDD-03 RF-10) en cada transición relevante: inicio/fin de fase, fichero procesado, lote cargado, registro rechazado, agregado calculado.

### Reproducibilidad e idempotencia

- **RF-15**: Dadas las mismas fuentes y la misma semilla del generador sintético, **dos ejecuciones sucesivas del pipeline end-to-end producen el mismo estado final** en PostgreSQL y MongoDB (salvo los campos de timestamp de ingesta).
- **RF-16**: El pipeline es **idempotente**: reejecutarlo sobre datos ya cargados (mismas fuentes, mismo hash) no crea duplicados en el destino. La decisión concreta (skip vs upsert) se documenta por tipo de registro.
- **RF-17**: El pipeline debe poder ejecutarse por **fase individual** (`--only ingesta`, `--only limpieza`, etc.) o **end-to-end**, sin que el resultado difiera. Útil para depuración y para reintentos acotados.

### Modo online (ficha del formulario web)

- **RF-24**: El pipeline debe ofrecer un punto de entrada **online** que reciba **una única ficha de paciente** en formato JSON (con los campos definidos en SDD-08 RF-1) y la procese síncronamente.
- **RF-25**: El modo online aplica las **mismas reglas de validación y limpieza** que el modo batch (RF-5) — única fuente de verdad para las reglas. Si la ficha es inválida, devuelve 422 con motivos concretos y no persiste.
- **RF-26**: Tras validar, limpiar y transformar, el modo online **persiste el paciente** en PostgreSQL (delegando en SDD-03) y, a continuación, **invoca el servicio de triaje** (SDD-08 RF-13/RF-14) pasándole la ficha transformada.
- **RF-27**: El modo online persiste la **predicción de triaje** devuelta por SDD-08 como documento en MongoDB ligado al `pseudo_id` del paciente recién creado, consistente con SDD-03 RF-13.
- **RF-28**: Si el servicio de triaje **no responde** o falla, el pipeline online deja al paciente persistido con estado `pending_triage` (consistente con SDD-08 RF-19) y devuelve una respuesta parcial al cliente indicando que el triaje se completará más tarde. Automation (SDD-04) lo reintentará.
- **RF-29**: El modo online debe completarse con latencia baja (ligado a RNF-1 y a SDD-05 RF-5/RNF-2). Si el tiempo se va por encima del presupuesto, se documenta como riesgo y se evalúa desacoplar la predicción de triaje a asíncrono.

### Justificación técnica (entregable)

- **RF-18**: El repositorio debe contener un documento (`DESIGN-02` o equivalente) que **justifique la elección de pandas** frente a Spark/Dask/Beam, incluyendo:
  - Referencia explícita a la autorización del profesor.
  - Argumentos técnicos (volumen simulado, simplicidad, integración con PyTorch).
  - **Plan de escalado a Dask** con API equivalente: qué importaciones cambiarían (`import dask.dataframe as dd`), qué operaciones necesitarían `.compute()`, estimación de coste del cambio.
  - Referencia al requisito del enunciado §4.2.3 y a la sección correspondiente de la memoria técnica.

## 4. Requisitos no funcionales

### Rendimiento

- **RNF-1**: El pipeline debe procesar end-to-end un volumen objetivo de radiografías y registros clínicos en tiempo acotado, en el entorno de desarrollo. **[NEEDS CLARIFICATION]** volumen y tiempo exactos (ligados a SDD-01 RNF-3 y SDD-03 RNF-6).
- **RNF-2**: La lectura y validación de un CSV de hasta 10 000 filas debe completarse en segundos, no minutos.

### Reproducibilidad

- **RNF-3**: Todas las dependencias Python del pipeline tienen versión pinneada (`requirements.txt` o equivalente). Consistente con SDD-01 RNF-12.
- **RNF-4**: Las semillas aleatorias (splits, muestreos) son configurables y se registran como parámetros del run.

### Robustez y tolerancia a fallos

- **RNF-5**: Un fallo puntual en un fichero no aborta el pipeline completo; el fichero falla, se registra el motivo y el pipeline continúa con los siguientes.
- **RNF-6**: Las escrituras a almacenamiento usan el patrón de reintento con backoff de SDD-03 (ver casos borde).

### Observabilidad

- **RNF-7**: Cada fase del pipeline emite logs estructurados con `correlation_id` común para todo el run, compatible con SDD-07.
- **RNF-8**: Al final de cada run, el pipeline produce un **resumen** (stdout + evento de dominio) con: ficheros procesados, registros válidos, registros rechazados, tiempo por fase, errores detectados.

### Escalabilidad (plan teórico)

- **RNF-9**: El código del pipeline se diseña de modo que migrar a Dask requiera cambios acotados: preferir operaciones pandas que tienen equivalente en Dask DataFrame, evitar iteración Python pura sobre filas cuando haya alternativa vectorizada. Documentado en RF-18.

### Mantenibilidad

- **RNF-10**: Las reglas de validación (campos obligatorios, rangos, etc.) se expresan de forma **declarativa y editable** (diccionario, YAML o similar), no hardcodeadas en el flujo de control. Permite ajustar reglas sin tocar la lógica del pipeline.

## 5. Casos borde / errores

### Ingesta

| Caso | Comportamiento esperado | RF afectado |
|------|------------------------|-------------|
| Directorio de entrada vacío | Terminar el run con resumen "0 ficheros, 0 registros" y sin error. | RF-1, RF-2 |
| Fichero CSV con encoding inesperado (no UTF-8) | Rechazar el fichero entero, registrar motivo concreto, continuar. | RF-1, RNF-5 |
| CSV con separador inesperado | Intentar detección básica; si falla, rechazar con motivo. | RF-1 |
| Imagen corrupta o truncada | Rechazar antes de la fase de limpieza, registrar evento. | RF-2, RF-8 |
| Fichero cuyo hash coincide con uno ya procesado anteriormente | Marcar como duplicado, no reprocesar. | RF-3, RF-16 |

### Limpieza y validación

| Caso | Comportamiento esperado | RF afectado |
|------|------------------------|-------------|
| CSV de 10 000 filas con 300 inválidas por campos faltantes | 9 700 registros pasan a transformación; las 300 se persisten en rechazos con motivo individual. El pipeline no aborta. | RF-5, RF-6 |
| Registro con `pseudo_id` ya presente en PostgreSQL | Tratar como upsert o rechazo según política documentada en SDD-03; el pipeline no se detiene. | RF-7 |
| Timestamp futuro en un registro (> ahora) | Rechazar. Similar al ejemplo del PDF del Master (timestamps futuros > 24 h). | RF-5 |
| Radiografía con tamaño > 10 MB | Rechazar antes de cargar a GridFS. | RF-8, RNF-7 SDD-01 |

### Transformación y carga

| Caso | Comportamiento esperado | RF afectado |
|------|------------------------|-------------|
| PostgreSQL no disponible durante la carga | Reintento con backoff (SDD-03 casos borde). Si persiste, dejar el lote en cola local y emitir alerta; el pipeline no pierde los datos. | RF-12, RNF-6 |
| MongoDB no disponible durante la carga | Idem PostgreSQL. | RF-12, RNF-6 |
| Campo identificativo detectado en un CSV (p. ej. columna "nombre") | Omitir o enmascarar antes de persistir; registrar evento de auditoría de anonimización. | RF-11 |

### Reproducibilidad

| Caso | Comportamiento esperado | RF afectado |
|------|------------------------|-------------|
| Ejecución con misma semilla y mismas fuentes sobre base vacía | Produce estado final idéntico (salvo timestamps). | RF-15 |
| Reejecución completa sobre base ya poblada | No duplica ni corrompe datos; el resumen indica "N ya presentes, M nuevos". | RF-16 |

## 6. Criterios de aceptación

### Ingesta

- [ ] **CA-1** (cubre RF-1, RF-2): depositar un CSV válido y 5 imágenes JPG en los directorios de entrada y ejecutar el pipeline end-to-end deja los datos persistidos en PostgreSQL/MongoDB y un resumen con conteos correctos.
- [ ] **CA-2** (cubre RF-3): cada fichero procesado deja una entrada en la colección de eventos de dominio (SDD-03) con `source`, `ingested_at`, hash y resultado.
- [ ] **CA-3** (cubre RF-4): interrumpir el pipeline a mitad de un fichero CSV y reejecutarlo deja el fichero completo procesado sin duplicados.

### Limpieza

- [ ] **CA-4** (cubre RF-5, RF-6): un CSV de 100 filas con 10 inválidas (campos faltantes, rangos fuera) produce 90 registros válidos en destino y 10 en la colección de rechazos, cada uno con motivo legible.
- [ ] **CA-5** (cubre RF-7): un CSV con 5 filas duplicadas por clave lógica produce un único registro persistido para cada clave y 4 rechazos/upserts registrados.
- [ ] **CA-6** (cubre RF-8): una imagen de 15 MB depositada en el directorio de entrada se rechaza con motivo "tamaño superior a 10 MB" y no llega a GridFS.

### Transformación y anonimización

- [ ] **CA-7** (cubre RF-9, RF-10): una fila de prueba en PostgreSQL tras el pipeline contiene `source`, `ingested_at`, `processed_by` no nulos y coherentes con el run.
- [ ] **CA-8** (cubre RF-11): depositar un CSV con una columna "nombre" la omite en destino y registra un evento de anonimización en los logs.

### Carga y agregados

- [ ] **CA-9** (cubre RF-12): tras un run, el conteo de filas en PG y de documentos en Mongo coincide con el resumen emitido por el pipeline (± registros rechazados).
- [ ] **CA-10** (cubre RF-13): tras el run, la colección de agregados diarios en Mongo contiene un documento por cada día procesado con las métricas listadas en RF-13.

### Reproducibilidad e idempotencia

- [ ] **CA-11** (cubre RF-15): ejecutar dos veces el pipeline sobre la misma fuente y misma semilla, limpiando las bases entre runs, produce el mismo número de filas y documentos en destino.
- [ ] **CA-12** (cubre RF-16): ejecutar el pipeline sobre una base ya poblada con las mismas fuentes termina con éxito y el resumen indica "N ya presentes, 0 nuevos".
- [ ] **CA-13** (cubre RF-17): `pipeline --only ingesta` seguido de `pipeline --only limpieza` seguido de `pipeline --only transformacion` produce el mismo resultado que `pipeline` end-to-end.

### Justificación técnica

- [ ] **CA-14** (cubre RF-18): el repositorio contiene un documento que cita la autorización del profesor, argumenta la elección de pandas y describe el plan de escalado a Dask.

### Observabilidad y robustez

- [ ] **CA-15** (cubre RNF-7, RNF-8): `docker compose logs pipeline` muestra eventos JSON estructurados con `correlation_id` común durante todo el run y un evento final de resumen.
- [ ] **CA-16** (cubre RNF-5): un fichero CSV corrupto entre 10 ficheros válidos rechaza solo el corrupto, procesa los otros 9 y termina con resumen correcto.

## 7. Dudas abiertas

- **[NEEDS CLARIFICATION]** Volumen y tiempo exactos del objetivo de rendimiento (RNF-1). Ligado a SDD-01 RNF-3 y SDD-03 RNF-6.
- **[NEEDS CLARIFICATION]** **Orquestación** del pipeline: ejecución por `cron` + scripts, o por un orquestador tipo **Prefect**/Airflow. Decisión diferida a SDD-04.
- **[NEEDS CLARIFICATION]** Para el caso de upsert por clave lógica duplicada (RF-7), ¿sobrescribir con el último o conservar el primero? Decisión a tomar en `DESIGN-02`.
- **[NEEDS CLARIFICATION]** Lenguaje exacto de las reglas declarativas de validación (RNF-10): diccionario Python, YAML, JSON Schema, Pydantic. Decisión en `DESIGN-02`.
- ~~Fuente de datos crudos (S3 AWS vs MinIO)~~ — **decisión cerrada 2026-04-21**: **MinIO local** (ver SDD-03 §7). El pipeline lee con `boto3` contra `S3_ENDPOINT=http://minio:9000`. Mismo código serviría para AWS real (solo cambiaría `S3_ENDPOINT` y credenciales). Arquitectura **landing zone**: la API escribe la ficha cruda del formulario en S3 y el pipeline la toma de ahí para validar/transformar/cargar.

## 8. Referencias

- Enunciado: `Enunciado-Hospital.pdf` §4.2 (pipeline de datos a escala), §4.2.3 (framework distribuido — excepción autorizada)
- `CONTEXT.md` §4.2, §3.2
- Memoria de autorización del profesor: ver memoria del proyecto, archivo `project_pandas_autorizado.md`
- Spec raíz: `specs/SDD-01-sistema.md`
- Spec de almacenamiento: `specs/SDD-03-almacenamiento.md`
- Diseño asociado: `specs/DESIGN-02-pipeline.md` *(a crear)*
- SDDs relacionados: SDD-04 (disparo), SDD-06 (modelo DL — consumidor de radiografías), SDD-07 (logging)
