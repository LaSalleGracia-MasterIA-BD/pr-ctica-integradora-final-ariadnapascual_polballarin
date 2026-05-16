# 04 — API del flujo + dashboard v1 + vista Pacientes con PDF

## Contexto

Con el ETL batch verificado, quedaba conectar el flujo end-to-end de la demo: el usuario rellena un formulario (o sube un CSV), la API lo recibe, el pipeline lo procesa, el modelo de triaje lo clasifica, los resultados se ven en el dashboard. Dos fases: primero la API con los 3 endpoints mínimos, luego el dashboard en dos iteraciones (v1 sidebar, v2 con menú horizontal tipo hospital).

## Prompts clave

> Si, cuando haremos el frontend?

*Mi impaciencia por ver algo visual tras días de backend. La IA explicó el orden lógico: primero API + ETL online + endpoints del flujo, luego dashboard — para no escribir endpoints que nadie consume. Acepté. Commit `b837e76` + `fe839e7` ya preparaban el terreno.*

> Eres un profesional de UX; Quiero un dashboard mucho más profesional, con menu en el header; Para empezar tiene que haber un dashboard con todos los pacientes ya clasificados, con posibilidad de clicar en ellos y se despligue su ficha, un boton de descarga para poder descargar un pdf con la ficha del paciente; Vamos a simular una ficha de un hospital vale? Luego: en el siguiente apartado tiene que ser el triaje donde como ya habia dicho tienen que verse logs una vez ejecutado el formulario. en este triaje tiene que haber dos pestañas, la del formulario y la del batch. así lo unificamos en una sola ventana partida en pestañas entiendes? Luego el seguimiento del run yo lo incorporaria directamente en el triaje así lo vemos automaticamente al ejecutarlo. De momento haz esto y vemos; Usa una paleta de colores claros blancos, grises y azules, tipico de hospital

*El mejor prompt de toda la conversación. Un único mensaje con: rol (UX profesional), estructura (menú header, no sidebar), listado de vistas con sus interacciones, disposición (tabs dentro de Triaje, logs embebidos en la misma vista), paleta (blanco/gris/azul hospital). La IA pudo materializar todo sin preguntar nada extra.*

> Lo de la salle healthcare center sale cortado, haz todo responsive! Otra cosa, recuerdas que te he dicho que quiero todo en tonos claros, blancos grises y azules? Porque sigue todo el dashboard oscuro? Es una limitación del software?
> Otra cosa, en el formulario los textos estan en oscuro como el background por lo tanto no se puede leer! Arreglalo

*Tres bugs reportados en un mensaje. La IA diagnosticó correctamente: **no era limitación del software**, Streamlit heredaba el tema dark del SO a través del navegador. El CSS de mi `.hospital-brand` iba bien pero los widgets nativos (selectbox, input) salían en dark. Fix: crear `services/dashboard/.streamlit/config.toml` con `[theme] base="light"` + paleta hospital — esto **prevalece** sobre la preferencia del SO y unifica todo el chrome de Streamlit en light mode.*

> Vale otra vez, el recuadro donde está esto: 🏥 laSalle Health Center ... sale cortado por un header en blanco sin nada. por que?

*Último pulido. La IA detectó el `header[data-testid="stHeader"]` nativo de Streamlit (toolbar con menú hamburguesa) que seguía ocupando ~45px aunque estuviera en `toolbarMode: minimal`. Fix: CSS `display: none` sobre `stHeader`, `stToolbar`, `stDecoration`, `stStatusWidget`, `#MainMenu`, `footer` — el brand del hospital es ahora el único header de la app.*

## Lo que produjo la IA

### Backend (API)

Tres endpoints nuevos en `services/api/app/main.py` — todo respaldado por los esquemas de SDD-03:

1. `GET /patients?limit=&offset=&triage_class=` — listado paginado, JOIN LATERAL en PostgreSQL para obtener el último ingreso de cada paciente en una sola query + agregación Mongo para la última predicción de triaje (una sola query con `$group`/`$first`).
2. `GET /patients/{pseudo_id}` — detalle completo con historial de ingresos.
3. `GET /patients/{pseudo_id}/pdf` — ficha PDF generada con `fpdf2`.

