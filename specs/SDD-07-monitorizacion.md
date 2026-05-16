# SDD-07 — Monitorización, logging centralizado y calidad de datos

> Spec **transversal** del subsistema de observabilidad: logging centralizado, validación de calidad de datos y alertas ante fallos del procesamiento. Exigido por §4.3 del enunciado. El diseño de stack concreto (solo stdout + `docker compose logs`, o Loki/Promtail, o Grafana) va en `DESIGN-07-monitorizacion.md`.

---

**Versión:** 1.0
**Fecha:** 2026-04-20
**Autor:** Pol Ballarín
**Estado:** `ready-for-design`

---

## 1. Contexto y objetivo

### Contexto
El enunciado §4.3 exige tres cosas concretas: **logging centralizado de los procesos del pipeline**, **validación de calidad de datos** (incompletos, duplicados, corruptos) y **alertas/notificaciones ante fallos en el procesamiento** (log, email simulado o entrada en dashboard).

Estas responsabilidades atraviesan **todos los servicios** del sistema (pipeline, modelo DL, API, dashboard, automation). Este SDD define el **contrato común** que cada servicio debe cumplir para ser observable y el **mecanismo central** que los agrega.

### Objetivo
Proveer una capa transversal de observabilidad que:

1. Estandarice el **formato de log estructurado** (JSON) que emiten todos los servicios, con los campos mínimos obligatorios.
2. Propague un **`correlation_id`** a lo largo de una operación que cruza varios servicios (p. ej. ingesta → limpieza → carga → predicción → alerta), de modo que una traza humana sea trivial.
3. Centralice la **consulta de logs** de todos los servicios con un comando documentado (`docker compose logs` o un visor más amigable si se adopta Loki/Grafana).
4. Defina y haga efectiva una **batería de reglas de calidad de datos** aplicadas en las puertas relevantes del sistema (ingesta, transformación, carga).
5. Coordine con SDD-04 la **emisión de alertas de fallo** cuando el procesamiento se desvíe de lo esperado.

## 2. Actores y alcance

### Actores

| Actor | Dirección | Rol |
|-------|-----------|-----|
| **Pipeline** *(SDD-02)* | emisor | Produce logs y eventos de dominio en cada fase |
| **Modelo DL** *(SDD-06)* | emisor | Logs por petición, métricas de latencia |
| **API / Dashboard** *(SDD-05)* | emisor | Logs de acceso, logs de errores |
| **Automation** *(SDD-04)* | emisor | Logs de tareas y de emisión de alertas |
| **Almacenamiento** *(SDD-03)* | emisor indirecto | Logs propios de los contenedores PG / Mongo (stdout) |
| **Operador** *(Pol durante desarrollo y demo)* | consumidor | Ejecuta `docker compose logs` o el visor para inspeccionar |
| **Dashboard** *(SDD-05)* | consumidor parcial | Recibe alertas operativas emitidas por automation |

### Dentro del alcance

- **Contrato de formato de log** (JSON estructurado, campos mínimos obligatorios, niveles).
- **Propagación de `correlation_id`** entre servicios.
- **Centralización** de la consulta: cómo se ven los logs de todos los servicios desde un único comando o visor.
- **Catálogo de reglas de calidad de datos** aplicables en las tres puertas: ingesta (SDD-02 RF-5), transformación (SDD-02 RF-9), carga (SDD-03 RF-9, RF-10).
- **Política de niveles de log** (DEBUG, INFO, WARNING, ERROR, CRITICAL) y qué se loguea en cada uno.
- **Alertas de fallo del procesamiento** (coordinación con SDD-04 RF-12, RF-13).

### Fuera del alcance

