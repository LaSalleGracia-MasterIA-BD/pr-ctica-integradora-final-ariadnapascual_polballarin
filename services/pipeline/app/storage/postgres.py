"""Acceso a PostgreSQL (pacientes + ingresos). SDD-03 §3."""
from __future__ import annotations

from typing import Iterable

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.config import get_settings

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(
            get_settings().postgres_url,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
        )
    return _engine


def upsert_pacientes(rows: Iterable[dict]) -> int:
    """`first_wins`: ON CONFLICT (pseudo_id) DO NOTHING. Devuelve filas insertadas."""
    rows = list(rows)
    if not rows:
        return 0
    sql = text(
        """
        INSERT INTO pacientes (
            pseudo_id, edad, sexo, peso_kg, altura_cm,
            fumador, embarazo, enfermedades_cronicas,
            source, ingested_at, processed_by, created_at
        ) VALUES (
            :pseudo_id, :edad, :sexo, :peso_kg, :altura_cm,
            :fumador, :embarazo, :enfermedades_cronicas,
            :source, :ingested_at, :processed_by, now()
        )
        ON CONFLICT (pseudo_id) DO NOTHING
        """
    )
    with get_engine().begin() as conn:
        result = conn.execute(sql, rows)
        return result.rowcount or 0


def insert_ingresos(rows: Iterable[dict]) -> int:
    """Inserta ingresos. Cada ingreso es un episodio nuevo (no hay dedup)."""
    rows = list(rows)
    if not rows:
        return 0
    sql = text(
        """
        INSERT INTO ingresos (
            paciente_pseudo_id, fecha_ingreso, motivo,
            motivo_principal, duracion_sintomas, intensidad_dolor,
            fiebre_subjetiva, dificultad_respiratoria_subjetiva,
            tos, contacto_covid_reciente, hora_envio,
            source, ingested_at, processed_by
        ) VALUES (
            :paciente_pseudo_id, :fecha_ingreso, :motivo,
            :motivo_principal, :duracion_sintomas, :intensidad_dolor,
            :fiebre_subjetiva, :dificultad_respiratoria_subjetiva,
            :tos, :contacto_covid_reciente, :hora_envio,
            :source, :ingested_at, :processed_by
        )
        RETURNING id
        """
    )
    inserted = 0
    with get_engine().begin() as conn:
        for row in rows:
            conn.execute(sql, row)
            inserted += 1
    return inserted


def count_pacientes() -> int:
    with get_engine().begin() as conn:
        res = conn.execute(text("SELECT COUNT(*) FROM pacientes")).scalar()
        return int(res or 0)


def paciente_exists(pseudo_id: str) -> bool:
    with get_engine().begin() as conn:
        res = conn.execute(
            text("SELECT 1 FROM pacientes WHERE pseudo_id = :pid LIMIT 1"),
            {"pid": pseudo_id},
        ).first()
        return res is not None
