# SDD-01 — Sistema de Soporte Inteligente Hospitalario (laSalle Health Center)

> Spec **raíz** del sistema. Describe **qué** debe hacer la solución para el hospital laSalle Health Center y bajo qué condiciones la consideraremos correcta. **No** describe arquitectura ni tecnologías — eso va en `DESIGN-01-arquitectura.md`.

---

**Versión:** 1.0
**Fecha:** 2026-04-20
**Autor:** Pol Ballarín
**Estado:** `ready-for-design`

---

## 1. Contexto y objetivo

### Contexto
**laSalle Health Center** es un hospital de tamaño medio en proceso de transformación digital. Genera diariamente grandes volúmenes de datos clínicos (historiales, registros de pacientes, pruebas diagnósticas, radiografías) y operativos (logs de sistemas), pero carece de herramientas para extraer conocimiento, detectar patrones clínicos, automatizar tareas repetitivas y apoyar la toma de decisiones médicas y operativas.

### Objetivo
Proveer un sistema de soporte hospitalario dirigido al **personal clínico** (médicos y radiólogos) y a los **propios pacientes** (a través de un formulario web de triaje pre-consulta) que debe:

1. Ingerir y gestionar datos clínicos **estructurados** (pacientes, ingresos, personal, logs) y **no estructurados** (radiografías de tórax, informes, eventos).
2. **Triar automáticamente a cada paciente** que llega vía el formulario web en tres niveles de prioridad — *Alta · Media · Baja* — mediante un **modelo tabular** entrenado sobre datos sintéticos (SDD-08), como apoyo a la gestión de la agenda del hospital.
3. **Clasificar radiografías de tórax** en tres categorías — *Sana · Neumonía · COVID-19* — mediante un **modelo de Deep Learning** (SDD-06) entrenado sobre un dataset público, como apoyo a la decisión clínica.
4. **Automatizar** la generación de informes periódicos y la emisión de alertas ante eventos relevantes (p. ej. cuarentena por COVID-19 detectado, lote de radiografías pendientes de revisión, pacientes pendientes de triaje).
5. Exponer la información de forma **interpretable** al personal clínico (dashboard, consultas agregadas, trazabilidad del origen del dato) y a los pacientes (confirmación de triaje tras el formulario).

El diseño prioriza **calidad de datos, trazabilidad y evaluación clínica** (impacto de los errores del modelo, falsos negativos) por encima de la métrica estadística pura. Los datos clínicos asociados a pacientes se manejan **anonimizados por diseño** (solo pseudo-IDs, sin datos personales directamente identificables) en línea con el espíritu de §7 del enunciado (privacidad y protección de datos).

Las fuentes de datos son:
- **Radiografías reales**: dataset público *COVID-19 Radiography Database* (Kaggle).
- **Datos clínicos acompañantes**: generados sintéticamente (pacientes, ingresos, personal, eventos).

## 2. Actores y alcance

### Actores

| Actor | Tipo | Cómo interactúa |
|-------|------|-----------------|
| **Personal hospitalario** | humano | Usa el dashboard para consultar pacientes, radiografías con predicción, informes y alertas. Sube nuevas radiografías para clasificación. El enunciado no diferencia roles ni exige login, así que se trata como un único perfil genérico. |
| **Paciente** | humano | Se registra a través del **formulario web de triaje** del dashboard (datos básicos, antecedentes, síntomas auto-reportados). Recibe el nivel de triaje predicho como confirmación. |
| **Pipeline de datos** | sistema interno | Ingiere, limpia, transforma y analiza datos clínicos y radiografías. Opera en dos modos: **batch** (CSVs sintéticos) y **online** (ficha del formulario, en tiempo real). |
| **Servicio de inferencia DL (radiografías)** | sistema interno | Expone un endpoint de predicción sobre radiografías de tórax (Sana / Neumonía / COVID-19). |
| **Servicio de triaje (tabular)** | sistema interno | Expone un endpoint de predicción de nivel de triaje (Alta / Media / Baja) sobre una ficha de paciente. |
| **Servicio de automatización** | sistema interno | Detecta radiografías nuevas, dispara predicciones, genera informes y produce alertas ante eventos relevantes. |
| **Dataset externo** | fuente de datos | *COVID-19 Radiography Database* (Kaggle) — origen de las imágenes reales durante la carga inicial y la simulación de ingesta. |
| **Dataset sintético de triaje** | fuente de datos | Generado por un script versionado con reglas + ruido + variables espurias (SDD-08), para entrenar el modelo tabular. |

