# SDD-04 — Automatización (watchers, scheduler, alertas, informes)

> Spec del subsistema de **automatización** que coordina procesos sin intervención manual: detección de radiografías nuevas, disparo del modelo DL, generación de informes diarios, emisión de alertas y reconciliación eventual. El diseño concreto (elección del orquestador, estructura de jobs, formato exacto del informe PDF) va en `DESIGN-04-automatizacion.md`.

---

**Versión:** 1.0
**Fecha:** 2026-04-20
**Autor:** Pol Ballarín
**Estado:** `ready-for-design`

---

## 1. Contexto y objetivo

### Contexto
El enunciado §3.3 exige "mecanismos que mejoren la eficiencia operativa" mediante **generación automática de informes**, **envío de alertas ante eventos relevantes**, **procesamiento automático de nuevos datos** y **organización de ficheros**. El sistema debe reducir el trabajo manual del personal hospitalario ligando las demás piezas del sistema sin que el usuario tenga que invocarlas explícitamente.

Este subsistema es el **pegamento** entre el pipeline (SDD-02), el modelo DL (SDD-06), el almacenamiento (SDD-03) y la API/Dashboard (SDD-05). Sus responsabilidades son **transversales** y **dirigidas por eventos** o **por calendario**.

### Objetivo
Proveer un servicio de automatización (`automation` en SDD-01) que:

1. **Detecte** radiografías nuevas al llegar al sistema y **dispare** la predicción contra el servicio DL sin intervención manual.
2. **Programe** y ejecute la generación del **informe diario** (PDF + JSON) definido en RF-19 de SDD-01.
3. **Emita alertas** ante eventos relevantes del negocio (p. ej. predicción COVID-19 con alta confianza) y ante **fallos operativos** del sistema (pipeline fallido, inferencia caída, tasa anómala de rechazos).
4. **Deduplicar** alertas y **reintentar** tareas fallidas con backoff.
5. **Reconciliar** documentos de MongoDB marcados `awaiting_patient_sync` (caso borde de SDD-03) cuando los datos referenciados aparezcan en PostgreSQL.

## 2. Actores y alcance

### Actores

| Actor | Dirección | Rol |
|-------|-----------|-----|
| **Radiografía nueva en GridFS** *(SDD-03)* | evento | Dispara la detección y posterior predicción |
| **Servicio de inferencia** *(SDD-06)* | cliente | El automation le pide predicciones |
| **Almacenamiento** *(SDD-03)* | lectura/escritura | Leído para agregados y reconciliación; escrito para persistir informes, alertas y eventos |
| **API** *(SDD-05)* | cliente | Usada indirectamente para escrituras que cruzan varios módulos |
| **Reloj del sistema** | evento temporal | Dispara el informe diario y chequeos periódicos |
| **Logging centralizado** *(SDD-07)* | observador | Todas las acciones del automation quedan trazadas |

### Dentro del alcance

- **Watcher de radiografías**: mecanismo que detecta imágenes nuevas en GridFS y dispara la predicción. Puede basarse en polling de un estado `pending_prediction`, change streams de MongoDB, o un evento emitido por el pipeline. Decisión en `DESIGN-04`.
- **Scheduler** que ejecuta el informe diario a una hora fija (cierre de día natural, zona horaria *Europe/Madrid*, consistente con RF-19 de SDD-01).
- **Generador del informe**: consulta agregados del día, compone un PDF legible y persiste PDF + JSON en el almacén documental.
- **Emisor de alertas**: regla-por-regla, evalúa condiciones y produce alertas en dashboard + log "email simulado". Deduplicación por clave lógica.
- **Reintento con backoff** de tareas fallidas (predicciones, informes, alertas) con límite de intentos.
- **Reconciliador** periódico de documentos huérfanos.

### Fuera del alcance

- **Envío real de emails** (SMTP): el "email simulado" es una entrada de log etiquetada, no un correo real (consistente con SDD-01 fuera-de-alcance).
- **Orquestador tipo Airflow distribuido**: si se elige Prefect/Airflow, se corre en modo single-node local; nada de DAGs complejos con decenas de tareas.
- **Notificaciones push al navegador** en tiempo real: el dashboard se actualiza por polling/navegación.
- **Integración con sistemas externos** (Slack, Teams, SMS).
- **Reglas de alerta configurables por el usuario final desde la UI**: las reglas son código versionado, no configuración runtime.
- **Auto-retraining** del modelo DL.

