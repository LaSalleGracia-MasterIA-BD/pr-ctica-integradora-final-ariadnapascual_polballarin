# SDD-XX — [Nombre del sistema/módulo]

> Plantilla **spec-only** siguiendo la estructura enseñada en el Master (Spec Driven Development). Describe **qué** debe hacer el sistema y **con qué evidencias de corrección**, sin entrar en **cómo** se implementa.
>
> El diseño técnico (arquitectura, componentes, contratos, algoritmos) va en un documento aparte `DESIGN-XX-...md`, no en esta spec. Fases: **Necesidad → Spec → Diseño → Tareas → Código + pruebas**.

---

**Versión:** 0.1
**Fecha:** YYYY-MM-DD
**Autor:** Pol Ballarín
**Estado:** `draft` | `ready-for-design` | `ready-for-implementation` | `implemented`

---

## 1. Contexto y objetivo

Dos párrafos cortos:
- **Contexto**: qué situación de negocio u operación duele y por qué existe este módulo.
- **Objetivo**: qué debe conseguir. Lenguaje observable, sin tecnologías concretas.

## 2. Actores y alcance

### Actores
Quién interactúa con este sistema/módulo (usuarios humanos, sistemas externos, otros módulos internos).

### Dentro del alcance
Qué cubre este documento.

### Fuera del alcance
Qué queda explícitamente **fuera** (evita suposiciones ocultas).

## 3. Requisitos funcionales

Lista enumerada `RF-1, RF-2, ...`. Cada requisito:
- Empieza con "El sistema debe..." (lenguaje observable).
- Describe comportamiento, no implementación.
- Es atómico (un solo verbo de acción por requisito).

Ejemplo:
- **RF-1**: El sistema debe permitir subir una radiografía en formato JPG o PNG de hasta 10 MB.
- **RF-2**: El sistema debe asignar un identificador único a cada radiografía ingresada.

## 4. Requisitos no funcionales

Lista enumerada `RNF-1, RNF-2, ...`. Categorías habituales:
- **Rendimiento**: tiempos de respuesta, throughput.
- **Escalabilidad**: crecimiento esperado.
- **Disponibilidad**: uptime objetivo.
- **Seguridad / privacidad**: control de acceso, cifrado, normativa (LOPD-GDD, HIPAA-like).
- **Mantenibilidad / trazabilidad**: logs, auditoría.
- **Compatibilidad**: navegadores, sistemas operativos, versiones.

Ejemplo:
- **RNF-1**: La predicción de una radiografía debe devolverse en menos de 5 segundos.

## 5. Casos borde / errores

Qué debe pasar cuando las cosas no van bien o llegan valores extremos. Tabla recomendada:

| Caso | Comportamiento esperado |
|------|------------------------|
| Imagen corrupta o formato no soportado | Rechazar con error legible, no guardar |
| Dos usuarios suben la misma imagen simultáneamente | Deduplicar por hash, no duplicar registro |
| ... | ... |

## 6. Criterios de aceptación

Lista verificable. Cada criterio debe poderse comprobar con un comando, un test o una observación concreta. Debe ligarse a uno o más requisitos.

- [ ] **CA-1** (cubre RF-1): subir una radiografía JPG de 3 MB devuelve 200 OK y un `id` en < 2 s.
- [ ] **CA-2** (cubre RF-1, caso borde): subir un `.txt` devuelve 415 Unsupported Media Type.
- [ ] **CA-3** (cubre RNF-1): 50 peticiones concurrentes de predicción con tiempo mediano < 5 s.

## 7. Dudas abiertas

Ambigüedades aún por cerrar. Usar el tag `[NEEDS CLARIFICATION]` del Master.

- **[NEEDS CLARIFICATION]** ¿Pregunta concreta 1?
- **[NEEDS CLARIFICATION]** ¿Pregunta concreta 2?

Cada duda debe resolverse antes de pasar a estado `ready-for-design` — o registrarse una decisión explícita de asumir un valor por defecto.

## 8. Referencias (opcional)

- Enunciado: `Enunciado-Hospital.pdf`, sección §X.Y
- `CONTEXT.md` §X.Y
- SDDs relacionados: SDD-XX
- Diseño asociado: `DESIGN-XX-...md`
- Documentación externa: enlaces
