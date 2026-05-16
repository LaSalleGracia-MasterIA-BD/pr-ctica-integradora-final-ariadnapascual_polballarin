# DESIGN-08b — Modelo tabular de sospecha de enfermedad: diseño técnico

> Extensión de [`DESIGN-08-modelo-triaje.md`](DESIGN-08-modelo-triaje.md). Añade un **segundo clasificador** sobre el mismo formulario que predice una **sospecha de enfermedad** (diagnóstico diferencial orientativo), entrenado con el mismo generador sintético. Incluye también dos cambios arquitectónicos asociados: (1) renombre del endpoint de triaje a un **endpoint combinado `/predict`** que devuelve triaje + enfermedad, y (2) **persistencia raw del formulario en MinIO** al inicio del flujo online para cumplir el principio de data lake del enunciado §4.2.

---

**Versión:** 1.0
**Fecha:** 2026-04-27
**Autor:** Pol Ballarín
**Estado:** `ready-for-implementation`

---

## 1. Contexto

El enunciado §3.1 cita explícitamente *"predicción de enfermedades"* como ejemplo de modelo de IA aceptable. El triaje (DESIGN-08) ya cubre *"clasificación de pacientes"*, pero el formulario que el paciente rellena tiene 15 campos clínicos suficientes para sugerir un **diagnóstico diferencial orientativo** además del nivel de gravedad. Añadir esta segunda predicción enriquece el valor clínico simulado del sistema y aprovecha datos que ya estamos recogiendo.

Este DESIGN cierra:

- Catálogo de enfermedades (clases del clasificador).
- Reglas heurísticas que generan la etiqueta sintética (paralelas a las de `rules.py`).
- Estructura de la respuesta combinada del servicio `ml-triage` (triaje + enfermedad).
- Regla de "diagnóstico diferencial" (top-1, "X o Y", o top-3).
- Persistencia raw del formulario en MinIO (capa data lake del flujo online).
- Persistencia de la sospecha en Mongo (`predictions_disease`).
- Cambios en el pipeline online y en el dashboard.

## 2. Decisiones cerradas

| Decisión | Valor |
|---|---|
| Algoritmo | **`HistGradientBoostingClassifier`** (mismo que triaje, por consistencia y reutilización de pipeline de features) |
| Catálogo de clases | **11**: 10 enfermedades + `inespecifico` (catch-all) — ver §3 |
| Output | **Diagnóstico diferencial adaptativo** de 1 a 3 etiquetas — ver §6 |
| Umbral "X o Y" | Se incluye una clase secundaria si su `prob ≥ 0.70 × prob_primary` |
| Umbral `low_confidence` | `prob_primary < 0.40` |
| Servicio | **Mismo `ml-triage`** (puerto 8002). Carga ambos modelos en el mismo proceso. Renombrar a `ml-models` se descarta por evitar churn de infra. |
| Endpoint | **`POST /predict`** (renombre de `/predict-triage`). Output combinado `{triage, disease}`. El path antiguo se elimina, no se mantiene alias. |
| Versionado | `dis-<YYYYMMDD>-<hash8>` independiente de `tri-`. La respuesta declara ambas versiones. |
| Persistencia raw | **MinIO** bucket `raw`, prefijo `online/YYYY/MM/DD/<correlation_id>.json` |
| Persistencia sospecha | **Mongo** colección nueva `predictions_disease`, paralela a `predictions_triage` |

## 3. Catálogo de enfermedades

Definimos 11 clases mutuamente excluyentes. La granularidad busca: (a) cubrir los 7 valores de `motivo_principal`, (b) mantener clases distinguibles con los síntomas que tenemos, (c) no excederse del rango donde el modelo sintético deja de aprender bien (~10-12).