## 3. Requisitos funcionales

### Watcher y disparo de predicción

- **RF-1**: El sistema debe detectar, sin intervención manual, cada radiografía que llega al almacén documental (GridFS) y cuyo estado requiera predicción. El tiempo máximo entre llegada y detección debe mantenerse bajo un umbral razonable. **[NEEDS CLARIFICATION]** umbral exacto.
- **RF-2**: El sistema debe disparar una llamada al endpoint de predicción del servicio DL (`POST /predict` de SDD-06) por cada radiografía detectada, respetando el orden de llegada **no estricto** (best-effort). La respuesta se persiste como documento de predicción en MongoDB (SDD-03).
- **RF-3**: Si la radiografía ya tiene predicción con el mismo `model_version` activo, el automation **no** la vuelve a predecir. Si la versión cambió, puede disparar re-predicción versionada (política a decidir en `DESIGN-04`).

### Scheduler e informe diario

- **RF-4**: El sistema debe programar la **ejecución diaria** de la tarea "informe del día" a una hora fija documentada (propuesta: 23:59 hora *Europe/Madrid*), procesando el día natural que termina.
- **RF-5**: La tarea de informe debe **consultar** los agregados del día (SDD-02 RF-13 y SDD-03 colección de agregados) y producir:
  - Un **PDF** legible con resumen del día: radiografías ingeridas, distribución de predicciones por clase, registros clínicos cargados, registros rechazados, alertas emitidas.
  - Un **JSON** con los mismos datos estructurados.
- **RF-6**: Ambos artefactos se persisten en el almacén documental (SDD-03 RF-3) y son accesibles vía la API (SDD-05 RF-6, RF-7).
- **RF-7**: La tarea de informe es **idempotente**: reejecutar la tarea del mismo día natural **no crea** un segundo informe, **sobrescribe** o **versiona** según política documentada en `DESIGN-04`.

### Alertas de negocio

- **RF-8**: El sistema debe evaluar reglas de alerta **tras cada predicción** y emitir alerta cuando se cumplan las condiciones. Regla mínima obligatoria: **predicción COVID-19 con alta confianza** — umbral concreto marcado como `[NEEDS CLARIFICATION]` heredado de SDD-01 y SDD-06.
- **RF-9**: El sistema debe evaluar reglas periódicas sobre agregados y emitir alerta ante **tasas anómalas**: p. ej. tasa de rechazos > umbral configurable, número de radiografías procesadas muy por debajo de lo habitual. **[NEEDS CLARIFICATION]** umbrales concretos y periodicidad.
- **RF-10**: Cada alerta se persiste en la colección de alertas (SDD-03 RF-3) con `type`, `severity`, `message`, `correlated_radiograph_id` (opcional), `emitted_at`, `status`.
- **RF-11**: Cada alerta emite una entrada de log etiquetada con `type=email_simulated` (consistente con SDD-01 caso borde emails).

### Alertas operativas / de fallo

- **RF-12**: El sistema debe detectar y alertar ante: **servicio de inferencia no saludable** (chequeo periódico de `/healthz` de SDD-06), **pipeline fallado** (evento de fin de pipeline con errores críticos), **base de datos no disponible** (si el propio automation no puede conectar).
- **RF-13**: Las alertas operativas deben enriquecerse con el `correlation_id` del run o petición afectados para permitir su rastreo en logs (SDD-07).

### Deduplicación y reintento

- **RF-14**: El sistema debe **deduplicar** alertas emitidas en una ventana temporal configurable por **clave lógica**: `type + correlation_id` (o combinación equivalente). Una misma condición que persiste durante N minutos no emite N alertas sino una sola (y, opcionalmente, una alerta de cierre).
- **RF-15**: Las tareas que fallan (predicción, informe, emisión de alerta) se reintentan con **backoff exponencial** acotado y **límite máximo de reintentos**. Tras agotar intentos, se emite una alerta operativa de "tarea agotada".

### Reconciliación

- **RF-16**: El sistema debe ejecutar un **job periódico de reconciliación** que recorra documentos en Mongo marcados `awaiting_patient_sync` (SDD-03 caso borde) y los re-enlace cuando el paciente correspondiente aparezca en PostgreSQL. Frecuencia configurable.

### Observabilidad

- **RF-17**: Cada ejecución de tarea emite eventos de dominio (SDD-03 RF-10) con inicio, fin, resultado y contadores (objetos procesados, errores).