- **Métricas tipo Prometheus** con dashboards de rendimiento detallados: no exigido por el enunciado; se documenta como mejora opcional si hay tiempo.
- **Tracing distribuido avanzado** (OpenTelemetry con spans, Jaeger): el `correlation_id` propagado por logs cubre el caso sin la sobrecarga.
- **Auditoría de seguridad** / SIEM.
- **Alertas de negocio** derivadas de predicciones (p. ej. COVID-19): responsabilidad de SDD-04. Aquí solo alertas **operativas**: fallos, servicios caídos, calidad de datos degradada.
- **Agregación de logs fuera del host** (en cloud): demo local.
- **PII scrubbing avanzado** con regex complejos: basta con la regla de RNF-9 de SDD-01 (no loguear contenido binario ni datos clínicos sensibles — el código **no los manda**, no los filtra a posteriori).

## 3. Requisitos funcionales

### Formato y contrato de log

- **RF-1**: Cada servicio debe emitir logs en **formato JSON estructurado** (una línea JSON por evento) a **stdout**, con los siguientes campos **mínimos obligatorios**:
  - `ts` (ISO-8601 con microsegundos)
  - `level` (`DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL`)
  - `service` (nombre del servicio: `pipeline`, `api`, `ml-inference`, `automation`, etc.)
  - `correlation_id` (cadena; si no hay, se genera uno local para la operación)
  - `event` (etiqueta corta describiendo la operación: `ingest.start`, `prediction.done`, `alert.emitted`, …)
  - `message` (texto legible humano)
  - Campos adicionales libres según el evento (`duration_ms`, `records_in`, `records_out`, `error_code`, `radiograph_id`, …).
- **RF-2**: Ninguna línea de log debe contener datos personales directamente identificables (consistente con SDD-01 RNF-9) ni contenido binario de radiografías. Los datos clínicos sensibles se referencian siempre por `pseudo_id`.
- **RF-3**: Los logs en nivel `DEBUG` pueden incluir información de desarrollo adicional; deben poder **desactivarse** globalmente por variable de entorno en demo o producción.

### Propagación de `correlation_id`

- **RF-4**: Cuando un servicio recibe una petición HTTP entrante que lleva la cabecera `X-Correlation-ID`, debe usar ese valor. Si no viene, debe **generar uno** (UUID) al inicio de la operación.
- **RF-5**: Cuando un servicio hace una petición saliente a otro servicio (p. ej. API → ml-inference; automation → API), debe **propagar** el `correlation_id` activo vía `X-Correlation-ID`.
- **RF-6**: Los jobs batch del pipeline y del automation, aunque no sean HTTP, deben crear un `correlation_id` al inicio del run y usarlo consistentemente en todos los logs y eventos de dominio emitidos durante ese run.

### Centralización y consulta

El sistema ofrece **dos vistas distintas y complementarias** según el destinatario:

- **Logs técnicos** (destinatarios: operador técnico): JSON de stdout de todos los servicios, centralizados en **Loki + Promtail** (ya incluidos en `docker-compose.yml`). Útil para depurar excepciones, medir latencia, auditar el sistema. Consulta vía `docker compose logs` o la API HTTP de Loki (p. ej. Grafana como visor si se añade, o `curl` directo).
- **Eventos de dominio** (destinatarios: usuario del dashboard): documentos estructurados en la colección `system_events` de MongoDB (SDD-03 RF-10). Representan hitos de negocio: *"Ingesta iniciada"*, *"5 000 filas leídas"*, *"3 rechazadas"*, *"Carga completada"*. Se visualizan en el dashboard como **timeline** por `run_id` (SDD-05 RF-19quater) y alimentan los KPIs del informe diario (SDD-04).

- **RF-7**: Todos los servicios aplicativos envían logs técnicos a **stdout**; Docker los recoge. Loki + Promtail los centraliza; el operador consulta con `docker compose logs` como mínimo común, y con Loki HTTP API para filtros avanzados.
- **RF-8**: El README del proyecto debe documentar al menos un comando o URL para consultar los logs centralizados, incluyendo ejemplo de filtrado por `correlation_id` o por servicio.
- **RF-9**: Loki (puerto 3100) está arrancado por el mismo `docker compose up` y es accesible desde navegador sin credenciales (consistente con SDD-01).
- **RF-9bis**: La API (SDD-05 RF-2quater) expone los **eventos de dominio** filtrados por `run_id` para alimentar la vista de seguimiento del dashboard. Los eventos técnicos (Loki) y los de dominio (Mongo) **son emisiones paralelas y deliberadas** — un mismo hito del pipeline emite ambos (el técnico con detalles de debug, el de dominio con mensaje legible).