### Dentro del alcance

- **Generación reproducible de datos clínicos sintéticos** (pacientes, ingresos, personal, eventos, dataset de triaje para entrenamiento de SDD-08) mediante scripts versionados con semilla aleatoria, que sirven como seed del sistema y como dataset de entrenamiento del modelo tabular.
- **Formulario web de triaje pre-consulta** accesible desde el dashboard (sin credenciales), por el que un paciente introduce su ficha y recibe un nivel de triaje predicho como confirmación.
- **Pipeline online** que procesa cada ficha del formulario en tiempo real: valida, limpia, transforma, persiste en PostgreSQL, invoca el modelo tabular de triaje (SDD-08) y persiste la predicción en MongoDB.
- Ingesta automatizada de radiografías de tórax y de los datos clínicos sintéticos batch.
- Limpieza, validación de calidad y transformación de los datos ingeridos.
- Almacenamiento persistente en **PostgreSQL** (estructurados) + **MongoDB con GridFS** (radiografías y no estructurados).
- Clasificación automática de radiografías de tórax en *Sana / Neumonía / COVID-19* como apoyo a la decisión clínica.
- Generación automática de informes periódicos (p. ej. resumen diario de radiografías procesadas y distribución de predicciones).
- Emisión de alertas ante eventos relevantes del negocio o fallos de procesamiento, visibles en el dashboard y registradas en log (incluyendo "email simulado" como entrada de log, según §4.3 del enunciado).
- Dashboard de visualización accesible desde el navegador, con consultas agregadas e inspección de casos individuales.
- Logging centralizado y validación de calidad de datos transversales.
- Anonimización de datos de paciente por diseño (sin datos personales directamente identificables, solo pseudo-IDs).

### Fuera del alcance

- **Autenticación y control de acceso** (login, roles, permisos): el enunciado no lo exige. Todo el mundo accede al dashboard sin credenciales.
- **Envío real de correos electrónicos** (sin cliente SMTP ni MailHog): las "alertas por email" se simulan como entradas de log, según §4.3.
- **Integración con sistemas hospitalarios reales** (HIS, PACS, HL7, DICOM avanzado): la radiografía se trata como imagen JPG/PNG, no como estudio DICOM completo.
- **Historial médico complejo**: solo se modela la información clínica mínima necesaria para dar contexto a las radiografías (paciente, ingreso, fecha, motivo).
- **Otras modalidades de imagen** (TAC, resonancia magnética, ecografía): solo radiografías de tórax 2D.
- **Soporte multi-hospital / multi-tenant**: el sistema se diseña para un único hospital (laSalle Health Center).
- **Despliegue en producción real**: la entrega es un `docker compose up` local, sin orquestación en la nube, sin HA, sin auditoría de cumplimiento formal LOPD-GDD / GDPR.
- **Diagnóstico automatizado sin revisión humana**: el modelo es apoyo, nunca decisor final.

## 3. Requisitos funcionales

Lista enumerada de comportamientos observables que el sistema debe ofrecer. Los detalles técnicos de cada bloque se desarrollarán en los SDDs de cada módulo (SDD-02 a SDD-07) y en los `DESIGN-XX` correspondientes.

### Ingesta de datos

