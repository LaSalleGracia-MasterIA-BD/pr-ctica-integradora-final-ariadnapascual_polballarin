from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import torch
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    precision_recall_fscore_support,
)
from torch.utils.data import DataLoader

from .augment import get_eval_transforms
from .dataset import CLASSES, RadiographyDataset
from .model import build_model


def load_model(artifact_dir: Path, device: torch.device) -> tuple[torch.nn.Module, dict]:
    metadata_path = artifact_dir / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    backbone = metadata.get("config", {}).get("backbone", "efficientnet_b0")

    # pretrained=False para no descargar ImageNet al evaluar.
    model = build_model(
        num_classes=len(CLASSES),
        backbone=backbone,
        freeze_backbone=False,
        pretrained=False,
    )

    checkpoint = torch.load(artifact_dir / "model.pt", map_location=device)
    state_dict = checkpoint.get("state_dict") or checkpoint.get("model_state_dict")

    if state_dict is None:
        raise ValueError("Invalid checkpoint: state_dict not found")

    model.load_state_dict(state_dict)
    model.to(device)
    model.eval()

    return model, metadata


def plot_confusion_matrix(cm: np.ndarray, out_path: Path) -> None:
    plt.figure(figsize=(6, 6))
    plt.imshow(cm, interpolation="nearest", cmap=plt.cm.Blues)
    plt.title("Matriz de confusión — radiografías")
    plt.colorbar()

    tick_marks = np.arange(len(CLASSES))
    plt.xticks(tick_marks, CLASSES, rotation=45, ha="right")
    plt.yticks(tick_marks, CLASSES)
    plt.xlabel("Predicha")
    plt.ylabel("Real")

    thresh = cm.max() / 2.0 if cm.max() > 0 else 0
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            plt.text(
                j,
                i,
                format(cm[i, j], "d"),
                ha="center",
                va="center",
                color="white" if cm[i, j] > thresh else "black",
            )

    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Evalúa modelo DL de radiografías.")
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--test-csv", default="data/covid-subset/test.csv")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--num-workers", type=int, default=0)
    args = parser.parse_args()

    artifact_dir = Path(args.artifact_dir)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    test_tf = get_eval_transforms()
    test_ds = RadiographyDataset(args.test_csv, transform=test_tf)
    test_loader = DataLoader(
        test_ds,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.num_workers,
    )

    model, metadata = load_model(artifact_dir, device)

    all_preds: list[int] = []
    all_labels: list[int] = []

    with torch.no_grad():
        for images, labels in test_loader:
            images = images.to(device)
            logits = model(images)
            preds = torch.argmax(logits, dim=1).cpu().numpy()

            all_preds.extend(preds.tolist())
            all_labels.extend(labels.numpy().tolist())

    labels_order = list(range(len(CLASSES)))
    cm = confusion_matrix(all_labels, all_preds, labels=labels_order)

    accuracy = accuracy_score(all_labels, all_preds)
    precision, recall, f1, support = precision_recall_fscore_support(
        all_labels,
        all_preds,
        labels=labels_order,
        zero_division=0,
    )

    recall_covid = recall[CLASSES.index("COVID-19")]
    recall_neumonia = recall[CLASSES.index("Neumonía")]

    metrics = {
        "model_version": metadata.get("version", artifact_dir.name),
        "backbone": metadata.get("config", {}).get("backbone", "unknown"),
        "accuracy": float(accuracy),
        "f1_macro": float(np.mean(f1)),
        "recall_covid": float(recall_covid),
        "recall_neumonia": float(recall_neumonia),
        "per_class": {
            cls: {
                "precision": float(precision[i]),
                "recall": float(recall[i]),
                "f1": float(f1[i]),
                "support": int(support[i]),
            }
            for i, cls in enumerate(CLASSES)
        },
        "confusion_matrix": cm.tolist(),
        "classes": CLASSES,
        "test_rows": int(len(test_ds)),
    }

    with open(artifact_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)

    plot_confusion_matrix(cm, artifact_dir / "confusion_matrix.png")

    print(f"Saved metrics to {artifact_dir}")
    print(
        f"accuracy={accuracy:.4f} "
        f"f1_macro={np.mean(f1):.4f} "
        f"recall_covid={recall_covid:.4f} "
        f"recall_neumonia={recall_neumonia:.4f}"
    )


if __name__ == "__main__":
    main()