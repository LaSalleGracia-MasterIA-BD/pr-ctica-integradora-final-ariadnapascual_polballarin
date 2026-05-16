"""Generación de `pseudo_id` PAT-NNNNNN con contador atómico en Mongo (DESIGN-03 §5)."""
from __future__ import annotations

from app.storage.mongo import next_sequence


def next_pseudo_id() -> str:
    seq = next_sequence("patient_pseudo_id")
    return f"PAT-{seq:06d}"
