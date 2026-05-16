# SDD-03 — Almacenamiento: PostgreSQL + MongoDB (GridFS)

> Spec del subsistema de **persistencia** del Sistema de Soporte Hospitalario. Define **qué entidades se almacenan, dónde y con qué reglas**. No define esquemas físicos ni índices concretos — eso va en `DESIGN-03-almacenamiento.md`.

---

**Versión:** 1.0
**Fecha:** 2026-04-20
**Autor:** Pol Ballarín
**Estado:** `ready-for-design`

---

## 1. Contexto y objetivo

### Contexto
El Sistema de Soporte Hospitalario (SDD-01) necesita persistir dos naturalezas de datos muy distintas:

1. **Datos estructurados** con relaciones fuertes entre entidades (un paciente tiene varios ingresos, un ingreso pertenece a un paciente, etc.) y consultas agregadas por dimensiones estables (fecha, personal, tipo de evento).
2. **Datos no estructurados o semiestructurados** de gran tamaño y esquema variable: imágenes de radiografías, resultados de predicciones del modelo DL, informes generados automáticamente y eventos del sistema.

El enunciado §4.2.2 exige **al menos dos tipos de almacenamiento** y cita como ejemplo *"PostgreSQL + MinIO/S3 o MongoDB"*. La arquitectura adoptada combina los tres (ver tabla en `DESIGN-01 §5.3`): PostgreSQL para datos relacionales estrictos, MongoDB para documentos heterogéneos + GridFS, y MinIO como capa raw / data lake. El easter egg nº1 del PDF ("NoSQL sobre todo") es ambiguo y la decisión técnica se sostiene sin necesidad de invocarlo.

### Objetivo
Proveer una capa de persistencia que:

1. Almacene los **datos clínicos estructurados** (pacientes, ingresos, personal, eventos clínicos) en **PostgreSQL**, con integridad referencial y consultas SQL estándar.
2. Almacene las **radiografías** (bytes de la imagen), las **predicciones del modelo DL**, los **informes diarios** (PDF+JSON) y los **eventos del sistema** en **MongoDB**, usando **GridFS** para los binarios de las imágenes.
3. Garantice **trazabilidad** cruzada entre ambos mundos: cada predicción/radiografía en Mongo referencia el pseudo-id del paciente en PostgreSQL; cada documento persistido incluye metadatos de origen (`source`, `ingested_at`, `processed_by`).
4. Mantenga la **anonimización por diseño**: ninguna tabla/colección almacena nombre, apellidos, DNI, dirección u otros datos personales directamente identificables.
5. Se integre de forma natural con el pipeline pandas (SDD-02) y con la API FastAPI (SDD-05) mediante las credenciales y bases de datos definidas en el contrato `.env` de SDD-01.

## 2. Actores y alcance

Los "actores" de este subsistema son **otros módulos del propio sistema** que leen o escriben en la persistencia. No hay actores humanos directos (el personal hospitalario accede al dashboard vía SDD-05, no a la base de datos).

### Actores

| Actor (módulo) | Lectura | Escritura | SDD |
|----------------|---------|-----------|-----|
| **Pipeline de datos** | sí | sí — ingiere datos clínicos estructurados y radiografías | SDD-02 |
| **Servicio de inferencia DL** | sí — lee radiografías | sí — escribe predicciones | SDD-06 |
| **API / Dashboard** | sí — lectura intensiva de casi todo | sí — escrituras puntuales (p. ej. marcar alerta como vista, si aplica) | SDD-05 |
| **Servicio de automatización** | sí — lee predicciones y eventos | sí — escribe informes, alertas, eventos del sistema | SDD-04 |
| **Servicio de monitorización** | sí — puede leer eventos del sistema para observabilidad | no escribe en este subsistema (usa su propio backend de logs) | SDD-07 |
| **Script generador de datos sintéticos** | no | sí — pobla PostgreSQL con seed inicial reproducible | RF-23 de SDD-01 |

