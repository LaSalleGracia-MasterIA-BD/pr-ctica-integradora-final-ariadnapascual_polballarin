# SDD-08 — Modelo tabular de triaje de pacientes

> Spec del **modelo de IA tabular** que clasifica pacientes recién registrados en tres niveles de prioridad clínica (*Alta / Media / Baja*) a partir de un formulario de autoservicio rellenado por el propio paciente. Cumple §3.1 del enunciado ("Modelo de IA · clasificación de pacientes"). La arquitectura concreta, algoritmo, hiperparámetros y código de entrenamiento van en `DESIGN-08-modelo-triaje.md`.

---

**Versión:** 1.1
**Fecha:** 2026-04-20 (actualizado 2026-04-27 con nota de DESIGN-08b)
**Autor:** Pol Ballarín
**Estado:** `ready-for-design`

> **Nota 2026-04-27**: tras [DESIGN-08b](DESIGN-08b-modelo-enfermedad.md) el endpoint pasa a `POST /predict` y devuelve también la sospecha de enfermedad. Las referencias a `/predict-triage` y al output exclusivo de triaje en este documento se conservan por trazabilidad — el contrato vigente está en DESIGN-08b §6.1.

---

## 1. Contexto y objetivo

### Contexto
El enunciado §3.1 exige un modelo de IA que resuelva un problema concreto; entre los ejemplos que cita aparece explícitamente *"clasificación de pacientes"*. laSalle Health Center quiere ofrecer a los pacientes un **formulario web de triaje pre-consulta**: antes de acudir al hospital, el paciente rellena una ficha con sus datos básicos, antecedentes y síntomas auto-reportados. El sistema clasifica automáticamente la ficha en uno de tres niveles de prioridad (*Alta / Media / Baja*) como **apoyo a la gestión de la agenda** del hospital.

Este SDD es **distinto y complementario** al SDD-06 (clasificación de radiografías):

| | SDD-08 (triaje tabular) | SDD-06 (radiografías DL) |
|---|---|---|
| Tarea | Priorizar al paciente antes de la visita | Clasificar una radiografía ya tomada |
| Input | Formulario auto-reportado (~14 campos) | Imagen JPG/PNG de tórax |
| Output | Alta / Media / Baja | Sana / Neumonía / COVID-19 |
| Dataset | **Sintético** con reglas + ruido + variables espurias | Público (*COVID-19 Radiography Database*) |
| Momento clínico | Pre-consulta (web) | Durante consulta (radiología) |

### Objetivo
Proveer un modelo tabular de clasificación multiclase que:

1. Consuma una **ficha de paciente** procedente del formulario web (campos definidos en RF-3).
2. Prediga un **nivel de triaje** *(Alta / Media / Baja)* como apoyo a la decisión del personal hospitalario (nunca como asignación automática sin revisión humana).
3. Se entrene de forma **reproducible** sobre un dataset sintético con reglas clínicamente razonables, ruido intencional y variables espurias.
4. Se sirva como endpoint HTTP llamado por la API (SDD-05) al final del pipeline de ingesta online (SDD-02), de modo que cada ficha que entra por el formulario acabe con nivel de triaje asignado visible en el dashboard.
5. Exponga métricas de evaluación claras y un **análisis crítico** de sus limitaciones (entre ellas, la más importante: *los datos son sintéticos, el modelo aprende las reglas que nosotros mismos codificamos y su comportamiento no tiene valor clínico real* — consistente con §7 del enunciado).

## 2. Actores y alcance

### Actores

| Actor | Dirección | Rol |
|-------|-----------|-----|
| **Paciente en la web** | humano | Rellena el formulario de triaje pre-consulta desde el dashboard |
| **API** *(SDD-05)* | cliente | Recibe la ficha del formulario, la pasa por el ETL y, al final, llama al endpoint `/predict-triage` |
| **Pipeline** *(SDD-02)* | productor | En modo **online**, valida/limpia/transforma la ficha antes de persistir y predecir |
| **Almacenamiento** *(SDD-03)* | lectura/escritura | PostgreSQL para el paciente; MongoDB para la predicción de triaje como documento asociado |
| **Dashboard** *(SDD-05)* | consumidor | Muestra el nivel de triaje predicho junto al paciente en su detalle y en listados |
| **Script de entrenamiento** | operador | Genera el dataset sintético, entrena el modelo, produce el artefacto |
| **Pol (entrenador)** | humano | Ejecuta el script de entrenamiento, revisa métricas y análisis crítico |

