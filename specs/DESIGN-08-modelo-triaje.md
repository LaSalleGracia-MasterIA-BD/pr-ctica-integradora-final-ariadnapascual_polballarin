# DESIGN-08 — Modelo tabular de triaje: diseño técnico

> Diseño de implementación del modelo de triaje especificado en [`SDD-08-modelo-triaje.md`](SDD-08-modelo-triaje.md). Cierra las decisiones abiertas del SDD y define **cómo** se construyen las piezas: algoritmo concreto, hiperparámetros, reglas del generador sintético, estructura de código, endpoints y pruebas.

---

**Versión:** 1.1
**Fecha:** 2026-04-20 (actualizado 2026-04-27 con nota de DESIGN-08b)
**Autor:** Pol Ballarín
**Estado:** `ready-for-implementation`

> **Nota 2026-04-27**: tras [DESIGN-08b](DESIGN-08b-modelo-enfermedad.md) el servicio `ml-triage` aloja un **segundo modelo** (sospecha de enfermedad) y el endpoint se renombra de `POST /predict-triage` a `POST /predict`, devolviendo un output combinado `{triage, disease}`. Las referencias a `/predict-triage` en este documento se mantienen por contexto histórico — el contrato vigente es el de DESIGN-08b §6.

---

## 1. Contexto

Spec base: SDD-08 — clasificación de pacientes en **Alta / Media / Baja** a partir de una ficha de 15 campos auto-reportados. Dataset **sintético** con reglas + ruido + variable espuria (`hora_envio`). Entrenamiento offline, inferencia online al final del pipeline (SDD-02 modo online). Servicio dedicado `ml-triage` (puerto 8002) ya esqueletado en el repo.

Este documento cierra los **6 `[NEEDS CLARIFICATION]`** de SDD-08 §7, fija reglas concretas del generador y da la estructura de código lista para implementar.

## 2. Decisiones cerradas

| Duda de SDD-08 §7 | Decisión |
|---|---|
| Algoritmo | **`sklearn.ensemble.HistGradientBoostingClassifier`** |
| Ruido intencional (% sobre total) | **10 %**: 5 % etiqueta movida a clase adyacente + 5 % combinaciones síntoma-etiqueta contradictorias |
| Imputación de opcionales (`peso_kg`, `altura_cm`) | **Mediana**, calculada en training y persistida en el artefacto para aplicarse en inferencia |
| Servicio: compartido `ml-inference` vs dedicado | **Dedicado `ml-triage`** (puerto 8002, ya creado en Dockerfile + compose) |
| Umbral tiempo de inferencia (RNF-1) | **p95 < 200 ms** por petición, single-threaded, CPU |
| Confianza mínima `low_confidence` | `max(probabilities) < 0.50` → añadir flag `low_confidence: true` a la respuesta |

Razones breves del algoritmo elegido:

- **HistGradientBoostingClassifier** (sklearn) maneja nativamente mixto categórico/numérico y nulos, es rápido en CPU, ligero (sin dependencia extra de LightGBM/XGBoost) y trae `permutation_importance` para interpretabilidad.
- Alternativas descartadas: Random Forest (performance algo menor en tabular); regresión logística multiclase (insuficiente para interacciones no lineales); red neuronal tabular (overkill para 15 features + 10 k filas).

## 3. Estructura de código

```
services/ml-triage/
├── requirements.txt
├── app/                           # Runtime (servicio HTTP)
│   ├── __init__.py
│   ├── app.py                     # FastAPI + routes
│   ├── schemas.py                 # Pydantic: TriageInput, TriageOutput
│   ├── predictor.py               # Carga artefacto + inferencia + flag low_confidence
│   └── config.py                  # Lectura de ML_TRIAGE_MODEL_PATH + constantes
└── training/                      # Offline (no se copia al contenedor ml-triage)
    ├── __init__.py
    ├── generate_dataset.py        # CLI: produce data/synthetic/triage/{train,val,test}.csv + metadata.json
    ├── rules.py                   # Reglas clínicas del generador sintético
    ├── train.py                   # CLI: entrena y persiste artefacto + métricas
    ├── evaluate.py                # Cálculo métricas + matriz confusión PNG
    └── critical_analysis.py       # Genera informe clínico Markdown
```