### Dentro del alcance

- Definición lógica de **entidades** y **colecciones** en cada motor (PostgreSQL y MongoDB).
- Reparto de responsabilidades: qué va a PostgreSQL y qué va a MongoDB, y por qué.
- **Integridad referencial** cruzada entre ambos mundos mediante pseudo-IDs (PostgreSQL = fuente de verdad para entidades clínicas; MongoDB referencia por pseudo-ID).
- **GridFS** para almacenar los binarios de radiografías dentro de MongoDB.
- **Seed inicial** del entorno: ejecución del script de RF-23 al arrancar, si la base está vacía.
- **Metadatos de trazabilidad** obligatorios en cada documento/registro (`source`, `ingested_at`, `processed_by`).
- **Credenciales** y aislamiento: los servicios se conectan con las variables de entorno de SDD-01, sin acceso humano directo a las BBDD en el flujo normal.

### Fuera del alcance

- **Detalles físicos de esquema**: tipos SQL concretos, índices, tuning — eso va en `DESIGN-03-almacenamiento.md`.
- **Backups y recuperación ante desastres**: no requerido por el enunciado; basta con los volúmenes nombrados de Docker para la demo.
- **Replicación / alta disponibilidad**: mencionados solo en el plan de escalado teórico; no se implementan.
- **Sharding o particionado**.
- **UI de administración** de las BBDD (pgAdmin, Mongo Compass): no se incluyen en el stack.
- **Migraciones en caliente** con versionado de esquema (Alembic, Flyway): se usa seed+DDL simple; las migraciones complejas quedan fuera.
- **Logging técnico de los servicios** (trazas, métricas): pertenece a SDD-07. Aquí solo se almacenan **eventos de dominio** (ingesta, predicción, alerta, informe generado) como colección.
- **Cifrado at rest y en tránsito con certificados**: se usan credenciales de las BBDD, pero sin TLS entre servicios (demo local). Se documenta en memoria §7 como limitación.

## 3. Requisitos funcionales

> Los requisitos se expresan a nivel de **comportamiento observable**, sin nombres de tablas/colecciones ni tipos SQL concretos. El mapeo físico (DDL, índices, tipos, GridFS bucket exacto) se define en `DESIGN-03-almacenamiento.md`.

### Reparto de responsabilidades

- **RF-1**: El sistema debe almacenar los **datos clínicos estructurados** (como mínimo: pacientes, ingresos y relaciones entre ambos) en **PostgreSQL**, manteniendo integridad referencial a nivel de motor.
- **RF-2**: El sistema debe almacenar las **imágenes de radiografía** (bytes del fichero JPG/PNG original) en **MongoDB mediante GridFS**, junto con sus metadatos (pseudo-id de paciente si existe, hash de contenido, fecha de ingesta, origen).
- **RF-3**: El sistema debe almacenar en **MongoDB** los demás datos no estructurados/semiestructurados producidos por el sistema: predicciones del modelo DL, informes generados, alertas emitidas, eventos de dominio y registros de ingesta rechazados.

### Referencias cruzadas

- **RF-4**: Las colecciones MongoDB que se refieran a entidades clínicas deben hacerlo por **`pseudo_id` (cadena)** — el mismo valor que es clave primaria lógica de la entidad en PostgreSQL. No se fuerza integridad referencial a nivel de motor entre ambos; la consistencia la garantizan los servicios escritores.
- **RF-5**: Toda predicción persistida debe mantener una referencia **estable** a la radiografía concreta sobre la que se hizo (p. ej. `fs.files._id` de GridFS). La radiografía y su predicción deben poder recuperarse conjuntamente a partir de una sola de las dos referencias.

### Seed y datos iniciales

- **RF-6**: El sistema debe incluir un **script de seed** (ejecutable manualmente y, opcionalmente, como paso de arranque) que:
  - Cree el esquema relacional en PostgreSQL si no existe.
  - Cree los buckets/colecciones necesarias en MongoDB si no existen.
  - Pueble PostgreSQL con el dataset clínico sintético producido por el script de RF-23 (SDD-01).