- **RF-1**: El sistema debe permitir la ingesta automatizada de radiografías de tórax en formato JPG o PNG.
- **RF-2**: El sistema debe permitir la ingesta de datos clínicos estructurados (pacientes, ingresos, personal, eventos clínicos) desde ficheros CSV.
- **RF-3**: El sistema debe asignar un identificador único a cada radiografía ingerida y enlazarla, si procede, al pseudo-ID de paciente correspondiente.
- **RF-4**: El sistema debe detectar radiografías duplicadas mediante huella de contenido (hash) y evitar reprocesarlas.

### Validación y procesamiento

- **RF-5**: El sistema debe validar cada registro clínico contra un conjunto de campos obligatorios y reglas de formato, y marcar como inválidos los que incumplan las reglas.
- **RF-6**: El sistema debe ejecutar un pipeline con las fases *ingesta → limpieza → transformación → análisis* sobre los datos recibidos, de forma trazable.
- **RF-7**: El sistema debe calcular métricas agregadas diarias (número de radiografías procesadas, distribución de predicciones, tasa de registros inválidos) para alimentar el dashboard.

### Clasificación de radiografías (apoyo a la decisión)

- **RF-8**: El sistema debe clasificar cada radiografía de tórax ingerida en una y solo una de tres categorías: *Sana*, *Neumonía* o *COVID-19*.
- **RF-9**: El sistema debe asociar a cada predicción una probabilidad por clase (tres valores en [0, 1] que suman 1).
- **RF-10**: El sistema debe presentar la predicción como **apoyo a la decisión**, conservando la radiografía original sin modificarla y sin sustituir el juicio del personal clínico.

### Persistencia

- **RF-11**: El sistema debe persistir los datos clínicos estructurados en una base de datos **relacional**.
- **RF-12**: El sistema debe persistir las radiografías (bytes de la imagen) y sus metadatos en un **almacén documental / de objetos**.
- **RF-13**: El sistema debe persistir las predicciones, los informes generados y los eventos del sistema en el almacén documental, con referencia al registro original al que pertenecen.

### Visualización (dashboard)

- **RF-14**: El sistema debe exponer un dashboard accesible desde un navegador web, sin necesidad de credenciales (§2 fuera-de-alcance).
- **RF-15**: El dashboard debe permitir consultar la lista de pacientes con sus datos clínicos básicos anonimizados.
- **RF-16**: El dashboard debe permitir, para cada radiografía, mostrar la imagen, la predicción, las tres probabilidades por clase y los metadatos de ingreso.
- **RF-17**: El dashboard debe mostrar vistas agregadas: distribución de predicciones, radiografías procesadas por día, alertas emitidas y registros inválidos detectados.

### Automatización

- **RF-18**: El sistema debe detectar la llegada de nuevas radiografías al almacén documental y disparar la clasificación sin intervención manual.
- **RF-19**: El sistema debe generar automáticamente **un informe por día natural** (cierre a medianoche, zona horaria *Europe/Madrid*) con las radiografías procesadas, la distribución de predicciones y los eventos destacados. El informe se produce en **dos formatos**: PDF (para consumo del personal hospitalario) y JSON (persistido en el almacén documental para consultas posteriores).
- **RF-20**: El sistema debe emitir alertas ante eventos relevantes (p. ej. nueva predicción *COVID-19* con alta confianza, fallo de procesamiento, tasa anómala de registros inválidos). Las alertas deben visualizarse en el dashboard y registrarse como *email simulado* en log (§4.3 enunciado).

### Trazabilidad y calidad

- **RF-21**: El sistema debe registrar en **log centralizado** cada operación relevante (ingesta, validación, predicción, alerta, error) con marca temporal, origen y resultado.
- **RF-22**: El sistema debe conservar, para cada dato persistido, información de trazabilidad: origen, fecha de ingesta y referencia al proceso que lo generó.

### Datos sintéticos de apoyo