El stage `ml-triage` del Dockerfile solo necesita `app/`. El código de `training/` se ejecuta fuera del contenedor (o en una imagen aparte opcional). Esto mantiene la imagen de servicio pequeña.

## 4. Generación del dataset sintético

### 4.1 Esquema de salida

CSV (UTF-8, separador `,`) con 16 columnas: los 15 campos de SDD-08 RF-1 + `target` (`Alta | Media | Baja`).

Nombres de columnas coherentes con el formulario (en español) — mismo contrato usado en el endpoint `/predict-triage`.

### 4.2 Volumen y splits

- **Total**: 10 000 filas (configurable por CLI `--n`).
- **Splits estratificados**: **70 / 15 / 15** (train / val / test) con `random_state=42`.
- **Distribución objetivo de `target`** (sin hacer balanceo artificial — refleja una priorización realista):
  - Alta ~ 25 %
  - Media ~ 35 %
  - Baja ~ 40 %

Si tras aplicar reglas + ruido alguna clase cae por debajo del 10 % de su split, el generador aborta (SDD-08 caso borde "distribución degenerada").

### 4.3 Distribuciones por feature

| Feature | Distribución sintética |
|---|---|
| `edad` | mezcla: uniforme 18-85 (70 %), 0-17 (10 %), 86-110 (20 %) — para no concentrar en adultos |
| `sexo` | categórica {M: 0.48, F: 0.50, Otro: 0.02} |
| `peso_kg` | normal(75, 15), truncada a [40, 150]. Nulo con probabilidad 0.10. |
| `altura_cm` | normal(170, 10), truncada a [140, 205]. Nulo con probabilidad 0.10. |
| `enfermedades_cronicas` | multiselección con probabilidades independientes: diabetes 0.10, hipertension 0.15, asma_epoc 0.08, cardiopatia 0.07, inmunosupresion 0.03. Si ninguna, lista vacía o `['ninguna']` 50/50. |
| `fumador` | {no: 0.65, si: 0.22, exfumador: 0.13} |
| `embarazo` | si sexo=F y edad∈[15,55]: {si: 0.05, no: 0.95}; en otro caso `na` |
| `motivo_principal` | {dolor_toracico: 0.08, dificultad_respiratoria: 0.10, fiebre: 0.18, dolor_abdominal: 0.17, traumatismo: 0.15, sintomas_neurologicos: 0.05, otro: 0.27} |
| `duracion_sintomas` | {<24h: 0.35, 1-3d: 0.35, 4-7d: 0.18, >1sem: 0.12} |
| `intensidad_dolor` | discreta 0-10, sesgada hacia bajos: P(x)=geom(0.25) truncada |
| `fiebre_subjetiva` | {no: 0.55, leve: 0.30, alta: 0.15} |
| `dificultad_respiratoria_subjetiva` | {no: 0.60, leve: 0.22, moderada: 0.13, grave: 0.05} |
| `tos` | {no: 0.55, seca: 0.28, con_flema: 0.17} |
| `contacto_covid_reciente` | {no: 0.55, no_se: 0.30, si: 0.15} |
| `hora_envio` | uniforme discreta 0-23 (**variable espuria**, sin correlación con target) |

### 4.4 Reglas clínicas (función objetivo)

Orden: primera regla que cumple fija la clase antes de aplicar ruido.

**Alta** si cualquiera:
- `motivo_principal == 'sintomas_neurologicos'` Y `intensidad_dolor >= 7`
- `motivo_principal == 'dolor_toracico'` Y (`edad >= 50` O `'cardiopatia' in enfermedades_cronicas` O `intensidad_dolor >= 8`)
- `dificultad_respiratoria_subjetiva == 'grave'`
- `fiebre_subjetiva == 'alta'` Y (`edad >= 65` O `'inmunosupresion' in enfermedades_cronicas`)
- `motivo_principal == 'traumatismo'` Y `intensidad_dolor >= 8`

