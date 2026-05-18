# 99 — Reflexión crítica y estimación de impacto

## 1. Dónde aportó valor la IA

### Aportes claros y medibles

- **Velocidad de redacción de artefactos largos**. Los 7 SDDs iniciales y los 4 DESIGN docs suman ~3000 líneas de documentación estructurada y coherente internamente. Producirlos manualmente habría tomado entre 2 y 4 días de trabajo; con la IA se cerraron en ~6 horas distribuidas.
- **Plantillas y consistencia**. La IA mantuvo la misma estructura de SDD (Contexto · Actores · RF · RNF · Casos borde · CA · Dudas) en los 8 documentos sin desviarse. Hecho a mano, el cansancio habría introducido drift.
- **Detección de bugs "por lectura"**. El healthcheck roto de mongodb (`mongo --eval` ya no existe en la imagen `mongo:7`), el volumen `pgadmin-data` referenciado pero no declarado, el YAML con `no` sin comillas interpretado como booleano False — todos detectados al **revisar el código de otro/el mío**, no al ejecutarlo. Un smoke test los habría encontrado luego, más tarde y más caro.
- **Razonamiento sobre decisiones técnicas**. La discusión "S3 AWS vs MinIO" con argumentos operativos concretos (tribunal sin credenciales, §4.1 "un solo comando") llevó a una mejor decisión que habría tomado solo por convención ("usamos AWS porque tenemos credenciales").
- **Trabajo tedioso repetitivo**. Pinnear versiones en 6 `requirements.txt`, ajustar CSS para 10+ widgets de Streamlit, reescribir configs de Loki para una versión más nueva — trabajo que no es difícil, es lento.
- **Depuración de infraestructura distribuida**. La integración de Dask, Loki/Promtail, MinIO, MongoDB, PostgreSQL, modelos ML y Docker Compose generó errores reales de entorno: puertos ocupados, servicios unhealthy, rutas de modelos inexistentes, dependencias incompatibles en Windows, queries LogQL mal escapadas en PowerShell y conflictos de actualización en MongoDB. La IA ayudó a convertir errores largos de consola en hipótesis concretas y comandos verificables.
- **Validación contra el enunciado**. Se usó la IA para revisar el proyecto punto por punto frente a los requisitos: containerización, almacenamiento combinado, pipeline escalable, servicio REST/dashboard, logging centralizado, calidad de datos y alertas. Esto evitó dar por cubierta una sección solo porque “parecía funcionar”.
- **Diseño de pruebas demostrables**. En vez de limitarse a código, la IA ayudó a construir pruebas defendibles: batch con Dask, healthcheck de `ml-triage`, consulta real a Loki, CSV inválido con rechazos, persistencia en `ingestion_rejects` y creación de alertas en MongoDB.

### Aportes menos tangibles pero reales

- **Memoria entre sesiones**. La persistencia de decisiones en los *memory files* (*"pandas autorizado por el profesor"*, *"Pol trabaja con compañera ahora"*, *"MinIO como landing zone"*) evitó re-discutir cada vez que abría el editor.
- **Presión metodológica**. La IA **se opuso** varias veces a decisiones mías que habrían inflado scope sin ganancia (dataset de 100k filas, "lo más nuevo de todas las imágenes", pasar campos a 0/1 para ahorrar espacio). En todos los casos sus objeciones eran bien argumentadas y las acepté.

## 2. Dónde hubo que corregir