### Reglas de calidad de datos

- **RF-10**: El sistema debe aplicar, como mínimo, las siguientes **reglas de calidad** en las puertas relevantes (ingesta en SDD-02, carga en SDD-03, predicción en SDD-06):
  - **Campos obligatorios presentes** (no nulos) según el esquema lógico de cada entidad.
  - **Valores dentro de dominio** (p. ej. sexo en un conjunto cerrado; edad entre 0 y 120; `predicted_class` en *{Sana, Neumonía, COVID-19}*).
  - **Duplicados por clave lógica** detectados y gestionados.
  - **Timestamps coherentes**: no futuros (> ahora + tolerancia razonable), no anteriores a una fecha mínima plausible (p. ej. > 1900-01-01).
  - **Imágenes corruptas o formato inválido**: rechazadas antes de persistir.
- **RF-11**: Cada incumplimiento de regla produce un **evento de calidad** en los logs (con `level=WARNING` o `ERROR` según severidad) y, si el registro se rechaza, una entrada en la colección de rechazos (SDD-03 RF-3).
- **RF-12**: El sistema debe poder producir, bajo demanda (o como parte del informe diario de SDD-04), un **resumen de calidad** por ventana temporal: conteo de rechazos por regla incumplida, por fuente, por servicio.

### Alertas de fallo de procesamiento

- **RF-13**: El sistema debe emitir una alerta operativa (coordinación con SDD-04 RF-12, RF-13) cuando se den cualquiera de las siguientes condiciones:
  - Un **run del pipeline** termina con error crítico.
  - El **servicio de inferencia** está no saludable durante más de un intervalo configurable (chequeo de `/healthz`).
  - Una **base de datos** (PostgreSQL o MongoDB) deja de estar accesible para los servicios aplicativos.
  - La **tasa de rechazos** en una ventana temporal supera un umbral configurable.
- **RF-14**: Las alertas operativas se persisten en la colección de alertas con `severity=operational` (distinta de `severity=clinical` de las alertas de negocio) y se loguean con `level=ERROR` o `CRITICAL`.

### Política de niveles

- **RF-15**: Los niveles de log se usan consistentemente:
  - **DEBUG**: detalle de desarrollo, desactivable en despliegue estable.
  - **INFO**: eventos normales del sistema (inicio/fin de fase, petición servida, predicción hecha).
  - **WARNING**: situaciones recuperables que merecen atención (registro rechazado, reintento con éxito).
  - **ERROR**: fallo de una operación concreta pero no del sistema (tarea agotada, 500 HTTP).
  - **CRITICAL**: fallo que degrada el sistema entero (BD caída, modelo no cargado).

## 4. Requisitos no funcionales

### Overhead

- **RNF-1**: El coste del logging en tiempo normal de operación debe ser despreciable respecto al tiempo de la operación logueada. Un log por petición HTTP es aceptable; uno por fila de un CSV de 10 000 no.
- **RNF-2**: El logging de nivel `INFO` **no** debe afectar visiblemente la latencia percibida en la API (RNF-1 de SDD-05).

### Persistencia

- **RNF-3**: Los logs persisten **al menos** mientras los contenedores están corriendo (Docker los conserva en su driver por defecto). Si se monta volumen para logs, debe documentarse; si no, el borrado con `docker compose down` afecta el histórico.
- **RNF-4**: La retención de logs no es un requisito estricto para la demo; se documenta como limitación.

### Privacidad