**Media** si cualquiera (y no se activó Alta):
- `fiebre_subjetiva == 'alta'`
- `dificultad_respiratoria_subjetiva in ('leve', 'moderada')`
- `intensidad_dolor >= 7`
- `motivo_principal == 'dolor_abdominal'` Y `intensidad_dolor >= 6`
- `contacto_covid_reciente == 'si'` Y (`fiebre_subjetiva != 'no'` O `tos != 'no'`)
- `edad >= 65` Y al menos un síntoma presente
- `enfermedades_cronicas` no vacío ni `['ninguna']` Y cualquier síntoma con intensidad > 0

**Baja** en el resto.

> Las reglas priorizan gravedad clínica razonable. La `hora_envio` **no aparece** en ninguna regla — es la variable espuria (SDD-08 RF-6).

### 4.5 Inyección de ruido (10 % total)

Sobre la etiqueta producida por las reglas:

**Ruido tipo A (5 %) — etiqueta movida a clase adyacente**:
- Si era Alta → 50 % Media, 50 % se queda (en realidad, del 5 % afectado → todo a Media).
- Si era Baja → 50 % Media.
- Si era Media → 50 % Alta, 50 % Baja.

**Ruido tipo B (5 %) — contradicciones síntoma/etiqueta**:
- Con probabilidad 0.05 y regla activa, se alteran uno o dos campos de síntomas para generar incoherencia (p. ej. target=Alta pero `intensidad_dolor=0` y `fiebre_subjetiva='no'`), **manteniendo el target original**. Obliga al modelo a no ser trivialmente separable.

El tipo A y el tipo B se aplican sobre muestras **disjuntas**, de modo que el 10 % total es limpio.

### 4.6 CLI del generador

```
python training/generate_dataset.py \
  --n 10000 \
  --seed 42 \
  --output data/synthetic/triage/
```

Produce:
- `train.csv`, `val.csv`, `test.csv` (splits estratificados)
- `metadata.json`: `seed`, `n`, `created_at`, `class_distribution`, `generator_version`, `git_commit` (si disponible)

Dos ejecuciones con la misma `--seed` producen ficheros byte-idénticos (SDD-08 CA-1, RF-7).

## 5. Pipeline de entrenamiento

### 5.1 Preprocesado

`sklearn.compose.ColumnTransformer`:

- **Numéricos** (`edad`, `peso_kg`, `altura_cm`, `intensidad_dolor`, `hora_envio`):
  - `SimpleImputer(strategy='median')` (solo afecta a `peso_kg`/`altura_cm`).
  - Sin scaling — el algoritmo elegido no lo necesita.
- **Categóricos** (`sexo`, `fumador`, `embarazo`, `motivo_principal`, `duracion_sintomas`, `fiebre_subjetiva`, `dificultad_respiratoria_subjetiva`, `tos`, `contacto_covid_reciente`):
  - `OrdinalEncoder(handle_unknown='use_encoded_value', unknown_value=-1)`.
- **Multi-categoría** (`enfermedades_cronicas` como lista):
  - Expansión a 5 columnas booleanas one-hot (`has_diabetes`, `has_hipertension`, `has_asma_epoc`, `has_cardiopatia`, `has_inmunosupresion`) — hecho en un `FunctionTransformer` previo al `ColumnTransformer`.

### 5.2 Modelo

```python
HistGradientBoostingClassifier(
    max_iter=300,
    learning_rate=0.05,
    max_depth=6,
    min_samples_leaf=30,
    l2_regularization=0.1,
    early_stopping=True,
    validation_fraction=None,   # usamos val split externo
    n_iter_no_change=20,
    random_state=42,
)
```

Pipeline completo: `Pipeline([preprocessor, clf])`.

### 5.3 Reproducibilidad

- Semillas: `numpy` (42), `random` (42), `sklearn` `random_state=42` en splits y en el clasificador.
- `requirements.txt` con versiones pinneadas.
- Artefacto persiste: pipeline serializado (`joblib.dump`) + JSON con hiperparámetros, hash del dataset (SHA-256 de los CSVs) y fechas.

### 5.4 CLI de entrenamiento

```
python training/train.py \
  --data data/synthetic/triage/ \
  --output models/triage/ \
  --seed 42
```