| Etiqueta | Cuadro clínico que representa | Motivo principal típico |
|---|---|---|
| `gripe_resfriado` | Infección viral común autolimitada | fiebre, otro |
| `neumonia_sospecha` | Sospecha de infección pulmonar bacteriana/viral | fiebre, dificultad_respiratoria |
| `covid_sospecha` | Sospecha de COVID-19 (síntomas + contacto) | fiebre, dificultad_respiratoria, otro |
| `asma_epoc_exacerbacion` | Exacerbación de patología respiratoria crónica | dificultad_respiratoria |
| `cardiopatia_aguda_sospecha` | Sospecha de cardiopatía aguda (IAM, angina) | dolor_toracico |
| `gastroenteritis` | Gastroenteritis aguda (cuadro abdominal leve-moderado) | dolor_abdominal |
| `apendicitis_sospecha` | Sospecha de apendicitis (abdominal severo) | dolor_abdominal |
| `traumatismo` | Lesión traumática (sin distinguir leve/grave — el triaje ya lo hace) | traumatismo |
| `cefalea_migrana` | Cefalea/migraña (síntoma neurológico no urgente) | sintomas_neurologicos |
| `ictus_sospecha` | Sospecha de ictus / déficit neurológico agudo | sintomas_neurologicos |
| `inespecifico` | No hay sospecha clara o cuadro inespecífico | otro, multi-motivo |

> **Nota clínica obligatoria** (a documentar en memoria técnica §9 y §10 del enunciado): "sospecha" es lenguaje deliberado — el sistema **nunca diagnostica**. La salida es orientativa, dirigida al personal de admisión para apoyo a la priorización, no al paciente.

## 4. Generación del dataset sintético

### 4.1 Cambio mínimo en el generador

`training/generate_dataset.py` añade una **columna nueva** `disease_target` calculada por `disease_rules.py`. La columna `target` (triaje) **no cambia**. Mismo CSV, dos targets — el `train.py` actual lee `target` y el nuevo `train_disease.py` lee `disease_target`.

Esquema de salida actualizado: 17 columnas (15 features + `target` + `disease_target`).

### 4.2 Reglas clínicas para `disease_target`

Orden: primera regla que cumple fija la clase. Las reglas se evalúan **independientemente** de las de triaje.

```text
Reglas (en orden de evaluación)

1. cardiopatia_aguda_sospecha:
   motivo_principal == 'dolor_toracico' Y (
     edad >= 50 OR 'cardiopatia' in enfermedades_cronicas OR intensidad_dolor >= 7
   )

2. ictus_sospecha:
   motivo_principal == 'sintomas_neurologicos' Y (
     intensidad_dolor >= 7 OR edad >= 65
   )

3. cefalea_migrana:
   motivo_principal == 'sintomas_neurologicos' Y NOT regla 2

4. asma_epoc_exacerbacion:
   motivo_principal == 'dificultad_respiratoria' Y 'asma_epoc' in enfermedades_cronicas

5. covid_sospecha:
   contacto_covid_reciente == 'si' Y (
     fiebre_subjetiva != 'no' OR tos != 'no' OR motivo_principal == 'dificultad_respiratoria'
   )

6. neumonia_sospecha:
   motivo_principal in ('dificultad_respiratoria', 'fiebre') Y
   fiebre_subjetiva == 'alta' Y
   tos == 'con_flema'

7. apendicitis_sospecha:
   motivo_principal == 'dolor_abdominal' Y intensidad_dolor >= 7 Y duracion_sintomas in ('<24h', '1-3d')

8. gastroenteritis:
   motivo_principal == 'dolor_abdominal' Y NOT regla 7

9. traumatismo:
   motivo_principal == 'traumatismo'

10. gripe_resfriado:
    motivo_principal == 'fiebre' OR (
      tos != 'no' Y fiebre_subjetiva != 'no' Y motivo_principal == 'otro'
    )

11. inespecifico (catch-all):
    todo lo demás
```

> Las reglas son **deliberadamente más laxas y solapadas** que las de triaje, porque "diagnóstico diferencial" implica que un mismo cuadro puede caer en dos clases. El ruido tipo A (etiqueta movida a clase relacionada) se ajusta abajo.

