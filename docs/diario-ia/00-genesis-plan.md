# 00 — Génesis del plan y los SDDs iniciales

## Contexto

Primera sesión de la práctica. El repo tenía dos archivos: el PDF del enunciado y un `CONTEXT.md` con el resumen exhaustivo (incluyendo los *easter eggs* ocultos en blanco del PDF). Había que convertir esa idea difusa en un plan concreto y, según la metodología del Master, en una serie de SDDs antes de escribir una línea de código.

## Prompts clave

> Vamos a planificar la practica esta

*Apertura deliberadamente ambigua — quería ver qué devolvía la IA con poca guía. Me obligó a responder a preguntas de alcance (equipo, deadline, stack, dashboard vs Grafana, etc.) antes de producir un plan.*

> Vale, y tienes que ir haciendome preguntas para completar el sdd

*Punto de inflexión metodológico.* Pasamos de "IA escribe el plan y Pol valida" a "IA pregunta sección a sección y Pol va cerrando ambigüedades". Esto produjo SDDs mucho más densos y con menos `[NEEDS CLARIFICATION]` sueltos.

> Te paso este pdf para que veas como nos han enseñado a hacer sdd, echale un ojo

*El PDF "Spec Driven Development – Master IA Big Data" enseñaba una estructura distinta a la plantilla que la IA había usado inicialmente: separaba explícitamente **Spec** y **Diseño** como pasos distintos. La IA entonces identificó que su plantilla estaba mezclando ambos y propuso reescribirla con la estructura canónica (Contexto · Actores · RF · RNF · Casos borde · CA · Dudas).*

> Si, escribe ya todos los sdd no? A que esperas?

*Tras escribir SDD-01 y SDD-03 en modo "pregunta-respuesta sección a sección", decidí que el resto podía hacerlos en modo "batch" con decisiones ya tomadas. Esto pasó de un ritmo de ~30 min/SDD a ~10 min/SDD.*

## Lo que produjo la IA

- Un **plan global** (`C:\Users\polba\.claude\plans\...`) con 3 sprints de 15 días, decisiones técnicas cerradas (FastAPI, pandas autorizado, MongoDB + PostgreSQL con GridFS, dos modelos de IA), orden sugerido de los SDDs (01 → 03 → 02 → 06 → 05 → 04 → 07), checklist de riesgos.
- **7 SDDs iniciales** en `specs/` con la plantilla del Master aplicada:
  - SDD-01 sistema global (23 RF · 17 RNF · 20 casos borde · 25 CA · 3 dudas abiertas)
  - SDD-02 pipeline ETL
  - SDD-03 almacenamiento PostgreSQL + MongoDB + GridFS
  - SDD-04 automatización (watchers, scheduler, alertas)
  - SDD-05 API + Dashboard
  - SDD-06 modelo DL radiografías
  - SDD-07 monitorización
- Un **DESIGN-01** con la arquitectura Docker completa (11 servicios iniciales, red, volúmenes, diagrama ASCII).

## Aciertos

- La IA **respetó "pandas autorizado"** desde el primer momento tras confirmárselo, y **nunca** volvió a proponer Dask en serio, solo como *plan de escalado teórico documentado en memoria* — que es lo que pedía el enunciado §4.2.
- Captó los *easter eggs* del PDF (el "NoSQL sobre todo" y el "Times New Roman") y los llevó a las decisiones de arquitectura y al formato de la memoria técnica.
- La plantilla SDD inicial la tuvo bien pensada estructuralmente aunque metía diseño dentro de la spec — con el PDF del Master reconoció el error y propuso separar.

## Correcciones que hubo que hacer

- **Plantilla SDD inicial**: mezclaba `spec` y `diseño`. Fue el PDF del Master lo que reveló el problema. Refactorizamos y recuperamos el trabajo ya hecho moviendo lo de "arquitectura" al nuevo `DESIGN-01`.
- Al principio la IA asumía que éramos 2 personas trabajando en paralelo (por el nombre de la carpeta `YURI_JORDI_ENRIQUE`). Tuve que aclarar que trabajaba solo al inicio; la memoria se actualizó.

## Lecciones

1. **"Vamos a planificar" es un prompt útil** aunque suene vago: fuerza a la IA a hacerte preguntas antes de ejecutar.
2. **Mostrar el material docente del Master** (el PDF de SDD) alineó inmediatamente la metodología. Sin ese PDF, la IA habría seguido con su plantilla "correcta pero no la nuestra".
3. **Los `[NEEDS CLARIFICATION]` son más valiosos que las decisiones apresuradas**: cada duda abierta se cerró más tarde con contexto real (p. ej. el umbral `P(COVID-19)` se difirió a DESIGN-06, cuando ya había modelo entrenado).

## Commits afectados

- `997cd60` — SDDs iniciales commiteados
- `7e9bc14` — cierre de primera sesión
