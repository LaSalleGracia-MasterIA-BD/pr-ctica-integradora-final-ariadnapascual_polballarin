# SDD-05 — API (FastAPI) y Dashboard

> Spec del subsistema que **expone al personal hospitalario** los datos del sistema y la predicción del modelo DL. Define **qué operaciones y qué vistas** debe ofrecer. El diseño concreto de endpoints, esquemas de respuesta, estructura del frontend y tecnología del dashboard (Streamlit vs Grafana) va en `DESIGN-05-api-dashboard.md`.

---

**Versión:** 1.0
**Fecha:** 2026-04-20
**Autor:** Pol Ballarín
**Estado:** `ready-for-design`

---

## 1. Contexto y objetivo

### Contexto
El sistema necesita una **capa de servicio** que exponga los datos persistidos (pacientes, radiografías, predicciones, informes, alertas, agregados) y las operaciones relevantes al personal hospitalario. El enunciado §3.4 exige "visualización y comunicación de resultados" mediante gráficos, dashboards o informes interpretables. §4.2.4 pide "Servicio: datos procesados disponibles para consumo (API REST, dashboard, etc.)".

Se decide implementar **ambos**: una **API REST** con **FastAPI** (consistente con SDD-01, decisión ya tomada) como contrato estable, y un **Dashboard** como consumidor visual de esa API.

### Objetivo
Proveer:

1. Una **API REST con FastAPI** que ofrezca las operaciones necesarias sobre pacientes, radiografías, predicciones, informes, alertas y agregados. Con **OpenAPI automático**, tipado explícito (Pydantic) y **sin autenticación** (consistente con SDD-01 fuera-de-alcance — *"todo el mundo accede al dashboard"*).
2. Un **Dashboard** interactivo accesible desde navegador que consuma la API y muestre: listado de pacientes, detalle de radiografía con predicción, vistas agregadas (distribución de predicciones, radiografías por día, tabla de alertas), informes generados y estados vacíos coherentes.
3. Un contrato de **error HTTP limpio** (códigos estándar, mensajes legibles) y respuestas tipadas.

## 2. Actores y alcance

### Actores

| Actor | Tipo | Interacción |
|-------|------|-------------|
| **Personal hospitalario** | humano | Abre el dashboard en un navegador y consulta/sube radiografías |
| **Servicios internos** | máquina | Otros servicios (automation, scripts) pueden llamar a la API directamente |
| **Almacenamiento** *(SDD-03)* | dependencia | La API lee/escribe en PG y Mongo |
| **Servicio de inferencia** *(SDD-06)* | dependencia | La API delega las predicciones en `/predict` del servicio DL |
| **Logging centralizado** *(SDD-07)* | observador | Todas las peticiones quedan trazadas |

### Dentro del alcance

- **API REST FastAPI** con endpoints para: consulta de pacientes, consulta de radiografías con predicción, subida de radiografía (disparo de predicción a través del servicio DL), consulta de informes, consulta de alertas, vistas agregadas.
- **Documentación OpenAPI automática** (`/docs` y `/openapi.json`) sin configuración extra.
- **Dashboard web** con vistas mínimas de RF-14, RF-15, RF-16, RF-17 de SDD-01.
- **Contrato tipado** con Pydantic: modelos de entrada y salida explícitos.
- **Healthcheck** HTTP para compatibilidad con los healthchecks de Docker Compose (SDD-01 CA-1).
- **CORS** abierto para el dashboard (en local, mismo host; si dashboard y API corren en puertos distintos, configurado).

### Fuera del alcance

- **Autenticación y autorización** (JWT, OAuth2, API keys): consistente con SDD-01 fuera-de-alcance.
- **Rate limiting** y protección anti-DoS: demo local, no necesario.
- **Mutaciones del modelo clínico**: el API no permite editar ni borrar pacientes, ingresos o predicciones. Es principalmente **read-only**, con la única excepción de **subida de radiografía** y posibles marcados de alerta (p. ej. "vista").
- **Endpoints de administración** (re-seed, re-entrenamiento, reset): si existieran serían scripts aparte, no expuestos por la API.
- **WebSockets / Server-Sent Events** para notificaciones en tiempo real: el dashboard se actualiza con polling o al navegar.
- **Paginación cursor-based** sofisticada: basta con offset/limit.
- **Internacionalización**: el dashboard está en español.
- **Responsividad móvil**: se diseña para escritorio.

