# SDD-06 — Modelo de Deep Learning: clasificación de radiografías de tórax

> Spec del subsistema de **clasificación mediante Deep Learning** de radiografías de tórax en tres clases: *Sana*, *Neumonía*, *COVID-19*. Define **qué debe aprender, cómo se evalúa y cómo se sirve**. La arquitectura concreta, hiperparámetros exactos y código de entrenamiento van en `DESIGN-06-modelo-dl.md`.

---

**Versión:** 1.0
**Fecha:** 2026-04-20
**Autor:** Pol Ballarín
**Estado:** `ready-for-design`

---

## 1. Contexto y objetivo

### Contexto
El enunciado §6 exige un modelo de clasificación triple sobre radiografías de tórax como **apoyo a la decisión clínica**. El enunciado es explícito (§6.3): *"en un entorno sanitario es más importante entender cómo se comporta el modelo que su éxito estadístico. La nota NO depende de conseguir accuracy perfecta."* Lo que se valora es la **evaluación crítica**, la **matriz de confusión**, el **impacto clínico de los errores** y la **justificación técnica** de las decisiones.

El dataset de referencia es *COVID-19 Radiography Database* (Kaggle), con 4 clases originales — se utilizan las 3 requeridas por el enunciado. El modelo se entrena fuera de línea y se sirve como **servicio containerizado** (`ml-inference` en SDD-01) con endpoint de predicción consumido por API y por automation.

### Objetivo
Proveer un clasificador triple de radiografías de tórax que:

1. Se entrene de forma **reproducible** sobre un subset balanceado del dataset, con splits train/val/test documentados.
2. Exponga **métricas de evaluación completas** más allá de la accuracy: matriz de confusión, precisión/recall/F1 por clase, curvas ROC/AUC si procede.
3. Produzca **análisis clínico explícito** del tipo y gravedad de los errores: ¿cuántos falsos negativos de COVID-19 hay? ¿Se confunde COVID-19 con Neumonía con más frecuencia que con Sana?
4. Se sirva como **servicio HTTP** interno (endpoint `/predict`) que acepta una imagen y devuelve clase predicha + probabilidades por clase.
5. Sea **versionable**: cada modelo entrenado queda identificado (versión, timestamp, métricas, splits usados) y la predicción persistida referencia la versión que la produjo (SDD-03 RF-5, RF-13 y caso borde de predicción repetida).
6. Opere en **CPU** de portátil de desarrollo (sin asumir GPU), aunque el entrenamiento pueda usar GPU si está disponible.

## 2. Actores y alcance

### Actores

| Actor | Dirección | Rol |
|-------|-----------|-----|
| **Dataset público** *(COVID-19 Radiography Database)* | lectura | Fuente de imágenes de entrenamiento |
| **Pipeline de datos** *(SDD-02)* | — | Ingiere radiografías al almacén; el modelo es independiente de la ingesta |
| **Servicio de automatización** *(SDD-04)* | cliente | Dispara la predicción cuando llega una radiografía nueva |
| **API** *(SDD-05)* | cliente | Expone el endpoint de predicción al dashboard (o al usuario que sube una radiografía puntual) |
| **Almacenamiento** *(SDD-03)* | destino | Persiste las predicciones como documentos asociados a la radiografía |
| **Pol (entrenador)** | operador humano | Ejecuta el script de entrenamiento, revisa métricas, decide versión a desplegar |

### Dentro del alcance

