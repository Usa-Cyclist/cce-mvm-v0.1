#!/usr/bin/env python3
"""Generate the configured CCE-MVM v0.1 M0 baseline output group."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .cce_mvm import (
    DEFAULT_M0_CONFIG,
    load_baseline_config,
    run_baseline,
    write_baseline_results,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_M0_CONFIG)
    parser.add_argument("--output-dir", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_baseline(load_baseline_config(args.config))
    if args.output_dir:
        write_baseline_results(result, args.output_dir, config_path=args.config)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