## 3. Requisitos funcionales

### Operaciones de la API

#### Sobre pacientes

- **RF-1**: La API debe exponer un endpoint que **liste pacientes** con filtros simples (rango de edad, sexo, rango de fecha de ingreso, nivel de triaje) y paginación por offset/limit.
- **RF-2**: La API debe exponer un endpoint que devuelva el **detalle de un paciente** por `pseudo_id`, incluyendo sus ingresos, sus radiografías asociadas con predicción y su **predicción de triaje** (SDD-08) cuando exista.
- **RF-2bis**: La API debe exponer un endpoint `POST /patients` que **acepte una ficha** con los campos auto-reportados definidos en SDD-08 RF-1 (formulario web de triaje pre-consulta). El endpoint entrega la ficha al pipeline en **modo online** (SDD-02 RF-24) y devuelve en la misma respuesta (a) el `pseudo_id` asignado, (b) la clase predicha de triaje con sus probabilidades por clase y la `model_version`, o (c) si el servicio de triaje no respondió a tiempo, una respuesta 202 con `status: pending_triage` y el `pseudo_id` para que el cliente consulte después.
- **RF-2ter**: La API debe exponer un endpoint `POST /batch-runs` que **acepte un CSV multi-ficha** (mismo esquema que el formulario, una fila por paciente). Sube el CSV a **S3 como raw** (patrón *landing zone*), dispara el pipeline en **modo batch** (SDD-02 RF-1 y siguientes) y devuelve `{run_id, status: started}`. El procesamiento sigue en background; el cliente consulta progreso por RF-2quater.
- **RF-2quater**: La API debe exponer `GET /batch-runs/{run_id}/events` que devuelva los **eventos de dominio** asociados al `run_id` (leídos de la colección `system_events` de MongoDB, SDD-03 RF-10), ordenados cronológicamente, para que el dashboard muestre el progreso en tiempo real con polling. Debe incluir `timestamp`, `event`, `level`, `message` y contadores (`records_in`, `records_out`, etc.).
- **RF-2quinquies**: La API debe exponer `GET /batch-runs` listando runs recientes con su estado (`running | completed | failed`) y resumen.

#### Sobre radiografías y predicciones

- **RF-3**: La API debe exponer un endpoint que liste **radiografías** con filtros (rango de fecha, clase predicha, `pseudo_id` de paciente), paginado.
- **RF-4**: La API debe exponer un endpoint que devuelva el **detalle de una radiografía** por `id`: metadatos, **bytes de la imagen** (o URL interna para servirla), predicción asociada con probabilidades por clase, `model_version` y metadatos de trazabilidad (`source`, `ingested_at`, `processed_by`).
- **RF-5**: La API debe exponer un endpoint **de subida** que acepte una imagen (multipart/form-data) y metadatos opcionales (`pseudo_id`, motivo), persista la imagen en GridFS (vía SDD-03), dispare la predicción contra el servicio de inferencia (SDD-06) y devuelva el resultado completo en la respuesta **o** un `id` de seguimiento si se procesa asíncronamente. Decisión concreta en `DESIGN-05`.

#### Sobre informes y alertas

- **RF-6**: La API debe exponer un endpoint que **liste informes diarios** persistidos (PDF + JSON) con rango de fechas.
- **RF-7**: La API debe permitir **descargar** un informe PDF concreto.
- **RF-8**: La API debe exponer un endpoint que **liste alertas**, con filtros por tipo, severidad y rango temporal, paginado.

#### Sobre agregados

- **RF-9**: La API debe exponer endpoints de **agregados** listos para el dashboard: distribución de predicciones por clase en un rango, número de radiografías por día, número de registros inválidos por fuente, top de alertas por tipo.

### Estándares y observabilidad