- **RNF-5**: Consistente con SDD-01 RNF-9: los logs no contienen bytes de imágenes ni datos clínicos sensibles. Referencia por `pseudo_id` e `id` de radiografía siempre.

### Configurabilidad

- **RNF-6**: El **nivel de log** global (y por servicio, si procede) se controla con variables de entorno (`LOG_LEVEL` o similar); no hardcodeado.
- **RNF-7**: Los **umbrales de alerta operativa** (RF-13) son configurables por variable de entorno o fichero declarativo (consistente con SDD-04 RNF-7).

### Integración

- **RNF-8**: El formato de log debe ser **parseable** por herramientas estándar sin configuración ad-hoc: `jq`, filtros de Grafana/Loki, `cat | python -m json.tool`.

## 5. Casos borde / errores

### Logging

| Caso | Comportamiento esperado | RF afectado |
|------|------------------------|-------------|
| Un servicio lanza una excepción no capturada | La excepción se loguea con `level=ERROR` o `CRITICAL`, incluyendo traceback y `correlation_id` activo. El servicio no silencia el fallo. | RF-1, RF-15 |
| Un servicio loguea antes de que exista `correlation_id` | Se genera uno local y se etiqueta como `correlation_id=system-<uuid>`. | RF-4, RF-6 |
| Log saturado (cientos por segundo) | Docker tolera el volumen; si el stack se adopta con Loki, rate-limit documentado. Para demo basta. | RNF-1 |
| Intento accidental de loguear un byte-stream de imagen | El código que hace el log **no debe incluir** el contenido binario; la revisión de código lo detecta (el sistema por diseño no lo hace). | RF-2, RNF-5 |

### Correlation ID

| Caso | Comportamiento esperado | RF afectado |
|------|------------------------|-------------|
| Petición HTTP sin cabecera `X-Correlation-ID` | El servicio genera uno y lo devuelve en la respuesta para el cliente. | RF-4 |
| Llamada saliente a otro servicio sin `correlation_id` en scope | Se genera uno local y se propaga; se loguea con flag indicando "origen sintético". | RF-5 |
| Dos runs simultáneos del pipeline | Cada uno lleva su propio `correlation_id` independiente; no hay conflicto. | RF-6 |

### Calidad de datos

| Caso | Comportamiento esperado | RF afectado |
|------|------------------------|-------------|
| CSV con 300 registros, los 300 rechazados por la misma regla | Log WARNING consolidado (o uno por registro según política), conteo total emitido al final. Alerta operativa si supera umbral configurable (RF-13). | RF-10, RF-11, RF-13 |
| Imagen rechazada por formato ya rechazada 10 veces en 5 min | Deduplicar alerta operativa vía SDD-04 RF-14. | RF-13 |
| Regla nueva introducida tras un release | Los rechazos que antes pasaban ahora se bloquean; el informe diario reflejará el cambio. Documentar como parte de la release en CHANGELOG. | RF-10 |

### Alertas operativas

| Caso | Comportamiento esperado | RF afectado |
|------|------------------------|-------------|
| BD no disponible 10 s | Si el healthcheck pasa antes de disparar (intervalo superior a 10 s), no hay alerta. Si falla, alerta operativa con recuperación detectada al volver. | RF-13 |
| ml-inference no saludable 2 min | Alerta operativa "ml-inference unhealthy"; al volver a estar sana, alerta de recuperación. | RF-13 |

## 6. Criterios de aceptación

### Formato y centralización

- [ ] **CA-1** (cubre RF-1, RNF-8): `docker compose logs api | head -n 5 | jq .` produce cinco objetos JSON bien formados con los campos mínimos (`ts`, `level`, `service`, `correlation_id`, `event`, `message`).
- [ ] **CA-2** (cubre RF-7, RF-8): el README documenta al menos un comando que muestra los logs de **todos** los servicios unificados, con ejemplo de filtrado por `correlation_id` y por `service`.
- [ ] **CA-3** (cubre RF-15): una ejecución de prueba muestra logs con los 5 niveles usados coherentemente (no todo `INFO`, no todo `ERROR`).

