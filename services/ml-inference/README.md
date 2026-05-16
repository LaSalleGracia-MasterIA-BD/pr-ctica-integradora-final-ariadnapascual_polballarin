# ML Inference — Clasificación de radiografías de tórax

Servicio de Deep Learning para clasificación de radiografías de tórax en tres categorías:

- **Sana**
- **Neumonía**
- **COVID-19**

Este módulo forma parte del sistema hospitalario Big Data y proporciona inferencia HTTP mediante FastAPI. Su objetivo académico es demostrar un flujo completo de aprendizaje profundo aplicado a imágenes médicas: preparación de datos, entrenamiento, evaluación, análisis crítico, comparación de arquitecturas y despliegue containerizado.

El módulo responde específicamente al bloque del enunciado:

> **Aprendizaje Automático y Redes Neuronales: Clasificación de Radiografías**

La finalidad no es únicamente obtener un modelo con buena accuracy, sino justificar técnicamente las decisiones, evaluar los errores con criterio clínico y mostrar cómo se integra el modelo dentro de una infraestructura hospitalaria containerizada.

---

## 1. Objetivo del módulo

El servicio `ml-inference` procesa imágenes de radiografía de tórax y devuelve:

- clase predicha;
- probabilidades por clase;
- versión del modelo;
- tiempo de inferencia;
- indicador de baja confianza;
- alerta específica si la probabilidad de COVID-19 supera un umbral configurado.

Endpoints principales:

```http
GET /healthz
POST /predict
```

`/healthz` devuelve `200 OK` si el modelo está cargado y `503 Service Unavailable` si no hay artefacto disponible.

`/predict` recibe una imagen JPEG/PNG mediante `multipart/form-data`.

Ejemplo conceptual de respuesta:

```json
{
  "predicted_class": "COVID-19",
  "probabilities": {
    "Sana": 0.05,
    "Neumonía": 0.10,
    "COVID-19": 0.85
  },
  "model_version": "rx-20260515-a1b2c3d4",
  "inference_time_ms": 245,
  "low_confidence": false,
  "triggers_covid_alert": true
}
```

---

## 2. Requisitos del enunciado cubiertos

### Investigación y Desarrollo

| Requisito | Cómo se cubre |
|---|---|
| Elección del modelo | Se implementan y comparan varias arquitecturas: CNN simple, ResNet18 y EfficientNet-B0. |
| Tratamiento de datos | Se define preparación de dataset, split estratificado, resize, normalización y data augmentation moderado. |
| Integración | El modelo se expone como servicio Docker `ml-inference`, consumible desde API/dashboard y conectado al flujo Big Data. |

### Evaluación y criterio clínico

| Requisito | Cómo se cubre |
|---|---|
| Matriz de confusión | `training.evaluate` genera `confusion_matrix.png` y matriz numérica en `metrics.json`. |
| Reflexión crítica | `training.critical_analysis` genera `critical_analysis.md` con impacto clínico de errores. |
| Justificación técnica | Este README documenta arquitectura, preprocesamiento, limitaciones, métricas y decisión final. |

---

## 3. Dataset utilizado

Se utiliza el dataset público **COVID-19 Radiography Dataset**, con la siguiente estructura local:

```text
COVID-19_Radiography_Dataset/
├── COVID/
│   ├── images/
│   └── masks/
├── Lung_Opacity/
│   ├── images/
│   └── masks/
├── Normal/
│   ├── images/
│   └── masks/
├── Viral Pneumonia/
│   ├── images/
│   └── masks/
├── COVID.metadata.xlsx
├── Lung_Opacity.metadata.xlsx
├── Normal.metadata.xlsx
├── Viral Pneumonia.metadata.xlsx
└── README.md.txt
```

El dataset original **no se versiona en Git** porque contiene miles de imágenes y ficheros pesados. Se excluye mediante `.gitignore`.

Rutas ignoradas:

```gitignore
COVID-19_Radiography_Dataset/
data/covid-subset/
data/radiography/
models/radiography/**/model.pt
```

---

## 4. Importante: exclusión de máscaras

El dataset incluye carpetas `masks/` además de `images/`.

Las máscaras son segmentaciones binarias o auxiliares, no radiografías originales. Si se entrenara el modelo con máscaras, el aprendizaje quedaría contaminado porque el modelo podría aprender patrones artificiales no presentes en una radiografía real.

Por eso `prepare_data.py` se corrigió para recoger únicamente imágenes desde:

```text
COVID-19_Radiography_Dataset/<clase>/images/
```

y excluir explícitamente:

```text
COVID-19_Radiography_Dataset/<clase>/masks/
```

Comprobación ejecutada:

```powershell
Select-String -Path .\data\covid-subset\*.csv -Pattern "masks"
```

Resultado esperado:

```text
# Sin salida
```

Esto demuestra que los CSV limpios no contienen rutas a `masks`.

---

## 5. Definición de clases

El reto exige una clasificación triple. Para adaptarlo al dataset original se aplica el siguiente mapeo:

