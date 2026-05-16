# Notebooks de análisis y comunicación de resultados

Este documento define los notebooks usados para comunicar resultados, métricas, gráficas y decisiones técnicas del proyecto.

Los notebooks no sustituyen al dashboard. Su objetivo es explicar el razonamiento, mostrar evidencias y facilitar la defensa académica.

---

## 1. Estructura propuesta

```text
notebooks/
├── 00_overview_sistema.ipynb
├── 01_pipeline_bigdata.ipynb
├── 02_ml_triage_tabular.ipynb
├── 03_ml_inference_radiografias.ipynb
├── 04_monitoring_automation.ipynb
└── 05_dashboard_api_demo.ipynb
```

---

## 2. `00_overview_sistema.ipynb`

### Objetivo

Explicar el sistema completo.

### Debe incluir

- diagrama general;
- tabla de servicios Docker;
- tabla de puertos;
- tabla de almacenamiento;
- explicación de flujo end-to-end.

### Gráficas / tablas

- tabla de servicios;
- tabla de almacenamiento;
- diagrama Mermaid;
- resumen de responsabilidades.

### Mensaje que debe quedar claro

El sistema no es un script local. Es una infraestructura compuesta por servicios separados, bases de datos, pipeline, modelos, dashboard, monitorización y automatización.

---

## 3. `01_pipeline_bigdata.ipynb`

### Objetivo

Demostrar pipeline Big Data y calidad de datos.

### Debe incluir

- seed de datos;
- batch CSV;
- lectura con Dask;
- validación;
- transformación;
- carga;
- rechazos;
- eventos;
- alertas.

### Gráficas

- barras de válidos vs rechazados;
- eventos por tipo;
- timeline de pipeline;
- tabla de rechazos.

### Datos a mostrar

```text
records_in = 5
valid = 1
rejected = 4
rejects_persisted = 4
```

### Mensaje que debe quedar claro

El pipeline no solo procesa datos válidos. Detecta errores, persiste rechazos y genera eventos auditables.

---

## 4. `02_ml_triage_tabular.ipynb`

### Objetivo

Explicar modelos tabulares de triaje y enfermedad.

### Debe incluir

- dataset sintético;
- distribución de clases;
- modelo de triaje;
- modelo de enfermedad;
- métricas;
- matrices de confusión;
- análisis crítico.

### Gráficas

- distribución Alta / Media / Baja;
- matriz de confusión de triaje;
- matriz de confusión de enfermedad;
- barras accuracy / F1;
- ejemplo de probabilidades.

### Mensaje que debe quedar claro

El modelo tabular se usa para priorización inicial y sospecha orientativa, no para diagnóstico definitivo.

---

## 5. `03_ml_inference_radiografias.ipynb`

### Objetivo

Explicar el módulo Deep Learning de radiografías.

### Debe incluir

- ejemplos de imágenes por clase;
- distribución del dataset;
- limpieza de `masks/`;
- preprocesamiento;
- comparación CNN simple vs ResNet18 vs EfficientNet-B0;
- métricas por modelo;
- matrices de confusión;
- criterio clínico;
- selección final.

### Gráficas

- imágenes ejemplo por clase;
- distribución de clases;
- tabla comparativa;
- barras de accuracy;
- barras de F1 macro;
- barras de recall COVID;
- barras de recall Neumonía;
- matrices de confusión.

### Resultados actuales

| Modelo | Accuracy | F1 macro | Recall COVID | Recall Neumonía |
|---|---:|---:|---:|---:|
| EfficientNet-B0 | 0.9600 | 0.9601 | 0.9800 | 0.9333 |
| ResNet18 | 0.8933 | 0.8929 | 0.9667 | 0.8333 |
| CNN simple | 0.7022 | 0.7013 | 0.7000 | 0.7733 |

### Conclusión esperada

EfficientNet-B0 es el modelo seleccionado porque obtiene el mejor equilibrio clínico y estadístico.

---

## 6. `04_monitoring_automation.ipynb`

### Objetivo

Explicar monitorización, logs y alertas.

### Debe incluir

- Loki;
- Promtail;
- system_events;
- alerts;
- automation;
- ejemplo de CSV inválido;
- creación de alertas.

### Gráficas

- eventos por nivel;
- eventos por tipo;
- alertas abiertas;
- timeline de eventos.

### Mensaje que debe quedar claro

El sistema no solo ejecuta procesos. También observa, registra y alerta ante anomalías.

---

## 7. `05_dashboard_api_demo.ipynb`

### Objetivo

Demostrar comunicación API-dashboard-modelos.

### Debe incluir

- healthchecks;
- endpoints principales;
- ejemplo de paciente;
- ejemplo de radiografía;
- explicación del dashboard;
- prueba de `/predict`.

### Tablas

- endpoints;
- servicios consumidores;
- respuestas esperadas.

### Mensaje que debe quedar claro

El dashboard es una capa visual. La lógica está separada en API, pipeline y modelos.

---

## 8. Relación notebooks vs dashboard

| Elemento | Función |
|---|---|
| Dashboard | Uso interactivo del sistema. |
| Notebooks | Explicación, métricas, gráficas y defensa técnica. |
| README | Instrucciones de ejecución. |
| PROJECT_MAP | Mapa técnico del repositorio. |
| Specs | Especificaciones SDD. |
| critical_analysis.md | Interpretación clínica por modelo. |