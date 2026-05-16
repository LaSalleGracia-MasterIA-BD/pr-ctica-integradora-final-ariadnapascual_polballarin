"""Cross-validation k-fold estratificada del modelo de triaje.

Corre k-fold sobre `train.csv + val.csv` concatenados (el test.csv se reserva
para la evaluación final y nunca entra en cross-validation).

Uso:
    python -m training.cross_validate \
        --data data/synthetic/triage/ \
        --k 5 --seed 42

Imprime F1 macro por fold + media ± std. Persiste `cv_results.json` en el
directorio del dataset para trazabilidad.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import StratifiedKFold

try:
    from .model import CLASSES, build_pipeline, load_dataset, split_features_target
except ImportError:  # ejecución directa
    from model import CLASSES, build_pipeline, load_dataset, split_features_target  # type: ignore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="k-fold cross-validation sobre train+val."
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=Path("data/synthetic/triage/"),
        help="Directorio con train.csv y val.csv",
    )
    parser.add_argument("--k", type=int, default=5, help="Número de folds")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)

    df_train = load_dataset(args.data / "train.csv")
    df_val = load_dataset(args.data / "val.csv")
    df = pd.concat([df_train, df_val], ignore_index=True)
    X, y = split_features_target(df)

    skf = StratifiedKFold(n_splits=args.k, shuffle=True, random_state=args.seed)

    fold_results = []
    print(f"[cv] {args.k}-fold sobre {len(df)} filas (train + val)")
    for fold_idx, (train_ix, val_ix) in enumerate(skf.split(X, y), start=1):
        pipeline = build_pipeline(random_state=args.seed)
        pipeline.fit(X.iloc[train_ix], y.iloc[train_ix])
        y_pred = pipeline.predict(X.iloc[val_ix])
        acc = float(accuracy_score(y.iloc[val_ix], y_pred))
        f1m = float(
            f1_score(y.iloc[val_ix], y_pred, labels=CLASSES, average="macro")
        )
        fold_results.append({"fold": fold_idx, "accuracy": acc, "f1_macro": f1m})
        print(f"[cv] fold {fold_idx}: accuracy={acc:.4f}  f1_macro={f1m:.4f}")

    f1s = np.array([r["f1_macro"] for r in fold_results])
    accs = np.array([r["accuracy"] for r in fold_results])

    summary = {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "k": args.k,
        "seed": args.seed,
        "n_rows_total": len(df),
        "folds": fold_results,
        "f1_macro_mean": float(f1s.mean()),
        "f1_macro_std": float(f1s.std(ddof=1)) if len(f1s) > 1 else 0.0,
        "accuracy_mean": float(accs.mean()),
        "accuracy_std": float(accs.std(ddof=1)) if len(accs) > 1 else 0.0,
    }

    out = args.data / "cv_results.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(
        f"[cv] f1_macro = {summary['f1_macro_mean']:.4f} ± {summary['f1_macro_std']:.4f}  "
        f"accuracy = {summary['accuracy_mean']:.4f} ± {summary['accuracy_std']:.4f}"
    )
    print(f"[cv] Resultados -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
