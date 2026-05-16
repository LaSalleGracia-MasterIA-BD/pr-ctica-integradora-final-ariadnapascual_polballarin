# SDD-09 — Consideraciones éticas, legales y limitaciones del sistema

## 1. Contexto

El proyecto simula un sistema hospitalario de soporte a la decisión clínica basado en datos estructurados, síntomas auto-reportados, modelos tabulares y un módulo de Deep Learning para clasificación de radiografías de tórax.

Aunque el sistema es académico y no se despliega en un entorno sanitario real, trabaja con un dominio especialmente sensible: salud, enfermedad, triaje, predicciones clínicas y potenciales imágenes médicas. Por ello, no basta con que el sistema funcione técnicamente. Es necesario analizar riesgos de sesgo, privacidad, automatización, explicabilidad y uso responsable.

En un escenario real europeo, los datos de salud se consideran categorías especiales de datos personales y tienen protección reforzada. Además, los sistemas de IA usados en sanidad pueden entrar en marcos regulatorios exigentes cuando influyen en seguridad, diagnóstico o decisiones clínicas. :contentReference[oaicite:0]{index=0}

---

## 2. Principio general: sistema de apoyo, no diagnóstico autónomo

El sistema desarrollado no debe interpretarse como un médico automático ni como un dispositivo médico certificado.

Su función correcta es:

- priorizar casos;
- apoyar al personal sanitario;
- detectar patrones de riesgo;
- organizar información clínica;
- mostrar alertas;
- ayudar a explorar datos.

No debe:

- sustituir el juicio clínico;
- emitir diagnósticos definitivos;
- decidir altas médicas automáticamente;
- negar atención sanitaria;
- tomar decisiones sin supervisión humana.

Por tanto, todas las predicciones del sistema deben mostrarse como **apoyo a la decisión**, no como decisión final.

---

## 3. Sesgos en los modelos de IA

### 3.1. Sesgos del dataset de radiografías

El módulo `ml-inference` utiliza el dataset público `COVID-19_Radiography_Dataset`. Aunque es útil para aprendizaje y prototipado, tiene limitaciones claras:

- puede no representar todos los hospitales;
- puede contener imágenes tomadas con equipos distintos;
- puede tener sesgos de país, edad, gravedad o procedencia;
- puede contener patrones técnicos no clínicos;
- puede no representar variantes actuales de COVID-19;
- puede no incluir suficientes casos pediátricos, geriátricos o pacientes con comorbilidades.

Esto implica que un buen resultado en test no garantiza buen comportamiento en un hospital real.

### 3.2. Sesgos por clase

El reto académico exige tres clases:

- Sana;
- Neumonía;
- COVID-19.

Para adaptarlo al dataset original se agrupan:

- `Viral Pneumonia` → `Neumonía`;
- `Lung_Opacity` → `Neumonía`.

Esta decisión simplifica el problema, pero también introduce una limitación: una opacidad pulmonar no equivale siempre a neumonía. En un entorno real, esta simplificación podría ocultar otras patologías.

### 3.3. Sesgos en el modelo tabular de triaje

El modelo de triaje trabaja con datos sintéticos o auto-reportados:

- edad;
- sexo;
- enfermedades crónicas;
- motivo principal;
- duración de síntomas;
- intensidad del dolor;
- fiebre subjetiva;
- dificultad respiratoria subjetiva;
- tos;
- contacto COVID.

Estos campos pueden tener sesgos porque dependen de cómo el paciente interpreta sus síntomas. Dos pacientes con la misma patología pueden reportar dolor, fiebre o dificultad respiratoria de forma distinta.

También hay riesgo de sesgo si ciertos grupos están peor representados:

- personas mayores;
- personas embarazadas;
- pacientes con enfermedades crónicas;
- pacientes con baja alfabetización sanitaria;
- pacientes que no describen bien sus síntomas;
- personas que no dominan el idioma del formulario.

### 3.4. Mitigación aplicada

En el proyecto se han aplicado varias medidas:

- uso de clases balanceadas en radiografías;
- separación train/val/test estratificada;
- comparación de varios modelos;
- métricas por clase, no solo accuracy;
- revisión de `recall_covid` y `recall_neumonia`;
- análisis de matriz de confusión;
- aviso de baja confianza;
- documentación de limitaciones;
- supervisión humana como requisito.

