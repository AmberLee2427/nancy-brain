"""Lightweight OCR worker entrypoint for managed subprocess runtimes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional


def execute_worker(
    pdf_path: Path | str,
    *,
    cache_dir: Optional[Path | str] = None,
    backend: Optional[str] = None,
) -> tuple[dict, int]:
    """Process one PDF and return the stable worker payload plus exit code."""

    from nancy_brain.pdf_ocr import build_pdf_ocr_worker_record, extract_pdf_markdown

    pdf_path = Path(pdf_path)
    try:
        result = extract_pdf_markdown(
            pdf_path,
            cache_dir=cache_dir,
            preferred_backend=backend,
            allow_worker_spawn=False,
        )
        payload = result.to_worker_record(pdf_path, cache_dir=cache_dir)
    except Exception as exc:
        payload = build_pdf_ocr_worker_record(
            pdf_path,
            cache_dir=cache_dir,
            backend=backend,
            status="error",
            warning=str(exc),
        )
        return payload, 1

    return payload, 1 if payload["status"] == "error" else 0


def main(argv: Optional[list[str]] = None) -> int:
    """Entry point compatible with `nancy-brain ocr worker ...`."""

    parser = argparse.ArgumentParser(prog="nancy-brain")
    root = parser.add_subparsers(dest="group")
    ocr_parser = root.add_parser("ocr")
    ocr_subparsers = ocr_parser.add_subparsers(dest="ocr_command")
    worker_parser = ocr_subparsers.add_parser("worker")
    worker_parser.add_argument("pdf_path")
    worker_parser.add_argument("--cache-dir", default=None)
    worker_parser.add_argument("--backend", default=None)

    args = parser.parse_args(argv)
    if args.group != "ocr" or args.ocr_command != "worker":
        parser.print_help(sys.stderr)
        return 2

    payload, exit_code = execute_worker(args.pdf_path, cache_dir=args.cache_dir, backend=args.backend)
    sys.stdout.write(json.dumps(payload, sort_keys=True))
    sys.stdout.write("\n")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
