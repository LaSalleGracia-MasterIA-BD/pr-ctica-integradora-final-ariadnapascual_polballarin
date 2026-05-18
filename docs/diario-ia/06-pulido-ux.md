
# 06 — Pulido UX del dashboard y simplificación del arranque

## Contexto

Tras la v1 del dashboard (sidebar, 3 vistas) y los primeros smoke tests con Docker Compose, quedaron dos temas clave por pulir:

1. El arranque del stack obligaba a listar servicios explícitamente.
2. Los colores y la tipografía del dashboard heredaban el tema del SO, dando un aspecto poco profesional.

## Prompts clave y soluciones

### Simplificación del arranque

Se identificaron dos problemas principales:

1. El `CMD ["python", "main.py"]` del stage `pipeline` requería subcomando; sin él, `argparse` lanzaba `SystemExit` y, con `restart: on-failure`, entraba en bucle infinito de reinicios.
2. `ml-triage` necesitaba el modelo en el volumen. Tras `docker compose down -v`, era necesario copiar manualmente el artefacto con `docker cp`.

**Soluciones:**
- `CMD ["sleep", "infinity"]` en el stage pipeline (contenedor idle listo para `exec`).
- `COPY models/triage /app/models/triage` en el stage ml-triage (bake del modelo; si el volumen está vacío tras `down -v`, Docker inicializa desde la imagen).

Sobre las contraseñas: las de PG/Mongo/MinIO solo se aplican en la primera inicialización del volumen. Si ya hay datos, cambiar `.env` no cambia la password del motor. Dos caminos: `docker compose down -v` + editar + up (limpio), o `ALTER USER` + editar + restart (preserva datos). Se optó por el limpio.

El orden entre cambiar `.env` y `down -v` es irrelevante si se usa `-v`, ya que los volúmenes se borran a nivel Docker.

### Bump de versiones

Se realizó un listado exhaustivo de versiones de imágenes Docker, Python y requirements. La decisión fue usar versiones estables recientes, no necesariamente las más nuevas, para evitar breaking changes y problemas de compatibilidad (por ejemplo, Python 3.13 rompe numpy/scikit-learn en algunas plataformas, Loki 3.3+ exige migraciones de schema).

**Actualizaciones:**
- Imágenes: postgres 16→17, mongo 7→8, minio release 2024-12-18, mc release 2024-11-21, pgadmin 7.8→9, mongo-express 1.0.0→1.0.2, loki 2.8.2→3.2.1, promtail 2.8.2→3.2.1.
- Python base: 3.11-slim → 3.12-slim.
- 6 `requirements.txt` actualizados a versiones estables recientes (fastapi 0.115.6, pydantic 2.10.3, numpy 2.2.1, scikit-learn 1.6.0, streamlit 1.40.2, etc.).
- `monitoring/loki-config.yaml` reescrito para Loki 3.x (tsdb + schema v13 + common.path_prefix + allow_structured_metadata).

### UX del dashboard

Se detectaron varios bugs de UX:
- El dashboard seguía en modo oscuro por heredar el tema del SO. Se forzó `base="light"` en `services/dashboard/.streamlit/config.toml`.
- Problemas de legibilidad en formularios y recuadros. Se reforzó la paleta de colores (blancos, grises, azules) y la legibilidad de textos.
- El header nativo de Streamlit ocupaba espacio innecesario. Se ocultó con CSS (`display: none` sobre `[data-testid="stHeader"]` y otros elementos del chrome de Streamlit).
- Se mejoró la responsividad con `flex-wrap`, `clamp()` en tipografía y media queries.

## Aciertos

- Se rechazó el uso de "lo más nuevo de todo" con argumentos concretos, evitando roturas por incompatibilidades.
- Diagnóstico preciso del problema de tema heredado del SO, solucionado con la configuración canónica de Streamlit.
- Migración a Loki 3.x con configuración minimal oficial, evitando bucles de parches sobre la versión anterior.

## Correcciones necesarias

- El primer intento de arreglar Loki 2.8.2 fue un bucle de parches. Se reconoció el antipatrón y se migró a Loki 3.x.
- El CMD inválido en el pipeline se detectó tras ver contenedores en estado `Restarting`. Ahora está documentado.

## Lecciones aprendidas

1. "Lo más reciente no siempre es lo mejor" en Docker images: cada upgrade mayor puede requerir migraciones y cambios de config.
2. En apps profesionales con Streamlit, fuerza siempre un tema vía `config.toml`.
3. Si entras en bucle de parches, es mejor parar y cambiar de enfoque.
4. Los healthchecks con `curl` requieren instalarlo en la imagen base, o usar alternativas en Python.

## Commits afectados

- `fe839e7` — chore(deps): bump imágenes + Python 3.12 + packages + Loki 3.2 config
- `ed80845` — fix(dashboard): tema light forzado + brand responsive + legibilidad form
- `ec9cec5` — fix(dashboard): ocultar header nativo de Streamlit