- **Asumir features no realistas**. Propuso constantes vitales (tensión, saturación de oxígeno) para un formulario web auto-reportado, donde un paciente normal no las conoce. Corrección del usuario hizo pivotar a síntomas subjetivos. Sin la corrección, habría producido un formulario clínicamente inservible.
- **Plantilla SDD con diseño mezclado**. La plantilla inicial (antes del PDF del Master) metía `Diseño propuesto` dentro de la spec, contradiciendo explícitamente la metodología SDD. Reconoció el error cuando le pasé el PDF y propuso reestructurar.
- **Parches en bucle**. Un intento de arreglar Loki 2.8.2 con tres fixes consecutivos en la misma config. Tras el tercero pedí parar y actualizamos a Loki 3.2.1 con config oficial limpia.
- **Tema heredado del SO**. Asumió que el CSS custom bastaba para unificar colores; en realidad Streamlit heredaba el tema dark del OS. La corrección (`.streamlit/config.toml` con `base="light"`) vino tras el report del usuario. *Lección*: si tu CSS compite con los widgets nativos del framework, el framework gana.
- **Problemas de quoting en PowerShell**. Varias consultas a MongoDB y Loki fallaron por comillas, `$in`, backticks y encoding de URL. La solución final no fue “confiar” en el comando generado, sino aislar la query en variables PowerShell y usar `[uri]::EscapeDataString(...)`.
- **Promtail capturando logs de otros proyectos Docker**. La primera configuración de Promtail recogía contenedores antiguos de otros proyectos locales, generando errores de timestamps demasiado antiguos en Loki. Hubo que filtrar mejor, reiniciar Promtail y validar con labels reales antes de afirmar que el logging centralizado estaba cerrado.
- **Conflictos en MongoDB con `$setOnInsert` y `$set`**. El servicio `automation` falló porque intentaba insertar y actualizar el mismo campo (`updated_at` / `last_seen_at`) en la misma operación. Se corrigió separando los campos exclusivos de inserción de los campos actualizables.
- **Falsa sensación de éxito en Loki**. Loki y Promtail aparecían `healthy`, pero las queries devolvían `result: []`. Solo se dio por cerrado cuando una query LogQL devolvió explícitamente un evento `pipeline.run.end` del servicio `pipeline`.

## 3. Patrones de prompt que funcionaron bien

### Prompts directivos + ricos en contexto

El mejor ejemplo:

> Eres un profesional de UX; Quiero un dashboard mucho más profesional, con menu en el header; Para empezar tiene que haber un dashboard con todos los pacientes ya clasificados, con posibilidad de clicar en ellos y se despligue su ficha, un boton de descarga para poder descargar un pdf con la ficha del paciente; [...] Usa una paleta de colores claros blancos, grises y azules, tipico de hospital

Un solo mensaje que contenía:
- Rol a asumir (UX profesional).
- Estructura (menú header, no sidebar).
- Vistas + interacciones de cada una.
- Disposición interna (tabs en Triaje, logs embebidos).
- Paleta (blanco + gris + azul hospital).

Produjo la v2 del dashboard completa sin rondas de aclaración.

### Prompts de clarificación conceptual

> Que es el etl batch? Que podamos uplodear un dataset con varias fichas de pacientes y analice todas y de el resultado para todas o que?

Preguntas honestas ("no sé qué es X") obtuvieron explicaciones útiles **antes** de escribir código. Mucho más productivo que asumir y luego rehacer.

### Prompts de objeción razonada

> Pero podemos reducir peso tambien, por ejemplo los booleanos cambiarlos a 0 o 1 sabes?

Proponer una idea y preguntar si tiene sentido (en vez de ordenar "hazlo") obtuvo respuestas razonadas. La IA se opuso en este caso con 5 argumentos y evitó un cambio que habría roto legibilidad.

### Prompts con metamaterial

> te paso este pdf para que veas como nos han enseñado a hacer sdd, echale un ojo

Entregar el material docente a la IA alineó la metodología **sin reformular**. Extracto las lecciones y las aplica.

## 3.1. Evidencias finales añadidas tras la fase de infraestructura

En la fase final del proyecto se cerró la parte de **Infraestructura y Sistemas de Big Data Aplicados** con pruebas end-to-end reales.

### Dask como procesamiento escalable

Se añadió un despliegue con:

- `dask-scheduler`;

# 99 — Reflexión crítica y estimación de impacto

## 1. Dónde aportó valor la IA

### Aportes claros y medibles

