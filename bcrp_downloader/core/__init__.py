"""Core backend: metadata catalogue, HTTP client and exporters."""

from .api import (
    download_series_data,
    download_series_file,
    export_series,
    export_table,
    find_pdf_url,
    periods_to_dataframe,
)
from .metadata import filter_metadata, load_metadata
from .paths import DATA_DIR, METADATA_PATH, METADATA_URL, OUTPUT_DIR

__all__ = [
    "DATA_DIR",
    "METADATA_PATH",
    "METADATA_URL",
    "OUTPUT_DIR",
    "download_series_data",
    "download_series_file",
    "export_series",
    "export_table",
    "filter_metadata",
    "find_pdf_url",
    "load_metadata",
    "periods_to_dataframe",
]
