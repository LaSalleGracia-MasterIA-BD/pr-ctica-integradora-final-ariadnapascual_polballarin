# 07 — Desarrollo asistido por IA: módulo Deep Learning radiografías

## 1. Objetivo

El objetivo de esta fase fue construir un módulo de Deep Learning para clasificar radiografías de tórax en tres clases:

- Sana.
- Neumonía.
- COVID-19.

El módulo debía incluir:

- preparación del dataset;
- entrenamiento;
- evaluación;
- matriz de confusión;
- análisis crítico clínico;
- despliegue como servicio FastAPI;
- integración con dashboard;
- comparación entre arquitecturas.

## 2. Herramientas de IA utilizadas

Se utilizaron herramientas de IA generativa como apoyo para:

- diseñar la arquitectura del módulo;
- revisar el enunciado y traducirlo a requisitos técnicos;
- generar y corregir scripts de entrenamiento;
- depurar errores de Docker, PyTorch y rutas;
- redactar documentación técnica;
- justificar decisiones clínicas y técnicas;
- preparar comandos reproducibles;
- estructurar el análisis crítico.

Las decisiones finales se validaron mediante ejecución real en Docker Compose.

## 3. Prompt representativo 1 — Entender el requisito

### Prompt

> Esta parte pide clasificación triple de radiografías: Sana, Neumonía y COVID-19. Tengo el dataset COVID-19_Radiography_Dataset con carpetas COVID, Lung_Opacity, Normal y Viral Pneumonia. Quiero que me ayudes a diseñar el módulo ml-inference, justificar modelo, preprocesamiento, evaluación y cómo integrarlo con Docker y dashboard.

### Resultado

La IA propuso:

- agrupar `Normal` como `Sana`;
- agrupar `Viral Pneumonia` y `Lung_Opacity` como `Neumonía`;
- usar `COVID` como `COVID-19`;
- entrenar con transfer learning;
- generar `metrics.json`, `confusion_matrix.png` y `critical_analysis.md`;
- exponer el modelo mediante FastAPI.

### Validación humana

Se aceptó el planteamiento porque encajaba con el enunciado de clasificación triple. Se documentó como limitación que `Lung_Opacity` puede tener causas clínicas distintas y que agruparla en neumonía es una simplificación académica.

## 4. Prompt representativo 2 — Comparar modelos

### Prompt

> Para subir nota podríamos usar CNN simple, ResNet18 y EfficientNet-B0, comparar accuracy, F1 macro, recall COVID y recall neumonía, y explicar cuál es mejor clínicamente. Dame el código y la forma de evaluarlo.

### Resultado

Se amplió el código para permitir varios backbones:

- `simple_cnn`;
- `resnet18`;
- `efficientnet_b0`.

También se añadió:

- argumento `--backbone` en entrenamiento;
- lectura del backbone desde `metadata.json`;
- script `compare_models.py`;
- generación de `comparison.csv`, `comparison.md` y `comparison.json`.

### Validación humana

Se ejecutaron los tres modelos sobre el mismo dataset limpio y balanceado. EfficientNet-B0 fue seleccionado por mejor equilibrio clínico.

## 5. Prompt representativo 3 — Detectar contaminación del dataset

### Prompt

> Veo que en los CSV aparecen rutas con `masks/`. ¿Eso está bien o estoy entrenando con máscaras en vez de radiografías?

### Resultado

La IA identificó que entrenar con máscaras sería un error metodológico grave, porque las máscaras no son radiografías sino segmentaciones binarias. Se corrigió `prepare_data.py` para recoger únicamente archivos dentro de:

```text
COVID-19_Radiography_Dataset/<clase>/images/

y excluir:

COVID-19_Radiography_Dataset/<clase>/masks/
Validación humana

Se comprobó después con:

Select-String -Path .\data\covid-subset\*.csv -Pattern "masks"

La consulta no devolvió resultados, confirmando que el dataset final ya no estaba contaminado.

6. Prompt representativo 4 — Integración con dashboard
Prompt

Quiero añadir una pestaña Radiografías al dashboard Streamlit para subir una imagen y llamar a ml-inference /predict. Dentro de Docker, ¿debo llamar a localhost o al nombre del servicio?

Resultado

La IA indicó que dentro del contenedor dashboard se debe llamar a:

http://ml-inference:8001/predict

y no a localhost, porque localhost dentro de Docker apunta al propio contenedor.

Validación humana

Se añadió ML_INFERENCE_URL=http://ml-inference:8001 y se implementó la pestaña Radiografías con:

st.file_uploader;
llamada HTTP a /predict;
métricas de probabilidad por clase;
alerta visual si triggers_covid_alert=true;
aviso si low_confidence=true.
7. Resultados finales

La comparación final fue:

Ranking	Modelo	Accuracy	F1 macro	Recall COVID-19	Recall Neumonía
1	EfficientNet-B0	0.9600	0.9601	0.9800	0.9333
2	ResNet18	0.8933	0.8929	0.9667	0.8333
3	CNN simple	0.7022	0.7013	0.7000	0.7733
8. Decisión final

Se seleccionó EfficientNet-B0 como modelo final porque:

obtuvo la mejor accuracy;
obtuvo el mejor F1 macro;
obtuvo el mejor recall COVID-19;
obtuvo el mejor recall Neumonía;
tiene un tamaño razonable para desplegarse en CPU dentro de Docker Compose.
9. Correcciones realizadas

Durante la fase DL hubo que corregir:

uso accidental de carpetas masks/;
rutas incorrectas en comandos de prueba;
necesidad de reconstruir ml-inference tras cambios de código;
necesidad de apuntar ML_MODEL_PATH al artefacto final;
problemas de tiempo de entrenamiento en CPU;
diferencia entre rutas del host Windows y rutas internas /app/... dentro de contenedor.
10. Reflexión

La IA aceleró la construcción del módulo, pero no sustituyó la validación. La parte crítica fue ejecutar los comandos y comprobar:

que el dataset estaba limpio;
que no había máscaras en los CSV;
que los tres modelos entrenaban;
que cada artefacto generaba métricas;
que la comparación se hacía con el mismo test set;
que el dashboard llamaba al servicio correcto dentro de Docker.

El mayor aprendizaje fue que en Deep Learning médico una métrica alta no basta. Hay que mirar qué errores se producen y qué consecuencias clínicas tienen.