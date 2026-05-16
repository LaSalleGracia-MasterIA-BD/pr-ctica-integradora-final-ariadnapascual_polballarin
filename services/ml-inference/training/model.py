from __future__ import annotations

import torch
import torch.nn as nn
from torchvision.models import (
    efficientnet_b0,
    EfficientNet_B0_Weights,
    resnet18,
    ResNet18_Weights,
)


SUPPORTED_BACKBONES = ("simple_cnn", "resnet18", "efficientnet_b0")


class SimpleCNN(nn.Module):
    """CNN baseline pequeña entrenada desde cero.

    Sirve como baseline académico para comparar contra transfer learning.
    No está pensada como modelo clínico final.
    """

    def __init__(self, num_classes: int = 3) -> None:
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(3, 32, kernel_size=3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),  # 112x112

            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),  # 56x56

            nn.Conv2d(64, 128, kernel_size=3, padding=1),
            nn.BatchNorm2d(128),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),  # 28x28

            nn.Conv2d(128, 256, kernel_size=3, padding=1),
            nn.BatchNorm2d(256),
            nn.ReLU(inplace=True),
            nn.AdaptiveAvgPool2d((1, 1)),
        )
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Dropout(p=0.30),
            nn.Linear(256, num_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.features(x)
        return self.classifier(x)


def _freeze_except(module: nn.Module, trainable_names: tuple[str, ...]) -> None:
    for name, param in module.named_parameters():
        param.requires_grad = any(name.startswith(prefix) for prefix in trainable_names)


def build_model(
    num_classes: int = 3,
    backbone: str = "efficientnet_b0",
    freeze_backbone: bool = False,
    pretrained: bool = True,
) -> nn.Module:
    """Construye el modelo solicitado.

    Args:
        num_classes: número de clases finales.
        backbone: simple_cnn | resnet18 | efficientnet_b0.
        freeze_backbone: congela extractor salvo cabeza final.
        pretrained: usa pesos ImageNet para ResNet/EfficientNet.
    """
    backbone = backbone.lower().strip()

    if backbone not in SUPPORTED_BACKBONES:
        raise ValueError(
            f"Backbone no soportado: {backbone}. "
            f"Opciones: {', '.join(SUPPORTED_BACKBONES)}"
        )

    if backbone == "simple_cnn":
        return SimpleCNN(num_classes=num_classes)

    if backbone == "resnet18":
        weights = ResNet18_Weights.IMAGENET1K_V1 if pretrained else None
        model = resnet18(weights=weights)
        in_features = model.fc.in_features
        model.fc = nn.Linear(in_features, num_classes)

        if freeze_backbone:
            _freeze_except(model, trainable_names=("fc",))

        return model

    if backbone == "efficientnet_b0":
        weights = EfficientNet_B0_Weights.IMAGENET1K_V1 if pretrained else None
        model = efficientnet_b0(weights=weights)
        in_features = model.classifier[1].in_features
        model.classifier[1] = nn.Linear(in_features, num_classes)

        if freeze_backbone:
            for param in model.features.parameters():
                param.requires_grad = False

        return model

    raise AssertionError("Backbone unreachable")