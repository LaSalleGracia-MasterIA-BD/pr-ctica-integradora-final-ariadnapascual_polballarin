# Análisis crítico — modelo de enfermedad `dis-20260514-8c9a3874`

**Fecha de evaluación**: 2026-05-14T15:32:16.381565+00:00

## 1. Resumen de rendimiento

- **Accuracy**: 0.9267
- **F1 macro**: 0.8665 *(media simple — sensible al desbalance de clases minoritarias)*
- **F1 weighted**: 0.9250 *(ponderada por soporte — más representativa del rendimiento global)*

## 2. Top 5 errores más frecuentes

| # | Real | Predicha | Casos |
|---|------|----------|-------|
| 1 | Sospecha de neumonía | Gripe / resfriado | 13 |
| 2 | Gastroenteritis | Sospecha de apendicitis | 11 |
| 3 | Cuadro inespecífico | Gastroenteritis | 10 |
| 4 | Cuadro inespecífico | Traumatismo | 10 |
| 5 | Sospecha de COVID-19 | Gripe / resfriado | 9 |

Los errores entre clases **clínicamente próximas** (gripe ↔ COVID, gastroenteritis ↔ apendicitis, cefalea ↔ ictus) son esperables — reflejan la matriz de proximidad clínica del ruido tipo A (DESIGN-08b §4.4). Los errores entre clases lejanas (p. ej. traumatismo → cardiopatia) son señal de problema y requieren revisión del generador o del entrenamiento.

## 3. F1 por clase (peor → mejor)

| Clase | F1 | Precisión | Recall | Soporte |
|-------|----|-----------|--------|---------|
| Sospecha de neumonía | 0.522 | 0.750 | 0.400 | 30 |
| Sospecha de apendicitis | 0.733 | 0.647 | 0.846 | 26 |
| Exacerbación asma/EPOC | 0.833 | 0.909 | 0.769 | 13 |
| Cefalea / migraña | 0.878 | 0.900 | 0.857 | 42 |
| Sospecha de ictus | 0.903 | 0.913 | 0.894 | 47 |
| Sospecha de COVID-19 | 0.927 | 0.948 | 0.907 | 140 |
| Gastroenteritis | 0.932 | 0.932 | 0.932 | 190 |
| Cuadro inespecífico | 0.932 | 0.935 | 0.930 | 415 |
| Gripe / resfriado | 0.939 | 0.927 | 0.951 | 306 |
| Sospecha cardiopatía aguda | 0.962 | 0.946 | 0.978 | 90 |
| Traumatismo | 0.971 | 0.952 | 0.990 | 201 |

Las clases minoritarias clínicas (neumonía, asma/EPOC, apendicitis) tienen soporte bajo — el F1 es ruidoso. `class_weight='balanced'` compensa parcialmente: trade-off entre recall en minoritarias (falsos positivos) vs precision en mayoritarias.

## 4. Comportamiento ante la variable espuria

`hora_envio` es una variable espuria (DESIGN-08 §4.3): se genera aleatoriamente y **no** aparece en ninguna regla del generador. Un modelo bien entrenado debe asignarle importancia muy baja.

- Importancia normalizada de `hora_envio`: **-0.0014** (ratio respecto a la feature más importante).

## 5. Top 5 features por importancia (permutation)

| # | Feature | Importancia |
|---|---------|-------------|
| 1 | `motivo_principal` | 0.6547 |
| 2 | `contacto_covid_reciente` | 0.1408 |
| 3 | `fiebre_subjetiva` | 0.0788 |
| 4 | `tos` | 0.0781 |
| 5 | `edad` | 0.0445 |

## 6. Limitación crítica (obligatoria)

Las etiquetas de enfermedad son **sintéticas**, generadas por reglas heurísticas que el equipo ha codificado a mano. El modelo aprende esas reglas con un 10 % de ruido — **no aprende patrones epidemiológicos reales**. Su uso clínico real está **explícitamente desautorizado**: la salida es una sospecha orientativa para apoyo administrativo (priorización de admisión), nunca un diagnóstico.

En un sistema real haría falta entrenamiento con historiales clínicos validados, supervisión médica continua, y certificación regulatoria (CE, FDA, AEMPS). El valor de este modelo es **pedagógico**: demuestra el flujo SDD → reglas → dataset → entrenamiento → evaluación → servicio HTTP con un segundo target sobre el mismo formulario, alineado con §3.1 ("predicción de enfermedades") y §7 (ética y limitaciones) del enunciado.

## 7. Desbalance de clases — discusión

La distribución de `disease_target` es naturalmente desbalanceada: `asma_epoc_exacerbacion` ~0.8 %, `neumonia_sospecha` ~1.5 % vs `inespecifico` ~30 % o `gripe_resfriado` ~20 %. Esto refleja frecuencias plausibles en un servicio de admisión real, no un defecto del generador (DESIGN-08b §4.3). Compensamos con `class_weight='balanced'` en el entrenamiento — alternativas consideradas y descartadas: oversampling SMOTE (introduce muestras sintéticas no clínicas), inflar artificialmente las features de entrada (rompe el realismo de la generación).
