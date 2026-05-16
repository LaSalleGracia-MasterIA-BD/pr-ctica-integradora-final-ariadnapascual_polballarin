"""Acceso a MongoDB (colecciones de dominio + GridFS). SDD-03 §4."""
from __future__ import annotations

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from app.config import get_settings

_client: MongoClient | None = None


def get_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(get_settings().mongo_uri, tz_aware=True)
    return _client


def get_db() -> Database:
    return get_client()[get_settings().mongo_db]


# ---- Colecciones del dominio -----------------------------------------------

def predictions_triage() -> Collection:
    return get_db()["predictions_triage"]


def predictions_disease() -> Collection:
    """Sospecha de enfermedad (DESIGN-08b §8.4)."""
    return get_db()["predictions_disease"]


def predictions_radiography() -> Collection:
    return get_db()["predictions_radiography"]


def alerts() -> Collection:
    return get_db()["alerts"]


def system_events() -> Collection:
    return get_db()["system_events"]


def ingestion_rejects() -> Collection:
    return get_db()["ingestion_rejects"]


def reports() -> Collection:
    return get_db()["reports"]


def counters() -> Collection:
    return get_db()["counters"]


def aggregates_daily() -> Collection:
    return get_db()["aggregates_daily"]


# ---- Helpers ---------------------------------------------------------------

def next_sequence(name: str) -> int:
    """Contador atómico por `_id` (SDD-03 §5)."""
    doc = counters().find_one_and_update(
        {"_id": name},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True,
    )
    # `return_document=True` devuelve el doc después del incremento.
    return int(doc["seq"])
