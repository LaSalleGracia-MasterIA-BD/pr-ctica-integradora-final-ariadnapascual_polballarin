"""Configuración del pipeline leída de variables de entorno (SDD-02 §2 RNF-7)."""
from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Env vars del pipeline. Pydantic valida tipos y lanza error si faltan.

    Las variables siguen el contrato del `.env.example` raíz.
    """

    model_config = SettingsConfigDict(
        env_file=None,       # el compose ya carga .env; en local se puede pasar
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
    )

    # --- PostgreSQL
    postgres_host: str = Field(default="postgres")
    postgres_port: int = Field(default=5432)
    postgres_user: str = Field(default="admin")
    postgres_password: str = Field(default="change-me")
    postgres_db: str = Field(default="hospital")

    # --- MongoDB
    mongo_host: str = Field(default="mongodb")
    mongo_port: int = Field(default=27017)
    mongo_initdb_root_username: str = Field(default="admin")
    mongo_initdb_root_password: str = Field(default="change-me")
    mongo_db: str = Field(default="hospital")
    mongo_gridfs_bucket: str = Field(default="radiographs")

    # --- S3 / MinIO (capa raw — landing zone)
    s3_endpoint: str = Field(default="http://minio:9000")
    s3_region: str = Field(default="us-east-1")
    s3_bucket_raw: str = Field(default="hospital-raw")
    s3_access_key_id: str = Field(default="admin")
    s3_secret_access_key: str = Field(default="change-me")

    # --- Servicio de triaje
    ml_triage_url: str = Field(default="http://ml-triage:8002")

    # --- Paths locales (seed o fallback sin S3)
    data_dir: Path = Field(default=Path("/app/data"))

    # --- Reglas de validación
    validation_rules_path: Path = Field(
        default=Path("/app/config/validation_rules.yaml")
    )

    # --- Logging
    log_level: str = Field(default="INFO")

    # --- Identificador del processed_by del pipeline
    service_name: str = Field(default="pipeline")

    # --- URIs derivadas (helpers) ------------------------------------------

    @property
    def postgres_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def mongo_uri(self) -> str:
        return (
            f"mongodb://{self.mongo_initdb_root_username}:{self.mongo_initdb_root_password}"
            f"@{self.mongo_host}:{self.mongo_port}/?authSource=admin"
        )


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