### 4.3 Distribución medida

Distribución real con `--n 10000 --seed 42` (medida tras implementar las reglas de §4.2):

| Clase | Frecuencia (train) |
|---|---|
| `inespecifico` | ~30 % |
| `gripe_resfriado` | ~20 % |
| `gastroenteritis` | ~13 % |
| `traumatismo` | ~12 % |
| `covid_sospecha` | ~10 % |
| `cardiopatia_aguda_sospecha` | ~5 % |
| `ictus_sospecha` | ~2.5 % |
| `cefalea_migrana` | ~2.5 % |
| `apendicitis_sospecha` | ~2 % |
| `neumonia_sospecha` | ~1.5 % |
| `asma_epoc_exacerbacion` | ~0.8 % |

El desbalance es **realista**: en un servicio de admisión real, `asma_epoc` exacerbada es mucho más rara que un cuadro viral (`gripe_resfriado`) o un dolor abdominal genérico (`gastroenteritis`). Las frecuencias salen del producto de probabilidades de las features que activan cada regla (ej. `asma_epoc_exacerbacion` exige `motivo=dif_resp` × `asma_epoc` ≈ 0.10 × 0.08 = 0.8 %).

**Decisión**: no inflar artificialmente las minoritarias modificando las distribuciones de features — preservar la naturaleza desbalanceada y compensar con `class_weight='balanced'` en el entrenamiento (§5.3). El generador aborta solo si una clase cae **< 0.5 %** (protección contra degeneración severa, no contra desbalance natural).

### 4.4 Ruido específico para enfermedad

Reutilizamos las máscaras de muestra ya creadas para triaje (5 % tipo A + 5 % tipo B sobre filas disjuntas). El ruido tipo A para enfermedad sigue una **matriz de proximidad clínica**:

| Origen | Destinos plausibles (50/50) |
|---|---|
| `gripe_resfriado` | `covid_sospecha` o `neumonia_sospecha` |
| `neumonia_sospecha` | `covid_sospecha` o `gripe_resfriado` |
| `covid_sospecha` | `gripe_resfriado` o `neumonia_sospecha` |
| `gastroenteritis` | `apendicitis_sospecha` o `inespecifico` |
| `apendicitis_sospecha` | `gastroenteritis` |
| `cefalea_migrana` | `ictus_sospecha` o `inespecifico` |
| `ictus_sospecha` | `cefalea_migrana` |
| `cardiopatia_aguda_sospecha` | `inespecifico` |
| `asma_epoc_exacerbacion` | `neumonia_sospecha` |
| `traumatismo` | `inespecifico` |
| `inespecifico` | random uniforme entre las 10 enfermedades |

El ruido tipo B (síntomas contradictorios manteniendo target) ya implementado en triaje **no se duplica** — la misma alteración de campos también afecta al modelo de enfermedad sin código extra.

## 5. Pipeline de entrenamiento

### 5.1 Estructura de código añadida

```
services/ml-triage/training/
├── disease_rules.py            # Reglas §4.2
├── train_disease.py            # CLI: entrena clasificador de enfermedad
├── evaluate_disease.py         # Métricas + matriz confusión 11×11
└── critical_analysis_disease.py
```

`generate_dataset.py` se modifica para invocar `assign_disease_from_rules` además de `assign_triage_from_rules` y emitir la columna `disease_target`.

### 5.2 Preprocesado

**Idéntico al de triaje** (`features.py` ya lo expone). Los 15 campos del formulario van por el mismo `ColumnTransformer` — reutilizamos `ficha_to_feature_row`.

### 5.3 Modelo

```python
HistGradientBoostingClassifier(
    max_iter=400,                  # ligeramente más que triaje (más clases)
    learning_rate=0.05,
    max_depth=6,
    min_samples_leaf=20,           # más bajo: clases minoritarias
    l2_regularization=0.1,
    early_stopping=True,
    validation_fraction=None,
    n_iter_no_change=20,
    random_state=42,
    class_weight='balanced',       # compensa desbalance fuerte
)
```

