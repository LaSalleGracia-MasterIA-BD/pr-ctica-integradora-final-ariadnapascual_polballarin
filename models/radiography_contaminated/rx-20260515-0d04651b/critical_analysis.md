# Analisis critico del modelo de radiografias

## Error mas frecuente
El error mas frecuente es Neumonía -> COVID-19 con 24 casos en el conjunto de test.

## Impacto clinico de errores
- Falso negativo de COVID-19: riesgo de no aislar un paciente contagioso.
- Falso positivo de COVID-19: aislamiento innecesario y coste asistencial.
- Falso negativo de Neumonia: retraso en el tratamiento antibiotico.

## Sensibilidad de COVID-19
Recall COVID-19 en test: 0.720.
El valor es bajo para un entorno clinico y requiere mejoras.

## Limitaciones
- Dataset publico 2020-2021; no representa todas las variantes actuales.
- Calidad heterogenea de las radiografias del dataset.
- Agrupacion de Lung_Opacity con Neumonia por decision de diseño.
- Modelo academico sin validacion clinica certificada.