## 4. Requisitos no funcionales

### Latencia y rendimiento

- **RNF-1**: El tiempo desde que una radiografía llega a GridFS hasta que existe predicción asociada debe mantenerse bajo un umbral razonable. **[NEEDS CLARIFICATION]** umbral concreto (ligado a RF-18 de SDD-01 y al tiempo de inferencia).
- **RNF-2**: El informe diario completo debe generarse en un tiempo acotado. **[NEEDS CLARIFICATION]** umbral exacto.

### Robustez

- **RNF-3**: Un fallo en una tarea individual no debe detener las demás (aislamiento de fallos entre tareas).
- **RNF-4**: El servicio de automation debe poder **reiniciarse** sin perder el estado durable (las colas de reintento viven en Mongo o en ficheros persistidos, no solo en memoria).
- **RNF-5**: Si el automation está caído durante N minutos, tras rearrancar debe **recuperar** las radiografías que llegaron mientras tanto y dispararles predicción (no se pierden).

### Idempotencia

- **RNF-6**: Todas las tareas planificadas son **idempotentes**: ejecutar dos veces la misma tarea para el mismo input no produce efectos laterales duplicados.

### Configuración

- **RNF-7**: Umbrales de alerta, ventanas de deduplicación, horarios de scheduler, número de reintentos y backoff son **configurables vía variables de entorno** (o fichero declarativo versionado), no hardcodeados.

### Observabilidad

- **RNF-8**: Cada tarea emite logs estructurados JSON con `correlation_id`, duración, resultado y contadores, compatible con SDD-07.

## 5. Casos borde / errores

### Watcher

| Caso | Comportamiento esperado | RF afectado |
|------|------------------------|-------------|
| Radiografía llega mientras el automation está caído | Tras rearranque, el watcher la detecta (por estado `pending_prediction` o equivalente) y dispara predicción. | RNF-5, RF-1 |
| Radiografía con predicción ya existente bajo `model_version` activa | Omitir. | RF-3 |
| Servicio DL no responde al intentar predecir | Reintento con backoff. Tras agotar intentos, alerta "predicción agotada" y la radiografía queda `prediction_failed`. | RF-2, RF-15 |

### Scheduler / informe

| Caso | Comportamiento esperado | RF afectado |
|------|------------------------|-------------|
| El sistema estuvo apagado a la hora programada | Al rearrancar, detectar que el informe del día anterior no existe y ejecutarlo con retraso. | RF-4, RNF-5 |
| Fallo al generar el PDF | Reintento con backoff (RF-15). Si persiste, emitir alerta y persistir solo el JSON. | RF-5, RF-15 |
| Se ejecuta el informe dos veces para el mismo día | No crear dos informes; sobrescribir o versionar según política. | RF-7, RNF-6 |

### Alertas

| Caso | Comportamiento esperado | RF afectado |
|------|------------------------|-------------|
| Misma condición de alerta ocurre 100 veces en 5 minutos | Se emite 1 alerta inicial y, opcionalmente, 1 de cierre cuando deje de ocurrir. No 100 alertas. | RF-14 |
| Regla de alerta con umbral mal configurado (genera falsos positivos masivos) | El sistema seguirá emitiendo alertas hasta que un operador ajuste el umbral. Se documenta como riesgo operativo. | RF-8, RNF-7 |
| Servicio DL devuelve 500 pero no NaN (p. ej. modelo no cargado) | Detectar por código de respuesta y emitir alerta "ml-inference unhealthy". | RF-12 |

### Reconciliación

| Caso | Comportamiento esperado | RF afectado |
|------|------------------------|-------------|
| Documento lleva 24 h en `awaiting_patient_sync` y el paciente nunca llega | Emitir alerta "orphan record stale" pasado un umbral configurable. **[NEEDS CLARIFICATION]** umbral y política (mantener / archivar). | RF-16 |

## 6. Criterios de aceptación

### Watcher y predicción

- [ ] **CA-1** (cubre RF-1, RF-2): depositar una radiografía nueva en GridFS (simulando ingesta) sin más intervención produce, en un tiempo razonable, una predicción persistida asociada. Consistente con CA-18 de SDD-01.
- [ ] **CA-2** (cubre RF-3): depositar dos veces la misma radiografía (mismo hash) produce una sola predicción bajo la `model_version` activa.
- [ ] **CA-3** (cubre RF-15, caso borde "DL caído"): parar el servicio DL, depositar una radiografía, esperar el tiempo de reintentos, volver a arrancar DL: la radiografía acaba predicha sin intervención manual.

