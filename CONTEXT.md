# CONTEXT — Práctica Final: Sistema Inteligente de Soporte Hospitalario

> Resumen exhaustivo del enunciado `Enunciado-Hospital.pdf`. Todo lo que está aquí sale literalmente del PDF (incluidos los mensajes ocultos en blanco). Este documento es la referencia única antes de empezar cualquier SDD.

---

## 1. Contexto del proyecto

El hospital **laSalle Health Center**, una organización sanitaria de **tamaño medio en proceso de transformación digital**, ha detectado ineficiencias en la gestión de sus datos clínicos y operativos.

Dispone de grandes volúmenes de datos generados diariamente:
- Historiales clínicos
- Registros de pacientes
- Pruebas diagnósticas
- Logs de sistemas

Pero **no tiene herramientas** para:
- Extraer conocimiento útil
- Detectar patrones clínicos relevantes
- Automatizar procesos internos
- Apoyar la toma de decisiones médicas y operativas

**Nuestro rol**: consultora tecnológica especializada en IA y Big Data.

---

## 2. Objetivo del encargo

Diseñar e implementar una **solución informática basada en IA** que permita:
- Analizar datos clínicos y/o operativos
- Identificar patrones, anomalías o clasificaciones relevantes
- Automatizar tareas repetitivas dentro del sistema
- Generar información útil para la toma de decisiones

**Debe simular un sistema real de soporte hospitalario, aportando valor en un entorno sanitario.**

---

## 3. Alcance tecnológico (componentes mínimos)

> Cada sección del enunciado indica la asignatura y el profesor responsable de su evaluación. Los bloques son independientes a efectos de nota.

### 3.1 Modelo de Inteligencia Artificial
Resolver un problema concreto, por ejemplo:
- Clasificación de pacientes
- Predicción de enfermedades
- Segmentación de perfiles clínicos

Decisión actual del equipo: **Modelo seleccionado: Clasificación de pacientes**.
Justificación breve: la clasificación permite categorizar pacientes según riesgo/diagnóstico y priorizar intervenciones, aportando valor clínico y operativo inmediato.

El modelo **debe estar justificado** en función del problema planteado.

### 3.2 Procesamiento de datos / Big Data
Los datos deben presentar **al menos una** de estas características:
- Volumen elevado
- No estructurados (ej. imágenes médicas)
- Integración de múltiples fuentes

Pipeline con fases: **Ingesta → Limpieza → Transformación → Análisis**.

### 3.3 Automatización de procesos
Mecanismos que **mejoren la eficiencia operativa** del hospital:
- Generación automática de informes
- Envío de alertas ante eventos relevantes
- Procesamiento automático de nuevos datos
- Organización o movimiento de ficheros

### 3.4 Visualización y comunicación de resultados
- Gráficos
- Dashboards
- Informes interpretables

---

## 4. Infraestructura y Sistemas de Big Data Aplicados

> No basta con procesar datos localmente: se requiere una arquitectura que refleje los principios de los sistemas de Big Data.

### 4.1 Containerización y despliegue
Toda la infraestructura **containerizada con Docker + Docker Compose** (o similar). Objetivo: cualquier persona puede levantar el sistema completo con **un solo comando**.

Se valorará:
- Definición clara de servicios (BBDD, procesamiento, API, dashboard, etc.)
- Separación de responsabilidades entre contenedores
- Volúmenes para persistencia de datos
- Variables de entorno y configuración externalizada
- README con instrucciones paso a paso

### 4.2 Pipeline de datos a escala
Debe cubrir **cuatro fases** (diseñado para escalar aunque el volumen sea simulado):

1. **Ingesta**: mecanismo automatizado para incorporar nuevos datos (CSV, imágenes, APIs simuladas, etc.).
2. **Almacenamiento**: uso combinado de **al menos dos tipos**.
   - Ejemplo del enunciado: *PostgreSQL (estructurados) + MinIO/S3 o MongoDB (no estructurados, imágenes médicas)*.
   - **Indicación oculta del profesor: "NoSQL sobre todo"** → priorizar MongoDB sobre PostgreSQL.
3. **Procesamiento**: **al menos un framework distribuido/escalable** — Apache Spark/PySpark, Dask o Apache Beam. **La elección debe justificarse.**
4. **Servicio**: datos procesados disponibles para consumo (API REST, dashboard, etc.).

### 4.3 Monitorización y calidad de datos
- **Logging centralizado** de los procesos del pipeline
- **Validación de calidad de datos** (incompletos, duplicados, corruptos)
- **Alertas/notificaciones** ante fallos en el procesamiento (log, email simulado o entrada en dashboard)