`class_weight='balanced'` es la principal diferencia frente a triaje: con 11 clases y distribución asimétrica, sin compensación las minoritarias se ignoran.

### 5.4 CLI

```
python -m training.train_disease \
  --data data/synthetic/triage/ \
  --output models/disease/ \
  --seed 42
```

Produce `models/disease/dis-<YYYYMMDD>-<hash8>/` con la misma estructura del triaje (`model.joblib`, `metadata.json`, `metrics.json`, `confusion_matrix.png`, `critical_analysis.md`) + el symlink `models/disease/current`.

## 6. Output combinado del servicio

### 6.1 Schema Pydantic

`schemas.py` añade:

```python
class DiseasePrediction(BaseModel):
    label: str
    probability: float = Field(..., ge=0.0, le=1.0)


class DiseaseOutput(BaseModel):
    differential: list[DiseasePrediction]    # 1, 2 o 3 elementos
    low_confidence: bool                     # primary < 0.40
    model_version: str                       # dis-YYYYMMDD-hash8
    inference_time_ms: int


class PredictOutput(BaseModel):
    """Respuesta combinada del endpoint POST /predict (triaje + sospecha)."""
    triage: TriageOutput
    disease: DiseaseOutput
    inference_time_ms: int                   # latencia total (triage + disease)
```

`TriageOutput` no cambia (compatibilidad de tests existentes y de `predictions_triage` en Mongo).

### 6.2 Regla del diagnóstico diferencial

```text
probs = predict_proba(ficha)            # dict label -> p
sorted_probs = sort desc by p
primary = sorted_probs[0]
threshold = 0.70 * primary.probability

differential = [primary]
for cand in sorted_probs[1:3]:
    if cand.probability >= threshold:
        differential.append(cand)
    else:
        break

low_confidence = primary.probability < 0.40
```

Resultado por count:
- `len(differential) == 1` — sospecha clara.
- `len(differential) == 2` — "X o Y".
- `len(differential) == 3` — diagnóstico diferencial completo.

### 6.3 Predictor combinado

`predictor.py` se reescribe para:

- Cargar **ambos artefactos** al arrancar (`tri-...` desde `ML_TRIAGE_MODEL_PATH`, `dis-...` desde nueva env `ML_DISEASE_MODEL_PATH`).
- `is_healthy()` exige los dos cargados.
- `predict(ficha)` ejecuta los dos pipelines secuencialmente (~1-2 ms cada uno) y compone `PredictOutput`.

Si solo uno de los dos modelos carga, el servicio queda **unhealthy** entero — no degradamos a "solo triaje", para mantener simple el contrato del endpoint.

### 6.4 Rutas

| Antes | Después |
|---|---|
| `POST /predict-triage` → `TriageOutput` | `POST /predict` → `PredictOutput` |
| `GET /health` (igual) | `GET /health` (igual; chequea ambos modelos) |

`/predict-triage` se **elimina**, no queda alias. Confirmado: el único cliente runtime era `services/pipeline/app/clients/triage_client.py`, que se actualiza en §8.

## 7. Persistencia raw del formulario en MinIO

### 7.1 Motivación

Hoy el flujo online (`process_patient_ficha` en `services/pipeline/app/online.py`) no toca MinIO — el formulario va directo a validación → transform → PG → triaje. Esto rompe el principio de data lake del enunciado §4.2 ("ingesta automatizada en almacenamiento") porque solo el batch lo cumple.

Añadir un `put_object` al inicio del flujo es ~5 líneas y deja el original del formulario inmutable, addressable por `correlation_id`, recuperable para replay/debug/auditoría.

### 7.2 Convención de claves

```
s3://<S3_BUCKET_RAW>/online/YYYY/MM/DD/<correlation_id>.json
```