### Informe diario

- [ ] **CA-4** (cubre RF-4, RF-5, RF-6): forzar la ejecución de la tarea diaria (sin esperar al scheduler) produce un PDF y un JSON persistidos; el PDF es descargable vía API (SDD-05 CA-7) y el JSON tiene los campos esperados.
- [ ] **CA-5** (cubre RF-7, RNF-6): ejecutar la tarea dos veces consecutivas para el mismo día natural no deja dos informes activos; queda uno solo (sobrescrito o versionado).

### Alertas

- [ ] **CA-6** (cubre RF-8, RF-10, RF-11): disparar una predicción con `P(COVID-19)` por encima del umbral genera una alerta en la colección de alertas y una entrada de log con `type=email_simulated`.
- [ ] **CA-7** (cubre RF-14): simular 10 alertas idénticas en una ventana de 5 minutos produce **una única alerta** persistida.
- [ ] **CA-8** (cubre RF-12, RF-13): parar el servicio DL durante más que el intervalo de chequeo genera una alerta operativa `ml-inference unhealthy` con `correlation_id`.

### Reintento y robustez

- [ ] **CA-9** (cubre RNF-3, RNF-4): matar y relanzar el contenedor `automation` mientras hay tareas en vuelo termina procesando las tareas pendientes tras el rearranque (gracias a la persistencia del estado).
- [ ] **CA-10** (cubre RNF-5): depositar 3 radiografías con automation apagado; al encenderlo, las 3 quedan predichas.

### Reconciliación

- [ ] **CA-11** (cubre RF-16): insertar manualmente un documento de predicción con `pseudo_id` inexistente y luego crear el paciente en PostgreSQL: tras el siguiente ciclo de reconciliación, el documento pierde el flag `awaiting_patient_sync`.

### Configuración

- [ ] **CA-12** (cubre RNF-7): cambiar el umbral de alerta COVID vía variable de entorno y reiniciar el servicio aplica el nuevo umbral sin tocar código.

### Observabilidad

- [ ] **CA-13** (cubre RNF-8, RF-17): `docker compose logs automation` muestra eventos JSON por tarea con inicio/fin/resultado/`correlation_id`.

## 7. Dudas abiertas

- **[NEEDS CLARIFICATION]** **Orquestador**: cron + scripts Python (simple, suficiente para 1 servicio y 2-3 tareas) vs **Prefect** (más profesional, UI de jobs). Decisión en `DESIGN-04`. Recomendación por pragmatismo: cron + scripts si bastan 2-3 jobs; Prefect si la lista crece.
- **[NEEDS CLARIFICATION]** Mecanismo concreto del **watcher** (RF-1): polling de documentos `pending_prediction`, **Change Streams** de MongoDB, cola interna poblada por el pipeline. Trade-off simplicidad vs latencia.
- **[NEEDS CLARIFICATION]** Umbral `P(COVID-19)` para alerta (RF-8) — heredado de SDD-01 y SDD-06.
- **[NEEDS CLARIFICATION]** Umbrales de tasas anómalas (RF-9): tasa de rechazos máxima tolerada, volumen mínimo esperado por día.
- **[NEEDS CLARIFICATION]** Ventana de deduplicación de alertas (RF-14): ¿5 minutos, 1 hora, configurable por tipo?
- **[NEEDS CLARIFICATION]** Política de huérfanos `awaiting_patient_sync` cuando pasan N horas sin resolución (caso borde).
- **[NEEDS CLARIFICATION]** Para informe diario duplicado (RF-7): ¿sobrescribir o versionar? Afecta la respuesta de la API (¿un solo PDF por fecha o historial?).

## 8. Referencias

- Enunciado: `Enunciado-Hospital.pdf` §3.3 (automatización), §4.3 (alertas, monitorización)
- `CONTEXT.md` §3.3, §4.3
- Spec raíz: `specs/SDD-01-sistema.md`
- Especificaciones dependientes: `specs/SDD-02-pipeline.md`, `specs/SDD-03-almacenamiento.md`, `specs/SDD-05-api-dashboard.md`, `specs/SDD-06-modelo-dl.md`
- Diseño asociado: `specs/DESIGN-04-automatizacion.md` *(a crear)*
- SDD-07 (monitorización) — define el formato de log al que este servicio se adhiere
