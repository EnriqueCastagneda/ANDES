"""Filesystem paths and public endpoints."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ASSETS_DIR = str(PROJECT_ROOT / "assets")

METADATA_URL = "https://estadisticas.bcrp.gob.pe/estadisticas/series/metadata"
DATA_DIR = os.environ.get("BCRP_DATA_DIR", "data")
OUTPUT_DIR = os.environ.get("BCRP_OUTPUT_DIR", "outputs")
METADATA_PATH = os.path.join(DATA_DIR, "metadata_bcrp.csv")
