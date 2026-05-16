"""Abstracción de la fuente de datos crudos (DESIGN-02 §6.1).

Dos implementaciones con el mismo interfaz:
  - `LocalFSSource`: lee de un directorio local (útil para tests y seed).
  - `S3Source`: lee de un bucket S3-compatible (MinIO local o AWS real).
                `endpoint_url` configurable → mismo código para ambos.
"""
from __future__ import annotations

import io
from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO, Iterator

import boto3
from botocore.config import Config as BotoConfig

from app.config import get_settings


class RawSource(ABC):
    """Interfaz común. Devuelve *claves* (paths relativos o S3 keys)."""

    @abstractmethod
    def list_keys(self, prefix: str) -> Iterator[str]: ...

    @abstractmethod
    def open(self, key: str) -> BinaryIO: ...

    @abstractmethod
    def put(self, key: str, data: bytes, content_type: str | None = None) -> None: ...

    @abstractmethod
    def describe(self) -> str: ...


class LocalFSSource(RawSource):
    """Fuente basada en filesystem local. Útil para seeds y tests."""

    def __init__(self, base_path: Path | str) -> None:
        self._base = Path(base_path)
        self._base.mkdir(parents=True, exist_ok=True)

    def list_keys(self, prefix: str) -> Iterator[str]:
        root = self._base / prefix
        if not root.exists():
            return iter([])
        return (
            str(p.relative_to(self._base).as_posix())
            for p in root.rglob("*")
            if p.is_file()
        )

    def open(self, key: str) -> BinaryIO:
        return open(self._base / key, "rb")

    def put(self, key: str, data: bytes, content_type: str | None = None) -> None:
        dst = self._base / key
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)

    def describe(self) -> str:
        return f"local://{self._base.resolve()}"


class S3Source(RawSource):
    """Fuente sobre S3-compatible (MinIO o AWS). Usa boto3 + endpoint_url."""

    def __init__(
        self,
        endpoint_url: str,
        region: str,
        access_key: str,
        secret_key: str,
        bucket: str,
    ) -> None:
        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=BotoConfig(signature_version="s3v4", retries={"max_attempts": 3}),
        )

    def list_keys(self, prefix: str) -> Iterator[str]:
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for obj in page.get("Contents", []) or []:
                yield obj["Key"]

    def open(self, key: str) -> BinaryIO:
        obj = self._client.get_object(Bucket=self._bucket, Key=key)
        body = obj["Body"].read()
        return io.BytesIO(body)

    def put(self, key: str, data: bytes, content_type: str | None = None) -> None:
        extra: dict = {}
        if content_type:
            extra["ContentType"] = content_type
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data, **extra)

    def describe(self) -> str:
        return f"s3://{self._bucket}@{self._client.meta.endpoint_url}"


def make_raw_source(kind: str | None = None) -> RawSource:
    """Factory. `kind` opcional: 's3' | 'local'. Default: 's3'."""
    settings = get_settings()
    if (kind or "s3").lower() == "local":
        return LocalFSSource(settings.data_dir / "raw")
    return S3Source(
        endpoint_url=settings.s3_endpoint,
        region=settings.s3_region,
        access_key=settings.s3_access_key_id,
        secret_key=settings.s3_secret_access_key,
        bucket=settings.s3_bucket_raw,
    )