- **RF-23**: El sistema debe incluir un **script reproducible de generación de datos clínicos sintéticos** (pacientes, ingresos, personal, eventos), con semilla aleatoria fijable para reproducibilidad, que sirva como seed inicial del entorno y para regenerar datos en cualquier momento.

## 4. Requisitos no funcionales

### Rendimiento

> Los umbrales concretos de rendimiento quedan como **[NEEDS CLARIFICATION]** hasta que exista una primera medición real con el modelo entrenado y el pipeline levantado (ver §7). Se registra aquí **qué** se medirá y el entorno de referencia; el **cuánto** se fija tras la primera corrida.

- **RNF-1**: La clasificación end-to-end de una única radiografía (recepción → predicción devuelta) debe completarse en un tiempo objetivo a fijar, en CPU estándar de portátil de desarrollo. **[NEEDS CLARIFICATION]** umbral concreto.
- **RNF-2**: La carga inicial del dashboard con una base estable de radiografías procesadas debe completarse en un tiempo objetivo a fijar. **[NEEDS CLARIFICATION]** umbral concreto y tamaño de base de referencia.
- **RNF-3**: El pipeline de procesamiento diario debe procesar un volumen objetivo de radiografías y registros clínicos en un tiempo acotado, en el entorno de desarrollo. **[NEEDS CLARIFICATION]** volumen y tiempo concretos.

### Escalabilidad

- **RNF-4**: El sistema debe diseñarse de modo que el volumen de datos pueda crecer al menos **10×** sin cambios arquitectónicos de fondo (p. ej. dimensionando réplicas de MongoDB, migrando `pandas` a `Dask` con API compatible). La justificación técnica detallada va en SDD-02.

### Disponibilidad y despliegue

- **RNF-5**: El sistema completo debe levantarse con **un único comando** (`docker compose up -d`) siguiendo el README (§4.1 enunciado).
- **RNF-6**: Todos los servicios deben alcanzar estado `healthy` en **menos de 90 segundos** tras el arranque.
- **RNF-7**: La persistencia de datos (PostgreSQL, MongoDB) debe sobrevivir a un `docker compose down` sin la flag `-v`.

### Privacidad y protección de datos (§7 del enunciado)

- **RNF-8**: Ningún dato persistido puede contener información personal directamente identificable (nombre, apellidos, DNI, dirección). Se usan **pseudo-IDs** generados sintéticamente.
- **RNF-9**: Los logs no deben incluir el contenido binario de las radiografías ni datos clínicos sensibles; solo referencias por pseudo-ID.

### Calidad de datos y trazabilidad

- **RNF-10**: El sistema debe detectar y reportar al menos: **campos obligatorios ausentes**, **valores fuera de dominio** (p. ej. edad negativa), **duplicados** por clave lógica, **timestamps incoherentes** y **imágenes corruptas o de formato no soportado**.
- **RNF-11**: Todo evento relevante (ingesta, validación, predicción, alerta, error) debe quedar trazado en log **estructurado** (JSON) con al menos: timestamp, servicio, nivel, id de correlación del registro afectado, resultado.

### Mantenibilidad y reproducibilidad

- **RNF-12**: Todas las dependencias de cada servicio deben fijarse con versión explícita (`pip install paquete==X.Y.Z` o `requirements.txt` con versiones pinneadas).
- **RNF-13**: El entrenamiento del modelo DL debe ser reproducible: semillas fijadas, versión de dataset documentada, hiperparámetros registrados.
- **RNF-14**: El código fuente debe organizarse en un único repositorio con separación clara por servicio (`services/api/`, `services/pipeline/`, etc.) y con un `README.md` que documente prerequisitos, arranque, URLs y parada.

### Compatibilidad

- **RNF-15**: El dashboard debe ser accesible desde la última versión estable de los navegadores Chrome, Firefox y Edge.
- **RNF-16**: Las radiografías ingeridas deben aceptarse en formatos JPG y PNG, con tamaños de archivo de hasta 10 MB por imagen.

### Observabilidad