### Dentro del alcance

- **Generación del dataset sintético** con reglas clínicas razonables, **ruido** intencional y **variables espurias** (p. ej. hora del día) para evitar circularidad trivial.
- **Preparación de datos**: splits estratificados train/val/test, codificación de categóricas, manejo de opcionales/nulos.
- **Entrenamiento** del modelo multiclase con algoritmo tabular estándar (Random Forest, Gradient Boosting u otro — decisión en `DESIGN-08`).
- **Evaluación**: matriz de confusión 3×3, precisión/recall/F1 por clase, importancia de features.
- **Análisis crítico** obligatorio: reflexión sobre el hecho de que los datos son sintéticos, la distribución aprendida es la diseñada por nosotros, y los límites éticos y clínicos del uso.
- **Servicio de inferencia** (endpoint HTTP) que acepta una ficha y devuelve nivel + probabilidades por clase + `model_version`.
- **Integración al final del pipeline online**: cuando una ficha nueva llega por el formulario, al terminar el ETL se invoca el endpoint y se persiste la predicción.
- **Versionado** del modelo y trazabilidad de qué versión predijo qué.

### Fuera del alcance

- **Uso clínico real**: el modelo es un ejercicio académico, no un producto validado. Se etiqueta explícitamente como "apoyo, no diagnóstico" y nunca sustituye al personal sanitario (consistente con SDD-01 fuera-de-alcance).
- **Aprendizaje online / reentrenamiento automático**: el modelo se entrena offline y se despliega como artefacto inmutable. No aprende de los pacientes que llegan.
- **Explicabilidad avanzada** (SHAP, LIME): **opcional**, si hay tiempo; no es requisito. Basta con importancia de features del algoritmo.
- **Tests A/B** comparando modelos en producción.
- **Federated learning** u otras técnicas de privacidad distribuida.
- **Cinco niveles de triaje** tipo ESI/Manchester: el alcance se limita a tres (Alta/Media/Baja) por simplicidad. Se documenta en memoria la decisión.

## 3. Requisitos funcionales

### Formulario de ficha de paciente (features del modelo)

- **RF-1**: El sistema debe aceptar una ficha de paciente con los siguientes campos **auto-reportados** por el paciente:

  **Datos básicos** *(obligatorios)*
  1. `edad` — entero 0–120.
  2. `sexo` — enum `{M, F, Otro}`.

  **Datos básicos** *(opcionales)*
  3. `peso_kg` — entero positivo.
  4. `altura_cm` — entero positivo. *(A partir de peso y altura, el pipeline puede derivar `imc` como feature extra.)*

  **Antecedentes** *(obligatorios si aplica)*
  5. `enfermedades_cronicas` — multi-selección entre `{diabetes, hipertension, asma_epoc, cardiopatia, inmunosupresion, ninguna}`.
  6. `fumador` — enum `{no, si, exfumador}`.
  7. `embarazo` — enum `{si, no, na}`.

  **Síntomas actuales** *(obligatorios)*
  8. `motivo_principal` — enum `{dolor_toracico, dificultad_respiratoria, fiebre, dolor_abdominal, traumatismo, sintomas_neurologicos, otro}`.
  9. `duracion_sintomas` — enum `{<24h, 1-3d, 4-7d, >1sem}`.
  10. `intensidad_dolor` — entero 0–10 (escala auto-reportada).
  11. `fiebre_subjetiva` — enum `{no, leve, alta}`.
  12. `dificultad_respiratoria_subjetiva` — enum `{no, leve, moderada, grave}`.
  13. `tos` — enum `{no, seca, con_flema}`.

  **Exposición epidemiológica** *(obligatorio)*
  14. `contacto_covid_reciente` — enum `{si, no, no_se}`.

  **Variable espuria intencional**
  15. `hora_envio` — entero 0–23. Añadida como ruido deliberado: el modelo no debería basar sus decisiones en este campo.