- **Preparación de datos**: descarga del dataset (manual o scripted), filtrado a las 3 clases relevantes, splits estratificados train/val/test, preprocesado estándar (redimensionamiento, normalización), data augmentation para la clase minoritaria si fuera necesaria.
- **Arquitectura del modelo**: **transfer learning** sobre un backbone pre-entrenado (candidatos: ResNet50, EfficientNet-B0) con cabeza de clasificación de 3 salidas. Justificación técnica obligatoria (§6.2 enunciado).
- **Entrenamiento**: bucle reproducible con semillas fijadas, early stopping, persistencia del mejor checkpoint.
- **Evaluación**: cálculo de matriz de confusión, métricas por clase y análisis clínico de errores.
- **Versionado del modelo**: cada run de entrenamiento produce una versión identificable; la predicción en producción referencia la versión usada.
- **Servicio de inferencia**: endpoint HTTP que acepta una imagen y devuelve predicción estructurada (clase + probabilidades + versión del modelo).
- **Limitaciones y reflexión crítica**: documento que recoge qué hace bien el modelo, qué hace mal y qué implicaciones clínicas tiene — entregable de §6.3 del enunciado.

### Fuera del alcance

- **Entrenamiento distribuido** multi-GPU / multi-nodo.
- **Búsqueda de hiperparámetros** exhaustiva (grid search, Optuna): se acepta tuning manual documentado.
- **Segmentación** o localización de lesiones: clasificación global de la imagen, no por regiones.
- **Otras modalidades** (TAC, resonancia): solo radiografía de tórax 2D (consistente con SDD-01).
- **Continuous learning / online learning**: el modelo se entrena fuera de línea y se despliega como artefacto inmutable.
- **Explainability avanzada** (Grad-CAM, SHAP): **opcional**, si hay tiempo puede añadirse como mejora; no es requisito.
- **Federated learning** u otros enfoques de privacidad distribuida.
- **Calibración avanzada** de probabilidades (Platt scaling, isotonic regression): se acepta la salida softmax directa.

## 3. Requisitos funcionales

### Preparación de datos

- **RF-1**: El sistema debe preparar los datos de entrenamiento a partir del dataset público, filtrando las 3 clases relevantes (*Sana*, *Neumonía*, *COVID-19*) y descartando las no utilizadas (p. ej. *Lung Opacity* si aplica).
- **RF-2**: El sistema debe producir splits **estratificados** train/val/test (proporción típica 70/15/15 o equivalente) con distribución proporcional de clases en cada split.
- **RF-3**: Las imágenes se preprocesan con: **redimensionamiento** a la entrada esperada por el backbone, **normalización** con las estadísticas del backbone (media y desviación típica por canal) y **conversión a RGB** si vinieran en escala de grises.
- **RF-4**: Si el dataset presenta **desbalance relevante** entre clases, el sistema debe aplicar al menos una estrategia de compensación (oversampling, data augmentation dirigido a la clase minoritaria, o pesos de clase en la función de pérdida). La estrategia elegida se documenta.

### Arquitectura y entrenamiento

- **RF-5**: El modelo usa **transfer learning** con un backbone **pre-entrenado** en ImageNet (candidato principal: ResNet50 o EfficientNet-B0, a decidir en `DESIGN-06`). La cabeza final es una capa lineal con 3 salidas.
- **RF-6**: El entrenamiento es **reproducible**: semillas fijadas para numpy, torch, CUDA (si aplica); hiperparámetros registrados como artefacto del run.
- **RF-7**: El entrenamiento implementa **early stopping** sobre la métrica de validación (loss o F1 macro) para evitar overfitting, y persiste el **mejor checkpoint** encontrado.
- **RF-8**: Al terminar el entrenamiento, el sistema persiste el artefacto del modelo (pesos + metadatos) en el volumen `models-data` (ver SDD-01), identificado por una **versión** única (timestamp + short hash de hiperparámetros).

### Evaluación

- **RF-9**: El sistema debe calcular, sobre el split de **test**, como mínimo:
  - **Matriz de confusión 3×3**.
  - **Accuracy global**.
  - **Precisión, recall y F1 por clase**.
  - **F1 macro** (media no ponderada).
