import os
from typing import Literal

# Configuración del modelo
MODEL_PATH = os.getenv("ML_MODEL_PATH", "/app/models/rx-default/model.pt")
ML_DEVICE = os.getenv("ML_DEVICE", "cpu")
COVID_ALERT_THRESHOLD = float(os.getenv("COVID_ALERT_THRESHOLD", "0.80"))

# Clases del modelo
CLASSES = ["Sana", "Neumonía", "COVID-19"]
CLASS_TO_IDX = {cls: idx for idx, cls in enumerate(CLASSES)}
IDX_TO_CLASS = {idx: cls for idx, cls in enumerate(CLASSES)}

# Configuración de preprocesamiento (ImageNet)
IMG_SIZE = 224
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]

# Configuración de log
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