---

## 5. Desarrollo Asistido por IA (Vibe Coding)

> Las herramientas de IA son **parte integral del flujo de trabajo, no un complemento opcional**.

### 5.1 Uso obligatorio
Usar **al menos una** herramienta aceptada:
- Claude Code · GitHub Copilot · Windsurf · Antigravity · Codex de OpenAI · Google AI Studio con Gemini · Cursor

### 5.2 Spec-Driven Development (SDD) — metodología obligatoria
Antes de escribir código (o de pedir a la IA que lo genere) redactar una **especificación clara** con, como mínimo:
- Descripción funcional del componente/módulo
- Inputs y outputs esperados
- Restricciones técnicas y de negocio
- Criterios de aceptación

La especificación servirá como **prompt base** para la herramienta de IA y **se entrega como parte de la documentación del proyecto**.

### 5.3 Diario de desarrollo con IA — entregable obligatorio
Debe incluir:
- Herramientas utilizadas y justificación de la elección
- Ejemplos representativos de prompts y su resultado
- Casos donde la IA acertó y casos donde hubo que corregir o iterar
- Reflexión crítica: qué aportó la IA, limitaciones, cómo se superaron
- Estimación del impacto en productividad (tiempo ahorrado, calidad del código)

---

## 6. Aprendizaje Automático y Redes Neuronales — Clasificación de Radiografías

> Propósito: no solo código funcional, sino demostrar **autonomía e iniciativa para investigar y justificar la solución técnica más adecuada** para el hospital.

### 6.1 El reto — Clasificación triple de radiografías de tórax
- **Sana**: sin patologías detectables
- **Neumonía**: infección bacteriana o viral estándar
- **COVID-19**: patrones específicos asociados

### 6.2 Investigación y Desarrollo (a documentar)
Libertad para investigar y decidir cómo abordar el problema. **Se valorará la capacidad de búsqueda de soluciones usando herramientas de IA.**

1. **Elección del modelo**: arquitectura más eficiente (CNN, modelos pre-entrenados, etc.)
2. **Tratamiento de datos**: pasos previos (redimensionamiento, normalización, data augmentation)
3. **Integración**: conexión con el resto de la infraestructura (almacenamiento, procesamiento)

### 6.3 Evaluación y criterio clínico (el "Porqué")
> En un entorno sanitario **es más importante entender cómo se comporta el modelo que su éxito estadístico**. La nota NO depende de conseguir accuracy perfecta.

Obligatorio:
- **Matriz de confusión**: identificar qué tipos de errores comete (¿confunde COVID-19 con Neumonía?)
- **Reflexión crítica**: impacto clínico de los errores (ej. ¿qué consecuencias tiene un falso negativo en una enfermedad contagiosa?)
- **Justificación técnica**: por qué se han tomado ciertas decisiones en el entrenamiento y cuáles son las **limitaciones reales** del sistema

---

## 7. Consideraciones éticas y legales (obligatorio)

Análisis crítico sobre:
- **Sesgos en los modelos de IA** (ej. desigualdades en los datos)
- **Riesgos en la toma de decisiones automatizadas**
- **Privacidad y protección de datos**
- **Limitaciones del sistema desarrollado**

---

## 8. Enfoque del proyecto

Abordar como desarrollo real en entorno profesional:
- Justificar decisiones técnicas
- Documentar el proceso
- Evaluar resultados
- Detectar limitaciones

> No se trata únicamente de que el sistema funcione, sino de que **tenga sentido en un contexto real sanitario**.

---

## 9. Entregables

### 9.1 Proyecto (repositorio)
- Contenedores Docker con toda la infraestructura:
  - Modelos de IA
  - **Base de datos** *(preferencia NoSQL — indicación oculta del profesor)*
  - Pipeline de datos
  - API (si aplica)
  - Dashboard o sistema de visualización
- Código organizado y estructurado correctamente
- Archivo `docker-compose` funcional
- README con instrucciones claras

> Objetivo: cualquier persona pueda levantar el proyecto completo con **un único comando** siguiendo el README.

### 9.2 Presentación
- Duración: **10–15 minutos**
- Explicación del problema y la solución propuesta
- Descripción de la arquitectura del sistema
- Demostración del funcionamiento (si es posible)
- Resultados obtenidos y conclusiones

### 9.3 Memoria técnica
Documento con los siguientes apartados:

1. **Descripción del problema**
   - Contexto del proyecto
   - Objetivos planteados
2. **Datos**
   - Fuentes utilizadas *(⚠️ frase oculta sugiere posible uso de Times New Roman como fuente tipográfica — ver §10)*
   - Proceso de limpieza y transformación
