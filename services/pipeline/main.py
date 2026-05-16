"""CLI del pipeline (SDD-02 §13).

Uso:
    python main.py batch --key patients/seed-XXX.csv
    python main.py batch --key patients/seed-XXX.csv --no-triage
    python main.py batch-all --prefix patients/
    python main.py seed --n 100
    python main.py version
"""
from __future__ import annotations

import argparse
import json
import sys

from app.config import get_settings
from app.logging_setup import setup_logging
from app.orchestrator import run_batch
from app.phases.validation import load_rules
from app.storage.raw_source import make_raw_source


def cmd_version(_: argparse.Namespace) -> int:
    print("pipeline 1.0.0")
    return 0


def cmd_batch(args: argparse.Namespace) -> int:
    settings = get_settings()
    rules = load_rules(settings.validation_rules_path)
    source = make_raw_source(args.source)
    summary = run_batch(
        source=source,
        key=args.key,
        rules=rules,
        apply_triage=(not args.no_triage),
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
    return 0


def cmd_batch_all(args: argparse.Namespace) -> int:
    settings = get_settings()
    rules = load_rules(settings.validation_rules_path)
    source = make_raw_source(args.source)
    processed = 0
    failures = 0
    for key in source.list_keys(args.prefix):
        if not key.endswith(".csv"):
            continue
        try:
            run_batch(
                source=source,
                key=key,
                rules=rules,
                apply_triage=(not args.no_triage),
            )
            processed += 1
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"[warn] fallo procesando {key}: {exc}", file=sys.stderr)
    print(json.dumps({"processed": processed, "failures": failures}, indent=2))
    return 0


def cmd_seed(args: argparse.Namespace) -> int:
    from seed.generate_fichas import generate_and_upload

    summary = generate_and_upload(n=args.n, seed=args.seed, source_kind=args.source)
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Pipeline ETL Hospital laSalle")
    p.add_argument(
        "--source",
        choices=["s3", "local"],
        default="s3",
        help="Fuente de datos crudos (default: s3 = MinIO/AWS segun .env)",
    )

    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("batch", help="Procesa un CSV concreto por key")
    sp.add_argument("--key", required=True, help="Clave S3 o path local relativo (p.ej. patients/seed.csv)")
    sp.add_argument("--no-triage", action="store_true", help="No invocar ml-triage")
    sp.set_defaults(func=cmd_batch)

    sp = sub.add_parser("batch-all", help="Procesa todos los CSV bajo un prefijo")
    sp.add_argument("--prefix", default="patients/")
    sp.add_argument("--no-triage", action="store_true")
    sp.set_defaults(func=cmd_batch_all)

    sp = sub.add_parser("seed", help="Genera CSV sintetico y lo sube a la fuente raw")
    sp.add_argument("--n", type=int, default=100)
    sp.add_argument("--seed", type=int, default=42)
    sp.set_defaults(func=cmd_seed)

    sp = sub.add_parser("version")
    sp.set_defaults(func=cmd_version)

    return p


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    setup_logging(service=settings.service_name, level=settings.log_level)
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
