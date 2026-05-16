# Análisis crítico — modelo de triaje `tri-20260514-60eff3c2`

**Fecha de evaluación**: 2026-05-14T15:32:01.775256+00:00

## 1. Resumen de rendimiento

- **Accuracy**: 0.9180
- **F1 macro**: 0.8978
- **Recall clase Alta**: 0.8022 *(métrica clínicamente crítica — falsos negativos de Alta son el peor escenario)*

## 2. Error más frecuente

El error más frecuente en la matriz de confusión es **Alta → Media** con **48 casos** sobre 1500 registros de test.

**Impacto clínico**: Un paciente urgente fue clasificado como moderado. Retraso potencial en su atención, con riesgo clínico si se trata de patología tiempo-dependiente.

## 3. Comportamiento ante la variable espuria

`hora_envio` es una variable espuria (ver DESIGN-08 §4.3): se genera aleatoriamente en el dataset sintético y **no** está presente en ninguna regla clínica. Un modelo bien entrenado debería asignarle importancia **muy baja**.

- Importancia normalizada de `hora_envio`: **0.0095** (ratio respecto a la feature más importante).

> ⚠️ **Aviso**: `hora_envio` tiene importancia superior al umbral (0.0050). Esto sugiere que el generador sintético ha introducido alguna correlación accidental con el target. Revisar `generate_dataset.py` antes de defender resultados.

## 4. Top 5 features por importancia (permutation)

| # | Feature | Importancia (permutation) |
|---|---------|---------------------------|
| 1 | `dificultad_respiratoria_subjetiva` | 0.1749 |
| 2 | `edad` | 0.1619 |
| 3 | `fiebre_subjetiva` | 0.1371 |
| 4 | `motivo_principal` | 0.0942 |
| 5 | `intensidad_dolor` | 0.0903 |

## 5. Limitación fundamental

El dataset es **sintético** y sus etiquetas vienen de reglas que el propio equipo ha codificado, más un **10 % de ruido** deliberado (ver DESIGN-08 §4.4, §4.5). El modelo, por construcción, reproduce esas reglas; sus métricas **no reflejan utilidad clínica real**.

Su valor es **pedagógico**: demuestra que el flujo SDD → dataset → entrenamiento → evaluación → servicio HTTP funciona end-to-end, con trazabilidad, reproducibilidad y análisis crítico alineados con el enunciado §3.1 y §7.

En un despliegue clínico real, este modelo **no sustituye** al juicio del personal sanitario ni constituye un dispositivo médico validado.