- **RF-10**: La API debe exponer `/docs` con la **documentación OpenAPI** autogenerada por FastAPI.
- **RF-11**: La API debe exponer `/healthz` devolviendo 200 cuando puede alcanzar PG, Mongo y (opcionalmente) el servicio de inferencia. 503 en otro caso.
- **RF-12**: Todo endpoint debe emitir logs estructurados con `correlation_id` (cabecera o propio) compatible con SDD-07.
- **RF-13**: Todas las respuestas (200 y errores) son **JSON** con esquema documentado vía Pydantic y reflejado en OpenAPI.

### Dashboard

- **RF-14**: El dashboard debe ser accesible en una URL documentada en el README, **sin credenciales**.
- **RF-15**: La vista **Pacientes** muestra la lista paginada con filtros (consumiendo RF-1) y permite abrir el detalle (RF-2).
- **RF-16**: La vista **Radiografías** muestra la lista con filtros (consumiendo RF-3) y, al abrir una, muestra la **imagen**, la **predicción** con probabilidades por clase y los **metadatos** (consumiendo RF-4).
- **RF-17**: La vista **Agregados** muestra al menos tres gráficos alimentados por RF-9: distribución de predicciones (barras o pie), radiografías por día (línea o barras) y tabla de alertas emitidas.
- **RF-18**: La vista **Informes** permite listar y descargar informes diarios (consumiendo RF-6, RF-7).
- **RF-19**: La vista **Subir radiografía** permite a un usuario elegir un fichero, enviarlo al endpoint RF-5 y mostrar la predicción en la propia página cuando llegue.
- **RF-19bis**: La vista **Triaje pre-consulta** (formulario web del paciente) ofrece un **formulario** con los ~14 campos auto-reportados definidos en SDD-08 RF-1, lo envía al endpoint `POST /patients` (RF-2bis) y muestra una **página de confirmación** con el nivel de triaje predicho *(Alta / Media / Baja)*, un mensaje contextual apropiado y una nota explícita que indica que es **apoyo a la decisión**, no diagnóstico.
- **RF-19ter**: La vista **Carga por lotes (CSV)** permite al usuario subir un CSV con múltiples fichas (mismo esquema que el formulario). Al enviar, llama al endpoint `POST /batch-runs` (RF-2ter) y navega a la vista "Seguimiento de run".
- **RF-19quater**: La vista **Seguimiento de run** muestra una **timeline de eventos de dominio** del `run_id` obtenidos por polling de `GET /batch-runs/{run_id}/events` (RF-2quater). Renderiza iconos por nivel (`info`, `warning`, `error`), contadores (filas leídas, inválidas, triaje aplicado, carga) y un **resumen final** cuando llega el evento `pipeline.run.end`. Auto-refresca cada 1–2 s hasta que el run termine.
- **RF-20**: Todas las vistas muestran un **estado vacío coherente** cuando no hay datos (consistente con SDD-01 caso borde "dashboard antes de la primera ingesta").

### Decisión tecnológica del dashboard

- **RF-21**: La spec deja abierta la **tecnología del dashboard** entre dos candidatos: **Streamlit** (Python puro, rápido para demo; **recomendado**) y **Grafana** (métricas/monitorización). Decisión en `DESIGN-05`. Los requisitos funcionales del dashboard son agnósticos a la tecnología elegida.

## 4. Requisitos no funcionales

### Rendimiento

- **RNF-1**: Los endpoints de lista (pacientes, radiografías, alertas) deben responder en tiempo razonable para tamaños de base esperados. **[NEEDS CLARIFICATION]** umbral concreto — ligado a SDD-01 RNF-1/RNF-2.
- **RNF-2**: El endpoint de subida + predicción (RF-5) no debe superar el tiempo presupuestado para una predicción end-to-end (ligado a SDD-06 RNF-1).

### Tipado y documentación

- **RNF-3**: Todos los endpoints están tipados con Pydantic; OpenAPI se genera automáticamente sin anotaciones manuales.
- **RNF-4**: La documentación de `/docs` incluye ejemplos de request y response por cada endpoint.

### Robustez

- **RNF-5**: Peticiones inválidas devuelven 400/422 con detalle; peticiones a recursos inexistentes devuelven 404; errores internos devuelven 500 con identificador opaco y log correlacionado (sin stack trace al cliente).
- **RNF-6**: La API debe tolerar la **indisponibilidad temporal** de sus dependencias: si MongoDB o PostgreSQL están caídos, los endpoints afectados devuelven 503 con mensaje claro; no tiran la API entera.