- **RF-7**: El seed debe ser **idempotente**: ejecutarlo dos veces sobre una base ya poblada no debe duplicar registros ni fallar; debe detectar el estado y actuar en consecuencia (p. ej. omitir o reinicializar según flag).
- **RF-8**: El seed debe ser **reproducible**: con la misma semilla del generador sintético (RF-23 SDD-01), la base obtenida es byte-equivalente (excluyendo timestamps de ingesta).

### Trazabilidad obligatoria

- **RF-9**: Toda fila en PostgreSQL y todo documento en MongoDB debe contener, como mínimo, los siguientes campos de trazabilidad: `source` (origen del dato — fichero, servicio o módulo), `ingested_at` (timestamp de la primera escritura) y `processed_by` (identificador del servicio/proceso que lo generó o procesó).
- **RF-10**: Toda escritura debe registrar un evento en la colección de **eventos de dominio** (timestamp, servicio emisor, id de correlación, tipo de evento, id del registro afectado). Esta colección es auditoría, no logging técnico (que pertenece a SDD-07).

### Operaciones soportadas (mínimas)

- **RF-11**: Para las entidades clínicas estructuradas en PostgreSQL, el sistema debe permitir como mínimo: **alta** (por seed o por pipeline), **consulta** por pseudo-id, y **consulta listada con filtros simples** (rango de fechas, campo categórico).
- **RF-12**: Para las radiografías en GridFS, el sistema debe permitir: **subida** (upload con metadatos), **descarga** (recuperar los bytes originales), **consulta de metadatos** (sin descargar el binario), y **búsqueda por hash de contenido** (para detectar duplicados, RF-4 de SDD-01).
- **RF-13**: Para predicciones, informes, alertas, eventos y rechazos en MongoDB, el sistema debe permitir: **alta**, **consulta por referencia** (pseudo-id, radiografía, fecha), y **consulta agregada** (conteos, distribuciones por campo, filtros por rango temporal) suficiente para alimentar el dashboard (RF-17 de SDD-01).

### Anonimización

- **RF-14**: El esquema de PostgreSQL **no debe contener** columnas para nombre, apellidos, DNI, dirección, número de seguridad social ni otros datos personales directamente identificables. Solo `pseudo_id` y atributos clínicos no identificativos (edad aproximada, sexo biológico, motivo de ingreso, etc.).
- **RF-15**: Los metadatos almacenados en MongoDB (incluyendo EXIF/metadatos de imagen si los hubiera) deben ser limpiados de cualquier campo que pueda contener información personal antes de persistir.

### Credenciales y aislamiento

- **RF-16**: El acceso a PostgreSQL y a MongoDB debe ser mediante **credenciales** definidas en variables de entorno (`POSTGRES_*`, `MONGO_*` del contrato `.env` de SDD-01). No debe haber credenciales hardcodeadas en el código.
- **RF-17**: Las credenciales de administrador/root de las bases no deben usarse por los servicios aplicativos en tiempo de ejecución. Para la demo local se acepta un único usuario por motor; si se endurece, se crearían roles con permisos mínimos (fuera de alcance).

## 4. Requisitos no funcionales

### Rendimiento

- **RNF-1**: Las consultas típicas del dashboard (listado de pacientes, detalle de radiografía, distribuciones agregadas del día/semana) deben responder sin que el usuario perciba espera significativa. **[NEEDS CLARIFICATION]** umbrales concretos — ligados a los de SDD-01 RNF-1/2/3, se fijan tras la primera ejecución.
- **RNF-2**: La subida y almacenamiento de una radiografía en GridFS no debe superar el tiempo presupuestado para la ingesta completa. **[NEEDS CLARIFICATION]** umbral concreto.

### Integridad y consistencia