- **RF-2**: Los campos opcionales (`peso_kg`, `altura_cm`) deben aceptarse como nulos y el modelo debe tolerarlos (imputación por mediana o estrategia documentada en `DESIGN-08`).

### Target

- **RF-3**: El modelo debe predecir una de tres clases **mutuamente excluyentes**:
  - **Alta** — el paciente debería ser atendido con urgencia.
  - **Media** — atención recomendada en horas, no inmediata.
  - **Baja** — puede esperar a cita convencional.
- **RF-4**: La predicción debe ir acompañada de una **probabilidad por clase** (tres valores en [0, 1] que suman 1.0 ±1e-6), para reflejar la confianza del modelo.

### Dataset sintético

- **RF-5**: El sistema debe incluir un **script de generación** de dataset sintético que produzca, por defecto, al menos **10 000 ejemplos** con distribución de clases **no degenerada** (ninguna clase < 10% del total).
- **RF-6**: El dataset sintético debe construirse mediante:
  - **Reglas clínicamente razonables**: combinaciones de edad + antecedentes + síntomas que sugieren prioridad (p. ej. *dolor torácico intenso + edad > 50 → Alta*; *fiebre leve aislada + joven y sano → Baja*).
  - **Ruido intencional** en un porcentaje **configurable** (p. ej. 10 %) de ejemplos: el ruido puede ser (a) etiqueta cambiada a una clase adyacente, (b) síntomas contradictorios, (c) valores atípicos.
  - **Variables espurias**: al menos la `hora_envio` (RF-1 campo 15) sin correlación real con el target.
- **RF-7**: La generación debe ser **reproducible** con semilla aleatoria fijable: misma semilla ⇒ mismo dataset byte-a-byte.
- **RF-8**: El dataset se persiste como CSV versionado (o Parquet) en `./data/synthetic/triage/` con metadata asociada (semilla, versión del generador, fecha, tamaño, distribución de clases).

### Entrenamiento y evaluación

- **RF-9**: El entrenamiento produce splits **estratificados** train/val/test (propuesta inicial 70/15/15) con proporciones de clase similares en cada split.
- **RF-10**: El entrenamiento es **reproducible**: semillas fijadas, hiperparámetros registrados como artefacto del run.
- **RF-11**: Al terminar, el sistema calcula y persiste, sobre el split de **test**:
  - **Matriz de confusión 3×3** (PNG + JSON).
  - **Accuracy global**.
  - **Precisión, recall, F1 por clase**.
  - **F1 macro**.
  - **Importancia de features** (del algoritmo si la expone; p. ej. `feature_importances_` de Random Forest).
- **RF-12**: El sistema produce un **documento de análisis crítico** que discute como mínimo:
  - Tipos de error más frecuentes (¿confunde Alta con Media o con Baja?) e **impacto clínico** de cada error (un falso Baja sobre un paciente de Alta es más grave que lo contrario).
  - **Importancia de la `hora_envio`** en el modelo: debe ser **baja**. Si resulta alta, es señal de que el dataset o el entrenamiento tiene problema.
  - **Limitación crítica explícita**: el dataset es sintético, por lo que el modelo aprende las reglas que el generador codifica. No es un modelo clínico real y su accuracy no refleja utilidad sanitaria.

### Servicio de inferencia

- **RF-13**: El modelo se sirve en un endpoint HTTP (propuesta: `POST /predict-triage`, alojado en el mismo servicio `ml-inference` de SDD-06 o en uno dedicado `ml-triage` — decisión en `DESIGN-08`).
- **RF-14**: El endpoint acepta el cuerpo JSON con los 15 campos de RF-1 (los opcionales pueden faltar) y devuelve:
  ```
  {
    "predicted_class": "Alta" | "Media" | "Baja",
    "probabilities": { "alta": float, "media": float, "baja": float },
    "model_version": "tri-YYYYMMDD-xxxx",
    "inference_time_ms": int
  }
  ```
- **RF-15**: El servicio carga el modelo **una vez al arrancar** y lo mantiene en memoria.
- **RF-16**: El servicio expone `/healthz` que devuelve 200 solo si el modelo está cargado.
- **RF-17**: Cada predicción devuelta lleva la `model_version` activa, para trazabilidad (consistente con SDD-03 versionado).

### Integración con el pipeline online

