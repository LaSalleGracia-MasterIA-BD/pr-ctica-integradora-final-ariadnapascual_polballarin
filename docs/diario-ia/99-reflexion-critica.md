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
- `dask-worker`;
- integración del pipeline con `dask.dataframe`;
- dashboard en `http://localhost:8787`.

La ingesta batch registra metadatos como:

```json
{
  "processing_engine": "dask",
  "dask_partitions": 1,
  "dask_blocksize": "16MB",
  "dask_scheduler": "tcp://dask-scheduler:8786"
}

Modelos tabulares operativos

Se entrenaron dentro de Docker dos modelos:

modelo de triaje;
modelo de sospecha de enfermedad.

El healthcheck final de ml-triage devolvió:

{
  "status": "ok",
  "triage_version": "tri-20260514-60eff3c2",
  "disease_version": "dis-20260514-8c9a3874"
}
Logging centralizado con Loki y Promtail

Se desplegaron loki y promtail dentro de Docker Compose. La validación final no se basó solo en healthchecks, sino en una consulta real a Loki:

$query = '{compose_service="pipeline"} |= "pipeline.run.end"'
$url = "http://localhost:3100/loki/api/v1/query_range?limit=10&start=$start&end=$end&query=$([uri]::EscapeDataString($query))"
curl.exe -s $url

La respuesta incluyó un stream con:

{
  "compose_project": "practica_hospital_ariadnapascualpolballarin",
  "compose_service": "pipeline",
  "event": "pipeline.run.end"
}
Calidad de datos

Se creó un CSV inválido:

patients/quality-test-invalid.csv

El pipeline detectó correctamente registros incompletos o corruptos:

{
  "records_in": 5,
  "valid": 1,
  "rejected": 4,
  "rejects_persisted": 4
}

Los rechazos quedaron persistidos en MongoDB en ingestion_rejects, con motivos como:

missing_field:edad;
sexo:enum;
intensidad_dolor:max:10.
Alertas operativas

Se implementó el servicio automation, que revisa eventos warning y error en system_events y crea alertas deduplicadas en MongoDB.

Ejemplo de log:

Nueva alerta creada: pipeline.validation.done:<run_id>:warning | Validación: 1 válidos, 4 rechazados
Nueva alerta creada: pipeline.rejects.persisted:<run_id>:warning | 4 rechazos persistidos en ingestion_rejects

Ejemplo de documento en alerts:

{
  "source_event": "pipeline.validation.done",
  "severity": "warning",
  "status": "open",
  "notification_channel": "mongo_dashboard",
  "notification_status": "simulated"
}

Con esto quedan demostrados los tres requisitos de monitorización y calidad:

logging centralizado;
validación de calidad de datos;
alertas ante fallos o eventos anómalos.


## 3.2. Evidencias finales añadidas tras la fase de Deep Learning radiografías

En la fase final del módulo de redes neuronales se completó una comparación experimental entre tres enfoques para clasificación triple de radiografías de tórax:

- `simple_cnn`: CNN simple entrenada desde cero como baseline.
- `resnet18`: modelo preentrenado con transfer learning.
- `efficientnet_b0`: modelo preentrenado con transfer learning y arquitectura eficiente.

El dataset se limpió para usar únicamente imágenes reales dentro de carpetas `images/`, excluyendo explícitamente las carpetas `masks/`. Esta corrección fue importante porque inicialmente el script podía recoger máscaras binarias, lo que habría contaminado el entrenamiento y producido métricas artificiales o clínicamente inválidas.

La preparación final del dataset generó 1000 imágenes por clase final:

- `Sana`: procedente de `Normal/images`.
- `Neumonía`: procedente de `Viral Pneumonia/images` + `Lung_Opacity/images`.
- `COVID-19`: procedente de `COVID/images`.

La comparación final obtuvo:

| Modelo | Accuracy | F1 macro | Recall COVID-19 | Recall Neumonía |
|---|---:|---:|---:|---:|
| EfficientNet-B0 | 0.9600 | 0.9601 | 0.9800 | 0.9333 |
| ResNet18 | 0.8933 | 0.8929 | 0.9667 | 0.8333 |
| CNN simple | 0.7022 | 0.7013 | 0.7000 | 0.7733 |

El modelo seleccionado fue `EfficientNet-B0`, versión:

`rx-efficientnetb0-20260515-2b92eec9`

La elección no se basó únicamente en accuracy. Se priorizó:

- `F1 macro`, para equilibrar las tres clases.
- `recall_covid`, por el riesgo clínico y epidemiológico de falsos negativos.
- `recall_neumonia`, por el riesgo de retrasar tratamiento respiratorio.
- matriz de confusión, para entender qué errores cometía cada modelo.

El endpoint `/healthz` quedó validado:

```json
{"status":"ok","model_ready":true}

También se probaron predicciones reales desde el contenedor con imágenes de las tres clases:

