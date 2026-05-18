# 07 — Infraestructura Big Data, monitorización y calidad de datos

## Objetivo

Completar la parte de infraestructura Big Data exigida por el enunciado:

- despliegue completo con Docker Compose;
- pipeline escalable;
- almacenamiento combinado;
- monitorización centralizada;
- validación de calidad;
- alertas ante fallos o datos inválidos.

## Herramientas de IA utilizadas

- **Claude Code**: apoyo para modificar ficheros del repositorio, mejorar servicios y documentación.
- **ChatGPT**: apoyo para depuración guiada, diseño de pruebas, comandos Docker/Mongo/Loki y validación contra el enunciado.

## Especificación previa usada como prompt base

Antes de implementar esta parte se tomaron como referencia los siguientes documentos:

- `DESIGN-01-arquitectura.md`
- `DESIGN-02-pipeline.md`
- `DESIGN-03-almacenamiento.md`
- `SDD-02-pipeline.md`
- `SDD-07-monitorizacion.md`

La especificación pedía un sistema hospitalario con:

- servicios separados;
- almacenamiento estructurado y no estructurado;
- procesamiento escalable;
- API y dashboard;
- logs centralizados;
- validación de datos;
- alertas operativas.

## Prompts representativos

### Prompt 1 — Integración de Dask

> Necesito que el pipeline use un framework de procesamiento distribuido o escalable. Tenemos Docker Compose y un pipeline batch con CSV. Propón cómo integrar Dask con scheduler, worker y lectura mediante `dask.dataframe`.

### Resultado

Se añadió:

- servicio `dask-scheduler`;
- servicio `dask-worker`;
- integración del pipeline con Dask;
- lectura particionada de CSV;
- dashboard Dask en `http://localhost:8787`.

Se verificó con una prueba de CSV usando `dask.dataframe`, obteniendo particiones y ejecución correcta con un worker conectado.

## Prompts representativos

### Prompt 2 — Modelos tabulares de triaje y enfermedad

> El servicio `ml-triage` está unhealthy porque no encuentra los modelos. Necesito entrenar dos modelos tabulares, generar artefactos `model.joblib`, fijar `current.txt` y levantar el servicio con healthcheck correcto.

### Resultado

Se corrigió el flujo de entrenamiento en Docker:

- generación de dataset sintético;
- entrenamiento de modelo de triaje;
- entrenamiento de modelo de sospecha de enfermedad;
- creación de artefactos en `models/triage` y `models/disease`;
- healthcheck correcto de `ml-triage`.

Evidencia:

```json
{
  "status": "ok",
  "triage_version": "tri-20260514-60eff3c2",
  "disease_version": "dis-20260514-8c9a3874"
}

Prompts representativos
Prompt 3 — Monitorización con Loki y Promtail

Quiero que el proyecto tenga logging centralizado real con Loki y Promtail. Hay que evitar que Promtail recoja logs antiguos de otros proyectos Docker y verificar que Loki devuelve logs del pipeline.

Resultado

Se desplegaron:

loki;
promtail;
volumen persistente para Loki;
volumen de posiciones para Promtail;
configuración para recolectar logs Docker;
consulta LogQL validada contra el servicio pipeline.

Consulta final validada:

$query = '{compose_service="pipeline"} |= "pipeline.run.end"'
$url = "http://localhost:3100/loki/api/v1/query_range?limit=10&start=$start&end=$end&query=$([uri]::EscapeDataString($query))"
curl.exe -s $url

Resultado esperado:

status: success;
resultType: streams;
aparición de evento pipeline.run.end;
etiquetas compose_project, compose_service, container, logstream.
Prompts representativos
Prompt 4 — Calidad de datos y rechazos

Necesito demostrar detección de registros incompletos, corruptos o inválidos. Crea una prueba con un CSV inválido y comprueba que el pipeline persiste los rechazos en MongoDB.

Resultado

Se ejecutó el batch sobre:

patients/quality-test-invalid.csv

Resultado del pipeline:

{
  "records_in": 5,
  "valid": 1,
  "rejected": 4,
  "rejects_persisted": 4,
  "pacientes_insertados": 1,
  "ingresos_insertados": 1,
  "triage_completed": 1,
  "triage_pending": 0
}

Se verificó en MongoDB la colección ingestion_rejects, con rechazos como:

missing_field:edad;
sexo:enum;
intensidad_dolor:max:10.
Prompts representativos
Prompt 5 — Alertas automáticas

Quiero un servicio de automatización que revise system_events, detecte warnings/errors y cree alertas deduplicadas en MongoDB.

Resultado

Se implementó y corrigió el servicio automation.

Funcionalidades:

escaneo periódico de system_events;
detección de eventos warning y error;
generación de alertas en la colección alerts;
deduplicación mediante dedup_key;
notificación simulada por MongoDB/dashboard.

Evidencia:

Nueva alerta creada: pipeline.validation.done:<run_id>:warning
Nueva alerta creada: pipeline.rejects.persisted:<run_id>:warning

Documentos creados en MongoDB:

pipeline.validation.done
pipeline.rejects.persisted
Casos donde la IA acertó
Propuso separar claramente Dask, pipeline, API, dashboard y modelos.
Ayudó a identificar que el problema de ml-triage no era el endpoint, sino la ausencia de artefactos de modelo.
Propuso usar Docker para entrenar modelos y evitar problemas de dependencias locales en Windows/Python.
Ayudó a validar Loki con una query LogQL correcta usando start, end y codificación URL.
Ayudó a diseñar una prueba realista de calidad con registros inválidos.
Casos donde hubo que corregir o iterar
Inicialmente Promtail capturaba logs antiguos de otros proyectos Docker. Se corrigió aislando mejor la configuración y reiniciando Promtail.
Algunas queries LogQL fallaban por problemas de comillas en PowerShell. Se resolvió usando variables y EscapeDataString.
El servicio automation generaba conflictos en MongoDB al actualizar campos incluidos tanto en $setOnInsert como en $set. Se corrigió separando campos de inserción y campos de actualización.
El entrenamiento local falló por incompatibilidades de paquetes en Python/Windows. Se migró el entrenamiento al contenedor Docker.
Impacto estimado en productividad


# 07 — Infraestructura Big Data, monitorización y calidad de datos

## Objetivo

Completar la infraestructura Big Data exigida por el enunciado:
- Despliegue completo con Docker Compose
- Pipeline escalable
- Almacenamiento combinado
- Monitorización centralizada
- Validación de calidad
- Alertas ante fallos o datos inválidos

## Herramientas de IA utilizadas

- Claude Code: apoyo para modificar ficheros, mejorar servicios y documentación
- ChatGPT: apoyo para depuración, diseño de pruebas, comandos Docker/Mongo/Loki y validación

## Especificación previa

Se tomaron como referencia los documentos de arquitectura y pipeline (`DESIGN-01`, `DESIGN-02`, `DESIGN-03`, `SDD-02`, `SDD-07`). El sistema debía tener servicios separados, almacenamiento estructurado/no estructurado, procesamiento escalable, API/dashboard, logs centralizados, validación de datos y alertas operativas.

## Prompts y resultados clave

### 1. Integración de Dask

Se integró Dask con scheduler y worker, y el pipeline usa `dask.dataframe` para lectura particionada de CSV. Se desplegó dashboard Dask en `http://localhost:8787` y se verificó la ejecución distribuida.

