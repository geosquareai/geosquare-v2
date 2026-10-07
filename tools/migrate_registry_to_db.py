#!/usr/bin/env python3
"""One-time migration: legacy JSON registry -> SQLite registry database."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from geosquare_v2.db import MigrationTool  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("release"),
        help="Legacy JSON registry directory (default: release)",
    )
    parser.add_argument(
        "--destination",
        type=Path,
        default=Path("src/geosquare_v2/db/registry.db"),
        help="Output SQLite database path (default: src/geosquare_v2/db/registry.db)",
    )
    parser.add_argument("--manifest", default="registry.v2.json", help="Manifest filename within --source")
    args = parser.parse_args()

    args.destination.parent.mkdir(parents=True, exist_ok=True)
    domain_count = MigrationTool(args.source).migrate(args.destination, manifest_file=args.manifest)
    print(f"Wrote registry database: {args.destination} ({domain_count} domain(s))")


if __name__ == "__main__":
    main()
