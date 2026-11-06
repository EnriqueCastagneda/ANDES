#!/usr/bin/env python3
"""Exporta la jerarquía declarada de cada portal a ``fixtures/<id>/hierarchy.json``.

Los fixtures son la referencia versionada para tests y para revisar el contrato
sin volver a scrapear el portal.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from andes.core import portals

ROOT = Path(__file__).resolve().parent.parent / "fixtures"


def main() -> None:
    ROOT.mkdir(exist_ok=True)
    for spec in portals.specs():
        target = ROOT / spec.id
        target.mkdir(exist_ok=True)
        (target / "hierarchy.json").write_text(
            json.dumps(asdict(spec), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"{spec.id}: {target / 'hierarchy.json'}")


if __name__ == "__main__":
    main()
