# DESIGN-06 — Modelo DL de radiografías: diseño técnico

> Diseño de implementación del modelo DL especificado en [`SDD-06-modelo-dl.md`](SDD-06-modelo-dl.md). Cierra las 6 dudas abiertas del SDD y define backbone, hiperparámetros, augmentation, splits, métricas y estructura de código para `services/ml-inference/`.

---

**Versión:** 1.0
**Fecha:** 2026-04-21
**Autor:** Pol Ballarín
**Estado:** `ready-for-implementation`

---

## 1. Contexto

Spec base: SDD-06 — clasificación triple de radiografías de tórax en **Sana / Neumonía / COVID-19** mediante **transfer learning** sobre un backbone pre-entrenado en ImageNet. Dataset público *COVID-19 Radiography Database* (Kaggle). Servicio `ml-inference` (puerto 8001) ya esqueletado (stub en `services/ml-inference/app/app.py`).

Este DESIGN cierra los **6 `[NEEDS CLARIFICATION]`** de SDD-06 §7 y da la estructura lista para implementar. Además **cierra el `[NEEDS CLARIFICATION]` de SDD-03 RNF-6** (tamaño de subset).

## 2. Decisiones cerradas

| Duda de SDD-06 §7 | Decisión |
|---|---|
| Arquitectura del backbone | **`torchvision.models.efficientnet_b0`** pre-entrenado en ImageNet (~5 M params, más ligero que ResNet50 ~25 M). Alternativa documentada: ResNet50 como fallback si la convergencia falla. |
| Proporción de splits train / val / test | **70 / 15 / 15** estratificado por clase, `random_state=42`. |
| Estrategia de compensación de desbalance | **Pesos por clase en la pérdida** (`CrossEntropyLoss(weight=...)`). Cálculo: `w_i = N / (C * n_i)` donde `N` = total, `C` = 3, `n_i` = muestras clase i. Simple y efectivo sin duplicar datos. |
| Umbral `P(COVID-19)` para alerta (SDD-01 §7) | **`0.80`** por defecto (conservador sin ser estricto). Configurable vía env var `COVID_ALERT_THRESHOLD`. A revisar tras entreno si la distribución de probabilidades en test sugiere otro corte. |
| Regla de desempate de probabilidades (SDD-01 §7) | **Sana < Neumonía < COVID-19** (ante empate, elegir la clase de mayor gravedad — criterio clínico conservador). |
| Umbrales de tiempo de inferencia (RNF-1) | **p95 < 3 s** por imagen en CPU de portátil (EfficientNet-B0 en eval mode + imagen 224×224 debería cumplir con margen). Medir al final del entrenamiento y ajustar si se supera. |

**Adicionalmente cerramos**:

| Duda externa | Decisión |
|---|---|
| Tamaño de subset del dataset (SDD-03 RNF-6) | **Balanceado a ~3 000 imágenes por clase = 9 000 totales** para los tres splits conjuntos. Cubre entrenamiento viable en CPU y evita que las clases minoritarias del dataset original distorsionen la evaluación. |

## 3. Estructura de código

```
services/ml-inference/
├── requirements.txt                 # torch==2.4.1, torchvision, pillow, fastapi, pydantic, numpy
├── app/                             # Runtime (imagen ml-inference)
│   ├── __init__.py
│   ├── app.py                       # FastAPI
│   ├── schemas.py                   # Pydantic: PredictionOutput
│   ├── predictor.py                 # load model + predict()
│   └── config.py                    # env vars
└── training/                         # Offline (no se copia al contenedor)
    ├── __init__.py
    ├── prepare_data.py              # Download + subset balanceado + splits
    ├── dataset.py                   # torch.utils.data.Dataset custom
    ├── augment.py                   # Transforms torchvision
    ├── model.py                     # Construye EfficientNet-B0 + head de 3 clases
    ├── train.py                     # Loop de entrenamiento + early stopping
    ├── evaluate.py                  # Matriz confusión + métricas
    └── critical_analysis.py         # Informe clínico Markdown
```

Como en DESIGN-08, el stage `ml-inference` del Dockerfile solo necesita `app/`. `training/` se ejecuta fuera del contenedor.