- **RF-18**: Cuando la API (SDD-05) recibe una ficha nueva del formulario, el flujo debe ser:
  1. Validar y persistir el paciente en PostgreSQL (SDD-02 modo online + SDD-03).
  2. Invocar el endpoint de triaje con la ficha recién persistida.
  3. Persistir la predicción de triaje como documento en MongoDB (SDD-03), ligada al `pseudo_id` del paciente.
  4. Devolver a la web del formulario una página de confirmación con el nivel predicho y un mensaje apropiado.
- **RF-19**: Si el servicio de triaje **no está disponible** al momento de la petición, la ficha queda persistida igualmente en estado `pending_triage`; un reintento (automation SDD-04) lo completa más tarde.

### Versionado

- **RF-20**: Cada modelo entrenado produce un artefacto identificable por `model_version` (timestamp + hash corto de hiperparámetros). El artefacto incluye pesos/estructura del modelo + metadata (hiperparámetros, hash del dataset, métricas de test).
- **RF-21**: Desplegar un modelo nuevo requiere reiniciar el servicio de inferencia con el artefacto nuevo. Las predicciones persistidas anteriormente conservan la versión con la que se hicieron.

## 4. Requisitos no funcionales

### Rendimiento

- **RNF-1**: La predicción de una ficha debe completarse en tiempo razonable en CPU (modelos tabulares son baratos). **[NEEDS CLARIFICATION]** umbral concreto — propuesta: < 500 ms.
- **RNF-2**: El entrenamiento completo sobre 10 000 ejemplos debe completarse en minutos, no horas, en CPU de portátil.

### Reproducibilidad

- **RNF-3**: Semillas fijadas para: generación del dataset, splits train/val/test, entrenamiento (si el algoritmo admite `random_state`).
- **RNF-4**: Hiperparámetros persistidos junto al artefacto del modelo (JSON con todo lo necesario para reproducir el run).
- **RNF-5**: `requirements.txt` con versiones pinneadas (consistente con SDD-01 RNF-12).

### Robustez

- **RNF-6**: El servicio debe devolver 422 ante fichas con campos obligatorios ausentes o fuera de dominio, sin invocar el modelo.
- **RNF-7**: Un fallo al cargar el modelo al arrancar deja el servicio en estado no saludable (`/healthz` = 503), sin silenciar.

### Ética y limitaciones

- **RNF-8**: Toda respuesta del servicio y toda visualización en el dashboard etiqueta el nivel como **apoyo a la decisión**, nunca como diagnóstico automatizado.
- **RNF-9**: El análisis crítico documentado en RF-12 **debe** incluir explícitamente la limitación fundamental del dataset sintético y el efecto de "circularidad controlada" (el modelo aprende reglas que el generador codifica).
- **RNF-10**: En caso de que dos clases empaten en probabilidad, se aplica la **regla de desempate prudente**: elegir la clase de **mayor gravedad** (*Alta > Media > Baja*) — un falso positivo de urgencia es menos grave clínicamente que un falso negativo. *Coherente con la regla de desempate propuesta en SDD-01 §7 pero adaptada al contexto de triaje.*

### Privacidad

- **RNF-11**: La ficha persistida en PostgreSQL se guarda **anonimizada por diseño** (pseudo_id, sin nombre/DNI), consistente con SDD-01 RNF-8 y SDD-03 RF-14. El formulario **no pide** nombre ni identificadores directos.

## 5. Casos borde / errores

### Formulario e inputs

| Caso | Comportamiento esperado | RF afectado |
|------|------------------------|-------------|
| Campo obligatorio ausente (p. ej. falta `edad`) | 422 con detalle del campo. No se invoca el modelo. | RF-1, RNF-6 |
| Valor fuera de dominio (p. ej. `edad = 500`) | 422 con detalle. | RF-1, RNF-6 |
| Opcional ausente (`peso_kg` nulo) | Aceptar, imputar según estrategia documentada. | RF-2 |
| Usuario envía `hora_envio = 25` | 422 (fuera de dominio 0–23). | RF-1, RNF-6 |
| Usuario marca **a la vez** `embarazo = si` y `sexo = M` | Aceptar técnicamente (la BD no fuerza la coherencia biológica); el generador sintético **no debe producir** esta combinación, pero en producción se acepta con flag de warning. | RF-1 |