| Clase original del dataset | Clase final del modelo |
|---|---|
| `Normal` | `Sana` |
| `Viral Pneumonia` | `Neumonía` |
| `Lung_Opacity` | `Neumonía` |
| `COVID` | `COVID-19` |

La decisión de agrupar `Lung_Opacity` dentro de `Neumonía` se toma porque el objetivo académico pide tres clases, no cuatro.

Esta simplificación se documenta como limitación clínica: una opacidad pulmonar puede estar asociada a procesos distintos, no necesariamente neumonía infecciosa. Sin embargo, para el reto académico permite representar un grupo patológico respiratorio distinto de `Sana` y `COVID-19`.

---

## 6. Preparación de datos

El script de preparación está en:

```text
services/ml-inference/training/prepare_data.py
```

Genera tres particiones estratificadas:

```text
data/covid-subset/
├── train.csv
├── val.csv
├── test.csv
└── metadata.json
```

Cada CSV contiene:

| Campo | Descripción |
|---|---|
| `filepath` | Ruta local de la imagen. |
| `class_original` | Clase original del dataset. |
| `class_target` | Clase final usada por el modelo. |

---

## 7. Preparación limpia usada para experimentación

Preparación limpia con 1000 imágenes por clase final:

```powershell
docker compose run --rm ml-inference python -m training.prepare_data `
  --raw-dir /app/COVID-19_Radiography_Dataset `
  --output-dir /app/data/covid-subset `
  --limit-per-class 1000 `
  --seed 42
```

Resultado esperado:

```text
Saved splits to /app/data/covid-subset
Counts final: {'Sana': 1000, 'Neumonía': 1000, 'COVID-19': 1000}
```

La distribución final queda balanceada:

```powershell
Import-Csv .\data\covid-subset\train.csv | Group-Object class_target | Select-Object Name, Count
Import-Csv .\data\covid-subset\val.csv   | Group-Object class_target | Select-Object Name, Count
Import-Csv .\data\covid-subset\test.csv  | Group-Object class_target | Select-Object Name, Count
```

Distribución esperada aproximada:

| Split | Sana | Neumonía | COVID-19 |
|---|---:|---:|---:|
| Train | 699-700 | 699-700 | 699-700 |
| Val | 150-151 | 150-151 | 150-151 |
| Test | 150 | 150 | 150 |

La pequeña diferencia de una muestra se debe al redondeo del split estratificado.

---

## 8. Preprocesamiento de imágenes

El preprocesamiento se define en:

```text
services/ml-inference/training/augment.py
```

### Entrenamiento

Se aplican transformaciones moderadas:

```python
Resize((256, 256))
RandomResizedCrop(224)
RandomHorizontalFlip(p=0.5)
RandomRotation(degrees=10)
ColorJitter(brightness=0.1, contrast=0.1)
ToTensor()
Normalize(mean=ImageNet, std=ImageNet)
```

### Justificación clínica

No se aplican aumentos agresivos porque podrían alterar patrones radiológicos relevantes.

Por ejemplo:

- rotaciones grandes podrían cambiar la orientación anatómica;
- deformaciones fuertes podrían crear estructuras no reales;
- cambios extremos de contraste podrían ocultar patrones pulmonares;
- crops excesivos podrían eliminar zonas diagnósticas.

Por eso se usan aumentos suaves, suficientes para mejorar generalización sin distorsionar la imagen médica.

### Validación, test e inferencia

Para validación, test e inferencia se usa un pipeline determinista:

```python
Resize((224, 224))
ToTensor()
Normalize(mean=ImageNet, std=ImageNet)
```

Esto garantiza que las métricas sean reproducibles y que el endpoint `/predict` procese las imágenes igual que el conjunto de test.

---

## 9. Arquitecturas investigadas

Para responder al requisito de investigación del enunciado, se plantean tres arquitecturas:

| Arquitectura | Tipo | Rol experimental |
|---|---|---|
| `simple_cnn` | CNN entrenada desde cero | Baseline simple. |
| `resnet18` | Transfer learning | Modelo preentrenado clásico, robusto y fácil de justificar. |
| `efficientnet_b0` | Transfer learning | Modelo eficiente con buena relación precisión/coste. |

---

## 10. CNN simple

La CNN simple se usa como baseline.

Objetivo:

- comprobar si una red entrenada desde cero aprende patrones básicos;
- establecer una referencia mínima;
- comparar contra modelos preentrenados.

Ventajas:

- arquitectura sencilla;
- entrenamiento más ligero;
- interpretabilidad técnica más directa;
- útil como control experimental.

Limitaciones:

- aprende desde cero;
- necesita más datos para generalizar bien;
- suele rendir peor que transfer learning en datasets médicos pequeños o medianos;
- mayor riesgo de sobreajuste.

Comando:

