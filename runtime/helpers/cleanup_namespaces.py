#!/usr/bin/env python3
"""Remove only explicitly named demo namespace directories."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil


ALLOWED = re.compile(r"^order-(?:a-docs|a-query|b)-[a-z0-9-]{1,24}$")
UNITS_ROOT = Path("/data/units")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("namespaces", nargs="+")
    args = parser.parse_args()
    removed = []
    for namespace in args.namespaces:
        if not ALLOWED.fullmatch(namespace):
            raise RuntimeError(f"Refusing unexpected namespace name: {namespace}")
        target = UNITS_ROOT / f"unit-{namespace}"
        if target.parent != UNITS_ROOT:
            raise RuntimeError("Namespace cleanup target escaped the units root")
        existed = target.is_dir()
        if existed:
            shutil.rmtree(target)
        removed.append({"namespace": namespace, "existed": existed, "removed": not target.exists()})
    print(json.dumps({"namespaces": removed, "all_removed": all(item["removed"] for item in removed)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