- Velocidad de redacción de artefactos largos: los SDDs y DESIGN docs se generaron en horas en vez de días.
- Plantillas y consistencia: estructura uniforme en todos los documentos.
- Detección de bugs por lectura: errores de healthcheck, volúmenes, YAML, detectados antes de ejecutar.
- Razonamiento sobre decisiones técnicas: argumentos operativos y técnicos mejor fundamentados.
- Trabajo tedioso repetitivo: pinnear versiones, ajustar CSS, reescribir configs.
- Depuración de infraestructura distribuida: integración de servicios, resolución de errores reales de entorno.
- Validación contra el enunciado: revisión punto por punto de los requisitos.
- Diseño de pruebas demostrables: batch con Dask, healthcheck, consulta real a Loki, CSV inválido, persistencia y alertas.

### Aportes menos tangibles

- Memoria entre sesiones: persistencia de decisiones en memory files.
- Presión metodológica: la IA se opuso a inflar el scope sin ganancia.

## 2. Dónde hubo que corregir

- Asumir features no realistas: propuesta de constantes vitales para un formulario auto-reportado.
- Plantilla SDD con diseño mezclado: error de estructura inicial, corregido tras revisión de la metodología.
- Parches en bucle: intentos repetidos de arreglar Loki antes de migrar a versión nueva.
- Tema heredado del SO: CSS no bastaba, fue necesario forzar el tema en config.toml.
- Problemas de quoting en PowerShell: solución con variables y EscapeDataString.
- Promtail capturando logs de otros proyectos: filtrado y reinicio necesarios.
- Conflictos en MongoDB con $setOnInsert y $set: separación de campos de inserción y actualización.
- Falsa sensación de éxito en Loki: validación solo con eventos reales, no solo healthchecks.

## 3. Patrones de prompt efectivos

- Prompts directivos y ricos en contexto: rol, estructura, vistas, disposición, paleta.
- Prompts de clarificación conceptual: preguntar antes de asumir.
- Prompts de objeción razonada: pedir argumentos antes de ejecutar cambios.
- Prompts con metamaterial: aportar material docente para alinear metodología.

## 4. Evidencias finales

### Infraestructura y sistemas de Big Data

- Dask integrado con pipeline y dashboard.
- Modelos tabulares entrenados y validados en Docker.
- Logging centralizado con Loki y Promtail, validado con eventos reales.
- Calidad de datos: detección y persistencia de rechazos en MongoDB.
- Alertas operativas: servicio automation con deduplicación y notificación simulada.

### Deep Learning radiografías

- Dataset limpio, sin máscaras.
- Comparación experimental entre simple_cnn, resnet18 y efficientnet_b0.
- Selección de EfficientNet-B0 por F1 macro y recall clínicamente relevantes.
- Validación de endpoints y predicciones reales en Docker.
- Integración completa con el dashboard.

## 5. Estimación de productividad

| Bloque | Sin IA | Con IA |
|---|---|---|
| SDDs + DESIGN docs | 3-4 días | 1 día |
| Pipeline ETL | 3-4 días | 1 día |
| Modelo triaje | 2-3 días | 0.5 día |
| API | 1-2 días | 0.3 día |
| Dashboard v2 | 2-3 días | 0.7 día |
| Bump de versiones + fixes | 1 día | 0.3 día |
| Memoria de decisiones | 0.5 día | intrínseco |
| **Total estimado** | **12-17 días** | **~4 días** |

Factor de productividad observado: **~3-4×**. No es universal: depende de tener specs claras y validar cada cambio. El juicio crítico sigue siendo imprescindible.

## 6. Conclusión para la práctica

En un proyecto de 3 semanas con 1-2 personas, la IA permitió entregar un sistema completo (modelos IA, pipeline, API, dashboard, infraestructura, documentación) en tiempo récord, sin recortar funcionalidades clave. La IA no sustituyó el juicio humano, pero aceleró la toma de decisiones y la coherencia documental.

Algunas decisiones defendidas por la IA (MinIO sobre AWS, rechazar dataset de 100k, no pasar booleanos a 0/1) resultaron mejores que las iniciales del usuario.

## 7. Consideraciones éticas

La IA se usó también para revisar riesgos y priorizar el análisis de falsos negativos en COVID-19 y Neumonía. Se evitó subir datasets, pesos y `.env` al repo, y se documentó que el sistema es académico y no sustituye criterio médico.