Body: el dict del formulario serializado a JSON UTF-8 sin transformar. Content-Type `application/json`. Metadata S3:

- `source=formulario_web`
- `correlation_id=<id>`
- `received_at=<ISO 8601 UTC>`

### 7.3 Implementación

`storage/raw_source.py` ya tiene `S3Source.put_object`. Añadimos un helper:

```python
def persist_raw_online_payload(
    payload: dict,
    correlation_id: str,
    s3_source: S3Source,
) -> str:
    """Sube el JSON original a raw/ y devuelve la key. Best-effort: si falla,
    log warning y continuar — no bloquear el flujo online por MinIO caído."""
    today = datetime.now(timezone.utc)
    key = f"online/{today:%Y/%m/%d}/{correlation_id}.json"
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    s3_source.put_object(
        key,
        body,
        ContentType="application/json",
        Metadata={
            "source": "formulario_web",
            "correlation_id": correlation_id,
            "received_at": today.isoformat(),
        },
    )
    return key
```

`process_patient_ficha` lo invoca **antes** de la validación, dentro de un `try/except` que solo registra warning si falla — la captura raw es valor añadido, no debe tirar el flujo si MinIO está caído.

### 7.4 Decisión: por qué best-effort y no bloqueante

Alternativas consideradas:

- **Bloqueante** (raw obligatorio antes de procesar): si MinIO cae, el formulario se pierde. Inaceptable para una práctica que enseña resiliencia.
- **Asíncrono** (cola tipo Redis): añade infra. Sobreingeniería para el alcance.
- **Best-effort con log de warning** (elegida): el flujo continúa; el evento `pipeline.online.raw_persisted=false` queda en `system_events` para auditar después. Trade-off: en caso de outage de MinIO, la trazabilidad raw se pierde para esos formularios. Aceptable y honesto.

## 8. Cambios en el pipeline online

### 8.1 `services/pipeline/app/clients/triage_client.py`

- URL: `<ml_triage_url>/predict-triage` → `<ml_triage_url>/predict`.
- Función renombrada: `predict_triage(ficha)` → `predict_combined(ficha)`. Devuelve el dict completo `{triage, disease, inference_time_ms}`. Renombrar `TriageUnavailable` → `MlServiceUnavailable` (evita confusión cuando falla la sospecha).
- Settings (`config.py`): la env var `ml_triage_url` se mantiene (apunta al mismo servicio); no se renombra a `ml_models_url` para no inflar el diff.

### 8.2 `services/pipeline/app/online.py`

- Tras transform y carga en PG, una sola llamada `predict_combined(ficha)` devuelve ambas predicciones.
- `loading.persist_triage_prediction(...)` se mantiene tal cual (consume `prediction["triage"]`).
- Se añade `loading.persist_disease_prediction(...)` — análogo, escribe en `predictions_disease`.
- El `try/except MlServiceUnavailable` envuelve la llamada combinada. Si el servicio cae, **ambos** quedan `pending_*`. No se intenta separar fallos entre los dos modelos (simplicidad).

### 8.3 `services/pipeline/app/orchestrator.py` (batch)

Mismo cambio: `predict_triage` → `predict_combined`, persistir ambas. El batch ya itera fila a fila, no hay refactor estructural.

### 8.4 Persistencia en Mongo: `predictions_disease`

Documento:

```json
{
  "_id": ObjectId,
  "pseudo_id": "PAT-000123",
  "admission_id": null,
  "differential": [
    {"label": "covid_sospecha", "probability": 0.62},
    {"label": "gripe_resfriado", "probability": 0.45}
  ],
  "low_confidence": false,
  "model_version": "dis-20260427-abcd1234",
  "ficha_snapshot": {...},
  "correlation_id": "online-...",
  "source": "formulario_web",
  "predicted_at": ISODate,
  "inference_status": "completed"
}
```

