# 03 — ETL pipeline batch y online

## Contexto

El enunciado §4.2 exige un pipeline en 4 fases — **ingesta → limpieza → transformación → análisis** — con un framework distribuido/escalable. Mi profesor autorizó explícitamente **pandas** como excepción (más fácil para el equipo, volumen manejable en memoria). El pipeline tenía que soportar dos modos: batch (CSV grandes) y online (una ficha del formulario web con triaje en vivo).

## Prompts clave

> Que es el etl batch? Que podamos uplodear un dataset con varias fichas de pacientes y analice todas y de el resultado para todas o que?

*Pregunta conceptual. La IA respondió con una tabla comparando batch vs online (qué procesa, cuándo, disparador, reglas compartidas, invocación del modelo) y confirmó que el caso que yo describía es exactamente **batch**.*

> Si, al final es eso, tendremos el formulario o la opción de subir un csv para multiples fichas tecnicas, entonces deberiamos ver el proceso con sus logs, recuerda que lo pide el enunciado, tenemos que poder ver los logs en el dashboard

*Requisito nuevo que obligó a un diseño explícito.* La IA propuso distinguir **dos tipos de log distintos**:
- **Logs técnicos** (stdout JSON, recogidos por Loki/Promtail) → destinatario: operador.
- **Eventos de dominio** (colección `system_events` en Mongo) → destinatario: usuario del dashboard, con mensajes en español legibles.*

*Esto tiene impacto arquitectónico:* SDD-07 se actualizó con la separación, SDD-05 añadió tres endpoints nuevos (`POST /batch-runs`, `GET /batch-runs/{run_id}/events`, `GET /batch-runs`), y la API empezó a emitir `system_events` **paralelos** a los logs técnicos por cada evento relevante. La timeline del dashboard se alimenta de esos eventos de dominio.*

> Y cuando ponemos las reglas del ETL?

*Mi pregunta revela que no había visto el `validation_rules.yaml`. La IA aclaró que las reglas ya estaban puestas (commit `7f2ed89`) y explicó el formato: YAML declarativo con tipos, min/max, patrones regex, enums, cross-field rules, política de dedup. El propio smoke test de ese momento estaba **validando las reglas**: rechazaba 99 de 100 filas por un bug de YAML (`no` sin comillas → booleano False).*

> Pero podemos reducir peso tambien, por ejemplo los booleanos cambiarlos a 0 o 1 sabes? el si o no a 0 o 1, o sexo hombre mujer a 0 o 1 entiendes?

*Propuesta de optimización prematura.* La IA **se opuso** razonadamente:
- Muchos enums no son binarios (sexo tiene 3 valores, fumador 3, embarazo 3, motivo 7, dificultad respiratoria 4…).
- Ahorro real con 10k filas: ~1-2 MB, despreciable frente a TOAST de PostgreSQL.
- PostgreSQL ya tiene `ENUM` nativo que almacena como int interno pero devuelve string — no hay trade-off.
- Perderíamos legibilidad (`SELECT * FROM pacientes` devuelve `sexo=0` en vez de `'M'`).*

> Pues no toquemos nada, que toca hacer ahora?

*Aceptación del argumento. Lección: a veces pedir una optimización vale la pena aunque no se haga, solo por aprender por qué no.*

## Lo que produjo la IA

1. **DESIGN-02** (pipeline) cerrando 4 de 5 `[NEEDS CLARIFICATION]` de SDD-02 con decisiones concretas: volumen 10k/1min, orquestación cron+scripts (Prefect diferido), dedup `first_wins`, reglas en YAML.
2. **Scaffolding completo** de `services/pipeline/`:
   - `app/config.py` con `Settings` Pydantic (lee envs, expone URIs derivadas).
   - `app/logging_setup.py` con `JsonFormatter` + `correlation_id` via `ContextVar`.
   - `app/events.py` con `emit_event()` — función que persiste en `system_events` **y** emite al log técnico (paralelas).
   - `app/storage/{postgres,mongo,raw_source}.py` con singletons thread-safe + interfaz `RawSource` abstracta (LocalFS / S3).
   - `app/phases/{ingestion,validation,transformation,loading,aggregates}.py` — 4 fases + agregados.
   - `app/clients/triage_client.py` — httpx al endpoint del modelo.
   - `app/orchestrator.py` con `run_batch()` y `run_id` externo (para que la API lo pase antes de arrancar el background task).
   - `app/online.py` con `process_patient_ficha()` reutilizando las mismas fases.
   - `main.py` CLI con subcomandos `batch` / `batch-all` / `seed` / `version`.
3. **`config/validation_rules.yaml`** — 15 campos tipados + 2 cross-field rules + dedup.
4. **`seed/generate_fichas.py`** — réplica ligera del generador de training (sin target) que sube CSV a S3/MinIO como landing zone.
5. **Reglas cruzadas** con `eval` sandboxed (sin `__builtins__` ni globals) para las condiciones lógicas entre campos.

## Aciertos

- La **separación de log técnico vs evento de dominio** fue clave para el dashboard. Un log técnico de stack trace no le dice nada al profesor viendo la demo; un evento `pipeline.loading.done — Cargados 20 pacientes y 20 ingresos` sí.
- La **abstracción `RawSource`** (LocalFS vs S3) desbloqueó el trabajo sin tener que decidir S3 vs MinIO de inmediato.
- La **idempotencia explícita** en cada fase (`first_wins` en PG vía `ON CONFLICT DO NOTHING`, dedup por hash en GridFS, `find_one_and_update($inc)` atómico para pseudo_ids) hace el pipeline rerun-safe.

## Correcciones que hubo que hacer

- **YAML + `no` sin comillas**: el mayor bug del sprint. 99 de 100 filas rechazadas por `fumador:enum` porque `['no', 'si', 'exfumador']` en YAML sin quotes se parseaba como `[False, 'si', 'exfumador']` (YAML 1.1). Fix con quoting explícito. **Lección**: cada vez que un enum de YAML contenga "no", "yes", "on", "off" — o se pone entre comillas o se usa "false"/"true" sin ambigüedad.
- **Credenciales de PG/Mongo no propagadas al contenedor de API**: el compose tenía `POSTGRES_HOST: postgres` pero **no** `POSTGRES_USER/PASSWORD/DB`, así que la API caía al `Field(default="change-me")` y fallaba auth en PG cuando cambié las passwords en `.env`. Fix: añadir las vars explícitamente en `environment:` de `api` y `pipeline`.

## Lecciones

1. **Las reglas declarativas en YAML son superiores al código Python embebido** para validación: el profesor puede editar el fichero sin tocar el pipeline. Prototipamos 15 reglas en 10 minutos sin reescribir lógica.
2. **La IA a veces sobre-diseña; preguntar "¿por qué no lo más simple?" la centra**. El debate 0/1 vs string enseña: a veces la respuesta correcta es "no hagas nada".
3. **Un smoke test real contra el stack (`docker compose up -d postgres mongodb minio minio-init`) revela bugs que ningún test unitario detecta** — el bug del YAML solo apareció al ver "99 rechazados de 100" con datos reales.

## Commits afectados

- `b15b58d` — DESIGN-02: diseño técnico del pipeline
- `7f2ed89` — feat(pipeline): ETL batch completo con RawSource + YAML + triaje
- `a6109c6` — fix(pipeline): quoting de enums en validation_rules.yaml + smoke E2E