### Compatibilidad

- **RNF-7**: El dashboard debe funcionar en las últimas versiones estables de **Chrome, Firefox y Edge** (consistente con SDD-01 RNF-15).

### Mantenibilidad

- **RNF-8**: El código de la API y del dashboard viven en `services/api/` y `services/dashboard/` respectivamente, cada uno con su Dockerfile y `requirements.txt` pinneado.
- **RNF-9**: Los endpoints de agregados **no duplican lógica** del pipeline: delegan en las colecciones de agregados persistidas por el pipeline (SDD-02 RF-13). La API es fina; no recomputa.

### Seguridad operativa

- **RNF-10**: El dashboard y la API **no exponen** credenciales ni variables de entorno en respuestas ni en logs.
- **RNF-11**: CORS configurado solo para los orígenes necesarios del dashboard.

## 5. Casos borde / errores

### Peticiones inválidas

| Caso | Comportamiento esperado | RF afectado |
|------|------------------------|-------------|
| Filtro de fecha con formato inválido | 422 con detalle del campo. | RF-1, RF-3, RF-8 |
| `pseudo_id` inexistente en detalle de paciente | 404 con cuerpo explicativo. | RF-2 |
| `id` de radiografía inexistente | 404. | RF-4 |
| Subida sin fichero | 422. | RF-5 |
| Subida con fichero no-imagen | 415 Unsupported Media Type. | RF-5, caso borde SDD-01 |
| Subida con imagen > 10 MB | 413 Payload Too Large. | RF-5, RNF-7 SDD-01 |

### Dependencias

| Caso | Comportamiento esperado | RF afectado |
|------|------------------------|-------------|
| MongoDB no disponible | Endpoints que lo usen devuelven 503 con `{"detail": "storage unavailable"}`; `/healthz` devuelve 503. | RNF-6 |
| PostgreSQL no disponible | Idem MongoDB. | RNF-6 |
| Servicio de inferencia no disponible al hacer `POST /upload` | Persistir la radiografía en estado `pending_prediction` (consistente con caso borde SDD-01) y devolver 202 Accepted con `id` y `status: pending`. El dashboard hará polling para la predicción. | RF-5, RF-19 |

### Dashboard

| Caso | Comportamiento esperado | RF afectado |
|------|------------------------|-------------|
| Carga del dashboard con base vacía | Mostrar "aún no hay datos" en cada vista; sin errores en consola. | RF-20 |
| API no disponible al cargar el dashboard | Mostrar banner global "servicio no disponible, reintentando…"; no crashear la UI. | RNF-6 |
| Upload desde dashboard de imagen > 10 MB | Rechazar en cliente antes de enviar, o mostrar mensaje claro si el backend responde 413. | RF-19 |

### Paginación y volumen

| Caso | Comportamiento esperado | RF afectado |
|------|------------------------|-------------|
| Lista con 100 000 registros | La API aplica límite máximo de página (p. ej. `limit ≤ 100`), no devuelve todo. | RF-1, RF-3, RF-8 |
| `offset` absurdo (negativo, enorme) | 422 para negativo; lista vacía para grande. | RF-1, RF-3 |

## 6. Criterios de aceptación

### API — disponibilidad y documentación

- [ ] **CA-1** (cubre RF-10, RNF-3): `curl http://api:8000/docs` devuelve la documentación OpenAPI de Swagger UI. `curl http://api:8000/openapi.json` devuelve el esquema JSON válido.
- [ ] **CA-2** (cubre RF-11): `curl http://api:8000/healthz` devuelve 200 cuando PG y Mongo están sanos; 503 si cualquiera de los dos no está disponible.

### API — pacientes y radiografías