Nuevo módulo `services/api/app/pdf_generator.py` con:
- Cabecera azul navy con nombre del hospital.
- Secciones de datos demográficos + último episodio clínico.
- Box de triaje con franja coloreada (rojo/naranja/verde según nivel).
- Footer con timestamp de generación.
- Nota legal al pie explicitando "apoyo a la decisión, no diagnóstico".

### Dashboard v2

Reescrito desde cero con `streamlit-option-menu` (librería añadida a requirements) para tener **menú horizontal** en vez del sidebar nativo. Paleta implementada como variables CSS:

```python
PRIMARY_BLUE = "#1E3A8A"   # navy (header, botones, títulos)
ACCENT_BLUE = "#2563EB"    # hover
LIGHT_BLUE = "#DBEAFE"     # tab seleccionada
GREY_BG = "#F8FAFC"        # fondo app
GREY_BORDER = "#E2E8F0"    # bordes de tarjetas
TEXT_DARK = "#0F172A"      # texto
```

Tres vistas:
- **Pacientes**: tabla de todos los registrados, filtro por triaje, selector para abrir ficha. La ficha muestra cabecera con nivel de triaje coloreado, 2 columnas de datos (demográficos / último episodio), probabilidades como `st.metric`, botón **"⬇️ Descargar ficha PDF"** que consume `/patients/{id}/pdf`.
- **Triaje** con `st.tabs(["Formulario individual", "Lote CSV"])` — los dos flujos en una sola vista. Tras ejecutar, los logs del pipeline aparecen **embebidos abajo** en la misma vista (polling de `/batch-runs/{run_id}/events` cada 1.5 s).
- **Estado**: health de la API.

## Aciertos

- **Endpoint `/patients` con `LATERAL JOIN` + `aggregate` de Mongo** evita el N+1 query clásico (1 query SQL + 1 query Mongo para N pacientes, no 2N).
- **Bake del modelo en la imagen `ml-triage`**: `COPY models/triage /app/models/triage` en Dockerfile hace que al hacer `docker compose down -v && up -d` el modelo se restaure en el volumen automáticamente. Elimina el paso manual `docker cp models/triage ...` que hacía falta antes.
- **`CMD ["sleep", "infinity"]` en el stage `pipeline`**: el contenedor queda idle esperando `docker compose exec pipeline python main.py batch ...`. Evita el loop de reinicios por `argparse: required subcommand`.
- **CSS `display: none` sobre el stHeader** es *opinión de diseño* controvertida, pero el brand del hospital queda más profesional sin el toolbar de Streamlit encima.

## Correcciones que hubo que hacer

- **API no leía las credenciales de PG/Mongo** (describo arriba en 03). Afectó al primer smoke test de `/patients` que devolvió 500. Fix en el compose propagando las env vars.
- **Streamlit heredaba el tema del SO**. Yo asumí que mi CSS era suficiente; no lo era para los widgets nativos. El `config.toml` con `base="light"` unificó todo.
- **Brand del hospital se cortaba en viewport estrecho** por falta de `flex-wrap`. Fix con `flex-wrap: wrap` + `clamp()` en el tamaño de fuente.
- **Header nativo de Streamlit seguía tapando** aunque estuviera en modo minimal. Ocultación explícita con `display: none`.

## Lecciones

1. **Un prompt bien escrito ahorra 10 rondas de iteración**. El prompt de "eres UX profesional, quiero esto así..." produjo la v2 del dashboard de una sentada. Los 3 bugs de UX posteriores se arreglaron en 2 mensajes.
2. **El tema del navegador/SO es invisible hasta que te muerde**. Forzar `base="light"` en apps clínicas/profesionales debería ser default — nadie quiere una UI hospitalaria en dark mode inesperado.
3. **Streamlit mezcla CSS nativo y custom**. Si quieres personalización seria, vas a acabar con un bloque `<style>` grande con overrides de `[data-testid="..."]`. Es aceptable para un proyecto de 3 semanas.
4. **Responsive con CSS moderno es fácil**: `clamp()`, `flex-wrap`, `@media` con 1-2 breakpoints basta para que el brand no se rompa.

## Commits afectados

- `9750b8b` — feat(api+dashboard): vista Pacientes con ficha + PDF + dashboard v2 estilo hospital
- `ed80845` — fix(dashboard): tema light forzado + brand responsive + legibilidad form
- `ec9cec5` — fix(dashboard): ocultar header nativo de Streamlit
