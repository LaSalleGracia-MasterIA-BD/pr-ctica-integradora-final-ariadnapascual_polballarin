from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def _load_artifact_metrics(path: Path) -> dict | None:
    metrics_path = path / "metrics.json"
    metadata_path = path / "metadata.json"

    if not metrics_path.exists() or not metadata_path.exists():
        return None

    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    return {
        "version": metadata.get("version", path.name),
        "backbone": metadata.get("config", {}).get("backbone", metrics.get("backbone", "unknown")),
        "accuracy": metrics.get("accuracy"),
        "f1_macro": metrics.get("f1_macro"),
        "recall_covid": metrics.get("recall_covid"),
        "recall_neumonia": metrics.get("recall_neumonia"),
        "best_val_f1_macro": metadata.get("best_val_f1_macro"),
        "test_rows": metrics.get("test_rows"),
        "artifact_dir": str(path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compara modelos de radiografías.")
    parser.add_argument("--models-root", default="models/radiography")
    parser.add_argument("--output", default="models/radiography/comparison")
    args = parser.parse_args()

    models_root = Path(args.models_root)
    output_root = Path(args.output)
    output_root.mkdir(parents=True, exist_ok=True)

    rows = []
    for path in sorted(models_root.iterdir()):
        if not path.is_dir():
            continue
        if path.name == "current":
            continue
        row = _load_artifact_metrics(path)
        if row:
            rows.append(row)

    if not rows:
        raise SystemExit(f"No artifacts with metrics.json found in {models_root}")

    df = pd.DataFrame(rows)

    # Orden clínico: prioriza F1 macro y recall COVID.
    df = df.sort_values(
        by=["f1_macro", "recall_covid", "accuracy"],
        ascending=False,
    ).reset_index(drop=True)

    csv_path = output_root / "comparison.csv"
    md_path = output_root / "comparison.md"
    json_path = output_root / "comparison.json"

    df.to_csv(csv_path, index=False)
    df.to_json(json_path, orient="records", indent=2, force_ascii=False)

    md_lines = [
        "# Comparación de modelos — radiografías",
        "",
        "| Ranking | Versión | Backbone | Accuracy | F1 macro | Recall COVID | Recall Neumonía |",
        "|---:|---|---|---:|---:|---:|---:|",
    ]

    for i, row in df.iterrows():
        md_lines.append(
            f"| {i + 1} | `{row['version']}` | `{row['backbone']}` | "
            f"{row['accuracy']:.4f} | {row['f1_macro']:.4f} | "
            f"{row['recall_covid']:.4f} | {row['recall_neumonia']:.4f} |"
        )

    md_lines += [
        "",
        "## Criterio de selección",
        "",
        (
            "El modelo no se selecciona solo por accuracy. En contexto hospitalario se "
            "priorizan F1 macro y recall de COVID-19/Neumonía para reducir falsos "
            "negativos clínicamente relevantes."
        ),
    ]

    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    print(df)
    print(f"Saved {csv_path}")
    print(f"Saved {md_path}")
    print(f"Saved {json_path}")


if __name__ == "__main__":
    main()