Índices: `pseudo_id` (lookup por paciente), `predicted_at` (rango), `inference_status` (cola de pendientes para automation).

`init/mongo/init.js` añade la creación de la colección + índices al arranque.

## 9. Cambios en API y dashboard

### 9.1 API (`services/api/`)

- `schemas.py`: añadir `DiseasePrediction` + `DiseaseOutput`. La respuesta de `POST /patients` (que hoy devuelve el resultado del pipeline online) incluye también la sospecha.
- `main.py`: ajustar la construcción de la respuesta — ya delega en `process_patient_ficha`, así que el cambio es propagar el dict tal cual.
- Endpoint nuevo: `GET /patients/{pseudo_id}/disease` para que el dashboard recupere la última sospecha al refrescar la ficha (paralelo a `/patients/{pseudo_id}/triage` si existe).

### 9.2 Dashboard Streamlit (`services/dashboard/app.py`)

Las vistas que ya muestran el resultado del triaje (Alta/Media/Baja) añaden inline un bloque debajo:

- **1 etiqueta**: "Sospecha: **gripe_resfriado** (62%)"
- **2 etiquetas**: "Posible **gripe_resfriado** (38%) **o COVID-19 sospecha** (32%)"
- **3 etiquetas**: "Diagnóstico diferencial: **gripe_resfriado** / **COVID-19 sospecha** / **neumonía sospecha**" (con probabilidades en tooltip o subtítulo).
- **`low_confidence: true`**: banner amarillo "Sin sospecha clara — derivar a valoración médica".

Disclaimer fijo visible en cada bloque: *"Sospecha orientativa basada en síntomas auto-reportados. No sustituye valoración médica."* (cumple §6.3 y §7 del enunciado).

Mapping de etiqueta interna → label visible (snake_case → human):

```python
DISEASE_LABELS_HUMAN = {
    "gripe_resfriado": "Gripe / resfriado",
    "neumonia_sospecha": "Sospecha de neumonía",
    "covid_sospecha": "Sospecha de COVID-19",
    ...
    "inespecifico": "Cuadro inespecífico",
}
```

## 10. Versionado

`predict.model_version` ya no aplica al output combinado. La versión vive **dentro de cada bloque**:

- `triage.model_version` = `tri-...` (sin cambios)
- `disease.model_version` = `dis-...`

Ambas se persisten respectivamente en `predictions_triage` y `predictions_disease`. Despliegue: actualizar el symlink `models/disease/current` y reiniciar `ml-triage`.

## 11. Pruebas y validación (checklist implementable)

### Generación y entrenamiento

- [ ] `generate_dataset.py --n 10000 --seed 42` produce CSVs con columnas `target` Y `disease_target`. Bytes-idénticos en dos ejecuciones (extiende SDD-08 CA-1).
- [ ] Distribución de `disease_target` cumple §4.3: ninguna clase < 1.5 % en ningún split.
- [ ] `train_disease.py --data data/synthetic/triage/ --output models/disease/` produce `model.joblib`, `metadata.json`, `metrics.json`, `confusion_matrix.png`, `critical_analysis.md`.
- [ ] F1 macro sobre test ≥ 0.55 (umbral mínimo para 11 clases con ruido). F1 macro ≤ 0.95 (no debe ser perfecto — hay ruido y solapes).

### Servicio

- [ ] `curl -X POST http://localhost:8002/predict -H 'Content-Type: application/json' -d '{...ficha...}'` devuelve `PredictOutput` con `triage` + `disease`.
- [ ] La regla del 70 %: con una ficha conocida que active solapamiento, `differential` tiene 2 elementos.
- [ ] `low_confidence: true` cuando `primary < 0.40` (verificable con ficha "inespecifica" todo a defaults).
- [ ] `GET /health` sigue devolviendo 200 con ambos modelos cargados; 503 si falta cualquiera de los dos.
- [ ] Eliminar `models/disease/current` y reiniciar: `/health` = 503.

### Persistencia raw