### Modelo y predicción

| Caso | Comportamiento esperado | RF afectado |
|------|------------------------|-------------|
| Dos clases con misma probabilidad | Aplicar regla de desempate prudente (elegir mayor gravedad). | RNF-10 |
| Probabilidades devueltas no suman 1 (redondeo) | Normalizar si la diferencia es ≤ 1e-6; rechazar la predicción y marcar alerta si la diferencia es mayor. | RF-4 |
| Predicción devuelve NaN o probabilidades negativas | Devolver 500 con `model_version` en cuerpo; alerta crítica al log. | RF-4 |
| Ficha cuyos valores están todos en la frontera entre dos clases | El modelo predice con **baja confianza** (probabilidad máxima < 0.5); se marca la predicción con flag `low_confidence` visible en dashboard. | RF-4 |

### Dataset sintético

| Caso | Comportamiento esperado | RF afectado |
|------|------------------------|-------------|
| Regla del generador produce distribución degenerada (clase < 5 %) | El script aborta con error antes de persistir; hay que rebalancear el generador. | RF-5 |
| Dos ejecuciones con misma semilla producen datasets distintos | Bug crítico. Los tests lo detectan. | RF-7 |
| Generar dataset con 0 ejemplos ruidosos | Aceptado pero documentado en metadata; el entrenamiento probablemente overfiteará las reglas al 100 %. | RF-6 |

### Integración con pipeline

| Caso | Comportamiento esperado | RF afectado |
|------|------------------------|-------------|
| Servicio de triaje caído cuando llega una ficha del formulario | La ficha se persiste igualmente con estado `pending_triage`; automation (SDD-04) la completa al reintentar. | RF-19 |
| Ficha llega con `pseudo_id` duplicado (retry del formulario) | Idempotencia: no crear paciente duplicado; si ya existía, actualizar la predicción o emitir alerta según política de `DESIGN-08`. | RF-18 |
| Modelo devuelve predicción válida pero el pipeline falla al persistirla en Mongo | Reintento con backoff (consistente con SDD-03); tras agotar, alerta operativa y la predicción se pierde pero el paciente queda en `pending_triage`. | RF-18, RF-19 |

### Versionado

| Caso | Comportamiento esperado | RF afectado |
|------|------------------------|-------------|
| Despliegue de una versión nueva mientras hay fichas pendientes | Las nuevas predicciones llevarán la versión nueva; las ya hechas conservan su versión original. | RF-20, RF-21 |
| Artefacto corrupto al arrancar el servicio | `/healthz` devuelve 503, ninguna predicción se sirve hasta que se arregle. | RNF-7 |

## 6. Criterios de aceptación

### Dataset y preparación

- [ ] **CA-1** (cubre RF-5, RF-7): ejecutar el generador con semilla fija dos veces produce dos CSVs byte-idénticos. Con al menos 10 000 filas y ninguna clase por debajo del 10 %.
- [ ] **CA-2** (cubre RF-6): el dataset generado contiene (a) al menos 5 % de ejemplos con ruido intencional (etiqueta cambiada o contradicción), (b) la columna `hora_envio` sin correlación estadística significativa con `target`.
- [ ] **CA-3** (cubre RF-8): en `./data/synthetic/triage/` existe un `metadata.json` con semilla, versión del generador, tamaño, distribución de clases.

### Entrenamiento y evaluación

- [ ] **CA-4** (cubre RF-9, RF-10): ejecutar el script de entrenamiento con misma semilla y mismo dataset en dos corridas produce métricas de validación dentro de margen tolerable (diferencia de F1 macro ≤ 2 puntos).
- [ ] **CA-5** (cubre RF-11): al terminar el entrenamiento existen: JSON con matriz de confusión, accuracy, precision/recall/F1 por clase, F1 macro, importancia de features; y un PNG de la matriz de confusión.
- [ ] **CA-6** (cubre RF-12): existe un documento de análisis crítico que: (a) discute el tipo de error más frecuente y su impacto clínico, (b) verifica que la importancia de `hora_envio` es baja, (c) enuncia explícitamente que el dataset es sintético y sus consecuencias.

### Servicio