- **RNF-17**: El sistema debe exponer una forma sencilla de consultar los logs centralizados de todos los servicios (p. ej. `docker compose logs` estructurado, o endpoint/visor dedicado — a concretar en SDD-07).

## 5. Casos borde / errores

### Ingesta

| Caso | Comportamiento esperado | RF afectado |
|------|------------------------|-------------|
| Imagen corrupta o no legible | Rechazar la imagen. Registrar evento de error con pseudo-id del paciente (si existe) y motivo. No persistir la imagen. | RF-1, RNF-10 |
| Formato de imagen no soportado (p. ej. `.tiff`, `.bmp`, `.pdf`) | Rechazar la imagen con motivo "formato no soportado". Registrar evento. No persistir. | RF-1, RNF-16 |
| Imagen con tamaño > 10 MB | Rechazar y registrar evento. | RF-1, RNF-16 |
| Radiografía duplicada (mismo hash) | Detectar duplicado por contenido. No volver a persistir ni reclasificar. Registrar evento informativo "duplicado detectado". | RF-4 |
| CSV clínico con campos obligatorios vacíos | Marcar el registro como inválido. Persistirlo aparte en una colección de "rechazos" con el motivo. El pipeline continúa con el resto. | RF-5, RNF-10 |
| CSV con encoding no UTF-8 / separador inesperado | Rechazar el fichero entero, registrar evento de error con causa concreta. No procesar registros parciales. | RF-2, RNF-10 |
| Radiografía ingerida que referencia un pseudo-id de paciente inexistente | Persistir la radiografía marcada como "sin paciente asociado". No bloquear el flujo. Registrar alerta de calidad. | RF-3, RF-22 |
| Radiografía ingerida sin pseudo-id de paciente | Persistir como "anónima en el sistema" (pseudo-id autogenerado). La predicción se realiza igualmente. | RF-3 |

### Clasificación DL

| Caso | Comportamiento esperado | RF afectado |
|------|------------------------|-------------|
| Imagen con dimensiones muy pequeñas (p. ej. < 64×64 px) | Rechazar antes de llegar al modelo, registrar evento "imagen fuera de dimensiones válidas". | RF-8, RNF-10 |
| Imagen completamente negra o completamente blanca | Clasificar si técnicamente es posible, pero acompañar la predicción con un flag de baja confianza y registrar evento informativo. | RF-8, RF-9 |
| Servicio de inferencia no disponible | La ingesta persiste la radiografía con estado `pending_prediction`. Un reintento posterior completa la predicción. Se emite alerta al dashboard + log. | RF-18, RF-20 |
| Predicción con dos clases empatadas en probabilidad | Asignar la clase con mayor índice (orden estable: Sana < Neumonía < COVID-19) **[NEEDS CLARIFICATION]** ¿otra regla? | RF-8, RF-9 |
| Modelo devuelve probabilidades inválidas (NaN, negativas, no suman 1) | Rechazar la predicción, marcar radiografía como `prediction_failed`, registrar alerta técnica. | RF-9, RNF-10 |

### Persistencia

| Caso | Comportamiento esperado | RF afectado |
|------|------------------------|-------------|
| PostgreSQL no disponible | Los servicios que lo necesiten reintentan con backoff. Si persiste el fallo, registran alerta de infraestructura. El ingesta queda pausada hasta recuperación. | RF-11, RNF-7 |
| MongoDB no disponible | Mismo patrón: reintento con backoff + alerta. Radiografías en cola local hasta recuperación. | RF-12, RNF-7 |
| Volumen de GridFS lleno (simulado) | Rechazar nuevas radiografías con error claro. Alerta crítica. | RF-12, RNF-10 |

### Visualización y automatización