- [ ] Enviar formulario por dashboard → existe objeto en `s3://raw/online/YYYY/MM/DD/<correlation_id>.json` con el JSON original (verificable con `mc cp` o consola MinIO en :9001).
- [ ] Apagar MinIO, enviar formulario: el flujo termina con éxito (paciente persistido + predicciones guardadas) y se emite evento `system_events` con nivel warning indicando raw no persistido.

### Persistencia sospecha

- [ ] Tras envío del formulario, en Mongo `predictions_disease` aparece un documento con `pseudo_id` igual al paciente, `differential` con 1-3 entradas, `model_version` = `dis-...`.
- [ ] Apagar `ml-triage`, enviar formulario, rearrancar: tanto `predictions_triage` como `predictions_disease` quedan en estado `pending_*` y se completan en el reintento de automation (extiende SDD-08 CA-12 a ambas predicciones).

### Dashboard

- [ ] La vista de paciente muestra el bloque de sospecha bajo el nivel de triaje, con disclaimer visible.
- [ ] El renderizado coincide con `len(differential)`: 1 → "Sospecha", 2 → "Posible X o Y", 3 → "Diagnóstico diferencial".
- [ ] Cuando `low_confidence`, banner amarillo presente.

## 12. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| 11 clases con dataset sintético produce F1 macro muy bajo | `class_weight='balanced'` + `min_samples_leaf=20`; si aun así <0.55, fusionar clases solapadas (`cefalea_migrana` + `ictus_sospecha` → `neurologico`) |
| El umbral 0.70 da siempre `len(differential) == 1` (modelo demasiado seguro) | Calibrar con `CalibratedClassifierCV` si la distribución de probabilidades es muy bimodal |
| MinIO best-effort esconde fallos silenciosos | Cada fallo emite evento `system_events` con nivel warning; queda visible en el dashboard de monitorización |
| Doble inferencia añade latencia | Medir; si p95 > 250 ms, ejecutar las dos predicciones en paralelo con `concurrent.futures` |
| El nombre `ml-triage` pasa a ser engañoso (ahora también predice enfermedad) | No renombramos el servicio para no inflar el diff de Docker/compose. Documentar en README que el servicio aloja **ambos** modelos. |

## 13. Limitación crítica (obligatoria en memoria técnica)

Ampliación de la limitación de DESIGN-08 §6.2.4 (a copiar verbatim al `critical_analysis_disease.md`):

> Las etiquetas de enfermedad son **sintéticas**, generadas por reglas heurísticas que el equipo ha codificado a mano. El modelo aprende esas reglas con un 10 % de ruido — no aprende patrones epidemiológicos reales. Su uso clínico real está **explícitamente desautorizado**: la salida es una sospecha orientativa para apoyo administrativo (priorización de admisión), nunca un diagnóstico. En un sistema real haría falta entrenamiento con historiales clínicos validados, supervisión médica continua, y certificación regulatoria (CE, FDA, AEMPS, etc.).

Encaja directamente con §6.3 ("Evaluación y criterio clínico") y §7 ("Consideraciones éticas y legales") del enunciado.

## 14. Referencias

- Spec base de triaje: [`SDD-08-modelo-triaje.md`](SDD-08-modelo-triaje.md)
- Diseño previo de triaje: [`DESIGN-08-modelo-triaje.md`](DESIGN-08-modelo-triaje.md)
- Spec pipeline (consumidor): [`SDD-02-pipeline.md`](SDD-02-pipeline.md), [`DESIGN-02-pipeline.md`](DESIGN-02-pipeline.md)
- Spec almacenamiento (`predictions_disease`): [`SDD-03-almacenamiento.md`](SDD-03-almacenamiento.md)
- Spec API + Dashboard (formulario): [`SDD-05-api-dashboard.md`](SDD-05-api-dashboard.md)
- Enunciado §3.1 ("predicción de enfermedades"), §6.3, §7 (ética y limitaciones)
