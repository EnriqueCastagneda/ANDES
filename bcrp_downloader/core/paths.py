"""Filesystem paths and public endpoints."""

from __future__ import annotations

import os

METADATA_URL = "https://estadisticas.bcrp.gob.pe/estadisticas/series/metadata"
DATA_DIR = os.environ.get("BCRP_DATA_DIR", "data")
OUTPUT_DIR = os.environ.get("BCRP_OUTPUT_DIR", "outputs")
METADATA_PATH = os.path.join(DATA_DIR, "metadata_bcrp.csv")
