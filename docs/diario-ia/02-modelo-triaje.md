# 02 — Modelo de triaje tabular (SDD-08)

## Contexto

El enunciado pide **dos modelos de IA**: uno general (§3.1, puede ser tabular) y otro de Deep Learning para radiografías (§6). Inicialmente asumí que el ETL iría acoplado al modelo de radiografías, pero el razonamiento con la IA descartó esa idea: la clasificación de pacientes es tabular, usa datos que el ETL sí puede generar/procesar, y el formulario web es el punto natural de entrada. Nació así el **SDD-08 — Modelo de triaje**.

## Prompts clave

> A ver, el etl va de la mano del modelo de IA, ya que escogeremos el de clasificacion de pacientes, que hay que hacer primero? el etl o el modelo que clasificará?

*Pregunta de dependencias. La IA respondió con un análisis preciso: si el modelo se entrena con dataset externo (Kaggle), puede ir en paralelo; si se entrena con datos del ETL, el ETL va primero. También señaló que **el enunciado pide dos modelos distintos** — yo no lo había leído así de claro hasta ese intercambio.*

> Si el enunciado pide dos modelos separados, uno para el etl que será el de clasificacion de pacientes y otro de radiografias que se hará al final pues eso

*Decisión tomada: dos modelos. La IA inmediatamente advirtió de un problema — si entrenamos con datos sintéticos generados por nosotros, el modelo aprende las reglas que nosotros mismos hemos codificado. Propuso tres vías: ruido fuerte + variables espurias, dataset público, o usar las etiquetas del dataset Kaggle.*

> Hay que hacer clasificacion de pacientes, eso significa el triaje no?

*Clarificación conceptual importante. La IA explicó la diferencia (triaje = priorización por gravedad, clasificación = término amplio) y propuso usar triaje porque es clínicamente realista y defendible. Propuso 3 niveles (Alta / Media / Baja) en vez de los 5 de ESI / Manchester por simplicidad.*

> Claro es triaje, generaremos un dataset con muchos ejemplos y el modelo entrenará con eso, luego tendremos un formulario en el dashboard para ingresar "fichas de clientes" es decir, como si un cliente entrara a la web del hospital y se registrara para recibir una visita medica.

*Aterriza el caso de uso: **triaje pre-consulta web**. La IA propuso 15 features (edad, sexo, peso, altura, enfermedades crónicas, fumador, embarazo, motivo, duración, dolor 0-10, fiebre subjetiva, dificultad respiratoria, tos, contacto COVID, hora_envio como **variable espuria intencional**).* 

> Lo de constantes vitales no tiene sentido, la gente no sabe esto. Que otros campos podriamos meter?

*Crítica muy buena del usuario. La IA había propuesto frecuencia cardiaca, tensión arterial, SatO₂ — cosas que solo una enfermera mide. Tras la corrección, reemplazó por **síntomas subjetivos auto-reportados**: fiebre subjetiva (no/leve/alta), dificultad respiratoria (no/leve/moderada/grave), intensidad de dolor 0-10 auto-reportada. Mucho más realista para un formulario web de pre-consulta.*

> Quiero 100k no 10k, así el modelo será mejor; Que modelo usaremos? Cual es el que mejor puede ir?

*Aviso honesto de la IA: con dataset sintético + reglas deterministas + 10% de ruido, el techo de accuracy lo fija el ruido, no el volumen. De 10k a 100k la diferencia en F1 macro era < 1pp. Dejé 10k. Para el modelo: `HistGradientBoostingClassifier` de sklearn (mismo rendimiento que XGBoost/LightGBM pero sin dependencias extras, maneja nulos y categóricos nativamente).* 

> Dale pues 10k entonces, Ok el modelo ese

## Lo que produjo la IA

1. **SDD-08** (21 RF + 11 RNF + 14 casos borde + 14 CA + 6 dudas).
2. **DESIGN-08** con reglas clínicas concretas del generador (13 reglas Alta/Media/Baja, distribuciones por feature, 10% ruido = 5% etiqueta adyacente + 5% síntomas contradictorios, splits 70/15/15).
3. **Implementación completa** en `services/ml-triage/`:
   - `training/rules.py` — reglas clínicas como funciones puras.
   - `training/generate_dataset.py` — CLI reproducible con semilla.
   - `training/model.py` — pipeline sklearn (ColumnTransformer + HistGB) + constantes compartidas.
   - `training/train.py`, `evaluate.py`, `critical_analysis.py`, `cross_validate.py` — cada paso del ciclo ML como CLI independiente.
   - `app/schemas.py`, `app/predictor.py`, `app/app.py` — servicio FastAPI real (reemplazando el stub aleatorio de Ariadna).
4. **Métricas reproducibles**: accuracy 0.9133, F1 macro 0.8961, **recall de la clase Alta 0.8345** (métrica clínica crítica). 5-fold CV: 0.8994 ± 0.0083 (bajísima varianza).
5. **Verificación del "no-trampa"**: la importancia (permutation) de `hora_envio` (la variable espuria) quedó en **-0.0115** — el modelo la ignora, como diseñamos.

## Aciertos

- La IA **se opuso explícitamente** a inflar el dataset a 100k cuando no mejoraba nada. Me enseñó que "más datos" no siempre es la respuesta en sintético.
- Extraer el contrato de features a `app/features.py` (compartido entre `training/` y `app/`) para evitar divergencias entre "formato de entreno" y "formato de inferencia" fue un acierto que me ahorró bugs.
- El informe crítico de `critical_analysis.py` **detecta automáticamente** si `hora_envio` acaba con importancia alta y emite aviso — auto-validación del propio modelo.

## Correcciones que hubo que hacer

- **La propuesta inicial de features tenía constantes vitales**. Tras mi corrección, eliminadas las variables que un paciente no conoce de sí mismo. Antes de pulir, habría producido un formulario inservible en un portal hospitalario real.
- **Target inicial propuesto**: "patología probable Sana/Neumonía/COVID-19" (simétrico con el modelo DL). Yo redirigí a triaje porque es clínicamente más defendible sin radiografía. La IA aceptó y lo apuntó en memoria.
- **Prints con carácter `→`** fallaron en Windows cp1252. Sustituidos por `->`.
- **YAML interpretaba `no` sin comillas como bool False**. Bug descubierto en el primer smoke test del ETL; fix con quoting explícito en los enums del `validation_rules.yaml` (no afectaba al modelo pero sí al pipeline que lo usa).

## Lecciones

1. **Los datos sintéticos son una herramienta pedagógica, no un sustituto de datos reales**. La IA lo dijo al inicio y lo documentó en el `critical_analysis.md` — sin ese aviso explícito, un lector podría confundir "accuracy 0.91" con "valor clínico".
2. **Confrontar a la IA sobre decisiones de producto** (constantes vitales → síntomas auto-reportados) salió bien: respondió razonadamente y corrigió en dos mensajes. Es fundamental: ella tiene conocimiento técnico, pero el contexto de usuario lo traigo yo.
3. **Replicar distribuciones estadísticas en código** (mezcla de edades, geometría truncada para dolor, multi-selección independiente de enfermedades crónicas) produjo un dataset que no es trivial pero tampoco aleatorio. El modelo aprendió patrones razonables.

## Commits afectados

- `b835d4b` — DESIGN-08: diseño técnico del modelo de triaje
- `85afb61` — feat(triage): generador + entreno + k-fold
- `b837e76` — feat(triage): servicio HTTP ml-triage con predictor real
