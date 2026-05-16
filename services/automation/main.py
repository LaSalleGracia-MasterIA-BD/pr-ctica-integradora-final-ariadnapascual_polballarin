"""Servicio de automatización y alertas operativas.

Responsabilidades:
- Revisar periódicamente eventos de dominio en MongoDB (`system_events`).
- Detectar eventos warning/error recientes.
- Crear alertas deduplicadas en la colección `alerts`.
- Emitir logs técnicos para que Docker/Loki/stdout puedan recogerlos.

Cumple:
- alertas/notificaciones ante fallos de procesamiento
- monitorización básica del pipeline
- automatización operativa
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.collection import Collection


logging.basicConfig(
    level=os.getenv("AUTOMATION_LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] automation: %(message)s",
)
logger = logging.getLogger("automation")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _mongo_uri() -> str:
    user = os.getenv("MONGO_INITDB_ROOT_USERNAME", "admin")
    password = os.getenv("MONGO_INITDB_ROOT_PASSWORD", "change-me")
    host = os.getenv("MONGO_HOST", "mongodb")
    port = os.getenv("MONGO_PORT", "27017")
    return f"mongodb://{user}:{password}@{host}:{port}/?authSource=admin"


def _db_name() -> str:
    return os.getenv("MONGO_DB", "hospital")


def _interval_seconds() -> int:
    return int(os.getenv("AUTOMATION_INTERVAL_SECONDS", "30"))


def _lookback_minutes() -> int:
    return int(os.getenv("AUTOMATION_LOOKBACK_MINUTES", "10"))


def _get_client() -> MongoClient:
    client = MongoClient(_mongo_uri(), serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    return client


def _system_events(db) -> Collection:
    return db["system_events"]


def _alerts(db) -> Collection:
    return db["alerts"]


def _ensure_indexes(db) -> None:
    _alerts(db).create_index([("dedup_key", ASCENDING)], unique=True)
    _alerts(db).create_index([("created_at", DESCENDING)])
    _alerts(db).create_index([("updated_at", DESCENDING)])
    _alerts(db).create_index([("status", ASCENDING)])
    _alerts(db).create_index([("severity", ASCENDING)])
    _alerts(db).create_index([("correlation_id", ASCENDING)])

    _system_events(db).create_index([("timestamp", DESCENDING)])
    _system_events(db).create_index([("level", ASCENDING), ("timestamp", DESCENDING)])
    _system_events(db).create_index([("correlation_id", ASCENDING)])


def _alert_from_event(event_doc: dict[str, Any]) -> dict[str, Any]:
    """Construye el documento base de alerta.

    Importante: NO incluir `updated_at` aquí, porque se actualiza en `$set`.
    Si `updated_at` aparece en `$setOnInsert` y en `$set`, Mongo lanza:
    Updating the path 'updated_at' would create a conflict.
    """
    now = _utcnow()

    correlation_id = event_doc.get("correlation_id", "-")
    event_name = event_doc.get("event", "unknown")
    level = event_doc.get("level", "warning")
    payload = event_doc.get("payload", {}) or {}

    dedup_key = f"{event_name}:{correlation_id}:{level}"

    return {
        "dedup_key": dedup_key,
        "created_at": now,
        "first_seen_at": now,
        "status": "open",
        "severity": "error" if level == "error" else "warning",
        "source_service": event_doc.get("service", "unknown"),
        "source_event": event_name,
        "source_event_id": str(event_doc.get("_id", "")),
        "source_timestamp": event_doc.get("timestamp"),
        "correlation_id": correlation_id,
        "message": event_doc.get("message", ""),
        "payload": payload,
        "notification_channel": "mongo_dashboard",
        "notification_status": "simulated",
    }


def scan_recent_events_once(db) -> dict[str, int]:
    """Escanea eventos recientes y crea alertas deduplicadas."""
    since = _utcnow() - timedelta(minutes=_lookback_minutes())

    cursor = _system_events(db).find(
        {
            "timestamp": {"$gte": since},
            "level": {"$in": ["warning", "error"]},
        }
    ).sort("timestamp", ASCENDING)

    scanned = 0
    inserted = 0
    already_existing = 0

    for event_doc in cursor:
        scanned += 1

        alert = _alert_from_event(event_doc)
        now = _utcnow()

        result = _alerts(db).update_one(
            {"dedup_key": alert["dedup_key"]},
            {
                "$setOnInsert": alert,
                "$set": {
                    "updated_at": now,
                    "last_seen_at": now,
                    "last_message": alert["message"],
                    "last_payload": alert["payload"],
                },
            },
            upsert=True,
        )

        if result.upserted_id:
            inserted += 1
            logger.warning(
                "Nueva alerta creada: %s | %s",
                alert["dedup_key"],
                alert["message"],
            )
        else:
            already_existing += 1

    return {
        "events_scanned": scanned,
        "alerts_inserted": inserted,
        "alerts_existing": already_existing,
    }


def run() -> None:
    logger.info("Automation service iniciado")

    client = _get_client()
    db = client[_db_name()]
    _ensure_indexes(db)

    while True:
        try:
            summary = scan_recent_events_once(db)
            logger.info(
                "Escaneo completado: events_scanned=%s alerts_inserted=%s alerts_existing=%s",
                summary["events_scanned"],
                summary["alerts_inserted"],
                summary["alerts_existing"],
            )
        except Exception:
            logger.exception("Fallo durante el escaneo de alertas")

        time.sleep(_interval_seconds())


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        logger.info("Automation service detenido")