- [ ] **CA-3** (cubre RF-1, RF-2): `GET /patients?limit=10` devuelve una lista JSON con 10 pacientes o menos. `GET /patients/{pseudo_id}` devuelve el detalle con ingresos y radiografías asociadas.
- [ ] **CA-4** (cubre RF-3, RF-4): `GET /radiographs?limit=10` devuelve lista. `GET /radiographs/{id}` devuelve detalle con URL o bytes de la imagen, predicción y metadatos.
- [ ] **CA-5** (cubre RF-5, caso borde "inferencia no disponible"): `POST /radiographs` con un JPG válido devuelve 201 con predicción completa si el servicio DL responde, o 202 con `status: pending` si el servicio DL está caído.
- [ ] **CA-6** (cubre RF-5, RNF-5, casos borde): `POST /radiographs` con un `.txt` devuelve 415; con imagen > 10 MB devuelve 413; sin fichero devuelve 422.

### API — informes, alertas, agregados

- [ ] **CA-7** (cubre RF-6, RF-7): `GET /reports?from=...&to=...` lista informes diarios; `GET /reports/{date}/pdf` devuelve un PDF descargable.
- [ ] **CA-8** (cubre RF-8): `GET /alerts` lista alertas con filtros por tipo y rango.
- [ ] **CA-9** (cubre RF-9): `GET /aggregates/predictions?from=...&to=...` devuelve el conteo por clase listo para gráfico.

### API — contrato y errores

- [ ] **CA-10** (cubre RF-13, RNF-5): todas las respuestas son JSON válido; las 5xx tienen un `detail` genérico y un `correlation_id` que aparece también en los logs.

### Dashboard

- [ ] **CA-11** (cubre RF-14): el dashboard carga en la URL del README sin credenciales.
- [ ] **CA-12** (cubre RF-15, RF-16): desde la vista Pacientes se navega al detalle; desde Radiografías se navega al detalle con imagen visible y predicción mostrada.
- [ ] **CA-13** (cubre RF-17): la vista Agregados muestra los tres gráficos mínimos (distribución, radiografías/día, tabla de alertas).
- [ ] **CA-14** (cubre RF-18): desde la vista Informes se descarga un PDF existente.
- [ ] **CA-15** (cubre RF-19): subir una radiografía desde la vista de subida muestra la predicción en la misma página tras recibirla.
- [ ] **CA-16** (cubre RF-20): con la base vacía, todas las vistas cargan sin errores y muestran estados vacíos legibles.

### Robustez

- [ ] **CA-17** (cubre RNF-6): parar MongoDB durante 30 s deja al dashboard con banner de error controlado; al volver, la navegación vuelve a funcionar sin recargar el servicio.

### Observabilidad

- [ ] **CA-18** (cubre RF-12): `docker compose logs api` muestra una línea JSON por petición con método, ruta, código, duración y `correlation_id`.

## 7. Dudas abiertas

- **[NEEDS CLARIFICATION]** **Tecnología del dashboard**: Streamlit vs Grafana (RF-21). Streamlit es más directo para demo con Python y FastAPI; Grafana pesa más hacia métricas y observabilidad. Decisión en `DESIGN-05`. Recomendación: Streamlit.
- **[NEEDS CLARIFICATION]** `POST /radiographs` (RF-5): ¿**síncrono** (devuelve predicción en la respuesta) o **asíncrono** (devuelve 202 y el cliente consulta estado)? La spec acepta ambos; el diseño decide según el tiempo de inferencia medido.
- **[NEEDS CLARIFICATION]** Umbrales concretos de rendimiento (RNF-1, RNF-2) — heredados de SDD-01.
- **[NEEDS CLARIFICATION]** Formato exacto de las URL de la imagen (bytes inline en el JSON vs endpoint dedicado `/radiographs/{id}/image`). Decisión de diseño.

## 8. Referencias

- Enunciado: `Enunciado-Hospital.pdf` §3.4 (visualización), §4.2.4 (servicio)
- `CONTEXT.md` §3.4, §4.2
- Spec raíz: `specs/SDD-01-sistema.md`
- Diseño asociado: `specs/DESIGN-05-api-dashboard.md` *(a crear)*
- SDDs relacionados: SDD-03 (persistencia que se consulta), SDD-06 (servicio DL que se invoca), SDD-04 (actor secundario — llama a la API), SDD-07 (logs)
- [FastAPI docs](https://fastapi.tiangolo.com/) — referencia externa
