"""Filesystem paths and public endpoints."""

from __future__ import annotations

import os
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PACKAGE_ROOT.parent
# Prefer the repository assets; fall back to the assets shipped in the wheel.
ASSETS_DIR = str(
    PROJECT_ROOT / "assets"
    if (PROJECT_ROOT / "assets").is_dir()
    else PACKAGE_ROOT / "assets"
)

METADATA_URL = "https://estadisticas.bcrp.gob.pe/estadisticas/series/metadata"
DATA_DIR = os.environ.get("ANDES_DATA_DIR", "data")
OUTPUT_DIR = os.environ.get("ANDES_OUTPUT_DIR", "outputs")
METADATA_PATH = os.path.join(DATA_DIR, "metadata_bcrp.csv")
