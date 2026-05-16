from __future__ import annotations

import argparse
import json
from pathlib import Path

CLASSES = ["Sana", "Neumonía", "COVID-19"]


def _top_errors(cm: list[list[int]]) -> list[tuple[str, str, int]]:
    errors: list[tuple[str, str, int]] = []
    for i, real in enumerate(CLASSES):
        for j, pred in enumerate(CLASSES):
            if i == j:
                continue
            count = int(cm[i][j])
            if count > 0:
                errors.append((real, pred, count))
    errors.sort(key=lambda x: x[2], reverse=True)
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", required=True)
    args = parser.parse_args()

    artifact_dir = Path(args.artifact_dir)
    metrics_path = artifact_dir / "metrics.json"
    metadata_path = artifact_dir / "metadata.json"

    if not metrics_path.exists():
        raise SystemExit("metrics.json not found. Run evaluate.py first.")

    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}

    cm = metrics.get("confusion_matrix", [])
    top_errors = _top_errors(cm)

    version = metrics.get("model_version") or metadata.get("version") or artifact_dir.name
    backbone = metrics.get("backbone") or metadata.get("config", {}).get("backbone", "unknown")

    recall_covid = float(metrics.get("recall_covid", 0.0))
    recall_neumonia = float(metrics.get("recall_neumonia", 0.0))
    accuracy = float(metrics.get("accuracy", 0.0))
    f1_macro = float(metrics.get("f1_macro", 0.0))

    lines: list[str] = [
        f"# Análisis crítico del modelo de radiografías `{version}`",
        "",
        "## 1. Resumen técnico",
        "",
        f"- **Backbone**: `{backbone}`",
        f"- **Accuracy**: {accuracy:.4f}",
        f"- **F1 macro**: {f1_macro:.4f}",
        f"- **Recall COVID-19**: {recall_covid:.4f}",
        f"- **Recall Neumonía**: {recall_neumonia:.4f}",
        "",
        "## 2. Errores principales observados",
        "",
    ]

    if top_errors:
        lines += [
            "| # | Clase real | Clase predicha | Casos |",
            "|---|------------|----------------|-------|",
        ]
        for idx, (real, pred, count) in enumerate(top_errors[:5], start=1):
            lines.append(f"| {idx} | {real} | {pred} | {count} |")
    else:
        lines.append("No se detectaron errores fuera de la diagonal en el conjunto de test.")

    lines += [
        "",
        "## 3. Impacto clínico de errores",
        "",
        "### Falso negativo COVID-19",
        "",
        (
            "Una radiografía de COVID-19 clasificada como `Sana` o `Neumonía` tiene "
            "riesgo epidemiológico alto. Puede provocar falta de aislamiento, "
            "exposición del personal sanitario y contagios intrahospitalarios. "
            "Este es uno de los errores más graves del sistema."
        ),
        "",
        "### COVID-19 confundido con neumonía",
        "",
        (
            "El riesgo es medio-alto. Parte del manejo respiratorio puede ser similar, "
            "pero se pierde el componente epidemiológico: aislamiento, trazabilidad de "
            "contactos y protocolos COVID."
        ),
        "",
        "### Neumonía clasificada como sana",
        "",
        (
            "Implica retraso diagnóstico y terapéutico, especialmente problemático en "
            "pacientes vulnerables. Puede retrasar antibiótico, seguimiento o derivación."
        ),
        "",
        "### Sana clasificada como patológica",
        "",
        (
            "Es menos crítico que un falso negativo, pero genera sobrecarga asistencial, "
            "pruebas innecesarias, ansiedad del paciente y coste operativo."
        ),
        "",
        "## 4. Interpretación de sensibilidad",
        "",
    ]

    if recall_covid < 0.85:
        lines.append(
            f"El recall COVID-19 ({recall_covid:.3f}) es insuficiente para uso clínico real. "
            "El modelo puede servir como demostrador académico, pero no como herramienta "
            "autónoma de cribado."
        )
    else:
        lines.append(
            f"El recall COVID-19 ({recall_covid:.3f}) es razonable para un prototipo, "
            "aunque seguiría requiriendo validación clínica externa."
        )

    lines += [
        "",
        "## 5. Limitaciones reales",
        "",
        "- Dataset público con sesgos de adquisición, procedencia y calidad.",
        "- No existe validación externa con datos hospitalarios propios.",
        "- La clase `Neumonía` agrupa `Viral Pneumonia` y `Lung_Opacity`, simplificando una realidad clínica más compleja.",
        "- El modelo puede aprender artefactos del dataset en lugar de patrones radiológicos generalizables.",
        "- El sistema no sustituye criterio médico ni constituye dispositivo médico certificado.",
        "",
        "## 6. Conclusión",
        "",
        (
            "El modelo es válido como módulo académico de Deep Learning integrado en una "
            "infraestructura Big Data hospitalaria. Para producción real harían falta "
            "más datos, validación multicéntrica, revisión radiológica experta, calibración "
            "de probabilidades y certificación regulatoria."
        ),
    ]

    (artifact_dir / "critical_analysis.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved critical_analysis.md to {artifact_dir}")


if __name__ == "__main__":
    main()