```powershell
docker compose run --rm ml-inference python -m training.train `
  --backbone simple_cnn `
  --train-csv /app/data/covid-subset/train.csv `
  --val-csv /app/data/covid-subset/val.csv `
  --models-root /app/models/radiography `
  --batch-size 32 `
  --warmup-epochs 0 `
  --max-epochs 8 `
  --num-workers 0 `
  --seed 42
```

---

## 11. ResNet18

ResNet18 se usa como modelo de transfer learning clásico.

Objetivo:

- comparar una arquitectura ampliamente usada con la CNN simple;
- aprovechar pesos preentrenados en ImageNet;
- evaluar si una red residual mejora la generalización.

Ventajas:

- arquitectura conocida y estable;
- menor riesgo de degradación del gradiente gracias a conexiones residuales;
- buen equilibrio entre tamaño y rendimiento;
- más fácil de explicar que arquitecturas más modernas.

Limitaciones:

- ImageNet no es un dataset médico;
- los filtros preentrenados no están especializados en radiografías;
- puede requerir fine-tuning cuidadoso;
- puede ser más pesado que una CNN simple en CPU.

Comando:

```powershell
docker compose run --rm ml-inference python -m training.train `
  --backbone resnet18 `
  --train-csv /app/data/covid-subset/train.csv `
  --val-csv /app/data/covid-subset/val.csv `
  --models-root /app/models/radiography `
  --batch-size 16 `
  --warmup-epochs 2 `
  --max-epochs 8 `
  --num-workers 0 `
  --seed 42
```

---

## 12. EfficientNet-B0

EfficientNet-B0 se usa como modelo eficiente de transfer learning.

Objetivo:

- evaluar una arquitectura moderna y ligera;
- buscar mejor equilibrio entre precisión, coste computacional y tamaño;
- mantener viabilidad de inferencia en CPU dentro de Docker Compose.

Ventajas:

- buena relación precisión/parámetros;
- eficiente para despliegue;
- suele rendir bien con transfer learning;
- tamaño manejable para un servicio hospitalario académico.

Limitaciones:

- arquitectura menos intuitiva que ResNet18;
- requiere descarga de pesos preentrenados si no están cacheados;
- puede tardar más en entrenar que una CNN simple;
- el rendimiento final depende de la calidad del dataset y de la ausencia de fugas como máscaras.

Comando:

```powershell
docker compose run --rm ml-inference python -m training.train `
  --backbone efficientnet_b0 `
  --train-csv /app/data/covid-subset/train.csv `
  --val-csv /app/data/covid-subset/val.csv `
  --models-root /app/models/radiography `
  --batch-size 16 `
  --warmup-epochs 2 `
  --max-epochs 8 `
  --num-workers 0 `
  --seed 42
```

---

## 13. Estrategia de entrenamiento

El entrenamiento está en:

```text
services/ml-inference/training/train.py
```

Se utiliza:

- semilla fija (`--seed 42`);
- splits estratificados;
- batch size configurable;
- entrenamiento en CPU o GPU según disponibilidad;
- versionado automático de artefactos;
- registro de configuración en `metadata.json`.

Para modelos preentrenados se usa una estrategia en dos fases:

### Fase 1 — Warmup

Se congela el backbone y se entrena principalmente la cabeza clasificadora.

Objetivo:

- adaptar la última capa a las tres clases del problema;
- evitar destruir pesos preentrenados desde el primer epoch;
- estabilizar el entrenamiento.

### Fase 2 — Fine-tuning

Se desbloquea el modelo completo y se entrena con learning rate menor.

Objetivo:

- adaptar representaciones internas a radiografías;
- mejorar rendimiento sin sobreajuste extremo;
- permitir que el modelo aprenda patrones específicos del dominio.

---

## 14. Artefactos generados

Cada entrenamiento genera un artefacto versionado:

```text
models/radiography/rx-YYYYMMDD-hash8/
├── model.pt
└── metadata.json
```

Después de evaluación se añaden:

```text
models/radiography/rx-YYYYMMDD-hash8/
├── metrics.json
├── confusion_matrix.png
└── critical_analysis.md
```

También se actualiza:

```text
models/radiography/current.txt
```

con la versión activa del último entrenamiento.

---

## 15. Evaluación obligatoria

La evaluación se ejecuta con:

```text
services/ml-inference/training/evaluate.py
```

Comando:

```powershell
$version = Get-Content .\models\radiography\current.txt

docker compose run --rm ml-inference python -m training.evaluate `
  --artifact-dir "/app/models/radiography/$version" `
  --test-csv /app/data/covid-subset/test.csv `
  --batch-size 16 `
  --num-workers 0