- **RNF-3**: PostgreSQL debe aplicar restricciones de integridad referencial (claves foráneas y `NOT NULL` en los campos obligatorios definidos en RF).
- **RNF-4**: Entre PostgreSQL y MongoDB la consistencia es **eventual** y responsabilidad de los servicios escritores. El sistema debe tolerar temporalmente un documento en Mongo cuya referencia en PG aún no exista (p. ej. predicción persistida antes de que la fila del paciente esté disponible), pero debe poder reconciliarlo cuando el dato llegue.
- **RNF-5**: Las escrituras a GridFS deben ser atómicas desde el punto de vista del consumidor: no se devuelve "éxito" si la imagen se subió parcialmente o si faltan metadatos obligatorios.

### Capacidad

- **RNF-6**: El sistema debe soportar al menos el volumen inicial derivado del dataset *COVID-19 Radiography Database* (decenas de miles de imágenes) **[NEEDS CLARIFICATION]** tamaño exacto del subset elegido — a fijar en SDD-06.
- **RNF-7**: Cada radiografía tiene tamaño máximo de **10 MB** (consistente con SDD-01 RNF-16). El sistema debe rechazar imágenes mayores.

### Escalabilidad

- **RNF-8**: El reparto PG+Mongo debe permitir escalar 10× en volumen (consistente con SDD-01 RNF-4) sin rediseño arquitectónico: PG con réplicas de lectura y particionado por fecha; MongoDB con Replica Set y sharding de GridFS sobre `fs.chunks`. Documentado a nivel teórico en `DESIGN-03`.

### Disponibilidad y durabilidad

- **RNF-9**: Los datos persistidos deben sobrevivir a `docker compose down` (sin `-v`) y a reinicios de los contenedores (consistente con SDD-01 RNF-7). Los volúmenes nombrados `postgres-data` y `mongo-data` del contrato de SDD-01 son la base de esta garantía.
- **RNF-10**: Al arrancar el stack, los servicios aplicativos no deben comenzar sus operaciones de escritura hasta que PostgreSQL y MongoDB estén `healthy`. Implementado vía `depends_on` + healthchecks en el compose (SDD-01).

### Privacidad y protección de datos

- **RNF-11**: Consistente con SDD-01 RNF-8 y RNF-9: anonimización por diseño (solo pseudo-IDs) y logs sin contenido binario ni datos sensibles.
- **RNF-12**: Las credenciales de acceso a las bases están en `.env` (fuera del repositorio) y nunca en el código. `.env.example` suministra la plantilla sin valores reales.
- **RNF-13**: Sin TLS entre servicios ni cifrado at rest de los volúmenes para la demo local. Se documenta en la memoria §10 (consideraciones éticas) como limitación conocida.

### Mantenibilidad y reproducibilidad

- **RNF-14**: El DDL de PostgreSQL y la definición de colecciones/índices de MongoDB deben residir en el repositorio como artefactos versionados (scripts `.sql` y `.js`/Python). Cambios futuros van por Pull Request, no por intervención manual.
- **RNF-15**: El seed sintético (RF-6) es reproducible con la misma semilla (consistente con SDD-01 RNF-13).

## 5. Casos borde / errores

### Integridad referencial y consistencia

| Caso | Comportamiento esperado | RF afectado |
|------|------------------------|-------------|
| Inserción de ingreso referenciando un `pseudo_id` de paciente inexistente en PostgreSQL | Fallar por FK a nivel motor. El servicio emisor registra evento de error y no marca el registro como válido. | RF-1, RNF-3 |
| Documento en Mongo creado (p. ej. predicción) cuyo `pseudo_id` aún no existe en PG | Aceptar y almacenar. Marcar el documento con flag `awaiting_patient_sync` y registrar evento de dominio. Un proceso periódico reconcilia cuando el paciente aparece. | RF-4, RNF-4 |
| Borrado de un paciente con ingresos/radiografías asociados | Por defecto, **bloquear el borrado** (RESTRICT). Un borrado efectivo requiere una operación explícita de purga que primero descuelga los hijos. La spec no cubre borrado del usuario final; aplica solo a mantenimiento. | RF-1, RF-14 |