### 2. Modelos tabulares de triaje y enfermedad

Se corrigió el flujo de entrenamiento en Docker:
- Generación de dataset sintético
- Entrenamiento de modelos de triaje y enfermedad
- Creación de artefactos en `models/triage` y `models/disease`
- Healthcheck correcto de `ml-triage`

Evidencia:
```json
{
  "status": "ok",
  "triage_version": "tri-20260514-60eff3c2",
  "disease_version": "dis-20260514-8c9a3874"
}
```

### 3. Monitorización con Loki y Promtail

Se desplegaron Loki y Promtail, con volúmenes persistentes y configuración para recolectar solo logs del proyecto. Se validó la consulta LogQL:
```powershell
$query = '{compose_service="pipeline"} |= "pipeline.run.end"'
$url = "http://localhost:3100/loki/api/v1/query_range?limit=10&start=$start&end=$end&query=$([uri]::EscapeDataString($query))"
curl.exe -s $url
```
Resultado esperado: status success, aparición de evento `pipeline.run.end`, etiquetas compose_project, compose_service, container, logstream.

### 4. Calidad de datos y rechazos

Se probó el pipeline con un CSV inválido (`patients/quality-test-invalid.csv`). Resultado:
```json
{
  "records_in": 5,
  "valid": 1,
  "rejected": 4,
  "rejects_persisted": 4,
  "pacientes_insertados": 1,
  "ingresos_insertados": 1,
  "triage_completed": 1,
  "triage_pending": 0
}
```
Se verificaron los rechazos en MongoDB (`ingestion_rejects`).

### 5. Alertas automáticas

Se implementó un servicio de automatización que escanea `system_events`, detecta warnings/errors y crea alertas deduplicadas en MongoDB (`alerts`). Ejemplo de alertas:
- `pipeline.validation.done:<run_id>:warning`
- `pipeline.rejects.persisted:<run_id>:warning`

## Aciertos de la IA

- Separación clara de servicios (Dask, pipeline, API, dashboard, modelos)
- Identificación de problemas de artefactos en `ml-triage`
- Uso de Docker para entrenar modelos y evitar problemas de dependencias locales
- Validación de Loki con query LogQL correcta
- Diseño de pruebas realistas de calidad

## Correcciones y aprendizajes

- Promtail capturaba logs antiguos: se aisló la configuración y se reinició el servicio
- Problemas de comillas en queries LogQL en PowerShell: se resolvió usando variables y EscapeDataString
- Conflictos en MongoDB por $setOnInsert/$set: se separaron campos de inserción y actualización
- Entrenamiento local fallido por incompatibilidades: se migró al contenedor Docker

## Impacto en productividad

- Ahorro de tiempo alto en generación de comandos, depuración, diseño de scripts, documentación y pruebas
- Mejora de documentación alta
- Calidad del código buena, pero siempre revisada manualmente
- Dependencia de la IA controlada mediante pruebas end-to-end

## Conclusión

La IA aceleró el desarrollo y debugging, pero la validación manual fue imprescindible. Cada cambio relevante se verificó con comandos Docker, consultas a MongoDB, healthchecks y pruebas funcionales del pipeline.