```

Genera:

```text
models/radiography/<VERSION>/
├── metrics.json
├── confusion_matrix.png
└── metadata.json
```

El archivo `metrics.json` incluye:

- `accuracy`;
- `f1_macro`;
- `recall_covid`;
- precision por clase;
- recall por clase;
- F1 por clase;
- matriz de confusión.

---

## 16. Por qué no basta con accuracy

En un entorno sanitario, una accuracy alta puede ocultar errores clínicamente graves.

Ejemplo:

- un modelo puede acertar muchos casos sanos;
- pero fallar casos COVID;
- y aun así tener una accuracy aparentemente aceptable.

Por eso se prioriza revisar:

| Métrica | Motivo |
|---|---|
| `recall_covid` | Mide cuántos casos COVID reales detecta el modelo. |
| `recall_neumonia` | Mide cuántas neumonías reales detecta. |
| `f1_macro` | Penaliza mal rendimiento en clases minoritarias o difíciles. |
| Matriz de confusión | Permite ver qué errores concretos comete. |
| `low_confidence` | Ayuda a detectar predicciones poco fiables. |

---

## 17. Matriz de confusión

La matriz de confusión se interpreta como:

| Fila | Columna |
|---|---|
| Clase real | Clase predicha |

Orden de clases:

```text
Sana
Neumonía
COVID-19
```

Ejemplo de matriz:

```json
[
  [65, 4, 6],
  [13, 113, 24],
  [12, 9, 54]
]
```

Interpretación:

| Real | Predicha Sana | Predicha Neumonía | Predicha COVID-19 |
|---|---:|---:|---:|
| Sana | 65 | 4 | 6 |
| Neumonía | 13 | 113 | 24 |
| COVID-19 | 12 | 9 | 54 |

Lectura clínica:

- `COVID-19 -> Sana`: falso negativo COVID de alto riesgo;
- `COVID-19 -> Neumonía`: error epidemiológico relevante;
- `Neumonía -> Sana`: riesgo de retraso diagnóstico;
- `Sana -> COVID-19`: falso positivo con sobrecarga asistencial.

---

## 18. Resultado intermedio registrado

Durante el desarrollo se generó un modelo EfficientNet-B0 con artefacto:

```text
rx-20260515-0d04651b
```

Métricas observadas:

```json
{
  "accuracy": 0.7733333333333333,
  "f1_macro": 0.7619882168692668,
  "recall_covid": 0.72,
  "per_class": {
    "Sana": {
      "precision": 0.7222222222222222,
      "recall": 0.8666666666666667,
      "f1": 0.7878787878787878
    },
    "Neumonía": {
      "precision": 0.8968253968253969,
      "recall": 0.7533333333333333,
      "f1": 0.8188405797101449
    },
    "COVID-19": {
      "precision": 0.6428571428571429,
      "recall": 0.72,
      "f1": 0.6792452830188679
    }
  },
  "confusion_matrix": [
    [65, 4, 6],
    [13, 113, 24],
    [12, 9, 54]
  ]
}
```

### Nota metodológica importante

Ese resultado se conserva como evidencia de que el flujo de entrenamiento/evaluación funciona, pero no debe considerarse necesariamente resultado final si fue generado antes de corregir la contaminación de rutas `masks/`.

Tras detectar que algunos CSV incluían rutas a `masks/`, se corrigió `prepare_data.py` para recoger solo imágenes desde carpetas `images/`. Los resultados finales deben salir de entrenamientos posteriores con el dataset limpio.

---

## 19. Análisis crítico clínico

El análisis crítico se genera con:

```text
services/ml-inference/training/critical_analysis.py
```

Comando:

```powershell
$version = Get-Content .\models\radiography\current.txt

docker compose run --rm ml-inference python -m training.critical_analysis `
  --artifact-dir "/app/models/radiography/$version"
```

Genera:

```text
models/radiography/<VERSION>/critical_analysis.md
```

Este informe analiza:

- error más frecuente de la matriz de confusión;
- impacto clínico de falsos negativos;
- impacto clínico de falsos positivos;
- sensibilidad específica de COVID-19;
- limitaciones del dataset;
- limitaciones del modelo;
- recomendación de uso como apoyo, no diagnóstico.

---

## 20. Impacto clínico de errores

### Falso negativo COVID-19

Caso:

```text
Real: COVID-19
Predicción: Sana
```

Impacto:

- riesgo epidemiológico alto;
- posible falta de aislamiento;
- contagio intrahospitalario;
- retraso en activación de protocolo COVID;
- falsa sensación de seguridad clínica;
- posible exposición de otros pacientes vulnerables.

Este es uno de los errores más graves del sistema.

---

### COVID-19 confundido con Neumonía

Caso:

```text
Real: COVID-19
Predicción: Neumonía
```

Impacto:

- riesgo medio-alto;
- el paciente puede recibir atención respiratoria;
- pero se pierde el componente epidemiológico;
- puede fallar el aislamiento;
- se reduce la vigilancia de contactos;
- puede afectar a la gestión hospitalaria.

Este error es menos grave que clasificar COVID como sano, pero sigue siendo relevante.

---

### Neumonía clasificada como Sana

Caso:

```text
Real: Neumonía
Predicción: Sana
```

Impacto:

- retraso en tratamiento antibiótico o antiviral;
- empeoramiento clínico;
- posible alta incorrecta;
- riesgo en pacientes ancianos o con comorbilidades;
- falta de seguimiento respiratorio.