## 4. Preparación del dataset

### 4.1 Origen

**COVID-19 Radiography Database** (Kaggle, M.E.H. Chowdhury et al., 2020-2021). ~21 k imágenes, 4 clases originales. Usaremos **3**:

| Clase original (Kaggle) | Clase del proyecto |
|---|---|
| `Normal` | **Sana** |
| `Viral Pneumonia` + `Lung_Opacity` (opacidad pulmonar no-COVID) | **Neumonía** |
| `COVID` | **COVID-19** |

**Nota**: `Lung_Opacity` no es idéntica a neumonía viral, pero clínicamente suele indicar infiltrado compatible con neumonía. Juntarlas mejora el balance y es defendible clínicamente. Documentar en la memoria.

Descarga manual (no automatizada — Kaggle requiere auth):

```
# Fuera del contenedor, una vez
kaggle datasets download -d tawsifurrahman/covid19-radiography-database -p data/raw/
unzip data/raw/covid19-radiography-database.zip -d data/raw/
```

Alternativa documentada: dejar las imágenes en `data/raw/covid-radiography/` con la estructura esperada y saltarse el paso `kaggle`.

### 4.2 Subset balanceado

`training/prepare_data.py`:

1. Listar ficheros por clase tras el mapeo de §4.1.
2. **Muestrear aleatoriamente 3 000** por clase (con `random_state=42`). Si una clase tiene menos de 3 000 → coger todo lo disponible + loguear aviso.
3. Generar splits **estratificados** 70/15/15 con `sklearn.model_selection.train_test_split` (dos pasadas: 85/15 → de ese 85 saca 70/15 para entreno/validación).
4. Escribir tres CSVs con columnas `filepath, class_original, class_target` en `data/covid-subset/{train,val,test}.csv`.
5. Guardar `metadata.json` con semilla, conteos por clase y split, versión del script y `git_commit`.

### 4.3 Preprocesado (inferencia y entrenamiento)

- **Resize** a 224×224 (input estándar de EfficientNet-B0).
- **Conversión a RGB** (si fuera escala de grises, se replica canal 3 veces).
- **Normalización** con `mean=[0.485, 0.456, 0.406]`, `std=[0.229, 0.224, 0.225]` (ImageNet).

### 4.4 Augmentation (solo en train, no en val/test)

```python
# training/augment.py
from torchvision import transforms as T

train_tf = T.Compose([
    T.Resize((256, 256)),
    T.RandomResizedCrop(224, scale=(0.85, 1.0)),
    T.RandomHorizontalFlip(p=0.5),
    T.RandomRotation(degrees=10),
    T.ColorJitter(brightness=0.1, contrast=0.1),
    T.ToTensor(),
    T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])

eval_tf = T.Compose([
    T.Resize((224, 224)),
    T.ToTensor(),
    T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])
```

No se aplica flip vertical (anatómicamente incorrecto en radiografía) ni rotaciones fuertes. Se prioriza realismo clínico.

## 5. Modelo

### 5.1 Arquitectura

```python
# training/model.py
import torch.nn as nn
from torchvision.models import efficientnet_b0, EfficientNet_B0_Weights

def build_model(num_classes: int = 3, freeze_backbone: bool = False):
    weights = EfficientNet_B0_Weights.IMAGENET1K_V1
    model = efficientnet_b0(weights=weights)

    if freeze_backbone:
        for p in model.features.parameters():
            p.requires_grad = False

    # Sustituir la cabeza (1 capa final)
    in_features = model.classifier[1].in_features
    model.classifier[1] = nn.Linear(in_features, num_classes)
    return model
```

### 5.2 Estrategia de entrenamiento

**Dos fases** (transfer learning clásico):

1. **Warm-up** (3 épocas): backbone **congelado**, solo entrena la nueva cabeza (`classifier[1]`). Aprende rápido sin desestabilizar el backbone pre-entrenado.
2. **Fine-tuning** (hasta 17 épocas más con early stopping): **descongelar** backbone completo. LR más bajo (1/10 del warm-up).

### 5.3 Hiperparámetros