- [ ] **CA-7** (cubre RF-13, RF-14): `curl -X POST http://<host>/predict-triage -H "Content-Type: application/json" -d '{...ficha completa...}'` devuelve un JSON con `predicted_class` ∈ {Alta, Media, Baja}, `probabilities` (3 valores que suman 1.0 ±1e-6), `model_version`, `inference_time_ms`.
- [ ] **CA-8** (cubre RF-16, RNF-7): al arrancar sin artefacto en el volumen, `/healthz` devuelve 503; con artefacto presente y tras reiniciar, `/healthz` devuelve 200.
- [ ] **CA-9** (cubre RNF-6): enviar una ficha sin campo obligatorio devuelve 422 con detalle; enviar `edad = 500` devuelve 422.
- [ ] **CA-10** (cubre RNF-10): cuando `P(Alta) = P(Media)`, la respuesta es `Alta` (regla de desempate prudente).

### Integración con pipeline

- [ ] **CA-11** (cubre RF-18): rellenar el formulario en el dashboard y enviarlo produce (a) un paciente nuevo en PostgreSQL con `pseudo_id` autogenerado, (b) un documento de predicción de triaje en MongoDB con la misma `pseudo_id`, (c) una página de confirmación en el navegador con el nivel predicho.
- [ ] **CA-12** (cubre RF-19, caso borde "servicio caído"): parar el servicio de triaje, enviar una ficha del formulario, esperar el tiempo de reintentos, rearrancar el servicio: la ficha acaba con predicción persistida y el estado `pending_triage` desaparece.

### Versionado

- [ ] **CA-13** (cubre RF-17, RF-20, RF-21): dos predicciones sobre la misma ficha bajo la misma `model_version` producen el mismo resultado. Desplegar una versión nueva no altera las predicciones ya persistidas.

### Privacidad

- [ ] **CA-14** (cubre RNF-11): el formulario del dashboard no pide nombre, DNI ni dirección; la fila persistida en PostgreSQL no contiene ninguno de esos campos.

## 7. Dudas abiertas

- **[NEEDS CLARIFICATION]** **Algoritmo concreto** del modelo: Random Forest, Gradient Boosting (XGBoost/LightGBM), regresión logística multiclase, o red neuronal tabular simple. Decisión en `DESIGN-08` tras banco de pruebas corto.
- **[NEEDS CLARIFICATION]** Proporción exacta del **ruido intencional** en el dataset (RF-6): propuesta 10 %, puede ajustarse.
- **[NEEDS CLARIFICATION]** Estrategia de **imputación** para opcionales (`peso_kg`, `altura_cm` nulos): mediana, moda condicional a `edad+sexo`, o flag "unknown" (RF-2).
- **[NEEDS CLARIFICATION]** El servicio de inferencia de triaje, ¿va **en el mismo contenedor `ml-inference`** (de SDD-06) o en uno **dedicado `ml-triage`**? Propuesta: contenedor dedicado, para aislar fallos y versionados independientes.
- **[NEEDS CLARIFICATION]** Umbral concreto de tiempo de inferencia (RNF-1).
- **[NEEDS CLARIFICATION]** Confianza mínima para marcar una predicción como `low_confidence` (caso borde "valores en frontera").

## 8. Referencias

- Enunciado: `Enunciado-Hospital.pdf` §3.1 (Modelo de IA — *"clasificación de pacientes"*), §7 (ética y limitaciones)
- `CONTEXT.md` §3.1, §7
- Spec raíz: `specs/SDD-01-sistema.md`
- Spec del pipeline (modo online): `specs/SDD-02-pipeline.md`
- Spec de API + Dashboard (formulario): `specs/SDD-05-api-dashboard.md`
- Spec del modelo de radiografías (complementario): `specs/SDD-06-modelo-dl.md`
- Spec de almacenamiento: `specs/SDD-03-almacenamiento.md`
- Spec de automatización (reintento de `pending_triage`): `specs/SDD-04-automatizacion.md`
- Diseño asociado: `specs/DESIGN-08-modelo-triaje.md` *(a crear)*
- Sistemas de triaje estándar de referencia (contexto, no implementación): **ESI** (Emergency Severity Index, 5 niveles) · **Manchester Triage System** (5 colores). En este proyecto se simplifica a 3 niveles.