- **RF-10**: El sistema debe persistir estas métricas junto al artefacto del modelo (JSON con métricas + PNG de la matriz de confusión).
- **RF-11**: El sistema debe producir un **informe de reflexión clínica** con al menos:
  - Qué tipo de error es más frecuente (p. ej. *COVID-19 → Neumonía* o *Sana → COVID-19*).
  - Discusión del impacto clínico de cada tipo de error (falso negativo de enfermedad contagiosa vs falso positivo).
  - Limitaciones detectadas (clase minoritaria, confusión anatómica, dataset no representativo).

### Servicio de inferencia

- **RF-12**: El servicio `ml-inference` expone un endpoint HTTP (`POST /predict`) que acepta una imagen (multipart/form-data o referencia a GridFS) y devuelve un objeto con: `predicted_class` ∈ {Sana, Neumonía, COVID-19}, `probabilities` {sana, neumonía, covid19}, `model_version`, `inference_time_ms`.
- **RF-13**: El servicio debe cargar el modelo **una vez al arrancar** (no por petición) y mantenerlo en memoria.
- **RF-14**: Cada predicción devuelve la **versión del modelo** que la produjo, para trazabilidad (SDD-03 RF-5 y caso borde "predicción repetida").
- **RF-15**: El servicio debe exponer un endpoint `/healthz` que devuelva 200 OK solo cuando el modelo está cargado y listo para inferir.

### Versionado y trazabilidad

- **RF-16**: Cada artefacto de modelo lleva metadatos inmutables: versión, timestamp de entrenamiento, hiperparámetros, hash del dataset usado, splits usados, métricas de test.
- **RF-17**: El servicio de inferencia declara en su respuesta la `model_version` activa; cambiar de versión requiere reiniciar el servicio con el nuevo artefacto.

## 4. Requisitos no funcionales

### Rendimiento

- **RNF-1**: La predicción de una única imagen end-to-end (cargada en memoria → salida softmax → respuesta HTTP) debe completarse en un tiempo razonable en CPU de portátil. **[NEEDS CLARIFICATION]** umbral concreto — ligado a SDD-01 RNF-1. Se fija tras la primera medición.
- **RNF-2**: El modelo debe poder servirse en **CPU sin GPU**. El entrenamiento puede usar GPU si está disponible, pero el despliegue es CPU-first.

### Reproducibilidad

- **RNF-3**: Consistente con SDD-01 RNF-13: semillas fijadas, versión del dataset documentada (hash o revisión), hiperparámetros registrados.
- **RNF-4**: El proceso de entrenamiento completo debe poder relanzarse con un único comando (`make train` o script equivalente) y producir un artefacto comparable.

### Robustez

- **RNF-5**: El servicio de inferencia debe tolerar entradas inválidas (formato incorrecto, dimensiones raras) devolviendo **error HTTP claro** (4xx), no un 500 genérico.
- **RNF-6**: Un fallo al cargar el modelo al arrancar debe dejar el servicio en estado **no saludable** (`/healthz` devuelve 503), no silencioso.

### Integración

- **RNF-7**: El servicio de inferencia debe poder invocarse tanto por la API (SDD-05) como por el servicio de automation (SDD-04) sin código específico para cada cliente — protocolo HTTP estándar.

### Ética y limitaciones (§7 enunciado)

- **RNF-8**: Ninguna predicción se presenta como diagnóstico automatizado (consistente con SDD-01 RF-10 y fuera-de-alcance). Toda salida del modelo se etiqueta como **apoyo a la decisión**.
- **RNF-9**: El sistema debe documentar las **limitaciones conocidas** del modelo en un apartado específico de la memoria técnica: sesgo por composición del dataset, no validación clínica, no certificación médica.

## 5. Casos borde / errores

### Datos

| Caso | Comportamiento esperado | RF afectado |
|------|------------------------|-------------|
| Dataset no descargado en el entorno de entrenamiento | El script aborta con mensaje claro y enlace de descarga documentado. No continúa en seco. | RF-1 |
| Desbalance severo entre clases (una clase con <10% del total) | Aplicar estrategia de compensación documentada; registrar aviso en el log de entrenamiento. | RF-4 |
| Imágenes en blanco y negro puro dentro del split | Pasan por RGB conversion (RF-3) y se procesan normalmente. | RF-3 |

