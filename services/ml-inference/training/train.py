from __future__ import annotations

import argparse
import copy
import csv
import json
import random
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

import numpy as np
import torch
from sklearn.metrics import f1_score
from torch.utils.data import DataLoader

from .augment import get_eval_transforms, get_train_transforms
from .dataset import CLASS_TO_IDX, CLASSES, RadiographyDataset
from .model import SUPPORTED_BACKBONES, build_model


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)

    # Reproducibilidad. En GPU puede reducir rendimiento, pero el proyecto usa CPU por defecto.
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


def compute_hash(paths: list[str | Path]) -> str:
    h = sha256()
    for path in paths:
        with open(path, "rb") as f:
            h.update(f.read())
    return h.hexdigest()


def create_version(config: dict[str, Any], dataset_hash: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    payload = json.dumps({"config": config, "dataset_hash": dataset_hash}, sort_keys=True)
    hash8 = sha256(payload.encode("utf-8")).hexdigest()[:8]
    backbone_short = config["backbone"].replace("_", "")
    return f"rx-{backbone_short}-{stamp}-{hash8}"


def train_one_epoch(model, loader, optimizer, criterion, device) -> tuple[float, float]:
    model.train()
    total_loss = 0.0
    all_preds: list[int] = []
    all_labels: list[int] = []

    for images, labels in loader:
        images = images.to(device)
        labels = labels.to(device)

        optimizer.zero_grad(set_to_none=True)
        logits = model(images)
        loss = criterion(logits, labels)
        loss.backward()
        optimizer.step()

        total_loss += loss.item() * images.size(0)
        preds = torch.argmax(logits, dim=1)

        all_preds.extend(preds.detach().cpu().numpy().tolist())
        all_labels.extend(labels.detach().cpu().numpy().tolist())

    avg_loss = total_loss / max(len(loader.dataset), 1)
    f1_macro = f1_score(all_labels, all_preds, average="macro", zero_division=0)
    return avg_loss, float(f1_macro)


def eval_one_epoch(model, loader, criterion, device) -> tuple[float, float]:
    model.eval()
    total_loss = 0.0
    all_preds: list[int] = []
    all_labels: list[int] = []

    with torch.no_grad():
        for images, labels in loader:
            images = images.to(device)
            labels = labels.to(device)

            logits = model(images)
            loss = criterion(logits, labels)

            total_loss += loss.item() * images.size(0)
            preds = torch.argmax(logits, dim=1)

            all_preds.extend(preds.detach().cpu().numpy().tolist())
            all_labels.extend(labels.detach().cpu().numpy().tolist())

    avg_loss = total_loss / max(len(loader.dataset), 1)
    f1_macro = f1_score(all_labels, all_preds, average="macro", zero_division=0)
    return avg_loss, float(f1_macro)


def update_current_pointer(models_root: Path, version: str) -> None:
    current_txt = models_root / "current.txt"
    current_txt.write_text(version, encoding="utf-8")

    symlink_path = models_root / "current"
    try:
        if symlink_path.exists() or symlink_path.is_symlink():
            symlink_path.unlink()
        symlink_path.symlink_to(version)
    except OSError:
        # Windows puede no permitir symlinks. current.txt es el fallback portable.
        pass


def save_history(artifact_dir: Path, history: list[dict[str, Any]]) -> None:
    with open(artifact_dir / "history.json", "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

    if not history:
        return

    with open(artifact_dir / "history.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(history[0].keys()))
        writer.writeheader()
        writer.writerows(history)


def main() -> None:
    parser = argparse.ArgumentParser(description="Entrena modelo DL de radiografías.")
    parser.add_argument("--train-csv", default="data/covid-subset/train.csv")
    parser.add_argument("--val-csv", default="data/covid-subset/val.csv")
    parser.add_argument("--models-root", default="models/radiography")
    parser.add_argument("--backbone", choices=SUPPORTED_BACKBONES, default="efficientnet_b0")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--warmup-epochs", type=int, default=2)
    parser.add_argument("--max-epochs", type=int, default=6)
    parser.add_argument("--lr-warmup", type=float, default=1e-3)
    parser.add_argument("--lr-finetune", type=float, default=1e-4)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--num-workers", type=int, default=0)
    parser.add_argument("--patience", type=int, default=5)
    parser.add_argument("--no-pretrained", action="store_true")
    args = parser.parse_args()

    set_seed(args.seed)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[train] device={device}")
    print(f"[train] backbone={args.backbone}")

    train_tf = get_train_transforms()
    eval_tf = get_eval_transforms()

    train_ds = RadiographyDataset(args.train_csv, transform=train_tf)
    val_ds = RadiographyDataset(args.val_csv, transform=eval_tf)

    train_loader = DataLoader(
        train_ds,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=args.num_workers,
    )
    val_loader = DataLoader(
        val_ds,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.num_workers,
    )

    train_targets = train_ds.data["class_target"].map(CLASS_TO_IDX).astype(int).to_numpy()
    class_counts = np.bincount(train_targets, minlength=len(CLASSES))
    total = class_counts.sum()

    # Pesos inversos por clase para compensar desbalance.
    weights_np = total / np.maximum(len(CLASSES) * class_counts, 1)
    weights = torch.tensor(weights_np, dtype=torch.float32).to(device)

    pretrained = not args.no_pretrained and args.backbone != "simple_cnn"

    config = {
        "img_size": 224,
        "batch_size": args.batch_size,
        "warmup_epochs": args.warmup_epochs,
        "max_epochs": args.max_epochs,
        "lr_warmup": args.lr_warmup,
        "lr_finetune": args.lr_finetune,
        "weight_decay": args.weight_decay,
        "seed": args.seed,
        "backbone": args.backbone,
        "pretrained": pretrained,
        "class_weight": "balanced",
        "train_rows": len(train_ds),
        "val_rows": len(val_ds),
        "classes": CLASSES,
    }

    dataset_hash = compute_hash([args.train_csv, args.val_csv])
    version = create_version(config, dataset_hash)

    models_root = Path(args.models_root)
    artifact_dir = models_root / version
    artifact_dir.mkdir(parents=True, exist_ok=True)

    criterion = torch.nn.CrossEntropyLoss(weight=weights)

    history: list[dict[str, Any]] = []
    best_f1 = -1.0
    best_state: dict[str, torch.Tensor] | None = None
    epochs_without_improve = 0

    # Fase 1: warmup con backbone congelado si aplica.
    model = build_model(
        num_classes=len(CLASSES),
        backbone=args.backbone,
        freeze_backbone=True,
        pretrained=pretrained,
    ).to(device)

    optimizer = torch.optim.AdamW(
        filter(lambda p: p.requires_grad, model.parameters()),
        lr=args.lr_warmup,
        weight_decay=args.weight_decay,
    )

    for epoch in range(args.warmup_epochs):
        train_loss, train_f1 = train_one_epoch(model, train_loader, optimizer, criterion, device)
        val_loss, val_f1 = eval_one_epoch(model, val_loader, criterion, device)

        row = {
            "epoch": epoch + 1,
            "phase": "warmup",
            "train_loss": train_loss,
            "train_f1_macro": train_f1,
            "val_loss": val_loss,
            "val_f1_macro": val_f1,
        }
        history.append(row)

        if val_f1 > best_f1:
            best_f1 = val_f1
            best_state = copy.deepcopy(model.state_dict())
            epochs_without_improve = 0
        else:
            epochs_without_improve += 1

        print(
            f"Warmup {epoch + 1}/{args.warmup_epochs} "
            f"- train_f1={train_f1:.4f} val_f1={val_f1:.4f}"
        )

    # Fase 2: fine-tuning completo.
    if args.max_epochs > args.warmup_epochs:
        model = build_model(
            num_classes=len(CLASSES),
            backbone=args.backbone,
            freeze_backbone=False,
            pretrained=pretrained,
        ).to(device)

        if best_state is not None:
            model.load_state_dict(best_state)

        optimizer = torch.optim.AdamW(
            model.parameters(),
            lr=args.lr_finetune,
            weight_decay=args.weight_decay,
        )
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
            optimizer,
            mode="min",
            factor=0.5,
            patience=2,
        )

        for epoch in range(args.warmup_epochs, args.max_epochs):
            train_loss, train_f1 = train_one_epoch(model, train_loader, optimizer, criterion, device)
            val_loss, val_f1 = eval_one_epoch(model, val_loader, criterion, device)
            scheduler.step(val_loss)

            row = {
                "epoch": epoch + 1,
                "phase": "finetune",
                "train_loss": train_loss,
                "train_f1_macro": train_f1,
                "val_loss": val_loss,
                "val_f1_macro": val_f1,
            }
            history.append(row)

            if val_f1 > best_f1:
                best_f1 = val_f1
                best_state = copy.deepcopy(model.state_dict())
                epochs_without_improve = 0
            else:
                epochs_without_improve += 1

            print(
                f"Epoch {epoch + 1}/{args.max_epochs} "
                f"- train_f1={train_f1:.4f} val_f1={val_f1:.4f}"
            )

            if epochs_without_improve >= args.patience:
                print("Early stopping")
                break

    if best_state is None:
        raise SystemExit("Training failed to produce a valid model state")

    torch.save(
        {
            "state_dict": best_state,
            "backbone": args.backbone,
            "classes": CLASSES,
        },
        artifact_dir / "model.pt",
    )

    metadata = {
        "version": version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "config": config,
        "dataset_hash": dataset_hash,
        "class_names": CLASSES,
        "class_counts_train": {
            cls: int(class_counts[i]) for i, cls in enumerate(CLASSES)
        },
        "best_val_f1_macro": float(best_f1),
    }

    with open(artifact_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    save_history(artifact_dir, history)
    update_current_pointer(models_root, version)

    print(f"Saved model artifact to {artifact_dir}")
    print(f"Best val_f1_macro={best_f1:.4f}")
    print("Run evaluate.py to compute test metrics.")


if __name__ == "__main__":
    main()