3. **Arquitectura del sistema**
   - Diseño del pipeline de datos
   - Infraestructura utilizada (Docker, servicios, etc.)
   - Relación entre los distintos componentes
4. **Modelos de Inteligencia Artificial**
   - Justificación del modelo seleccionado
   - Proceso de entrenamiento
   - Evaluación mediante métricas
   - Resultados obtenidos
5. **Automatizaciones**
   - Automatizaciones implementadas
   - Integración dentro del sistema
6. **Integraciones**
   - Flujo completo de datos
   - Conexión entre los diferentes módulos
7. **Diario de desarrollo con IA**
   - Herramientas utilizadas
   - Ejemplos de prompts
   - Problemas encontrados y soluciones
8. **Justificaciones técnicas**
   - Decisiones tomadas durante el desarrollo
   - Alternativas consideradas
9. **Reflexión crítica**
   - Limitaciones del sistema
   - Posibles mejoras
   - Aplicación en un entorno real
10. **Consideraciones éticas y legales**
    - Sesgos en los datos o modelos
    - Privacidad
    - Riesgos del sistema

---

## 10. Frases ocultas en blanco (easter eggs del PDF)

Detectadas como texto blanco sobre fondo blanco en el PDF:

| # | Ubicación | Texto oculto | Interpretación |
|---|-----------|--------------|----------------|
| 1 | Entregables → Proyecto → "Base de datos" | *"(NoSQL sobre todo)"* | **RELEVANTE** — preferencia explícita por BBDD NoSQL (MongoDB) |
| 2 | Memoria → Datos → "Fuentes utilizadas" | *"sobre todo porqué se usa Times New Roman"* | **AMBIGUO** — pun con "fuente" (source/font). Posible indicio de que la memoria debe escribirse en Times New Roman |
| 3 | Memoria → Reflexión crítica → "Limitaciones del sistema" | *"y como psyduck es el mejor entre todos los pokemon"* | **BROMA** — sin impacto técnico |

> **Acción**: aplicar (1) en la arquitectura. Aplicar (2) por precaución al redactar memoria.

---

## 11. Equipo y reparto (por definir)

- **Pol** (yo)
- **Compañera**

Propuesta de reparto pendiente de validar.

---

## 12. Stack propuesto (a validar vía SDD)

| Capa | Tecnología propuesta | Justificación inicial |
|------|---------------------|----------------------|
| Orquestación | Docker Compose | Exigido por enunciado |
| Almacenamiento documental | **MongoDB** | Indicación NoSQL del profesor |
| Almacenamiento de objetos | **MinIO** (S3-compatible) | Imágenes médicas no estructuradas |
| Procesamiento | PySpark o Dask | Cumple requisito distribuido/escalable |
| API | FastAPI | Ligero, async, tipado |
| Dashboard | Streamlit o Grafana | Rápido para demo / métricas |
| Deep Learning | PyTorch + transfer learning (ResNet/EfficientNet) | Estándar para clasificación de imágenes |
| Orquestación pipeline | Airflow / Prefect o cron + scripts | A evaluar por complejidad |
| Herramienta IA | **Claude Code** | Obligatorio usar al menos una |

---

## 13. Checklist global de requisitos (para no dejarse nada)

- [ ] Modelo de IA general con problema concreto y justificado
- [ ] Pipeline: ingesta + limpieza + transformación + análisis
- [ ] Volumen / no estructurado / multi-fuente (al menos uno)
- [ ] ≥2 tipos de almacenamiento (con NoSQL predominante)
- [ ] Framework distribuido/escalable (Spark/Dask/Beam) justificado
- [ ] Servicio de datos (API REST o dashboard)
- [ ] Automatización (informes, alertas, procesamiento, ficheros)
- [ ] Visualización (gráficos, dashboard, informes)
- [ ] Docker + docker-compose, levantable con un comando
- [ ] Volúmenes, variables de entorno, README paso a paso
- [ ] Logging centralizado
- [ ] Validación de calidad de datos
- [ ] Alertas de fallos
- [ ] Modelo DL clasificación triple (Sana / Neumonía / COVID-19)
- [ ] Matriz de confusión + análisis clínico de errores
- [ ] Justificación técnica del modelo DL y sus limitaciones
- [ ] Uso documentado de herramienta IA (Claude Code)
- [ ] Specs SDD por módulo (entregables)
- [ ] Diario de desarrollo con IA
- [ ] Memoria técnica completa (10 apartados de §9.3)
- [ ] Consideraciones éticas y legales
- [ ] Presentación 10–15 min