```python
config = {
    "img_size": 224,
    "batch_size": 32,              # reducible a 16 en CPU modesta
    "num_epochs_max": 20,
    "warmup_epochs": 3,
    "lr_warmup": 1e-3,
    "lr_finetune": 1e-4,
    "weight_decay": 1e-4,
    "optimizer": "AdamW",
    "loss": "CrossEntropyLoss (class-weighted)",
    "lr_scheduler": "ReduceLROnPlateau(factor=0.5, patience=2)",
    "early_stopping_patience": 5,
    "early_stopping_metric": "val_f1_macro",
    "seed": 42,
    "device": "cuda if available else cpu",
    "num_workers": 2,
}
```

### 5.4 Reproducibilidad

- Semillas fijadas en `numpy`, `random`, `torch`, `torch.cuda` (si aplica) al arranque del script.
- `torch.backends.cudnn.deterministic = True` si hay GPU.
- `requirements.txt` pinneado.
- Dataset splits con la misma semilla producen los mismos CSVs byte-idénticos.

## 6. Métricas y evaluación

### 6.1 Cálculo sobre test

- Matriz de confusión 3×3 (absoluta y normalizada).
- Accuracy global.
- Precisión, recall y F1 por clase.
- **F1 macro** (media no ponderada — importante con clases ligeramente desbalanceadas).
- **Sensibilidad (recall) de COVID-19**: métrica crítica clínicamente, reportarla explícitamente. Un modelo con alta accuracy pero baja recall de COVID es inaceptable en contexto sanitario.
- **Matriz de confusión + PNG** guardados en el artefacto.

### 6.2 Análisis crítico obligatorio (SDD-06 RF-11)

`training/critical_analysis.py` genera un Markdown con:

1. **Tipo de error más frecuente**: celda máxima fuera de la diagonal. Ej.: si *COVID-19 → Neumonía* es el error más frecuente, discutir que clínicamente son parecidos en radiografía y que un humano también los confunde.
2. **Impacto clínico de cada tipo de error**:
   - Falso negativo de **COVID-19** (predicho como Sana o Neumonía) → **peor escenario**: paciente contagioso sin aislar.
   - Falso positivo de **COVID-19** (predicho cuando es Sana o Neumonía) → aislamiento innecesario, coste sanitario pero sin riesgo clínico directo.
   - Falso negativo de **Neumonía** (predicho como Sana) → retraso en tratamiento antibiótico.
3. **Sensibilidad de COVID-19**: valor + interpretación. Si < 0.85, señalar como limitación grave.
4. **Limitaciones documentadas**:
   - Dataset público construido en 2020-2021 — posible no-representatividad de variantes actuales de COVID.
   - Calidad heterogénea de las radiografías de Kaggle (distintos equipos, distintos hospitales).
   - `Lung_Opacity` agrupada con `Viral Pneumonia` por decisión de diseño — agrupa neumonías no solo virales.
   - **No es un producto clínicamente validado**: el modelo es académico.

## 7. Servicio de inferencia

### 7.1 Schema de entrada/salida

El endpoint recibe una imagen por `multipart/form-data` o una referencia a GridFS. Esquema de respuesta:

```python
# app/schemas.py
from pydantic import BaseModel
from typing import Literal

class RadiographyPredictionOutput(BaseModel):
    predicted_class: Literal["Sana", "Neumonía", "COVID-19"]
    probabilities: dict[str, float]    # {"sana": .., "neumonia": .., "covid": ..}
    model_version: str                 # "rx-YYYYMMDD-hash8"
    inference_time_ms: int
    low_confidence: bool                # max(probs) < 0.50
    triggers_covid_alert: bool          # P(COVID-19) > COVID_ALERT_THRESHOLD (0.80)
```

### 7.2 Predictor (`app/predictor.py`)