### Duplicados e idempotencia

| Caso | Comportamiento esperado | RF afectado |
|------|------------------------|-------------|
| Alta de un paciente con `pseudo_id` que ya existe | Fallar por restricción de unicidad. El servicio escritor decide si es upsert legítimo o error lógico. | RF-1, RNF-3 |
| Subida a GridFS de una radiografía cuyo hash ya está presente | No crear nuevo objeto. Devolver la referencia al existente. Registrar evento informativo "duplicado detectado". | RF-12, caso borde SDD-01 "radiografía duplicada" |
| Ejecución repetida del script de seed sobre base ya poblada | Detectar estado, omitir filas ya presentes, no duplicar. Salida de éxito. | RF-7 |
| Predicción nueva sobre una radiografía que ya tiene predicción | Persistir la nueva predicción **versionada** (con `model_version` distinto y timestamp). No sobrescribir la anterior. | RF-5, RF-13 |

### Conexión y disponibilidad

| Caso | Comportamiento esperado | RF afectado |
|------|------------------------|-------------|
| PostgreSQL no disponible en el momento de una escritura | Reintento con backoff exponencial acotado. Si falla persistentemente, registrar evento crítico y dejar el dato en cola local del servicio escritor. | RNF-9, RNF-10 |
| MongoDB no disponible en el momento de una escritura | Mismo patrón que PG. Las radiografías ingeridas pero no persistidas quedan en cola local. | RNF-9, RNF-10 |
| Timeout de conexión lenta (p. ej. GridFS tarda en escribir imagen grande) | Operación falla con error claro tras el timeout configurado. El servicio decide si reintentar o abortar. | RF-12, RNF-5 |
| Healthcheck de PG/Mongo falla intermitentemente | Los servicios aplicativos ven el motor como "no sano" y entran en modo degradado (no aceptan nuevas escrituras, registran alerta). | RNF-10 |

### Corrupción y validación

| Caso | Comportamiento esperado | RF afectado |
|------|------------------------|-------------|
| Hash almacenado de una radiografía no coincide al recomputarlo sobre los bytes de GridFS | Marcar la radiografía como `integrity_failed`, emitir alerta crítica. No devolver los bytes a consumidores sin flag de advertencia. | RF-12 |
| Documento en Mongo sin alguno de los campos de trazabilidad obligatorios (`source`, `ingested_at`, `processed_by`) | Rechazar la inserción. El servicio escritor es responsable de cumplir RF-9. | RF-9, RF-10 |
| DDL evoluciona y una fila antigua carece de una columna nueva no-null | Gestionar con valor por defecto o migración explícita versionada. Ningún servicio puede asumir el esquema nuevo sin verificarlo. | RNF-14 |

### Recursos y capacidad

| Caso | Comportamiento esperado | RF afectado |
|------|------------------------|-------------|
| Volumen de PostgreSQL casi lleno | Emitir alerta de capacidad. Seguir aceptando lecturas, rechazar escrituras con error claro cuando llegue el límite. | RNF-6, RNF-9 |
| Volumen de MongoDB/GridFS casi lleno | Igual que PG. Las radiografías en cola local no se reintentan hasta que haya espacio. | RNF-6, RNF-9 |
| Subida de una imagen > 10 MB | Rechazar antes de escribir a GridFS. Registrar evento. | RNF-7 |

### Concurrencia

| Caso | Comportamiento esperado | RF afectado |
|------|------------------------|-------------|
| Dos servicios intentan insertar simultáneamente la misma alerta | Deduplicar por clave lógica (`type + correlation_id + ventana_temporal`) en el servicio escritor (automation). Si llega igualmente a la BD, restricción de unicidad en la clave lógica la rechaza. | RF-3, RF-20 SDD-01 |
| Dos predicciones concurrentes sobre la misma radiografía | Ambas se persisten versionadas (RF-5 de casos borde anteriores). No hay exclusión mutua a nivel BD. | RF-5 |

