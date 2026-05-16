"""Fase 2 — Validación. Aplica reglas declarativas desde YAML.

SDD-02 RF-5, RF-6, RNF-10. Separa `(valid_df, rejects_df)`.
Sandbox muy simple para `cross_field_rules`: se evalúan con `eval`
pasando solo el dict de la fila como contexto — sin `__builtins__`.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

logger = logging.getLogger(__name__)


# ---- Carga y validación estructural del YAML -------------------------------

def load_rules(path: Path | str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        rules = yaml.safe_load(f)
    if not isinstance(rules, dict) or "entities" not in rules:
        raise ValueError("YAML de reglas inválido: falta bloque 'entities'")
    return rules


# ---- Aplicación de reglas --------------------------------------------------

def _check_field(value: Any, rule: dict) -> list[str]:
    """Devuelve lista de motivos de violación para un valor dado una sub-regla."""
    motivos: list[str] = []
    nullable = bool(rule.get("nullable", False))
    is_null = value is None or (isinstance(value, float) and pd.isna(value)) or value == ""
    if is_null:
        if not nullable:
            motivos.append("missing_value")
        return motivos

    rtype = rule.get("type")
    if rtype == "int":
        try:
            value = int(value)
        except (TypeError, ValueError):
            return ["type_int"]
        if "min" in rule and value < rule["min"]:
            motivos.append(f"min:{rule['min']}")
        if "max" in rule and value > rule["max"]:
            motivos.append(f"max:{rule['max']}")
    elif rtype == "float":
        try:
            value = float(value)
        except (TypeError, ValueError):
            return ["type_float"]
    elif rtype == "enum":
        if value not in rule.get("values", []):
            motivos.append("enum")
    elif rtype == "string":
        pattern = rule.get("pattern")
        if pattern:
            flags = re.IGNORECASE if rule.get("case_insensitive") else 0
            if re.fullmatch(pattern, str(value), flags=flags) is None:
                motivos.append("pattern")
    return motivos


def _eval_cross(expr: str, row: dict) -> bool:
    """Sandbox muy simple. No incluye __builtins__ ni globals propios."""
    try:
        return bool(eval(expr, {"__builtins__": {}}, dict(row)))
    except Exception:
        return False


def validate_entity(df: pd.DataFrame, entity: str, rules: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Valida `df` contra las reglas de `rules["entities"][entity]`."""
    erules = rules["entities"].get(entity)
    if erules is None:
        raise KeyError(f"Entidad desconocida en reglas: {entity}")

    required = erules.get("required_fields", [])
    field_rules = erules.get("field_rules", {})
    cross_rules = erules.get("cross_field_rules", [])

    reject_records: list[dict] = []
    keep_mask: list[bool] = []

    for idx, row in df.iterrows():
        row_dict = row.to_dict()
        motivos: list[str] = []

        # 1) required fields
        for f in required:
            v = row_dict.get(f)
            is_null = v is None or (isinstance(v, float) and pd.isna(v)) or v == ""
            if is_null:
                motivos.append(f"missing_field:{f}")

        # 2) field rules
        for fname, frule in field_rules.items():
            v = row_dict.get(fname)
            # ya reportado por required si falta; no duplicar
            if f"missing_field:{fname}" in motivos:
                continue
            for m in _check_field(v, frule):
                motivos.append(f"{fname}:{m}")

        # 3) cross_field rules (solo si no hay errores de campo)
        if not motivos:
            for cr in cross_rules:
                severity = cr.get("severity", "error")
                ok = _eval_cross(cr["rule"], row_dict)
                if not ok and severity == "error":
                    motivos.append(f"cross_field:{cr['rule']}")

        if motivos:
            reject_records.append({
                "entity": entity,
                "row_index": int(idx) if not pd.isna(idx) else -1,
                "raw_record": row_dict,
                "reject_reasons": motivos,
                "severity": "error",
            })
            keep_mask.append(False)
        else:
            keep_mask.append(True)

    valid_df = df.loc[keep_mask].reset_index(drop=True)
    rejects_df = pd.DataFrame(reject_records)
    return valid_df, rejects_df


# ---- Deduplicación por clave lógica (first_wins) ---------------------------

def dedup_by_key(df: pd.DataFrame, entity: str, rules: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """`first_wins`: conserva la primera aparición; duplicados a rechazos."""
    erules = rules["entities"].get(entity, {})
    dedup = erules.get("deduplication")
    if not dedup:
        return df.reset_index(drop=True), pd.DataFrame()

    key = dedup["key"]
    if key not in df.columns:
        return df.reset_index(drop=True), pd.DataFrame()

    first_mask = ~df[key].duplicated(keep="first")
    kept = df.loc[first_mask].reset_index(drop=True)
    dup_rows = df.loc[~first_mask]
    if dup_rows.empty:
        return kept, pd.DataFrame()

    rejects = pd.DataFrame([
        {
            "entity": entity,
            "row_index": int(i) if not pd.isna(i) else -1,
            "raw_record": row.to_dict(),
            "reject_reasons": [f"duplicate_key:{key}"],
            "severity": "error",
        }
        for i, row in dup_rows.iterrows()
    ])
    return kept, rejects