### Entrenamiento

| Caso | Comportamiento esperado | RF afectado |
|------|------------------------|-------------|
| Pérdida diverge (explodes, NaN) | Abortar el run con mensaje explícito; persistir el último checkpoint estable si lo hay. | RF-7 |
| Validación no mejora durante N épocas consecutivas | Early stopping se dispara; se conserva el mejor checkpoint. | RF-7 |
| Espacio en disco insuficiente al persistir artefacto | Fallar el run con mensaje claro, sin corromper artefactos anteriores. | RF-8 |

### Inferencia

| Caso | Comportamiento esperado | RF afectado |
|------|------------------------|-------------|
| Petición con fichero que no es una imagen | 400 Bad Request con detalle. No se invoca el modelo. | RNF-5 |
| Petición con imagen de dimensiones muy pequeñas (< 64×64) | 422 Unprocessable Entity con motivo "dimensiones insuficientes". Consistente con caso borde SDD-01. | RF-12, RNF-5 |
| Modelo no cargado al arrancar | `/healthz` devuelve 503; las peticiones a `/predict` devuelven 503 hasta que cargue. | RNF-6 |
| Predicción devuelve NaN o probabilidades no válidas | Devolver 500 con `model_version` en el cuerpo; registrar alerta crítica. Consistente con caso borde SDD-01 "probabilidades inválidas". | RF-12 |
| Dos clases empatadas en probabilidad | Aplicar regla de desempate documentada (propuesta: *Sana < Neumonía < COVID-19*). **[NEEDS CLARIFICATION]** heredado de SDD-01 §7. | RF-12 |

### Versionado

| Caso | Comportamiento esperado | RF afectado |
|------|------------------------|-------------|
| Se entrena un nuevo modelo con mejor F1 y se despliega | La nueva `model_version` aparece en las nuevas predicciones; las antiguas conservan su versión original (consistente con SDD-03 versionado de predicciones). | RF-16, RF-17 |
| Dos instancias del servicio cargan versiones distintas | Situación anómala; la API/automation debe tolerarlo y registrarlo como aviso. En demo mono-instancia no aplica. | RF-17 |

## 6. Criterios de aceptación

### Preparación de datos

- [ ] **CA-1** (cubre RF-1, RF-2): el script de preparación descarga/localiza el dataset y produce tres conjuntos `train.csv`, `val.csv`, `test.csv` (o equivalente) con distribución de clases documentada y estratificación verificable.
- [ ] **CA-2** (cubre RF-3): una imagen de muestra pasa por el pipeline de preprocesado y resulta en un tensor de dimensiones esperadas por el backbone, con valores normalizados (media ≈ 0, std ≈ 1 para ImageNet).

### Entrenamiento

- [ ] **CA-3** (cubre RF-5, RF-6): ejecutar el script de entrenamiento con la misma semilla y mismo dataset en dos máquinas comparables produce métricas de validación **dentro de un margen tolerable** (diferencias < 2 puntos porcentuales en F1 macro).
- [ ] **CA-4** (cubre RF-7, RF-8): el script de entrenamiento produce un artefacto en `models-data` identificado por versión única, con checkpoint de mejor validación.

### Evaluación

- [ ] **CA-5** (cubre RF-9, RF-10): al terminar el entrenamiento existe un JSON con matriz de confusión 3×3, accuracy, precision/recall/F1 por clase y F1 macro, más un PNG de la matriz de confusión, persistidos junto al artefacto.
- [ ] **CA-6** (cubre RF-11): existe un documento (Markdown o sección de la memoria) que discute: tipo de error más frecuente, impacto clínico de cada error, limitaciones conocidas.

### Servicio

