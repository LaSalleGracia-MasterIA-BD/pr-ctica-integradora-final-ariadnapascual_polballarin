"""Configuración de la API leída de variables de entorno."""
from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ApiSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False, extra="ignore")

    api_log_level: str = Field(default="INFO")

    # Archivo de reglas YAML (montado desde el Dockerfile)
    validation_rules_path: Path = Field(default=Path("/app/config/validation_rules.yaml"))


settings = ApiSettings()