COVID-19.
Normal.
Viral Pneumonia.
Lung Opacity.

La pestaña Radiografías del dashboard quedó integrada y funcional. El dashboard llama internamente a:

http://ml-inference:8001/predict

Esto fue importante porque dentro de Docker Compose no se debe llamar a localhost, ya que localhost dentro del contenedor del dashboard apunta al propio dashboard, no al servicio ml-inference.

Decisión crítica

El punto más importante de esta fase no fue conseguir una accuracy alta, sino evitar una evaluación engañosa. La detección de rutas con masks/ dentro de los CSV permitió corregir el dataset antes de defender resultados. Si se hubieran usado máscaras en lugar de radiografías, el modelo habría aprendido patrones que no representan imágenes clínicas reales.




## 4. Estimación de productividad

**Tiempo real invertido** en la conversación principal: ~4 días laborales efectivos, combinando trabajo manual, Claude Code como pair programmer dentro del repositorio y ChatGPT como apoyo de arquitectura, depuración, comandos de verificación y redacción técnica.

**Output producido** (medido en commits reales del repo, descontando merges):

| Bloque | Tiempo estimado sin IA | Con IA |
|---|---|---|
| 7 SDDs + 4 DESIGN docs | 3-4 días | 1 día |
| Pipeline ETL (batch + online, 22 módulos Python, YAML rules, seed) | 3-4 días | 1 día |
| Modelo triaje (generador sintético + entreno + evaluate + CV + servicio HTTP) | 2-3 días | 0.5 día |
| API (3 endpoints listado + PDF generator) | 1-2 días | 0.3 día |
| Dashboard v2 (Streamlit con CSS custom + menú horizontal + formulario + PDF download + timeline polling) | 2-3 días | 0.7 día |
| Bump de versiones + fixes de config (Loki, healthchecks, credenciales) | 1 día | 0.3 día |
| Memoria de decisiones + trazabilidad en CHANGELOG | 0.5 día | intrínseco (parte de cada commit) |
| **Total estimado** | **12-17 días** | **~4 días** |

**Factor de productividad observado**: **~3-4×** en este proyecto concreto. No lo interpreto como una métrica universal: dependió mucho de tener specs claras, validar cada cambio con comandos reales y no aceptar código generado sin revisión.

**Pero hay un coste oculto**: la revisión crítica sigue requiriendo tiempo humano. Aceptar ciegamente produce deuda:
- El primer `validation_rules.yaml` con `no` sin comillas habría arrasado la ingesta si no fuera por el smoke test.
- La propuesta de constantes vitales en el formulario habría producido una UX rota.
- Python 3.13 "porque es lo más nuevo" habría roto el build.

**Conclusión**: la IA aporta **velocidad**, pero el juicio sigue siendo humano. El multiplicador real de productividad depende de la atención crítica del operador.

## 5. Conclusión para la práctica

En un proyecto de 3 semanas con un equipo de 1-2 personas,**Claude Code como pair programmer y ChatGPT como apoyo de arquitectura/debugging** permitió entregar un sistema con:

- **Dos modelos de IA** (uno tabular entrenado en vivo, uno DL diferido).
- **Pipeline de datos con patrón landing zone** (MinIO S3-compat + PostgreSQL + MongoDB/GridFS).
- **API completa** con 3 endpoints del flujo + 3 de listado/detalle/PDF.
- **Dashboard Streamlit** con diseño clínico, PDF descargable, timeline de eventos.
- **más de 15 servicios** en Docker Compose, levantables con un único `docker compose up -d`.
- **Documentación SDD + DESIGN** exhaustiva en markdown, siguiendo la metodología del Master.

Sin la IA, el mismo scope habría requerido más tiempo del disponible o un recorte funcional severo.

La IA **no me sustituyó**: me obligó a tomar decisiones más rápido y a argumentarlas mejor, porque cada cambio arrastraba documentación, spec, código y CHANGELOG de forma coherente.

**Honestidad final**: algunas decisiones que la IA defendió mejor que yo (MinIO sobre AWS real, rechazar el dataset de 100k, rechazar pasar booleanos a 0/1) habrían sido peores si yo hubiera insistido. Esa capacidad de argumentar en contra — y cambiar mi propia decisión — es probablemente el aporte más valioso, por encima de la velocidad de tecleo.

## Consideraciones éticas trabajadas con IA

Durante el desarrollo se usó IA no solo para generar código, sino también para revisar riesgos del sistema. La discusión permitió identificar que, en un entorno sanitario, no basta con maximizar accuracy. Se priorizó el análisis de falsos negativos, especialmente COVID-19 y Neumonía, porque tienen mayor impacto clínico que ciertos falsos positivos.

También se revisó la necesidad de no subir datasets, pesos ni `.env` al repositorio, y de documentar claramente que el sistema es académico y no sustituye el criterio médico.