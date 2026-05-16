from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Dict, List

import pandas as pd
from sklearn.model_selection import train_test_split

IMAGE_EXTS = {".png", ".jpg", ".jpeg"}

CLASS_MAPPING = {
    "Normal": "Sana",
    "Viral Pneumonia": "Neumonía",
    "Lung_Opacity": "Neumonía",
    "COVID": "COVID-19",
}

FINAL_CLASSES = ["Sana", "Neumonía", "COVID-19"]


def _collect_files(raw_dir: Path) -> Dict[str, List[Path]]:
    """Recoge solo radiografías desde <clase>/images.

    Importante: se excluyen las carpetas masks porque contienen máscaras de
    segmentación, no radiografías diagnósticas.
    """
    files_by_target: Dict[str, List[Path]] = {cls: [] for cls in FINAL_CLASSES}

    for source_class, target_class in CLASS_MAPPING.items():
        images_dir = raw_dir / source_class / "images"
        if not images_dir.exists():
            print(f"[warn] No existe carpeta images para {source_class}: {images_dir}")
            continue

        for path in images_dir.rglob("*"):
            if path.suffix.lower() in IMAGE_EXTS:
                files_by_target[target_class].append(path)

    return files_by_target


def _sample_files(files: List[Path], limit: int, rng: random.Random) -> List[Path]:
    if limit <= 0:
        return files
    if len(files) <= limit:
        return files
    return rng.sample(files, limit)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", default="data/raw/covid-radiography")
    parser.add_argument("--output-dir", default="data/covid-subset")
    parser.add_argument(
        "--limit-per-class",
        type=int,
        default=1000,
        help="Máximo de imágenes por clase final: Sana, Neumonía, COVID-19. 0 = todas.",
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    raw_dir = Path(args.raw_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rng = random.Random(args.seed)
    files_by_target = _collect_files(raw_dir)

    rows = []
    counts_available = {k: len(v) for k, v in files_by_target.items()}
    counts_used = {}

    for target_class, files in files_by_target.items():
        sampled = _sample_files(files, args.limit_per_class, rng)
        counts_used[target_class] = len(sampled)

        for path in sampled:
            source_class = path.parts[-3] if len(path.parts) >= 3 else "unknown"
            rows.append(
                {
                    "filepath": str(path),
                    "class_original": source_class,
                    "class_target": target_class,
                }
            )

    if not rows:
        raise SystemExit("No images found. Check raw-dir and dataset structure.")

    df = pd.DataFrame(rows)

    # Validación defensiva: no permitir máscaras.
    mask_rows = df[df["filepath"].str.contains(r"[/\\]masks[/\\]", regex=True)]
    if not mask_rows.empty:
        raise SystemExit(
            f"Se han detectado {len(mask_rows)} máscaras en el dataset. "
            "Revisa prepare_data.py."
        )

    train_val, test = train_test_split(
        df,
        test_size=0.15,
        stratify=df["class_target"],
        random_state=args.seed,
    )

    train, val = train_test_split(
        train_val,
        test_size=0.1765,
        stratify=train_val["class_target"],
        random_state=args.seed,
    )

    train_path = output_dir / "train.csv"
    val_path = output_dir / "val.csv"
    test_path = output_dir / "test.csv"

    train.to_csv(train_path, index=False)
    val.to_csv(val_path, index=False)
    test.to_csv(test_path, index=False)

    metadata = {
        "seed": args.seed,
        "limit_per_class": args.limit_per_class,
        "counts_available": counts_available,
        "counts_used": counts_used,
        "counts_final": df["class_target"].value_counts().to_dict(),
        "splits": {
            "train": len(train),
            "val": len(val),
            "test": len(test),
        },
        "class_mapping": CLASS_MAPPING,
        "note": "Solo se usan imágenes dentro de carpetas images/. Se excluyen masks/.",
    }

    with open(output_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    print(f"Saved splits to {output_dir}")
    print("Counts final:", df["class_target"].value_counts().to_dict())


if __name__ == "__main__":
    main()