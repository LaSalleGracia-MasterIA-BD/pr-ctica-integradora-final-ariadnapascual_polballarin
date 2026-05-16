"""Informe de análisis crítico del modelo de triaje (DESIGN-08 §6.2).

Lee metrics.json del artefacto y produce critical_analysis.md con:
  - Tipo de error más frecuente e impacto clínico.
  - Importancia de `hora_envio` (debe ser baja — variable espuria).
  - Top 5 features más importantes.
  - Limitación fundamental (dataset sintético — circularidad controlada).

Uso:
    python -m training.critical_analysis \
        --artifact models/triage/tri-20260421-a1b2c3d4
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ESPURIOUS_FEATURE = "hora_envio"
ESPURIOUS_WARNING_THRESHOLD = 0.005  # 0.5 % del importancia máxima

CLINICAL_IMPACT = {
    ("Alta", "Media"): (
        "Un paciente urgente fue clasificado como moderado. Retraso potencial "
        "en su atención, con riesgo clínico si se trata de patología tiempo-dependiente."
    ),
    ("Alta", "Baja"): (
        "**Escenario más grave**: paciente urgente clasificado como no urgente. "
        "Riesgo clínico inmediato. Métrica a vigilar especialmente."
    ),
    ("Media", "Alta"): (
        "Paciente moderado clasificado como urgente. Genera carga asistencial "
        "innecesaria pero no riesgo clínico."
    ),
    ("Media", "Baja"): (
        "Paciente moderado clasificado como no urgente. Retraso en atención; "
        "riesgo clínico moderado según evolución."
    ),
    ("Baja", "Alta"): (
        "Paciente no urgente clasificado como urgente. Genera carga asistencial "
        "innecesaria. Sin riesgo clínico directo."
    ),
    ("Baja", "Media"): (
        "Paciente no urgente clasificado como moderado. Mismo efecto que el anterior "
        "con menor sobrecarga."
    ),
}


def _find_top_error(cm: dict) -> tuple[str, str, int]:
    """Devuelve la celda fuera de la diagonal con mayor conteo."""
    labels = cm["labels"]
    values = cm["values"]
    best = ("", "", -1)
    for i, row in enumerate(values):
        for j, v in enumerate(row):
            if i != j and v > best[2]:
                best = (labels[i], labels[j], int(v))
    return best


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Genera el informe crítico.")
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
        print(f"[error] No existe {metrics_path}. Ejecuta evaluate.py antes.", file=sys.stderr)
        return 2

    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    model_version = metadata.get("model_version", "UNKNOWN")

    top_real, top_pred, top_count = _find_top_error(metrics["confusion_matrix"])
    clinical = CLINICAL_IMPACT.get(
        (top_real, top_pred), "Sin descripción específica."
    )

    importance = metrics["feature_importance_permutation"]
    max_imp = max(importance.values()) if importance else 1.0
    espurious_imp = importance.get(ESPURIOUS_FEATURE, 0.0)
    espurious_ratio = espurious_imp / max_imp if max_imp > 0 else 0.0

    top5 = list(importance.items())[:5]

    recall_alta = metrics["per_class"]["Alta"]["recall"]

    md_lines = [
        f"# Análisis crítico — modelo de triaje `{model_version}`",
        "",
        f"**Fecha de evaluación**: {metadata.get('trained_at', 'desconocida')}",
        "",
        "## 1. Resumen de rendimiento",
        "",
        f"- **Accuracy**: {metrics['accuracy']:.4f}",
        f"- **F1 macro**: {metrics['f1_macro']:.4f}",
        f"- **Recall clase Alta**: {recall_alta:.4f} *(métrica clínicamente crítica — falsos negativos de Alta son el peor escenario)*",
        "",
        "## 2. Error más frecuente",
        "",
        (
            f"El error más frecuente en la matriz de confusión es **{top_real} → {top_pred}** "
            f"con **{top_count} casos** sobre {metrics['test_rows']} registros de test."
        ),
        "",
        f"**Impacto clínico**: {clinical}",
        "",
        "## 3. Comportamiento ante la variable espuria",
        "",
        (
            f"`{ESPURIOUS_FEATURE}` es una variable espuria (ver DESIGN-08 §4.3): se genera "
            f"aleatoriamente en el dataset sintético y **no** está presente en ninguna regla "
            f"clínica. Un modelo bien entrenado debería asignarle importancia **muy baja**."
        ),
        "",
        f"- Importancia normalizada de `{ESPURIOUS_FEATURE}`: **{espurious_ratio:.4f}** "
        f"(ratio respecto a la feature más importante).",
    ]
    if espurious_ratio > ESPURIOUS_WARNING_THRESHOLD:
        md_lines += [
            "",
            f"> ⚠️ **Aviso**: `{ESPURIOUS_FEATURE}` tiene importancia superior al umbral "
            f"({ESPURIOUS_WARNING_THRESHOLD:.4f}). Esto sugiere que el generador sintético "
            f"ha introducido alguna correlación accidental con el target. Revisar "
            f"`generate_dataset.py` antes de defender resultados.",
        ]

    md_lines += [
        "",
        "## 4. Top 5 features por importancia (permutation)",
        "",
        "| # | Feature | Importancia (permutation) |",
        "|---|---------|---------------------------|",
    ]
    for i, (feat, imp) in enumerate(top5, start=1):
        md_lines.append(f"| {i} | `{feat}` | {imp:.4f} |")

    md_lines += [
        "",
        "## 5. Limitación fundamental",
        "",
        (
            "El dataset es **sintético** y sus etiquetas vienen de reglas que el propio "
            "equipo ha codificado, más un **10 % de ruido** deliberado (ver "
            "DESIGN-08 §4.4, §4.5). El modelo, por construcción, reproduce esas reglas; "
            "sus métricas **no reflejan utilidad clínica real**."
        ),
        "",
        (
            "Su valor es **pedagógico**: demuestra que el flujo SDD → dataset → entrenamiento "
            "→ evaluación → servicio HTTP funciona end-to-end, con trazabilidad, "
            "reproducibilidad y análisis crítico alineados con el enunciado §3.1 y §7."
        ),
        "",
        (
            "En un despliegue clínico real, este modelo **no sustituye** al juicio del "
            "personal sanitario ni constituye un dispositivo médico validado."
        ),
        "",
    ]

    out = args.artifact / "critical_analysis.md"
    out.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"[analysis] Informe -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