| Caso | Comportamiento esperado | RF afectado |
|------|------------------------|-------------|
| Dashboard consultado antes de la primera ingesta | Mostrar estado vacío coherente (mensajes tipo "aún no hay datos"), sin errores. | RF-14, RF-15 |
| Dashboard con miles de registros | Paginar o limitar resultados en consultas agregadas. No bloquear la UI. | RF-15, RF-17 |
| Mismo evento genera la misma alerta varias veces (p. ej. reintento de procesamiento) | Deduplicar alertas por clave lógica (evento + id afectado) dentro de una ventana temporal razonable. | RF-20 |
| Informe diario programado falla | Registrar error, emitir alerta al dashboard, reintentar a la siguiente ejecución. No bloquear el resto del pipeline. | RF-19, RF-20 |

## 6. Criterios de aceptación

Cada criterio es verificable mediante un comando, un test o una observación concreta. Cada CA referencia uno o más RF/RNF.

### Despliegue

- [ ] **CA-1** (cubre RNF-5, RNF-6): `docker compose up -d` en la raíz del repo levanta todos los servicios y en menos de 90 s todos alcanzan `healthy`.
- [ ] **CA-2** (cubre RNF-7): `docker compose down && docker compose up -d` (sin `-v`) mantiene los datos de PostgreSQL y MongoDB ingeridos previamente.
- [ ] **CA-3** (cubre RNF-14): el README en la raíz documenta prerequisitos, `cp .env.example .env`, arranque, URLs de dashboard y API, y parada.

### Ingesta y validación

- [ ] **CA-4** (cubre RF-1): copiar una radiografía JPG válida al directorio/bucket de ingesta produce, en menos de un minuto, un nuevo registro en el almacén documental con su imagen y metadatos.
- [ ] **CA-5** (cubre RF-1, caso borde "formato no soportado"): copiar un `.txt` o `.pdf` al directorio de ingesta **no** produce nuevo registro y genera una entrada de log de tipo error con motivo "formato no soportado".
- [ ] **CA-6** (cubre RF-4): copiar dos veces la misma radiografía (mismo hash) produce un solo registro persistido y un evento informativo "duplicado detectado".
- [ ] **CA-7** (cubre RF-2, RF-5): ingerir un CSV con 100 registros clínicos donde 5 tienen campos obligatorios vacíos produce 95 registros válidos persistidos y 5 registros marcados como inválidos en la colección de rechazos.

### Clasificación

- [ ] **CA-8** (cubre RF-8, RF-9): para toda radiografía ingerida, en el almacén documental existe un documento de predicción asociado con: clase (`Sana`/`Neumonía`/`COVID-19`), tres probabilidades que suman 1.0 (±1e-6) y una referencia al identificador de la radiografía.
- [ ] **CA-9** (cubre RF-10): la radiografía original persistida es byte-idéntica a la ingerida (no se modifica por el proceso de clasificación).
- [ ] **CA-10** (cubre caso borde "servicio de inferencia no disponible"): parar el servicio de inferencia, ingerir 3 radiografías, volver a arrancar el servicio: las 3 radiografías quedan persistidas en estado `pending_prediction` y, tras el arranque, acaban con predicción asignada.

### Persistencia

- [ ] **CA-11** (cubre RF-11): tras ingerir N pacientes sintéticos, `SELECT COUNT(*) FROM patients` en PostgreSQL devuelve N.
- [ ] **CA-12** (cubre RF-12): tras ingerir M radiografías, `db.fs.files.count()` en MongoDB devuelve M (GridFS).
- [ ] **CA-13** (cubre RF-13): cada documento de predicción en MongoDB contiene referencia explícita al `fs.files._id` de su radiografía.

### Dashboard

- [ ] **CA-14** (cubre RF-14): el dashboard es accesible en la URL documentada en el README, desde navegador, sin credenciales.
- [ ] **CA-15** (cubre RF-15, RF-16): el dashboard muestra la lista de pacientes y, al seleccionar uno, sus radiografías con imagen, clase predicha, probabilidades y fecha.
- [ ] **CA-16** (cubre RF-17): el dashboard muestra al menos tres vistas agregadas: distribución de predicciones, radiografías por día y tabla de alertas emitidas.
- [ ] **CA-17** (cubre caso borde "dashboard sin datos"): con la base de datos vacía, el dashboard carga sin errores y muestra estados vacíos legibles.