---

### Sana clasificada como patológica

Caso:

```text
Real: Sana
Predicción: Neumonía o COVID-19
```

Impacto:

- pruebas innecesarias;
- ansiedad del paciente;
- sobrecarga asistencial;
- uso innecesario de recursos;
- posible aislamiento innecesario si se predice COVID.

Este error suele ser menos grave que un falso negativo, pero afecta a la eficiencia hospitalaria.

---

## 21. Criterio clínico de elección del modelo

La elección final del modelo no debe basarse únicamente en `accuracy`.

Criterio recomendado:

1. Descartar modelos con recall COVID-19 demasiado bajo.
2. Revisar falsos negativos COVID en matriz de confusión.
3. Revisar falsos negativos de neumonía.
4. Comparar `f1_macro`.
5. Considerar coste de inferencia y despliegue.
6. Elegir el modelo con mejor equilibrio clínico-operativo.

Ejemplo:

| Modelo | Accuracy | F1 macro | Recall COVID | Recall Neumonía | Decisión |
|---|---:|---:|---:|---:|---|
| CNN simple | pendiente | pendiente | pendiente | pendiente | Baseline |
| ResNet18 | pendiente | pendiente | pendiente | pendiente | Comparar |
| EfficientNet-B0 | pendiente | pendiente | pendiente | pendiente | Comparar |

La tabla se completa automáticamente con `training.compare_models`.

---

## 22. Comparación de modelos

El script de comparación es:

```text
services/ml-inference/training/compare_models.py
```

Comando:

```powershell
docker compose run --rm ml-inference python -m training.compare_models `
  --models-root /app/models/radiography `
  --output /app/models/radiography/comparison
```

Genera:

```text
models/radiography/comparison/
├── comparison.csv
├── comparison.md
└── comparison.json
```

La comparación debe analizar:

- accuracy;
- F1 macro;
- recall COVID-19;
- recall Neumonía;
- matriz de confusión;
- tipo de errores;
- coste de entrenamiento;
- coste de inferencia;
- facilidad de integración.

---

## 23. Notebook experimental

Además del README, se propone un notebook para mostrar visualmente el trabajo experimental:

```text
services/ml-inference/notebooks/radiography_experiments.ipynb
```

Contenido recomendado:

1. Carga de `metadata.json`.
2. Distribución de clases.
3. Visualización de ejemplos por clase.
4. Comprobación de que no hay rutas `masks/`.
5. Carga de `metrics.json`.
6. Visualización de `confusion_matrix.png`.
7. Comparación CNN simple vs ResNet18 vs EfficientNet-B0.
8. Tabla de métricas.
9. Reflexión clínica sobre errores.
10. Elección final del modelo.

Este notebook es útil porque demuestra que se ha “jugado con el código” y no solo ejecutado scripts cerrados.

---

## 24. Servicio de inferencia

El servicio FastAPI está en:

```text
services/ml-inference/app/
```

Archivos principales:

| Archivo | Responsabilidad |
|---|---|
| `app.py` | Define endpoints FastAPI. |
| `predictor.py` | Carga el modelo y ejecuta inferencia. |
| `config.py` | Variables de entorno, clases y configuración de imagen. |
| `schemas.py` | Esquema Pydantic de respuesta. |

---

## 25. Variables de entorno

| Variable | Valor por defecto | Descripción |
|---|---|---|
| `ML_MODEL_PATH` | `/app/models/rx-default/model.pt` | Ruta al modelo `.pt`. |
| `ML_DEVICE` | `cpu` | Dispositivo de inferencia: `cpu` o `cuda`. |
| `COVID_ALERT_THRESHOLD` | `0.80` | Umbral para activar alerta COVID. |
| `LOG_LEVEL` | `INFO` | Nivel de logging. |

Ejemplo recomendado en `.env`:

```dotenv
ML_MODEL_PATH=/app/models/radiography/current/model.pt
ML_DEVICE=cpu
COVID_ALERT_THRESHOLD=0.80
```

En Windows puede ser más robusto apuntar al artefacto concreto:

```dotenv
ML_MODEL_PATH=/app/models/radiography/rx-YYYYMMDD-hash8/model.pt
```

Comando usado durante las pruebas:

```powershell
$version = Get-Content .\models\radiography\current.txt
$line = "ML_MODEL_PATH=/app/models/radiography/$version/model.pt"

if (Select-String -Path .env -Pattern "^ML_MODEL_PATH=" -Quiet) {
  (Get-Content .env) -replace "^ML_MODEL_PATH=.*", $line | Set-Content .env
} else {
  Add-Content .env $line
}
```

---

## 26. Endpoint `/healthz`

Comprueba si el modelo está cargado.

Desde dentro del contenedor:

```powershell
docker compose exec ml-inference curl -s http://localhost:8001/healthz
```

Respuesta correcta:

```json
{
  "status": "ok",
  "model_ready": true
}
```

Si el modelo no existe o no se puede cargar:

```json
{
  "detail": "Model not loaded"
}
```

con HTTP 503.

---

## 27. Endpoint `/predict`

Recibe una imagen JPEG o PNG mediante `multipart/form-data`.

Ejemplo con COVID:

```powershell
docker compose exec ml-inference sh -lc "curl -s -X POST http://localhost:8001/predict -F 'file=@/app/COVID-19_Radiography_Dataset/COVID/images/COVID-1.png'"
```

Ejemplo real obtenido durante las pruebas:

```json
{
  "predicted_class": "COVID-19",
  "probabilities": {
    "Sana": 0.009261030703783035,
    "Neumonía": 0.05368303880095482,
    "COVID-19": 0.9370559453964233
  },
  "model_version": "rx-20260515-0d04651b",
  "inference_time_ms": 110,
  "low_confidence": false,
  "triggers_covid_alert": true
}
```

---

## 28. Pruebas manuales con imágenes reales

COVID:

```powershell
docker compose exec ml-inference sh -lc "curl -s -X POST http://localhost:8001/predict -F 'file=@/app/COVID-19_Radiography_Dataset/COVID/images/COVID-1.png'"
```

Sana:

```powershell
docker compose exec ml-inference sh -lc "curl -s -X POST http://localhost:8001/predict -F 'file=@/app/COVID-19_Radiography_Dataset/Normal/images/Normal-1.png'"
```

Neumonía viral:

```powershell
docker compose exec ml-inference sh -lc "curl -s -X POST http://localhost:8001/predict -F 'file=@/app/COVID-19_Radiography_Dataset/Viral Pneumonia/images/Viral Pneumonia-1.png'"
```

Lung opacity, mapeado a Neumonía:

```powershell
docker compose exec ml-inference sh -lc "curl -s -X POST http://localhost:8001/predict -F 'file=@/app/COVID-19_Radiography_Dataset/Lung_Opacity/images/Lung_Opacity-1.png'"
```

---

## 29. Integración con Docker Compose

El módulo `ml-inference` se integra como servicio independiente.

Rol dentro del sistema:

```text
Radiografía
   ↓
MinIO / MongoDB GridFS
   ↓
ml-inference /predict
   ↓
MongoDB predictions
   ↓
API / Dashboard
```

Separación de responsabilidades:

| Servicio | Responsabilidad |
|---|---|
| `ml-inference` | Inferencia DL sobre radiografías. |
| `api` | Exposición REST y orquestación. |
| `mongodb` | Persistencia flexible de predicciones e imágenes. |
| `minio` | Almacenamiento raw de ficheros. |
| `dashboard` | Visualización clínica y operativa. |

---

## 30. Integración con dashboard

El dashboard incluye una pestaña:

```text
Radiografías
```

Funcionalidad:

- subir imagen PNG/JPG;
- enviar imagen a `ml-inference`;
- mostrar clase predicha;
- mostrar probabilidades;
- mostrar alerta COVID si corresponde;
- mostrar aviso de baja confianza;
- mostrar JSON completo del modelo.

Dentro de Docker, el dashboard llama a:

```text
http://ml-inference:8001/predict
```

No debe llamar a `localhost`, porque dentro del contenedor `dashboard`, `localhost` sería el propio contenedor del dashboard.

Variable:

```dotenv
ML_INFERENCE_URL=http://ml-inference:8001
```

---

## 31. Limitaciones

Este módulo es académico y no está validado clínicamente.

Limitaciones principales:

- dataset público con sesgos de origen;
- posible diferencia entre imágenes del dataset y práctica hospitalaria real;
- no hay validación externa multicéntrica;
- no hay revisión radiológica experta de cada predicción;
- posible fuga de patrones no clínicos si no se controla bien el dataset;
- la clase `Neumonía` agrupa `Viral Pneumonia` y `Lung_Opacity`;
- no sustituye criterio médico;
- no constituye un dispositivo médico certificado;
- el rendimiento depende de la calidad y representatividad de las imágenes;
- entrenamiento en CPU limita número de experimentos y épocas.

---

## 32. Artefactos versionables

Se recomienda versionar:

```text
models/radiography/<VERSION>/metadata.json
models/radiography/<VERSION>/metrics.json
models/radiography/<VERSION>/confusion_matrix.png
models/radiography/<VERSION>/critical_analysis.md
models/radiography/current.txt
models/radiography/comparison/comparison.csv
models/radiography/comparison/comparison.md
models/radiography/comparison/comparison.json
```

No se recomienda versionar:

```text
models/radiography/<VERSION>/model.pt
COVID-19_Radiography_Dataset/
data/covid-subset/
```

Motivo:

- el dataset es pesado;
- los pesos del modelo son pesados;
- ambos son regenerables localmente mediante scripts;
- GitHub rechaza ficheros de más de 100 MB.

---

## 33. Estado actual de pruebas

Durante el desarrollo se ha verificado:

- build completo de `ml-inference` con `torch`, `torchvision`, `pandas`, `sklearn` y `matplotlib`;
- importación correcta de dependencias dentro del contenedor;
- acceso al dataset desde `/app/COVID-19_Radiography_Dataset`;
- generación de subset pequeño con `--limit-per-class 30`;
- entrenamiento smoke test con EfficientNet-B0;
- generación de artefactos `rx-*`;
- evaluación con `metrics.json`;
- generación de `confusion_matrix.png`;
- generación de `critical_analysis.md`;
- carga del modelo desde `.env`;
- `/healthz` correcto;
- `/predict` correcto con una imagen COVID real;
- corrección de `prepare_data.py` para excluir `masks/`;
- regeneración de dataset limpio con 1000 imágenes por clase final;
- inicio de comparación experimental con `simple_cnn`, `resnet18` y `efficientnet_b0`.

---

## 34. Comandos resumen

Preparar dataset limpio:

```powershell
docker compose run --rm ml-inference python -m training.prepare_data `
  --raw-dir /app/COVID-19_Radiography_Dataset `
  --output-dir /app/data/covid-subset `
  --limit-per-class 1000 `
  --seed 42
```

Comprobar que no hay masks:

```powershell
Select-String -Path .\data\covid-subset\*.csv -Pattern "masks"
```

Entrenar CNN simple:

```powershell
docker compose run --rm ml-inference python -m training.train `
  --backbone simple_cnn `
  --train-csv /app/data/covid-subset/train.csv `
  --val-csv /app/data/covid-subset/val.csv `
  --models-root /app/models/radiography `
  --batch-size 32 `
  --warmup-epochs 0 `
  --max-epochs 8 `
  --num-workers 0 `
  --seed 42
```

Entrenar ResNet18:

```powershell
docker compose run --rm ml-inference python -m training.train `
  --backbone resnet18 `
  --train-csv /app/data/covid-subset/train.csv `
  --val-csv /app/data/covid-subset/val.csv `
  --models-root /app/models/radiography `
  --batch-size 16 `
  --warmup-epochs 2 `
  --max-epochs 8 `
  --num-workers 0 `
  --seed 42
```

Entrenar EfficientNet-B0:

```powershell
docker compose run --rm ml-inference python -m training.train `
  --backbone efficientnet_b0 `
  --train-csv /app/data/covid-subset/train.csv `
  --val-csv /app/data/covid-subset/val.csv `
  --models-root /app/models/radiography `
  --batch-size 16 `
  --warmup-epochs 2 `
  --max-epochs 8 `
  --num-workers 0 `
  --seed 42