- Carga el modelo **una vez al arrancar** (`lru_cache` o global singleton).
- Ruta del artefacto: env var `ML_MODEL_PATH=/app/models/rx-20260425-xxxxxxxx/model.pt`. Si no existe, `/healthz` devuelve 503 (SDD-06 RNF-6).
- `predict(image: PIL.Image) -> dict`:
  1. Aplicar `eval_tf` (resize + normalize + tensor).
  2. Forward en modo `eval()` con `torch.no_grad()`.
  3. Softmax.
  4. **Regla de desempate** si dos clases empatan ≤ 1e-9 en probabilidad: elegir la de mayor gravedad (Sana < Neumonía < COVID-19).
  5. Calcular `low_confidence = max(probs) < 0.50` y `triggers_covid_alert = probs["covid"] > env.COVID_ALERT_THRESHOLD`.
  6. Devolver `RadiographyPredictionOutput`.

### 7.3 Rutas (`app/app.py`)

- `GET /health` → 200 si el modelo está cargado, 503 si no.
- `POST /predict` → 200 con `RadiographyPredictionOutput`, 422 si la imagen no es válida, 503 si el modelo no está cargado.

Ambos endpoints sustituyen al stub aleatorio actual de `services/ml-inference/app/app.py`.

### 7.4 Puerto y configuración

- Puerto interno: 8001 (ya en Dockerfile y compose).
- Device: CPU por defecto (`ML_DEVICE=cpu`). GPU solo si se mueve a un host con CUDA — el servicio tolera ambos vía `torch.device(os.getenv("ML_DEVICE", "cpu"))`.

## 8. Versionado

Misma convención que DESIGN-08 y SDD-06 RF-16/RF-17:

- `model_version = "rx-" + yyyymmdd + "-" + sha256(hiperparams || dataset_hash)[:8]`.
- Artefactos en `models/radiography/rx-<version>/`:
  - `model.pt` (pesos + arquitectura serializados con `torch.save`).
  - `metadata.json` (hiperparámetros, hash del dataset, splits, versión).
  - `metrics.json` (matriz confusión, accuracy, precision/recall/F1 por clase, F1 macro, recall COVID).
  - `confusion_matrix.png`.
  - `critical_analysis.md`.
- `models/radiography/current → rx-<version>` (symlink a la versión activa).
- Desplegar nuevo artefacto = actualizar symlink + reiniciar `ml-inference`.

## 9. Integración con el sistema

- **Ingestión**: las radiografías llegan al bucket GridFS `radiographs` vía pipeline batch (SDD-02 RF-2) o vía upload desde la API (SDD-05 RF-5).
- **Watcher de automation** (SDD-04 RF-1): detecta radiografías en estado `pending_prediction`, lee los bytes de GridFS, llama a `POST http://ml-inference:8001/predict` y persiste la respuesta en la colección `predictions_radiography` de Mongo (DESIGN-03 §4.2).
- **Alerta COVID-19** (SDD-04 RF-8, SDD-07): si `triggers_covid_alert = true`, automation emite una alerta tipo `covid_high_confidence` con `dedup_key = "covid_high_confidence:<patient_pseudo_id>:<YYYY-MM-DD>"` (DESIGN-03 §4.5).

## 10. Pruebas y validación (checklist implementable)

### Unitarias

- [ ] `prepare_data.py --seed 42` produce CSVs byte-idénticos en dos corridas (SDD-06 CA-1).
- [ ] Los splits son estratificados: diferencia de proporción por clase entre splits < 2 pp.
- [ ] `augment.py` con `seed=42` aplica la misma secuencia reproducible (verificar con test sobre una imagen fija).
- [ ] `build_model()` devuelve un modelo con la cabeza de 3 salidas y con `classifier[1].weight.requires_grad = True`.

### Entrenamiento

- [ ] Con semilla fijada, dos entrenamientos sobre el mismo subset producen F1 macro dentro de ±3 pp (SDD-06 CA-3).
- [ ] El artefacto persistido contiene `model.pt`, `metadata.json`, `metrics.json`, `confusion_matrix.png`, `critical_analysis.md` (SDD-06 CA-4, CA-5).
- [ ] `recall_covid > 0.75` como mínimo aceptable. Si no, retrabajar (más datos, augmentation, umbrales, arquitectura ResNet50 fallback).

### Servicio