## 6. Criterios de aceptación

### Despliegue y arranque

- [ ] **CA-1** (cubre RNF-9, RNF-10): `docker compose up -d` levanta PostgreSQL y MongoDB y ambos alcanzan `healthy` antes de que los servicios aplicativos comiencen a aceptar peticiones.
- [ ] **CA-2** (cubre RNF-9): `docker compose down && docker compose up -d` (sin `-v`) mantiene intactos los datos ingeridos previamente (filas en PG y documentos+archivos en Mongo/GridFS).

### Esquema y estructura

- [ ] **CA-3** (cubre RF-1): tras el seed, PostgreSQL contiene las tablas correspondientes a las entidades clínicas estructuradas definidas, con restricciones de clave primaria y claves foráneas activas. *(Verificable con `\d` en psql o equivalente.)*
- [ ] **CA-4** (cubre RF-2): tras el seed, MongoDB contiene un bucket GridFS destinado a radiografías y las colecciones necesarias para predicciones, informes, alertas, eventos de dominio y rechazos de ingesta.
- [ ] **CA-5** (cubre RNF-14): los scripts de DDL (SQL y Mongo) residen bajo control de versiones en el repositorio y son los que se aplican efectivamente al motor (no hay esquema oculto creado a mano).

### Seed e idempotencia

- [ ] **CA-6** (cubre RF-6, RF-7): ejecutar el script de seed sobre una base vacía deja PostgreSQL poblado con el dataset sintético y MongoDB con sus colecciones listas.
- [ ] **CA-7** (cubre RF-7): ejecutar el script de seed dos veces consecutivas termina con éxito y **no duplica filas ni documentos**.
- [ ] **CA-8** (cubre RF-8): dos ejecuciones del seed con la misma semilla producen, en PostgreSQL, un conjunto de filas **byte-equivalente** (excluyendo `ingested_at`).

### GridFS y radiografías

- [ ] **CA-9** (cubre RF-2, RF-12): subir una radiografía JPG a GridFS y descargarla a continuación devuelve bytes **byte-idénticos** al fichero original. El hash almacenado coincide con el recomputado.
- [ ] **CA-10** (cubre RF-12, caso borde "duplicado"): subir por segunda vez una radiografía con el mismo hash no crea un segundo objeto en GridFS; la operación devuelve la referencia existente.
- [ ] **CA-11** (cubre RNF-7): un intento de subida de una imagen > 10 MB se rechaza antes de escribir a GridFS y queda registrado como evento.

### Referencias cruzadas PG ↔ Mongo

- [ ] **CA-12** (cubre RF-4): una consulta de muestreo sobre 50 documentos de MongoDB que referencien `pseudo_id` encuentra, para cada uno, la fila correspondiente en PostgreSQL (o un flag explícito `awaiting_patient_sync`).
- [ ] **CA-13** (cubre RF-5): dada la referencia a un documento de predicción, el sistema puede recuperar la radiografía asociada (bytes + metadatos) con una única llamada más.
- [ ] **CA-14** (cubre integridad referencial, caso borde): intentar insertar en PostgreSQL un ingreso con `pseudo_id` de paciente inexistente **falla** con violación de FK.

### Trazabilidad

- [ ] **CA-15** (cubre RF-9): un muestreo aleatorio de 50 filas de PG y 50 documentos de Mongo contiene, en todos los casos, los campos `source`, `ingested_at` y `processed_by` con valores no nulos y coherentes.
- [ ] **CA-16** (cubre RF-10): toda escritura observable en el sistema durante una ejecución de prueba tiene su evento correspondiente en la colección de eventos de dominio, con `correlation_id` que permite ligarlo al registro afectado.

### Versionado de predicciones

- [ ] **CA-17** (cubre RF-13, caso borde "predicción repetida"): disparar dos predicciones sobre la misma radiografía produce **dos documentos** de predicción distintos con `model_version` diferenciable, y ambos son consultables como historial.