```

Evaluar todos los modelos:

```powershell
Get-ChildItem .\models\radiography -Directory | Where-Object { $_.Name -like "rx-*" } | ForEach-Object {
  $v = $_.Name

  docker compose run --rm ml-inference python -m training.evaluate `
    --artifact-dir "/app/models/radiography/$v" `
    --test-csv /app/data/covid-subset/test.csv `
    --batch-size 16 `
    --num-workers 0

  docker compose run --rm ml-inference python -m training.critical_analysis `
    --artifact-dir "/app/models/radiography/$v"
}
```

Generar comparación:

```powershell
docker compose run --rm ml-inference python -m training.compare_models `
  --models-root /app/models/radiography `
  --output /app/models/radiography/comparison
```

Activar mejor modelo:

```powershell
$best = "rx-YYYYMMDD-hash8"
$line = "ML_MODEL_PATH=/app/models/radiography/$best/model.pt"

if (Select-String -Path .env -Pattern "^ML_MODEL_PATH=" -Quiet) {
  (Get-Content .env) -replace "^ML_MODEL_PATH=.*", $line | Set-Content .env
} else {
  Add-Content .env $line
}
```

Recrear servicio:

```powershell
docker compose --env-file .env up -d --force-recreate ml-inference
```

Comprobar salud:

```powershell
docker compose exec ml-inference curl -s http://localhost:8001/healthz
```

Probar predicción:

```powershell
docker compose exec ml-inference sh -lc "curl -s -X POST http://localhost:8001/predict -F 'file=@/app/COVID-19_Radiography_Dataset/COVID/images/COVID-1.png'"
```

Recrear dashboard:

```powershell
docker compose --env-file .env up -d --force-recreate dashboard
```

Abrir:

```text
http://localhost:8502
```

---

## 35. Conclusión técnica

El módulo `ml-inference` implementa un flujo completo de Deep Learning aplicado a radiografías:

1. preparación de dataset;
2. limpieza de rutas para excluir máscaras;
3. partición estratificada;
4. entrenamiento con varias arquitecturas;
5. evaluación con métricas clínicas;
6. matriz de confusión;
7. análisis crítico;
8. comparación experimental;
9. despliegue en Docker;
10. consumo desde dashboard.

La decisión final del modelo se toma con criterio clínico, no únicamente por accuracy. En particular, se prioriza evitar falsos negativos de COVID-19 y neumonía, porque estos errores tienen más impacto hospitalario que un falso positivo.

El sistema se debe interpretar como apoyo a la decisión y demostración académica de infraestructura Big Data + IA, no como herramienta diagnóstica certificada.

Para clasificación de radiografías no se han usado KNN, árboles, random forest o regresión logística como modelos principales porque trabajan mejor con features tabulares o representaciones ya extraídas. En imágenes médicas crudas, una CNN o modelos preentrenados convolucionales son más adecuados porque aprenden patrones espaciales directamente. Por eso se comparan una CNN simple como baseline, ResNet18 como transfer learning clásico y EfficientNet-B0 como arquitectura eficiente.

(.venv) PS C:\Users\aripa\Downloads\Practica_Hospital_AriadnaPascualPolBallarin> docker compose run --rm ml-inference python -m training.compare_models `
>>   --models-root /app/models/radiography `
>>   --output /app/models/radiography/comparison
[+] Creating 1/1
 ✔ Container practica_hospital_ariadnapascualpolballarin-mongodb-1  Running                                   0.0s 
                               version  ...                                       artifact_dir
0  rx-efficientnetb0-20260515-2b92eec9  ...  /app/models/radiography/rx-efficientnetb0-2026...
1        rx-resnet18-20260515-d397f8e5  ...  /app/models/radiography/rx-resnet18-20260515-d...
2       rx-simplecnn-20260515-e8ac76f0  ...  /app/models/radiography/rx-simplecnn-20260515-...

[3 rows x 9 columns]
Saved /app/models/radiography/comparison/comparison.csv
Saved /app/models/radiography/comparison/comparison.md
Saved /app/models/radiography/comparison/comparison.json
(.venv) PS C:\Users\aripa\Downloads\Practica_Hospital_AriadnaPascualPolBallarin> Get-Content .\models\radiography\comparison\comparison.md -Encoding UTF8
# Comparación de modelos — radiografías

| Ranking | Versión | Backbone | Accuracy | F1 macro | Recall COVID | Recall Neumonía |
|---:|---|---|---:|---:|---:|---:|
| 1 | `rx-efficientnetb0-20260515-2b92eec9` | `efficientnet_b0` | 0.9600 | 0.9601 | 0.9800 | 0.9333 |
| 2 | `rx-resnet18-20260515-d397f8e5` | `resnet18` | 0.8933 | 0.8929 | 0.9667 | 0.8333 |
| 3 | `rx-simplecnn-20260515-e8ac76f0` | `simple_cnn` | 0.7022 | 0.7013 | 0.7000 | 0.7733 |

## Criterio de selección

El modelo no se selecciona solo por accuracy. En contexto hospitalario se priorizan F1 macro y recall de COVID-19/Neumonía para reducir falsos negativos clínicamente relevantes.
(.venv) PS C:\Users\aripa\Downloads\Practica_Hospital_AriadnaPascualPolBallarin> Import-Csv .\models\radiography\comparison\comparison.csv | Format-Table -AutoSize

version                             backbone        accuracy           f1_macro           recall_covid       recal
                                                                                                             l_neu
                                                                                                             monia
-------                             --------        --------           --------           ------------       -----
rx-efficientnetb0-20260515-2b92eec9 efficientnet_b0 0.96               0.960078515151551  0.98               0....
rx-resnet18-20260515-d397f8e5       resnet18        0.8933333333333333 0.8929190334071434 0.9666666666666667 0....
rx-simplecnn-20260515-e8ac76f0      simple_cnn      0.7022222222222222 0.7012595535305359 0.7                0....


(.venv) PS C:\Users\aripa\Downloads\Practica_Hospital_AriadnaPascualPolBallarin> 

## Comparación experimental de modelos

Se compararon tres arquitecturas sobre el mismo dataset limpio y balanceado:

- `simple_cnn`: baseline convolucional entrenado desde cero.
- `resnet18`: transfer learning clásico con backbone preentrenado en ImageNet.
- `efficientnet_b0`: transfer learning eficiente con mejor relación coste/rendimiento.

Resultados en test:

| Modelo | Accuracy | F1 macro | Recall COVID-19 | Recall Neumonía |
|---|---:|---:|---:|---:|
| EfficientNet-B0 | 0.9600 | 0.9601 | 0.9800 | 0.9333 |
| ResNet18 | 0.8933 | 0.8929 | 0.9667 | 0.8333 |
| CNN simple | 0.7022 | 0.7013 | 0.7000 | 0.7733 |

El modelo seleccionado para despliegue es `EfficientNet-B0`, versión `rx-efficientnetb0-20260515-2b92eec9`.

La elección no se basa únicamente en accuracy, sino en criterio clínico. EfficientNet-B0 obtiene el mejor equilibrio entre F1 macro, sensibilidad a COVID-19 y sensibilidad a neumonía. En un contexto hospitalario, reducir falsos negativos de COVID-19 es prioritario por el riesgo de contagio intrahospitalario; reducir falsos negativos de neumonía también es relevante para evitar retrasos terapéuticos.