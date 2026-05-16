"""Informe de análisis crítico del modelo de enfermedad (DESIGN-08b §13).

Lee metrics.json del artefacto y produce critical_analysis_disease.md con:
  - Top 5 errores más frecuentes (con 11 clases las celdas individuales son
    pequeñas; el top-5 da contexto suficiente).
  - Importancia de `hora_envio` (espuria — debe ser baja).
  - F1 por clase ordenado, identificando minoritarias problemáticas.
  - Top 5 features más importantes.
  - Limitación fundamental (dataset sintético + desautorización clínica).

Uso:
    python -m training.critical_analysis_disease \
        --artifact models/disease/dis-20260427-a1b2c3d4
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ESPURIOUS_FEATURE = "hora_envio"
ESPURIOUS_WARNING_THRESHOLD = 0.005

# Mapeo etiqueta interna → nombre humano (espejo del dashboard, ver DESIGN-08b §9.2)
DISEASE_LABELS_HUMAN = {
    "gripe_resfriado": "Gripe / resfriado",
    "neumonia_sospecha": "Sospecha de neumonía",
    "covid_sospecha": "Sospecha de COVID-19",
    "asma_epoc_exacerbacion": "Exacerbación asma/EPOC",
    "cardiopatia_aguda_sospecha": "Sospecha cardiopatía aguda",
    "gastroenteritis": "Gastroenteritis",
    "apendicitis_sospecha": "Sospecha de apendicitis",
    "traumatismo": "Traumatismo",
    "cefalea_migrana": "Cefalea / migraña",
    "ictus_sospecha": "Sospecha de ictus",
    "inespecifico": "Cuadro inespecífico",
}


def _top_errors(cm: dict, k: int = 5) -> list[tuple[str, str, int]]:
    """Top-k celdas fuera de la diagonal por conteo descendente."""
    labels = cm["labels"]
    values = cm["values"]
    errors: list[tuple[str, str, int]] = []
    for i, row in enumerate(values):
        for j, v in enumerate(row):
            if i != j and v > 0:
                errors.append((labels[i], labels[j], int(v)))
    errors.sort(key=lambda t: t[2], reverse=True)
    return errors[:k]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Genera el informe crítico del modelo de enfermedad."
    )
    parser.add_argument(
        "--artifact",
        type=Path,
        required=True,
        help="Directorio del artefacto (con metrics.json)",
    )
    args = parser.parse_args(argv)

    metrics_path = args.artifact / "metrics.json"
    metadata_path = args.artifact / "metadata.json"
    if not metrics_path.exists():
        print(
            f"[error] No existe {metrics_path}. Ejecuta evaluate_disease.py antes.",
            file=sys.stderr,
        )
        return 2

    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    model_version = metadata.get("model_version", "UNKNOWN")

    top_errs = _top_errors(metrics["confusion_matrix"], k=5)

    importance = metrics["feature_importance_permutation"]
    max_imp = max(importance.values()) if importance else 1.0
    espurious_imp = importance.get(ESPURIOUS_FEATURE, 0.0)
    espurious_ratio = espurious_imp / max_imp if max_imp > 0 else 0.0

    top5_features = list(importance.items())[:5]

    # F1 por clase ordenado de menor a mayor (las problemáticas arriba)
    per_class_sorted = sorted(
        metrics["per_class"].items(), key=lambda kv: kv[1]["f1"]
    )

    md_lines = [
        f"# Análisis crítico — modelo de enfermedad `{model_version}`",
        "",
        f"**Fecha de evaluación**: {metadata.get('trained_at', 'desconocida')}",
        "",
        "## 1. Resumen de rendimiento",
        "",
        f"- **Accuracy**: {metrics['accuracy']:.4f}",
        f"- **F1 macro**: {metrics['f1_macro']:.4f} *(media simple — sensible al desbalance de clases minoritarias)*",
        f"- **F1 weighted**: {metrics['f1_weighted']:.4f} *(ponderada por soporte — más representativa del rendimiento global)*",
        "",
        "## 2. Top 5 errores más frecuentes",
        "",
        "| # | Real | Predicha | Casos |",
        "|---|------|----------|-------|",
    ]
    for i, (real, pred, count) in enumerate(top_errs, start=1):
        md_lines.append(
            f"| {i} | {DISEASE_LABELS_HUMAN.get(real, real)} | "
            f"{DISEASE_LABELS_HUMAN.get(pred, pred)} | {count} |"
        )

    md_lines += [
        "",
        (
            "Los errores entre clases **clínicamente próximas** (gripe ↔ COVID, "
            "gastroenteritis ↔ apendicitis, cefalea ↔ ictus) son esperables — "
            "reflejan la matriz de proximidad clínica del ruido tipo A "
            "(DESIGN-08b §4.4). Los errores entre clases lejanas (p. ej. "
            "traumatismo → cardiopatia) son señal de problema y requieren "
            "revisión del generador o del entrenamiento."
        ),
        "",
        "## 3. F1 por clase (peor → mejor)",
        "",
        "| Clase | F1 | Precisión | Recall | Soporte |",
        "|-------|----|-----------|--------|---------|",
    ]
    for cls, vals in per_class_sorted:
        md_lines.append(
            f"| {DISEASE_LABELS_HUMAN.get(cls, cls)} | "
            f"{vals['f1']:.3f} | {vals['precision']:.3f} | "
            f"{vals['recall']:.3f} | {vals['support']} |"
        )

    md_lines += [
        "",
        (
            "Las clases minoritarias clínicas (neumonía, asma/EPOC, apendicitis) "
            "tienen soporte bajo — el F1 es ruidoso. `class_weight='balanced'` "
            "compensa parcialmente: trade-off entre recall en minoritarias "
            "(falsos positivos) vs precision en mayoritarias."
        ),
        "",
        "## 4. Comportamiento ante la variable espuria",
        "",
        (
            f"`{ESPURIOUS_FEATURE}` es una variable espuria (DESIGN-08 §4.3): "
            f"se genera aleatoriamente y **no** aparece en ninguna regla del "
            f"generador. Un modelo bien entrenado debe asignarle importancia muy baja."
        ),
        "",
        f"- Importancia normalizada de `{ESPURIOUS_FEATURE}`: **{espurious_ratio:.4f}** "
        f"(ratio respecto a la feature más importante).",
    ]
    if espurious_ratio > ESPURIOUS_WARNING_THRESHOLD:
        md_lines += [
            "",
            f"> **Aviso**: `{ESPURIOUS_FEATURE}` tiene importancia superior al umbral "
            f"({ESPURIOUS_WARNING_THRESHOLD:.4f}). Sospecha de correlación accidental — "
            f"revisar `generate_dataset.py`.",
        ]

    md_lines += [
        "",
        "## 5. Top 5 features por importancia (permutation)",
        "",
        "| # | Feature | Importancia |",
        "|---|---------|-------------|",
    ]
    for i, (feat, imp) in enumerate(top5_features, start=1):
        md_lines.append(f"| {i} | `{feat}` | {imp:.4f} |")

    md_lines += [
        "",
        "## 6. Limitación crítica (obligatoria)",
        "",
        (
            "Las etiquetas de enfermedad son **sintéticas**, generadas por reglas "
            "heurísticas que el equipo ha codificado a mano. El modelo aprende "
            "esas reglas con un 10 % de ruido — **no aprende patrones "
            "epidemiológicos reales**. Su uso clínico real está **explícitamente "
            "desautorizado**: la salida es una sospecha orientativa para apoyo "
            "administrativo (priorización de admisión), nunca un diagnóstico."
        ),
        "",
        (
            "En un sistema real haría falta entrenamiento con historiales clínicos "
            "validados, supervisión médica continua, y certificación regulatoria "
            "(CE, FDA, AEMPS). El valor de este modelo es **pedagógico**: "
            "demuestra el flujo SDD → reglas → dataset → entrenamiento → "
            "evaluación → servicio HTTP con un segundo target sobre el mismo "
            "formulario, alineado con §3.1 (\"predicción de enfermedades\") y §7 "
            "(ética y limitaciones) del enunciado."
        ),
        "",
        "## 7. Desbalance de clases — discusión",
        "",
        (
            "La distribución de `disease_target` es naturalmente desbalanceada: "
            "`asma_epoc_exacerbacion` ~0.8 %, `neumonia_sospecha` ~1.5 % vs "
            "`inespecifico` ~30 % o `gripe_resfriado` ~20 %. Esto refleja "
            "frecuencias plausibles en un servicio de admisión real, no un "
            "defecto del generador (DESIGN-08b §4.3). Compensamos con "
            "`class_weight='balanced'` en el entrenamiento — alternativas "
            "consideradas y descartadas: oversampling SMOTE (introduce muestras "
            "sintéticas no clínicas), inflar artificialmente las features de "
            "entrada (rompe el realismo de la generación)."
        ),
        "",
    ]

    out = args.artifact / "critical_analysis.md"
    out.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"[analysis-disease] Informe -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