- [ ] **CA-7** (cubre RF-12, RF-13, RF-14): `curl -F "file=@test.jpg" http://ml-inference:8000/predict` devuelve un JSON con `predicted_class`, `probabilities` (tres valores ∈ [0,1] que suman 1.0 ±1e-6), `model_version`, `inference_time_ms`.
- [ ] **CA-8** (cubre RF-15, RNF-6): al arrancar sin modelo en el volumen, `/healthz` devuelve 503; al presentar el artefacto y reiniciar, `/healthz` devuelve 200.
- [ ] **CA-9** (cubre RF-13): el tiempo de respuesta medio de `/predict` con el modelo ya cargado no incluye carga del modelo (verificable comparando primera petición vs siguientes).

### Robustez

- [ ] **CA-10** (cubre RNF-5, casos borde): enviar un `.txt` a `/predict` devuelve 400 con mensaje explícito; enviar una imagen 10×10 devuelve 422.
- [ ] **CA-11** (cubre caso borde "servicio no disponible"): parar `ml-inference` y reintentar desde automation deja la radiografía en `pending_prediction` (consistente con SDD-01 caso borde), y al rearrancar queda predicha.

### Versionado

- [ ] **CA-12** (cubre RF-14, RF-16): dos predicciones sucesivas bajo la misma `model_version` producen el mismo resultado (modulo no-determinismo de dropout en inferencia si aplicara — se fija `eval()` mode). Si se despliega una versión nueva, las nuevas predicciones llevan la nueva versión; las persistidas anteriormente conservan la suya.

## 7. Dudas abiertas

- **[NEEDS CLARIFICATION]** **Arquitectura concreta del backbone**: ResNet50 vs EfficientNet-B0 vs otra. Decisión en `DESIGN-06` tras pequeño banco de pruebas (una época por candidato).
- **[NEEDS CLARIFICATION]** Proporción exacta de los splits train/val/test (RF-2). Propuesta inicial 70/15/15; puede ajustarse según volumen de la clase minoritaria.
- **[NEEDS CLARIFICATION]** Estrategia concreta de compensación de desbalance (RF-4): oversampling, augmentation dirigido, pesos de clase. Decisión tras inspección del subset.
- **[NEEDS CLARIFICATION]** Umbral de `P(COVID-19)` que dispara alerta en RF-20 de SDD-01 (ya registrado en SDD-01 §7). Se fija aquí, tras conocer la distribución real de probabilidades.
- **[NEEDS CLARIFICATION]** Regla de desempate de probabilidades (caso borde). Propuesta por defecto en SDD-01 §7: *Sana < Neumonía < COVID-19*. A ratificar aquí.
- **[NEEDS CLARIFICATION]** Umbrales concretos de tiempo de inferencia (RNF-1) — ligado a SDD-01.

## 8. Referencias

- Enunciado: `Enunciado-Hospital.pdf` §6 (clasificación de radiografías), §6.3 (evaluación y criterio clínico), §7 (consideraciones éticas)
- `CONTEXT.md` §6
- Spec raíz: `specs/SDD-01-sistema.md`
- Spec de almacenamiento: `specs/SDD-03-almacenamiento.md`
- Diseño asociado: `specs/DESIGN-06-modelo-dl.md` *(a crear)*
- Dataset: *COVID-19 Radiography Database* (Kaggle, a citar en memoria técnica)
- SDDs relacionados: SDD-02 (fuente de radiografías ingeridas), SDD-04 (disparador), SDD-05 (cliente API), SDD-07 (logging)

Durante la implementación se añadieron tres arquitecturas comparables para el módulo de radiografías:

- `simple_cnn`: CNN simple desde cero como baseline.
- `resnet18`: transfer learning con arquitectura residual.
- `efficientnet_b0`: transfer learning con arquitectura eficiente.

Todas se entrenaron sobre el mismo dataset limpio y balanceado, usando únicamente imágenes de carpetas `images/` y excluyendo `masks/`.