Produce:
- `models/triage/tri-<YYYYMMDD>-<hash8>/`
  - `model.joblib`
  - `metadata.json` (hiperparámetros, versión, hash del dataset, fecha)
  - `metrics.json` (matriz confusión, accuracy, precision/recall/F1 por clase, F1 macro, importancia de features)
  - `confusion_matrix.png`
  - `critical_analysis.md`

Además copia como `models/triage/current -> tri-<YYYYMMDD>-<hash8>` (symlink) para que el servicio apunte siempre al artefacto activo.

## 6. Evaluación y análisis crítico

### 6.1 Métricas calculadas sobre test

- Matriz de confusión 3×3 (normalizada y absoluta).
- Accuracy global.
- Precisión / recall / F1 por clase.
- F1 macro.
- Importancia de features: `sklearn.inspection.permutation_importance` sobre val (robusto, no depende de impurity).

### 6.2 Análisis crítico (obligatorio — SDD-08 RF-12)

`training/critical_analysis.py` genera un Markdown con:

1. **Error más frecuente**: identifica la celda fuera de la diagonal con mayor conteo en la matriz de confusión. Discute impacto clínico (p. ej. falsa Baja sobre un Alta).
2. **Importancia de `hora_envio`**: debe ser **baja** (< 0.5 % del total normalizado). Si es mayor, el análisis emite una alerta escrita en el propio Markdown ("*revisa el generador — la variable espuria no debería tener peso*").
3. **Top 5 features más importantes**: lista con valor y discusión breve.
4. **Limitación fundamental**: párrafo fijo pero personalizado con la versión del modelo. Contenido mínimo:
   > El dataset es **sintético** y las etiquetas vienen de reglas que el propio equipo ha codificado (más un 10 % de ruido). El modelo reproduce esas reglas; por construcción, sus métricas **no reflejan utilidad clínica real**. Su valor es pedagógico: demostrar que el flujo SDD → dataset → entrenamiento → evaluación → servicio en producción funciona end-to-end.

## 7. Servicio de inferencia

### 7.1 Schemas (`app/schemas.py`)

`TriageInput` (Pydantic v2) replica exactamente los 15 campos de SDD-08 RF-1, con los mismos `Literal[...]` y rangos. Ya esqueletado en `services/ml-triage/app/app.py` — solo hay que mover a `schemas.py`.

`TriageOutput`:
```python
class TriageOutput(BaseModel):
    predicted_class: Literal["Alta", "Media", "Baja"]
    probabilities: dict[str, float]   # {"alta":.., "media":.., "baja":..}, suman 1.0 ±1e-6
    model_version: str                # ej. "tri-20260420-a1b2c3d4"
    inference_time_ms: int
    low_confidence: bool              # max(probs) < 0.50
```

### 7.2 Predictor (`app/predictor.py`)

- Carga el artefacto desde `ML_TRIAGE_MODEL_PATH` una vez al arrancar (`@lru_cache` o variable global). Si falla, deja el servicio en estado no saludable (SDD-08 RNF-7 / CA-8).
- `predict(ficha: dict) -> dict`:
  1. Convertir `enfermedades_cronicas` en booleanas.
  2. Aplicar el pipeline sklearn (imputación mediana + encoding + predict_proba).
  3. Aplicar **regla de desempate prudente** (SDD-08 RNF-10): si dos máximos empatan (≤ 1e-9), devolver el de mayor gravedad (`Alta > Media > Baja`).
  4. Flag `low_confidence = max(probs) < 0.50`.
  5. Devolver `TriageOutput`.

### 7.3 Rutas (`app/app.py`)

- `GET /health` → 200 si el modelo carga; 503 si no.
- `POST /predict-triage` → 200 con `TriageOutput`, o 422 si validación Pydantic falla, o 503 si `/health` no lo es.

### 7.4 Latencia objetivo

- Single-threaded, CPU: p95 < 200 ms. En tabular de 15 features con HistGB de 300 árboles y max_depth=6 esto debería cumplirse con margen.

## 8. Versionado del modelo

- `model_version = "tri-" + yyyymmdd + "-" + sha256(hiperparams || dataset_hash)[:8]`.
- Cada entrenamiento produce una carpeta con ese nombre; `models/triage/current` apunta a la versión activa.
- La predicción devuelve la `model_version` leída al arrancar; las predicciones persistidas en `predictions_triage` (Mongo) incluyen esa versión. Desplegar versión nueva = reiniciar el contenedor `ml-triage` tras actualizar el symlink.