- [ ] `curl -F "file=@test.jpg" http://ml-inference:8001/predict` devuelve JSON válido con los 7 campos (SDD-06 CA-7).
- [ ] `curl -F "file=@test.txt"` devuelve 415 (SDD-06 CA-10).
- [ ] Imagen 10×10 devuelve 422 (SDD-06 casos borde).
- [ ] Sin artefacto en el volumen, `/health` devuelve 503 (SDD-06 CA-8).
- [ ] Dos predicciones bajo la misma `model_version` son deterministas con `torch.manual_seed(42)` y `model.eval()` (SDD-06 CA-12).

### Integración

- [ ] Subir radiografía al endpoint `/upload` de la API (SDD-05 RF-5) → aparece en GridFS → watcher la detecta → predicción persiste en `predictions_radiography` (SDD-06 caso borde "servicio de inferencia no disponible", SDD-04 RF-18).
- [ ] Predicción con `P(COVID-19) > 0.80` produce alerta `covid_high_confidence` en `alerts` (DESIGN-03 §4.5).

### Criterios SDD-06 cubiertos

CA-1 → preparación; CA-2 → preprocesado; CA-3/CA-4 → reproducibilidad del entreno; CA-5 → métricas persistidas; CA-6 → análisis crítico; CA-7/CA-8/CA-9/CA-10 → endpoints; CA-11 → reintentos (combinado con SDD-04); CA-12 → versionado.

## 11. Requirements (pinneados)

`services/ml-inference/requirements.txt`:

```
torch==2.4.1
torchvision==0.19.1
pillow==10.4.0
numpy==2.1.1
fastapi==0.115.0
uvicorn[standard]==0.30.6
pydantic==2.9.2
python-multipart==0.0.12
```

> **Atención**: `torch==2.4.1` CPU-only tiene ~800 MB de imagen. Considerar en Sprint 2 usar `torch` CPU wheel oficial (`--index-url https://download.pytorch.org/whl/cpu`) para reducir a ~200 MB.

## 12. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Entrenamiento en CPU tarda horas | Subset a 3 000/clase + 20 épocas con early stopping + backbone pequeño. En benchmark EfficientNet-B0 en CPU sobre 9k imágenes, entrenamiento típico ~2-4 h. Dejar corriendo en background mientras se avanza en otras piezas. |
| Recall de COVID-19 bajo (< 0.75) | (a) subir peso de la clase COVID-19 en la loss, (b) augmentation más agresivo solo para COVID, (c) probar ResNet50 como fallback, (d) aumentar subset de COVID a 4 000-5 000. |
| Imagen de `ml-inference` > 1 GB | Usar torch CPU-only wheel (reduce a ~200 MB). Multi-stage build para no incluir las dependencias de training. |
| Drift entre preprocesado de training e inferencia | Mantener el preprocesado de inferencia (`eval_tf`) en un módulo compartido entre `training/` y `app/` (o serializado con el modelo). Tests unitarios verifican que coinciden. |
| Dataset no disponible (Kaggle cambió URL) | Documentar URL alternativa en README; subir subset a un bucket público (si se decide S3). |

## 13. Referencias

- Spec base: [`SDD-06-modelo-dl.md`](SDD-06-modelo-dl.md)
- Spec raíz: [`SDD-01-sistema.md`](SDD-01-sistema.md)
- Spec almacenamiento (destino predicciones): [`SDD-03-almacenamiento.md`](SDD-03-almacenamiento.md), [`DESIGN-03-almacenamiento.md`](DESIGN-03-almacenamiento.md)
- Spec automatización (watcher): [`SDD-04-automatizacion.md`](SDD-04-automatizacion.md)
- Spec API (upload): [`SDD-05-api-dashboard.md`](SDD-05-api-dashboard.md)
- Spec pipeline (ingestión): [`SDD-02-pipeline.md`](SDD-02-pipeline.md), [`DESIGN-02-pipeline.md`](DESIGN-02-pipeline.md)
- Dataset: [COVID-19 Radiography Database (Kaggle)](https://www.kaggle.com/datasets/tawsifurrahman/covid19-radiography-database)
- Backbone: [`torchvision.models.efficientnet_b0`](https://pytorch.org/vision/stable/models/generated/torchvision.models.efficientnet_b0.html)
- Transfer learning reference: [PyTorch tutorial](https://pytorch.org/tutorials/beginner/transfer_learning_tutorial.html)
