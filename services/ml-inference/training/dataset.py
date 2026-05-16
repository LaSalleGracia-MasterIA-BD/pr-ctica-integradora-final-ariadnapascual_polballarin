from typing import Tuple
import pandas as pd
from PIL import Image
from torch.utils.data import Dataset

CLASSES = ["Sana", "Neumonía", "COVID-19"]
CLASS_TO_IDX = {cls: idx for idx, cls in enumerate(CLASSES)}


class RadiographyDataset(Dataset):
    def __init__(self, csv_path: str, transform=None):
        self.data = pd.read_csv(csv_path)
        self.transform = transform

    def __len__(self) -> int:
        return len(self.data)

    def __getitem__(self, idx: int) -> Tuple:
        row = self.data.iloc[idx]
        image = Image.open(row["filepath"]).convert("RGB")
        label = CLASS_TO_IDX[row["class_target"]]
        if self.transform:
            image = self.transform(image)
        return image, label