### Anonimización

- [ ] **CA-18** (cubre RF-14, RNF-11): una inspección automatizada del esquema de PostgreSQL no encuentra columnas con nombres que evoquen datos personales directamente identificables (regex sobre `information_schema.columns`: `name`, `surname`, `dni`, `address`, `email`, `phone`, etc.).
- [ ] **CA-19** (cubre RF-15): los metadatos almacenados en MongoDB junto a las radiografías no contienen campos EXIF con información personal (verificable comparando EXIF del fichero original vs metadatos persistidos).

### Credenciales y seguridad operativa

- [ ] **CA-20** (cubre RF-16, RNF-12): una búsqueda en el repositorio no encuentra strings que parezcan credenciales reales de PG o Mongo (solo `.env.example` con placeholders y `${VAR}` en compose/código).
- [ ] **CA-21** (cubre RF-17): los servicios aplicativos se conectan con usuario y base de datos dedicados, no con el usuario `root`/`admin` del motor. *(Flexible para demo local; documentar desviación si aplica.)*

### Resiliencia

- [ ] **CA-22** (cubre RNF-9, caso borde "BD no disponible"): parar MongoDB durante 30 s mientras el pipeline intenta escribir una radiografía, y volver a arrancarlo: la radiografía acaba persistida sin intervención manual (gracias al reintento con backoff).

## 7. Dudas abiertas

- **[NEEDS CLARIFICATION]** Umbrales concretos de rendimiento para consultas típicas del dashboard y para subidas a GridFS (RNF-1, RNF-2). Ligado a la duda equivalente de SDD-01. Se fijarán tras la primera ejecución con datos reales.
- **[NEEDS CLARIFICATION]** Tamaño exacto del subset del dataset *COVID-19 Radiography Database* que se va a ingerir (RNF-6). Decisión diferida a SDD-06, donde se decide el balance entre clases y el volumen manejable para entrenamiento y demo.
- **[NEEDS CLARIFICATION]** Estrategia concreta de **reconciliación** de documentos Mongo marcados `awaiting_patient_sync` (caso borde "documento huérfano"). Opciones: (a) job periódico que reevalúa, (b) reintento lazy al leer, (c) ignorar y dejar flag para el dashboard. Decisión diferida a SDD-04 (automatización).
- **[NEEDS CLARIFICATION]** ¿Campo `pseudo_id` como string (`PAT-000123`) o como UUID? Afecta al tamaño de índices y a la legibilidad en logs. Decisión a tomar en `DESIGN-03-almacenamiento.md`.
- ~~Capa raw (S3 real, MinIO, o fallback)~~ — **decisión cerrada 2026-04-21**: **MinIO local S3-compatible** como backend del patrón *landing zone*. Razones: patrón industrial estándar de desarrollo (mismo `boto3`, migración a AWS real = solo cambiar `S3_ENDPOINT`), cumple §4.1 del enunciado ("un solo comando" sin credenciales externas), sin costes AWS, sin dependencia de Internet. En memoria se documenta que *"en producción apuntaríamos a AWS S3 sin cambios de código"*. Impacto aplicado: SDD-01 §2 y §7, SDD-02 §7, `DESIGN-01-arquitectura.md` (servicio `minio` añadido al compose), `.env.example` (variables `S3_*` + `MINIO_*`).

## 8. Referencias

- Enunciado: `Enunciado-Hospital.pdf` §4.2.2 (almacenamiento) + §10 easter egg nº1 ("NoSQL sobre todo")
- `CONTEXT.md` §4.2, §10
- Spec raíz: `specs/SDD-01-sistema.md`
- Diseño arquitectónico: `specs/DESIGN-01-arquitectura.md`
- SDDs relacionados (lectores): SDD-02 (pipeline), SDD-05 (API+dashboard), SDD-06 (modelo DL), SDD-04 (automatización), SDD-07 (monitorización)
