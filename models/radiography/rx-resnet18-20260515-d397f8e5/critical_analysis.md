# Análisis crítico del modelo de radiografías `rx-resnet18-20260515-d397f8e5`

## 1. Resumen técnico

- **Backbone**: `resnet18`
- **Accuracy**: 0.8933
- **F1 macro**: 0.8929
- **Recall COVID-19**: 0.9667
- **Recall Neumonía**: 0.8333

## 2. Errores principales observados

| # | Clase real | Clase predicha | Casos |
|---|------------|----------------|-------|
| 1 | Neumonía | Sana | 21 |
| 2 | Sana | COVID-19 | 13 |
| 3 | Sana | Neumonía | 5 |
| 4 | Neumonía | COVID-19 | 4 |
| 5 | COVID-19 | Sana | 3 |

## 3. Impacto clínico de errores

### Falso negativo COVID-19

Una radiografía de COVID-19 clasificada como `Sana` o `Neumonía` tiene riesgo epidemiológico alto. Puede provocar falta de aislamiento, exposición del personal sanitario y contagios intrahospitalarios. Este es uno de los errores más graves del sistema.

### COVID-19 confundido con neumonía

El riesgo es medio-alto. Parte del manejo respiratorio puede ser similar, pero se pierde el componente epidemiológico: aislamiento, trazabilidad de contactos y protocolos COVID.

### Neumonía clasificada como sana

Implica retraso diagnóstico y terapéutico, especialmente problemático en pacientes vulnerables. Puede retrasar antibiótico, seguimiento o derivación.

### Sana clasificada como patológica

Es menos crítico que un falso negativo, pero genera sobrecarga asistencial, pruebas innecesarias, ansiedad del paciente y coste operativo.

## 4. Interpretación de sensibilidad

El recall COVID-19 (0.967) es razonable para un prototipo, aunque seguiría requiriendo validación clínica externa.

## 5. Limitaciones reales

- Dataset público con sesgos de adquisición, procedencia y calidad.
- No existe validación externa con datos hospitalarios propios.
- La clase `Neumonía` agrupa `Viral Pneumonia` y `Lung_Opacity`, simplificando una realidad clínica más compleja.
- El modelo puede aprender artefactos del dataset en lugar de patrones radiológicos generalizables.
- El sistema no sustituye criterio médico ni constituye dispositivo médico certificado.

## 6. Conclusión

El modelo es válido como módulo académico de Deep Learning integrado en una infraestructura Big Data hospitalaria. Para producción real harían falta más datos, validación multicéntrica, revisión radiológica experta, calibración de probabilidades y certificación regulatoria.