# Diario de desarrollo con IA

> Entregable exigido por el enunciado §5.3. Cubre herramientas usadas, prompts representativos, aciertos y correcciones, reflexión crítica y estimación de impacto en productividad.

## 1. Herramientas utilizadas

- **Claude Code** (Anthropic) como herramienta principal de desarrollo asistido, integrada en el IDE. Seleccionada por:
  - Operar directamente sobre el sistema de ficheros (crear/editar/borrar, ejecutar comandos de shell y Docker) sin copiar/pegar del chat al editor.
  - Ventana de contexto amplia: permite mantener la conversación larga (multisesión) sin perder la memoria del proyecto.
  - Sistema de *memory files* persistente entre sesiones que recuerda decisiones ya tomadas (p. ej. *"pandas autorizado por el profesor"*, *"MinIO como landing zone"*) — evita re-discutir lo mismo.

- **Herramientas secundarias**: Git + Docker Desktop (sin IA). El repo + el stack Docker son el *output* físico.

## 2. Metodología aplicada — Spec Driven Development

Seguimos la metodología del Master (**SDD**) tal y como se enseñó en la sesión específica: pasar de *necesidad* → *spec* → *diseño* → *tareas* → *código* sin colapsar pasos. En concreto:

- **7 SDDs + 1 extra** (SDD-08 modelo triaje) escritos antes de una sola línea de código de producto. Cada uno con *Contexto · Actores y alcance · RF · RNF · Casos borde · Criterios de aceptación · Dudas abiertas* (tag `[NEEDS CLARIFICATION]`).
- **4 DESIGN docs** (DESIGN-01/02/03/06/08) traducen cada spec a decisiones técnicas concretas (algoritmo, hiperparámetros, esquema DDL, estructura de código) antes de implementar.
- Las **implementaciones** (ETL, modelo, API, dashboard) ejecutan lo que ya estaba decidido — la IA produce código alineado con la spec, no "improvisa".

Este orden — aunque a veces parezca lento al principio — **redujo retrabajo de forma observable**: cada decisión controvertida (pandas vs Spark, MinIO vs AWS, 5 niveles de ESI vs 3 niveles, constantes vitales vs campos auto-reportados, etc.) se discutió y se cerró en la spec, **antes** de que hubiera código que rehacer.

## 3. Organización del diario

Un fichero por episodio/sprint significativo, con la misma estructura fija:

1. **Contexto**: qué estábamos intentando hacer.
2. **Prompt clave** (verbatim, tal cual lo escribí): los momentos donde mi instrucción cambió la dirección del proyecto.
3. **Lo que produjo la IA**: respuesta / código / decisión que entregó.
4. **Aciertos y correcciones**: dónde la IA acertó al primer intento, dónde tuve que redirigir, y qué aprendí del intercambio.
5. **Commits afectados**: hashes concretos para trazabilidad con el repo.

### Índice

- [00 — Génesis del plan y los SDDs iniciales](00-genesis-plan.md)
- [01 — Integración con la rama de Ariadna](01-integracion-ariadna.md)
- [02 — Modelo de triaje tabular (SDD-08)](02-modelo-triaje.md)
- [03 — ETL pipeline batch y online](03-etl-pipeline.md)
- [04 — API del flujo + dashboard v1](04-online-api-dashboard.md)
- [05 — Decisión S3 → MinIO (landing zone)](05-minio-landing.md)
- [06 — Pulido UX del dashboard](06-pulido-ux.md)
- [99 — Reflexión crítica y productividad](99-reflexion-critica.md)

## 4. Convención de voz

Los fragmentos en `> blockquote` son **prompts míos tal y como los escribí**, con faltas de ortografía y castellano informal incluidos. No los he "limpiado" — el valor pedagógico está en ver cómo cambiaban de ambigüedad a precisión a medida que íbamos iterando.
