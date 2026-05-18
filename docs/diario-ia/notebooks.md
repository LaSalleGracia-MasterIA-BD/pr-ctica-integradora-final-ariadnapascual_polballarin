
# Notebooks de análisis y comunicación de resultados

Este documento describe los notebooks usados para comunicar resultados, métricas, gráficas y decisiones técnicas del proyecto. Los notebooks explican el razonamiento, muestran evidencias y facilitan la defensa académica, pero no sustituyen al dashboard.

---

## Estructura de notebooks

```
notebooks/
├── 00_overview_sistema.ipynb
├── 01_pipeline_bigdata.ipynb
├── 02_ml_triage_tabular.ipynb
├── 03_ml_inference_radiografias.ipynb
├── 04_monitoring_automation.ipynb
└── 05_dashboard_api_demo.ipynb
```

---

### 00_overview_sistema.ipynb
**Objetivo:** Explicar el sistema completo.
- Diagrama general, tabla de servicios Docker, puertos, almacenamiento, flujo end-to-end.
- Gráficas/tablas: servicios, almacenamiento, diagrama Mermaid, resumen de responsabilidades.
- Mensaje clave: el sistema es una infraestructura completa, no un script local.

---

### 01_pipeline_bigdata.ipynb
**Objetivo:** Demostrar pipeline Big Data y calidad de datos.
- Incluye: seed, batch CSV, lectura con Dask, validación, transformación, carga, rechazos, eventos, alertas.
- Gráficas: válidos vs rechazados, eventos por tipo, timeline, tabla de rechazos.
- Ejemplo de datos: records_in=5, valid=1, rejected=4, rejects_persisted=4.
- Mensaje clave: el pipeline detecta errores, persiste rechazos y genera eventos auditables.

---

### 02_ml_triage_tabular.ipynb
**Objetivo:** Explicar modelos tabulares de triaje y enfermedad.
- Incluye: dataset sintético, distribución de clases, modelos, métricas, matrices de confusión, análisis crítico.
- Gráficas: distribución, matrices de confusión, barras accuracy/F1, ejemplo de probabilidades.
- Mensaje clave: el modelo tabular es para priorización inicial, no diagnóstico definitivo.

---

### 03_ml_inference_radiografias.ipynb
**Objetivo:** Explicar el módulo Deep Learning de radiografías.
- Incluye: ejemplos de imágenes, distribución, limpieza de masks/, preprocesado, comparación de modelos, métricas, matrices de confusión, criterio clínico, selección final.
- Gráficas: ejemplos, distribución, tabla comparativa, barras accuracy/F1/recall, matrices de confusión.
- Resultados actuales: EfficientNet-B0 (0.96), ResNet18 (0.89), CNN simple (0.70).
- Conclusión: EfficientNet-B0 es el modelo seleccionado por equilibrio clínico y estadístico.

---

### 04_monitoring_automation.ipynb
**Objetivo:** Explicar monitorización, logs y alertas.
- Incluye: Loki, Promtail, system_events, alerts, automation, CSV inválido, creación de alertas.
- Gráficas: eventos por nivel/tipo, alertas abiertas, timeline.
- Mensaje clave: el sistema observa, registra y alerta ante anomalías.

---

### 05_dashboard_api_demo.ipynb
**Objetivo:** Demostrar comunicación API-dashboard-modelos.
- Incluye: healthchecks, endpoints, ejemplos, explicación del dashboard, prueba de `/predict`.
- Tablas: endpoints, servicios consumidores, respuestas esperadas.
- Mensaje clave: el dashboard es visual, la lógica está separada en API, pipeline y modelos.

---

## Relación notebooks vs dashboard

| Elemento           | Función                                 |
|--------------------|-----------------------------------------|
| Dashboard          | Uso interactivo del sistema             |
| Notebooks          | Explicación, métricas, gráficas, defensa|
| README             | Instrucciones de ejecución              |
| PROJECT_MAP        | Mapa técnico del repositorio            |
| Specs              | Especificaciones SDD                    |
| critical_analysis.md| Interpretación clínica por modelo       |