### Automatización

- [ ] **CA-18** (cubre RF-18): al depositar una nueva radiografía en el área de ingesta sin intervención manual, en menos de un minuto existe predicción asociada en el almacén documental.
- [ ] **CA-19** (cubre RF-19): tras ejecutar la tarea diaria (manualmente o por cron), existe un PDF de informe en el almacén documental y un JSON equivalente persistido.
- [ ] **CA-20** (cubre RF-20): una predicción con *P(COVID-19)* por encima del umbral definido genera una entrada visible en el dashboard (sección alertas) y una entrada en log etiquetada como `email_simulated`.

### Trazabilidad y calidad

- [ ] **CA-21** (cubre RF-21, RNF-11): `docker compose logs` (o el mecanismo equivalente de SDD-07) muestra, para cada ingesta-predicción, una secuencia coherente de eventos JSON con timestamp, servicio, nivel, id de correlación y resultado.
- [ ] **CA-22** (cubre RF-22): cada documento persistido contiene los campos `source`, `ingested_at` y `processed_by`.
- [ ] **CA-23** (cubre RNF-10): el sistema detecta al menos los cinco tipos de problema listados en RNF-10 cuando se fuerzan artificialmente en los datos de entrada.

### Privacidad

- [ ] **CA-24** (cubre RNF-8): una inspección manual de PostgreSQL y MongoDB no encuentra campos con nombre, apellidos, DNI, dirección u otros datos personales directamente identificables.
- [ ] **CA-25** (cubre RNF-9): una revisión de los logs generados durante la ingesta y clasificación no muestra contenido binario de radiografías ni datos clínicos sensibles — solo pseudo-IDs y metadatos no sensibles.

## 7. Dudas abiertas

- **[NEEDS CLARIFICATION]** ¿Qué umbral de probabilidad `P(COVID-19)` dispara la alerta de RF-20? Candidatos habituales: 0.50 (cualquier predicción mayoritaria), 0.80 (conservador), 0.95 (muy estricto). **Decisión diferida a SDD-06 / DESIGN-06**, una vez evaluada la distribución real de probabilidades del modelo entrenado y su matriz de confusión.
- **[NEEDS CLARIFICATION]** Umbrales concretos de rendimiento (RNF-1, RNF-2, RNF-3): tiempos de predicción por radiografía, tiempo de carga del dashboard y volumen/tiempo del pipeline diario. **Decisión diferida**: se fijarán tras una primera ejecución del sistema completo (fin del Sprint 2 del plan global), usando los tiempos observados como línea base.
- **[NEEDS CLARIFICATION]** Regla de desempate cuando dos clases del modelo DL obtienen igual probabilidad (§5 Clasificación DL). Propuesta por defecto: asignar la clase con mayor índice en el orden *Sana < Neumonía < COVID-19* (conservador clínicamente: ante la duda, asumir el caso más grave). A validar en SDD-06.
- ~~Capa de datos crudos (S3 AWS vs MinIO)~~ — **decisión cerrada 2026-04-21**: **MinIO local S3-compatible** (ver SDD-03 §7). Arquitectura *landing zone*: el formulario escribe la ficha cruda en S3, el pipeline la recoge de ahí y la procesa hacia PostgreSQL/MongoDB. Buena práctica industrial; migración a AWS real = solo cambiar `S3_ENDPOINT`.

## 8. Referencias

- Enunciado: `Enunciado-Hospital.pdf`
- Resumen del enunciado: `CONTEXT.md`
- Diseño asociado: `specs/DESIGN-01-arquitectura.md`
- Plan global aprobado: `C:\Users\polba\.claude\plans\vamos-a-planificar-la-vectorized-star.md`
