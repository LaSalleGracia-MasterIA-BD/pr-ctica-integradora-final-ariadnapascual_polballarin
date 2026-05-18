# 07 — Desarrollo asistido por IA: módulo Deep Learning radiografías

## 1. Objetivo

El objetivo de esta fase fue construir un módulo de Deep Learning para clasificar radiografías de tórax en tres clases:

- Sana.
- Neumonía.
- COVID-19.

El módulo debía incluir:

6. Prompt representativo 4 — Integración con dashboard
7. Resultados finales
2	ResNet18	0.8933	0.8929	0.9667	0.8333

# 08 — Desarrollo asistido por IA: módulo Deep Learning radiografías

## Objetivo

Construcción de un módulo de Deep Learning para clasificar radiografías de tórax en tres clases: Sana, Neumonía y COVID-19. El módulo incluye preparación del dataset, entrenamiento, evaluación, matriz de confusión, análisis crítico clínico, despliegue como servicio FastAPI, integración con dashboard y comparación entre arquitecturas.

## Herramientas de IA utilizadas

Se usaron herramientas de IA generativa para diseñar la arquitectura, traducir requisitos, generar y corregir scripts, depurar errores, redactar documentación, justificar decisiones clínicas y técnicas, preparar comandos reproducibles y estructurar el análisis crítico. Todas las decisiones se validaron mediante ejecución real en Docker Compose.

## Prompts y validaciones clave

### 1. Entender el requisito

Se propuso agrupar `Normal` como Sana, `Viral Pneumonia` y `Lung_Opacity` como Neumonía, y `COVID` como COVID-19. Se entrenó con transfer learning, generando `metrics.json`, `confusion_matrix.png` y `critical_analysis.md`, y exponiendo el modelo mediante FastAPI. Se documentó como limitación que `Lung_Opacity` puede tener causas clínicas distintas y que agruparla en neumonía es una simplificación académica.

### 2. Comparar modelos

Se amplió el código para permitir varios backbones (`simple_cnn`, `resnet18`, `efficientnet_b0`), añadiendo argumento `--backbone`, lectura desde `metadata.json`, script de comparación y generación de `comparison.csv`, `comparison.md` y `comparison.json`. EfficientNet-B0 fue seleccionado por mejor equilibrio clínico tras ejecutar los tres modelos sobre el mismo dataset limpio y balanceado.

### 3. Detectar contaminación del dataset

Se corrigió el preprocesado para excluir rutas con `masks/` y asegurar que solo se usaban imágenes radiográficas. Se comprobó con búsquedas en los CSV y se validó que el dataset final estaba limpio.

### 4. Integración con dashboard

Se añadió la pestaña Radiografías al dashboard Streamlit, usando `st.file_uploader` y llamada HTTP a `/predict` en `http://ml-inference:8001/predict` (usando el nombre del servicio, no localhost). Se mostraron métricas de probabilidad por clase, alerta visual si `triggers_covid_alert=true` y aviso si `low_confidence=true`.

## Resultados finales

| Ranking | Modelo          | Accuracy | F1 macro | Recall COVID-19 | Recall Neumonía |
|---------|-----------------|----------|----------|-----------------|-----------------|
| 1       | EfficientNet-B0 | 0.9600   | 0.9601   | 0.9800          | 0.9333          |
| 2       | ResNet18        | 0.8933   | 0.8929   | 0.9667          | 0.8333          |
| 3       | CNN simple      | 0.7022   | 0.7013   | 0.7000          | 0.7733          |

Se seleccionó EfficientNet-B0 como modelo final por su mejor accuracy, F1 macro, recall COVID-19 y recall Neumonía, además de su tamaño razonable para despliegue en CPU.

## Correcciones realizadas

- Exclusión accidental de carpetas masks/
- Rutas incorrectas en comandos de prueba
- Necesidad de reconstruir ml-inference tras cambios de código
- Apuntar ML_MODEL_PATH al artefacto final
- Problemas de tiempo de entrenamiento en CPU
- Diferencia entre rutas del host Windows y rutas internas en el contenedor

## Reflexión

La IA aceleró la construcción del módulo, pero la validación manual fue imprescindible. Se comprobó que el dataset estaba limpio, que no había máscaras en los CSV, que los tres modelos entrenaban, que cada artefacto generaba métricas, que la comparación se hacía con el mismo test set y que el dashboard llamaba al servicio correcto dentro de Docker.

El mayor aprendizaje fue que en Deep Learning médico una métrica alta no basta: hay que analizar los errores y sus consecuencias clínicas.