### Correlation ID

- [ ] **CA-4** (cubre RF-4, RF-5): una petición a `POST /radiographs` con cabecera `X-Correlation-ID: test-123` produce, en los logs de `api`, `ml-inference` y `automation`, al menos una línea cada uno con ese `correlation_id`.
- [ ] **CA-5** (cubre RF-6): un run del pipeline produce todas las líneas del run bajo un único `correlation_id`, distinto de `system-*`.

### Privacidad de logs

- [ ] **CA-6** (cubre RF-2, RNF-5): una revisión manual (o automática vía grep) de 1 000 líneas de log de una ejecución de prueba no encuentra bytes de imagen ni campos identificativos (nombre, DNI).

### Reglas de calidad

- [ ] **CA-7** (cubre RF-10, RF-11): forzar la ingesta de un CSV con registros que violan cada una de las 5 categorías de reglas produce, en los logs, 5 eventos WARNING distintos (uno por categoría) y entradas correspondientes en la colección de rechazos.
- [ ] **CA-8** (cubre RF-12): consultar el resumen de calidad (endpoint, informe o comando documentado) devuelve conteos por regla incumplida, por fuente y por servicio, coherentes con los logs.

### Alertas operativas

- [ ] **CA-9** (cubre RF-13): parar `ml-inference` durante más tiempo que el intervalo del chequeo produce una alerta operativa persistida con `severity=operational` y una línea de log `level=ERROR`.
- [ ] **CA-10** (cubre RF-13): parar MongoDB durante el procesamiento produce alerta operativa y log `level=CRITICAL`; al recuperarse, alerta de "back to healthy".

### Configuración

- [ ] **CA-11** (cubre RNF-6, RNF-7): cambiar `LOG_LEVEL=DEBUG` en `.env` y reiniciar muestra logs DEBUG; cambiar umbral de tasa de rechazos y reiniciar aplica el nuevo umbral en las alertas operativas.

## 7. Dudas abiertas

- **[NEEDS CLARIFICATION]** **Backend concreto** de logging centralizado: ¿nos quedamos con `docker compose logs` (cero dependencias) o adoptamos **Loki + Promtail + Grafana** (más profesional, más peso)? Decisión en `DESIGN-07`. Recomendación: `docker compose logs` + `jq` es suficiente para la demo; Loki/Grafana si tenemos tiempo y ya levantamos Grafana por otros motivos.
- **[NEEDS CLARIFICATION]** Intervalo concreto de chequeo de salud de servicios para alertas operativas (RF-13): ¿30 s? ¿1 min? Decisión en `DESIGN-04`/`DESIGN-07`.
- **[NEEDS CLARIFICATION]** Umbral concreto de **tasa de rechazos** que dispara alerta operativa (RF-13).
- **[NEEDS CLARIFICATION]** Volumen de retención de logs: para la demo `docker compose` por defecto es suficiente; ¿montamos volumen dedicado para histórico de 7 días? Depende de si se adopta Loki.
- **[NEEDS CLARIFICATION]** ¿Los logs de PostgreSQL y MongoDB (que siguen sus propios formatos) se parsean al formato JSON común o se dejan en bruto? Propuesta: dejarlos como vengan; solo nuestros servicios aplicativos emiten en JSON.

## 8. Referencias

- Enunciado: `Enunciado-Hospital.pdf` §4.3 (monitorización y calidad de datos)
- `CONTEXT.md` §4.3
- Spec raíz: `specs/SDD-01-sistema.md`
- SDDs que emiten logs y eventos: `specs/SDD-02-pipeline.md`, `specs/SDD-03-almacenamiento.md`, `specs/SDD-04-automatizacion.md`, `specs/SDD-05-api-dashboard.md`, `specs/SDD-06-modelo-dl.md`
- Diseño asociado: `specs/DESIGN-07-monitorizacion.md` *(a crear)*
