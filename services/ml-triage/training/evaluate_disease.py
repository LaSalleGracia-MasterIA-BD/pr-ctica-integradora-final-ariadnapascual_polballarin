"""Evaluación del modelo de enfermedad sobre el split de test (DESIGN-08b §11).

Uso:
    python -m training.evaluate_disease \
        --artifact models/disease/dis-20260427-a1b2c3d4 \
        --data data/synthetic/triage/

Produce, dentro del artefacto:
  - metrics.json (matriz confusión 11×11, accuracy, precision/recall/F1 por clase,
                  F1 macro y weighted, importancia de features permutation)
  - confusion_matrix.png (con etiquetas rotadas 45º y celdas con conteos)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from sklearn.inspection import permutation_importance  # noqa: E402
from sklearn.metrics import (  # noqa: E402
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
)

try:
    from .disease_rules import DISEASE_CLASSES
    from .model import ALL_FEATURE_COLS, load_dataset, split_features_disease_target
except ImportError:  # ejecución directa
    from disease_rules import DISEASE_CLASSES  # type: ignore
    from model import (  # type: ignore
        ALL_FEATURE_COLS,
        load_dataset,
        split_features_disease_target,
    )


def _plot_confusion(cm: np.ndarray, classes: list[str], out: Path) -> None:
    fig, ax = plt.subplots(figsize=(11, 9))
    im = ax.imshow(cm, interpolation="nearest", cmap="Blues")
    ax.figure.colorbar(im, ax=ax)
    ax.set(
        xticks=np.arange(cm.shape[1]),
        yticks=np.arange(cm.shape[0]),
        xticklabels=classes,
        yticklabels=classes,
        ylabel="Clase real",
        xlabel="Clase predicha",
        title="Matriz de confusión — sospecha de enfermedad (test)",
    )
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    plt.setp(ax.get_yticklabels(), rotation=0)
    thresh = cm.max() / 2.0 if cm.max() > 0 else 0
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            ax.text(
                j,
                i,
                format(cm[i, j], "d"),
                ha="center",
                va="center",
                fontsize=8,
                color="white" if cm[i, j] > thresh else "black",
            )
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evalúa el modelo de enfermedad sobre test."
    )
    parser.add_argument(
        "--artifact",
        type=Path,
        required=True,
        help="Directorio del artefacto (con model.joblib + metadata.json)",
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=Path("data/synthetic/triage/"),
        help="Directorio con test.csv",
    )
    args = parser.parse_args(argv)

    pipeline = joblib.load(args.artifact / "model.joblib")
    df_test = load_dataset(args.data / "test.csv")
    X_test, y_test = split_features_disease_target(df_test)

    y_pred = pipeline.predict(X_test)

    classes = list(DISEASE_CLASSES)
    acc = float(accuracy_score(y_test, y_pred))
    f1_macro = float(f1_score(y_test, y_pred, labels=classes, average="macro"))
    f1_weighted = float(
        f1_score(y_test, y_pred, labels=classes, average="weighted")
    )
    per_class = classification_report(
        y_test, y_pred, labels=classes, output_dict=True, zero_division=0
    )

    cm = confusion_matrix(y_test, y_pred, labels=classes)
    _plot_confusion(cm, classes, args.artifact / "confusion_matrix.png")

    print("[eval-disease] Calculando permutation importance…")
    perm = permutation_importance(
        pipeline, X_test, y_test, n_repeats=5, random_state=42, n_jobs=1
    )
    importances = {
        col: float(mean)
        for col, mean in zip(ALL_FEATURE_COLS, perm.importances_mean)
    }
    importances_sorted = dict(
        sorted(importances.items(), key=lambda kv: kv[1], reverse=True)
    )

    metrics = {
        "accuracy": acc,
        "f1_macro": f1_macro,
        "f1_weighted": f1_weighted,
        "per_class": {
            cls: {
                "precision": float(per_class[cls]["precision"]),
                "recall": float(per_class[cls]["recall"]),
                "f1": float(per_class[cls]["f1-score"]),
                "support": int(per_class[cls]["support"]),
            }
            for cls in classes
        },
        "confusion_matrix": {
            "labels": classes,
            "values": cm.tolist(),
        },
        "feature_importance_permutation": importances_sorted,
        "test_rows": int(len(df_test)),
    }
    with open(args.artifact / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)

    print(
        f"[eval-disease] accuracy={acc:.4f}  f1_macro={f1_macro:.4f}  f1_weighted={f1_weighted:.4f}"
    )
    print(f"[eval-disease] Metrics -> {args.artifact / 'metrics.json'}")
    print(f"[eval-disease] CM png  -> {args.artifact / 'confusion_matrix.png'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
