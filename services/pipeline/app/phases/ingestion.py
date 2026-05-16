"""Fase 1 — Ingestión.

Lee CSVs desde RawSource, calcula hash de contenido y devuelve un DataFrame.

SDD-02 RF-1, RF-3.
La fase no escribe en PostgreSQL ni MongoDB: solo lee, calcula metadatos y emite evento.
Cuando PIPELINE_PROCESSING_ENGINE=dask, la lectura batch usa Dask DataFrame.
"""
from __future__ import annotations

import io
import logging
import os

import pandas as pd

from app.events import emit_event
from app.phases.scalable_csv import read_csv_with_dask
from app.storage.raw_source import RawSource
from app.utils.hashing import sha256_bytes

logger = logging.getLogger(__name__)


def _processing_engine() -> str:
    """Devuelve el motor de procesamiento configurado para la ingesta batch."""
    return os.getenv("PIPELINE_PROCESSING_ENGINE", "dask").strip().lower()


def ingest_csv(source: RawSource, key: str) -> tuple[pd.DataFrame, dict]:
    """Lee `key` de `source`, calcula hash de contenido y devuelve:

    - DataFrame con las filas y columnas extra `_source_file`, `_content_hash`.
    - Dict con metadatos del fichero: key, size_bytes, content_hash y motor usado.
    """
    with source.open(key) as fh:
        raw = fh.read()

    content_hash = sha256_bytes(raw)
    size_bytes = len(raw)
    engine = _processing_engine()

    try:
        if engine == "dask":
            df = read_csv_with_dask(raw, source_name=key)
        elif engine == "pandas":
            df = pd.read_csv(io.BytesIO(raw), encoding="utf-8")
            df.attrs["processing_engine"] = "pandas"
        else:
            logger.warning(
                "pipeline.unknown_processing_engine_fallback_pandas",
                extra={"engine": engine, "file": key},
            )
            df = pd.read_csv(io.BytesIO(raw), encoding="utf-8")
            df.attrs["processing_engine"] = "pandas"

    except UnicodeDecodeError as exc:
        emit_event(
            "pipeline.file.rejected",
            level="error",
            message=f"Encoding inválido en {key}",
            payload={
                "file": key,
                "reason": "encoding",
                "detail": str(exc),
                "processing_engine": engine,
            },
        )
        raise

    except pd.errors.ParserError as exc:
        emit_event(
            "pipeline.file.rejected",
            level="error",
            message=f"CSV malformado en {key}",
            payload={
                "file": key,
                "reason": "parser",
                "detail": str(exc),
                "processing_engine": engine,
            },
        )
        raise

    except Exception as exc:
        emit_event(
            "pipeline.file.rejected",
            level="error",
            message=f"Error leyendo {key}",
            payload={
                "file": key,
                "reason": "read_error",
                "detail": str(exc),
                "processing_engine": engine,
            },
        )
        raise

    processing_metadata = {
        "processing_engine": df.attrs.get("processing_engine", engine),
        "dask_partitions": df.attrs.get("dask_partitions"),
        "dask_blocksize": df.attrs.get("dask_blocksize"),
        "dask_scheduler": df.attrs.get("dask_scheduler"),
    }

    df = df.assign(_source_file=key, _content_hash=content_hash)

    # assign() puede devolver un nuevo DataFrame. Reinyectamos attrs por seguridad.
    for attr_key, attr_value in processing_metadata.items():
        if attr_value is not None:
            df.attrs[attr_key] = attr_value

    metadata = {
        "key": key,
        "size_bytes": size_bytes,
        "content_hash": content_hash,
        **processing_metadata,
    }

    emit_event(
        "pipeline.file.read",
        message=f"{len(df)} filas leídas de {key}",
        payload={
            "file": key,
            "size_bytes": size_bytes,
            "records_in": len(df),
            **processing_metadata,
        },
    )

    return df, metadata