Aun así, estas medidas reducen el riesgo, pero no lo eliminan.

---

## 4. Riesgos en la toma de decisiones automatizadas

### 4.1. Riesgo de automatización excesiva

Un riesgo importante es que el usuario confíe demasiado en el modelo porque el sistema muestra porcentajes, colores y alertas. Esto se conoce como sesgo de automatización.

Ejemplo:

```text
El modelo predice "Baja" con 82%.
El personal puede relajarse y no revisar adecuadamente el caso.

En sanidad, este comportamiento es peligroso. Un porcentaje alto no equivale a certeza clínica.

4.2. Falsos negativos

Los falsos negativos son especialmente graves.

COVID-19 clasificado como Sana

Riesgos:

no aislar al paciente;
contagio intrahospitalario;
exposición de otros pacientes;
exposición del personal sanitario;
falsa sensación de seguridad.
Neumonía clasificada como Sana

Riesgos:

retraso terapéutico;
empeoramiento respiratorio;
alta incorrecta;
falta de seguimiento.
Triaje Alta clasificado como Media o Baja

Riesgos:

demora asistencial;
infrapriorización;
empeoramiento durante la espera.
4.3. Falsos positivos

Los falsos positivos también tienen impacto.

Sana clasificada como COVID-19

Riesgos:

aislamiento innecesario;
ansiedad del paciente;
uso innecesario de recursos;
pruebas adicionales.
Sana clasificada como Neumonía

Riesgos:

pruebas innecesarias;
posible tratamiento no indicado;
sobrecarga del sistema.
4.4. Decisión adoptada

El sistema no toma decisiones finales. Presenta:

clase predicha;
probabilidades;
baja confianza;
alertas;
explicación textual;
análisis clínico de errores.

La decisión final debe corresponder siempre a personal sanitario.

5. Privacidad y protección de datos
5.1. Naturaleza de los datos

El proyecto trabaja con datos de salud simulados o públicos. En un entorno real, estos datos serían especialmente sensibles:

síntomas;
antecedentes;
enfermedades crónicas;
resultados de modelos;
radiografías;
identificadores de paciente;
eventos clínicos.

Bajo el RGPD, los datos relativos a salud son una categoría especial de datos personales, con restricciones adicionales para su tratamiento.

5.2. Pseudonimización

El sistema usa pseudo_id en lugar de identificadores reales directos.

Ejemplo:

PAT-000401

Esto reduce exposición, pero no convierte automáticamente los datos en anónimos. Si existe una tabla, sistema externo o correlación que permita reidentificar al paciente, sigue existiendo riesgo de dato personal.

5.3. Minimización

El sistema debe almacenar solo los datos necesarios.

Medidas aplicadas o recomendadas:

no guardar DNI, nombre completo ni teléfono;
usar identificadores pseudónimos;
separar datos raw, datos procesados y predicciones;
no subir datasets clínicos reales al repositorio;
excluir .env del control de versiones;
excluir imágenes pesadas y datos privados mediante .gitignore;
evitar logs con datos personales innecesarios.
5.4. Seguridad de credenciales

Las credenciales se gestionan mediante .env.

El archivo .env no debe versionarse.

Sí se puede versionar:

.env.example

pero sin secretos reales.

5.5. Logs

El sistema usa logging centralizado con Loki/Promtail y eventos de dominio en MongoDB. Esto es útil para auditoría, pero también genera riesgo si se registran datos sensibles.

Criterios aplicados:

registrar eventos técnicos;
registrar contadores;
registrar correlation_id;
evitar datos clínicos completos en logs de stdout;
persistir rechazos en MongoDB para trazabilidad;
evitar mostrar información personal innecesaria.
5.6. Evaluación de impacto

En un entorno real, un sistema así requeriría una evaluación formal de impacto en protección de datos, auditoría del tratamiento y revisión de riesgos para derechos y libertades. La AEPD recomienda auditar tratamientos que incorporan IA teniendo en cuenta naturaleza, contexto, finalidad y riesgos del tratamiento, no solo el algoritmo aislado.

6. Transparencia y explicabilidad
6.1. Qué explica el sistema

El sistema muestra:

clase predicha;
probabilidades por clase;
versión del modelo;
tiempo de inferencia;
baja confianza;
alerta COVID;
matriz de confusión;
análisis crítico por modelo;
métricas por clase.

Esto permite entender parcialmente el comportamiento del modelo.

6.2. Qué no explica

El modelo de radiografías no explica visualmente qué zonas de la imagen han influido en la decisión. No se ha implementado Grad-CAM ni mapas de calor.

Limitación:

El sistema dice qué clase predice, pero no justifica visualmente qué patrón radiológico ha usado.

En un sistema clínico real, sería recomendable añadir:

Grad-CAM;
revisión por radiólogo;
explicación visual;
validación externa;
comparación con informes clínicos reales.
7. Limitaciones del sistema desarrollado
7.1. Limitaciones técnicas
Entrenamiento en CPU, con restricciones de tiempo.
Dataset público, no hospitalario local.
Modelo no validado externamente.
No hay calibración formal de probabilidades.
No hay evaluación por subgrupos demográficos.
No hay trazabilidad clínica real.
No hay integración con HIS/RIS/PACS real.
No hay firma digital ni trazabilidad legal de informes médicos.
7.2. Limitaciones clínicas
No sustituye al médico.
No sustituye al radiólogo.
No detecta todas las patologías torácicas.
Clasifica solo tres categorías.
Agrupa Lung_Opacity dentro de Neumonía.
Puede fallar ante imágenes de mala calidad.
Puede fallar ante pacientes fuera de distribución.
7.3. Limitaciones legales
No es un producto sanitario certificado.
No tiene marcado CE.
No ha pasado validación clínica.
No se ha realizado una evaluación formal de impacto.
No se ha desplegado con medidas completas de seguridad hospitalaria.
No debe usarse en producción real.
8. Relación con normativa de IA

El proyecto es académico, pero un sistema de IA aplicado a sanidad puede ser considerado de alto riesgo si afecta a seguridad, derechos fundamentales o decisiones clínicas. La Comisión Europea describe el AI Act como un marco basado en riesgos y señala que, junto con la regulación de productos sanitarios, proporciona un marco para el despliegue seguro y ético de IA en salud.

Por tanto, si este proyecto evolucionara a producto real, deberían añadirse:

gestión formal de riesgos;
documentación técnica completa;
trazabilidad de datos;
evaluación clínica;
supervisión humana;
monitorización post-despliegue;
ciberseguridad;
control de versiones de modelos;
registro de incidentes;
auditorías periódicas.
9. Medidas concretas aplicadas en el proyecto
Riesgo	Medida aplicada
Subir datos sanitarios o datasets pesados a Git	.gitignore excluye dataset, .env, datos generados y pesos .pt
Reidentificación directa	Uso de pseudo_id
Falta de trazabilidad	correlation_id, system_events, logs centralizados
Fallos silenciosos	Healthchecks y eventos de pipeline
Rechazos de calidad no visibles	ingestion_rejects en MongoDB
Eventos anómalos sin alerta	Servicio automation genera documentos en alerts
Métrica única engañosa	Evaluación con F1 macro, recall COVID, recall Neumonía y matriz de confusión
Selección arbitraria de modelo	Comparación CNN simple vs ResNet18 vs EfficientNet-B0
Uso acrítico del resultado	Avisos de baja confianza y apoyo a decisión
Opacidad del entrenamiento	metadata.json, metrics.json, critical_analysis.md
10. Reflexión crítica final

El sistema tiene sentido como prototipo académico de infraestructura Big Data e IA aplicada a sanidad. Integra ingesta, almacenamiento, procesamiento, modelos, API, dashboard, monitorización, validación y alertas.

Sin embargo, su uso real requeriría una fase muy superior de validación. En sanidad, un modelo con buen rendimiento estadístico puede seguir siendo peligroso si falla en poblaciones concretas, si no está calibrado, si no se monitoriza o si el personal lo interpreta como diagnóstico automático.

El resultado debe leerse como:

Sistema de apoyo y priorización, no sistema autónomo de diagnóstico.

La principal decisión ética del proyecto es mantener siempre al profesional sanitario como responsable final de la decisión.