### Resultados de test

| Modelo | Accuracy | F1 macro | Recall COVID-19 | Recall Neumonía |
|---|---:|---:|---:|---:|
| EfficientNet-B0 | 0.9600 | 0.9601 | 0.9800 | 0.9333 |
| ResNet18 | 0.8933 | 0.8929 | 0.9667 | 0.8333 |
| CNN simple | 0.7022 | 0.7013 | 0.7000 | 0.7733 |

### Modelo seleccionado

Se selecciona `EfficientNet-B0`, versión:

`rx-efficientnetb0-20260515-2b92eec9`

### Justificación

El modelo se selecciona por equilibrio clínico, no solo por accuracy. En particular:

- maximiza `F1 macro`;
- maximiza `recall_covid`;
- maximiza `recall_neumonia`;
- reduce falsos negativos relevantes en contexto hospitalario;
- mantiene un coste razonable de inferencia en CPU.

### Criterios de aceptación validados

- El dataset final no contiene rutas con `masks/`.
- El entrenamiento genera artefacto versionado.
- La evaluación genera `metrics.json`.
- La evaluación genera `confusion_matrix.png`.
- El análisis clínico genera `critical_analysis.md`.
- La comparación genera `comparison.csv`, `comparison.md` y `comparison.json`.
- El servicio `/healthz` devuelve `model_ready=true`.
- El endpoint `/predict` procesa imágenes reales del dataset.
- El dashboard permite subir radiografías y consumir `ml-inference`.


## Decisión técnica final de arquitectura

Se evaluaron tres enfoques:

### 1. CNN simple

Modelo convolucional pequeño entrenado desde cero. Se usa como baseline para demostrar el valor del transfer learning.

Ventajas:

- rápido de implementar;
- bajo coste computacional;
- fácil de explicar.

Limitaciones:

- aprende menos representaciones visuales complejas;
- requiere más datos para generalizar bien;
- peor sensibilidad clínica en COVID-19.

Resultado:

- accuracy: 0.7022;
- F1 macro: 0.7013;
- recall COVID-19: 0.7000;
- recall Neumonía: 0.7733.

### 2. ResNet18

Modelo residual preentrenado en ImageNet. Se usa como arquitectura clásica de transfer learning.

Ventajas:

- buena capacidad de representación;
- arquitectura conocida y estable;
- mejora clara frente a CNN simple.

Limitaciones:

- peor recall de neumonía que EfficientNet-B0;
- más coste que CNN simple;
- menor rendimiento global que EfficientNet-B0 en este dataset.

Resultado:

- accuracy: 0.8933;
- F1 macro: 0.8929;
- recall COVID-19: 0.9667;
- recall Neumonía: 0.8333.

### 3. EfficientNet-B0

Modelo preentrenado eficiente. Escala profundidad, anchura y resolución de forma equilibrada.

Ventajas:

- mejor rendimiento global;
- mejor F1 macro;
- mejor recall COVID-19;
- mejor recall Neumonía;
- tamaño razonable para despliegue en CPU.

Resultado:

- accuracy: 0.9600;
- F1 macro: 0.9601;
- recall COVID-19: 0.9800;
- recall Neumonía: 0.9333.

## Modelo final desplegado

Se selecciona:

`rx-efficientnetb0-20260515-2b92eec9`

La ruta de despliegue se configura con:

```env
ML_MODEL_PATH=/app/models/radiography/rx-efficientnetb0-20260515-2b92eec9/model.pt

ustificación clínica

En un entorno hospitalario, el error más peligroso no es cualquier error, sino especialmente el falso negativo en enfermedades contagiosas o respiratorias.

Por eso se prioriza:

recall COVID-19;
recall Neumonía;
F1 macro;
matriz de confusión.

EfficientNet-B0 es el modelo final porque reduce mejor los falsos negativos relevantes manteniendo buen rendimiento global.