## 9. Integración con el resto del sistema

- **API** (SDD-05 RF-2bis): `POST /patients` entrega la ficha al pipeline en modo online (SDD-02 RF-24–29).
- **Pipeline online** (SDD-02 RF-26–27): tras persistir paciente en PG, llama `POST http://ml-triage:8002/predict-triage` con la ficha; persiste la predicción en `predictions_triage` de Mongo ligada al `pseudo_id`.
- **Timeout del cliente**: 2 s; si vence, el paciente queda `pending_triage` (SDD-02 RF-28) y automation (SDD-04) reintenta.

## 10. Pruebas y validación (checklist implementable)

- [ ] `python training/generate_dataset.py --n 10000 --seed 42` genera los 3 CSVs + `metadata.json`. Repetir con misma semilla produce ficheros byte-idénticos (SDD-08 CA-1).
- [ ] Ninguna clase por debajo del 10 % en cada split (SDD-08 RF-5).
- [ ] Correlación estadística entre `hora_envio` y `target` (test chi² o Cramér's V) no significativa al 5 % (SDD-08 CA-2).
- [ ] `python training/train.py ...` produce `model.joblib`, `metadata.json`, `metrics.json`, `confusion_matrix.png`, `critical_analysis.md` (SDD-08 CA-4, CA-5, CA-6).
- [ ] Dos entrenamientos con misma semilla y mismo dataset dan F1 macro dentro de ±2 puntos (SDD-08 CA-4).
- [ ] `docker compose up ml-triage` + `curl POST /predict-triage` devuelve JSON válido con los 5 campos (SDD-08 CA-7).
- [ ] `GET /health` devuelve 200 con modelo cargado y 503 sin artefacto en el volumen (SDD-08 CA-8).
- [ ] Enviar ficha inválida (p. ej. `edad=500`) devuelve 422 (SDD-08 CA-9).
- [ ] Empate `P(Alta) = P(Media)` → respuesta es `Alta` (SDD-08 CA-10).
- [ ] Flujo end-to-end: dashboard → formulario → `POST /patients` → PG + `predictions_triage` Mongo → confirmación en navegador con nivel (SDD-08 CA-11).
- [ ] Apagar `ml-triage`, enviar ficha, volver a arrancar: ficha termina predicha sin intervención manual (SDD-08 CA-12).

## 11. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Generador sintético produce distribución degenerada con ciertas semillas | Test en `metadata.json` + abort si alguna clase < 10 % |
| `hora_envio` acaba con importancia alta (generador mal calibrado) | El propio `critical_analysis.md` avisa; retrabajo del generador (ajustar rangos de distribución para romper cualquier correlación accidental) |
| Imagen del contenedor `ml-triage` demasiado pesada (scikit-learn + pandas) | Usar `python:3.11-slim` + `pip install --no-cache-dir`; ~200 MB final |
| Latencia p95 > 200 ms en CPU modestas | Reducir `max_iter` o `max_depth`; medir y ajustar |
| Modelo sobreajusta las reglas y da 100 % accuracy | Sube a 15 % el ruido, verificar con cross-validation que F1 < 0.98 |

## 12. Referencias

- Spec base: [`SDD-08-modelo-triaje.md`](SDD-08-modelo-triaje.md)
- Spec raíz: [`SDD-01-sistema.md`](SDD-01-sistema.md)
- Spec pipeline (consumidor del endpoint): [`SDD-02-pipeline.md`](SDD-02-pipeline.md)
- Spec API (entrada del formulario): [`SDD-05-api-dashboard.md`](SDD-05-api-dashboard.md)
- Spec almacenamiento (`predictions_triage`): [`SDD-03-almacenamiento.md`](SDD-03-almacenamiento.md)
- Spec monitorización (logs): [`SDD-07-monitorizacion.md`](SDD-07-monitorizacion.md)
- [scikit-learn HistGradientBoostingClassifier](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingClassifier.html)
- [sklearn.inspection.permutation_importance](https://scikit-learn.org/stable/modules/generated/sklearn.inspection.permutation_importance.html)
