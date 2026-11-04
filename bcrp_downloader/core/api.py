"""BCRP series API, export helpers and PDF link detection."""

from __future__ import annotations

import json
import os
import re
import xml.etree.ElementTree as ET

import pandas as pd

from .paths import OUTPUT_DIR

EXPORT_FORMATS = {
    "CSV": "csv",
    "JSON": "json",
    "XLS": "xls",
    "XML": "xml",
    "TXT": "txt",
    "HTML": "html",
}

def periods_to_dataframe(data, code):
    """Convert a BCRP API JSON payload to a fecha/valor DataFrame."""
    rows = []
    for p in data.get("periods", []):
        date_val = p.get("name")
        val = p.get("values", [None])[0]
        rows.append({"fecha": date_val, code.upper(): val})
    return pd.DataFrame(rows)


def _dataframe_to_xml(df):
    """Serialize a DataFrame to XML using the standard library."""
    root = ET.Element("serie")
    for _, row in df.iterrows():
        rec = ET.SubElement(root, "periodo")
        for col in df.columns:
            el = ET.SubElement(rec, re.sub(r"[^\w]", "_", str(col)))
            el.text = str(row[col])
    return ET.tostring(root, encoding="unicode")


def _dataframe_to_html(df, code, start, end):
    """Serialize a DataFrame to a small standalone HTML page."""
    table = df.to_html(index=False, border=0)
    return (
        "<!DOCTYPE html>\n<html lang='es'>\n<head>\n<meta charset='utf-8'>\n"
        f"<title>{code.upper()} {start} - {end}</title>\n"
        "<style>body{font-family:system-ui,sans-serif;margin:24px;color:#1b1b1b}"
        "table{border-collapse:collapse}th,td{padding:6px 12px;border-bottom:1px solid #ddd;"
        "text-align:left}th{background:#f5f5f5}</style>\n</head>\n<body>\n"
        f"<h2>{code.upper()} ({start} - {end})</h2>\n{table}\n</body>\n</html>\n"
    )


def export_series(df, code, start, end, fmt, out_dir=None):
    """Write a series DataFrame to disk in the requested format.

    Returns the full file path. Raises ValueError for unknown formats.
    """
    if out_dir is None:
        out_dir = OUTPUT_DIR
    fmt = fmt.lower()
    if fmt == "xls":
        raise ValueError("xls handled via native endpoint")
    if fmt not in ("csv", "json", "txt", "xml", "html"):
        raise ValueError(f"Formato no soportado: {fmt}")

    safe_code = re.sub(r"[^\w\-_.]", "_", code.upper())
    filename = f"bcrp_serie_{safe_code}_{start}_to_{end}.{fmt}"
    filepath = os.path.join(out_dir, filename)

    if fmt == "csv":
        df.to_csv(filepath, index=False, encoding="utf-8-sig")
    elif fmt == "json":
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(df.to_dict(orient="records"), f, ensure_ascii=False, indent=2)
    elif fmt == "txt":
        df.to_csv(filepath, index=False, sep="\t", encoding="utf-8-sig")
    elif fmt == "xml":
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(_dataframe_to_xml(df))
    elif fmt == "html":
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(_dataframe_to_html(df, code, start, end))
    return filepath



PDF_URL_RE = re.compile(
    r"https?://[^\s\"'<>]+?\.pdf(?:\?[^\s\"'<>]*)?", re.IGNORECASE
)


def find_pdf_url(text):
    """Return the first .pdf URL found in text, or None."""
    if not text:
        return None
    match = PDF_URL_RE.search(str(text))
    return match.group(0) if match else None


def export_table(df, basename, fmt, out_dir=None):
    """Export an arbitrary DataFrame (e.g. a metadata listing) to disk."""
    if out_dir is None:
        out_dir = OUTPUT_DIR
    fmt = fmt.lower()
    if fmt == "xls":
        raise ValueError("xls only supported for series downloads")
    if fmt not in ("csv", "json", "txt", "xml", "html"):
        raise ValueError(f"Formato no soportado: {fmt}")
    filepath = os.path.join(out_dir, f"{basename}.{fmt}")
    if fmt == "csv":
        df.to_csv(filepath, index=False, encoding="utf-8-sig")
    elif fmt == "json":
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(df.to_dict(orient="records"), f, ensure_ascii=False, indent=2)
    elif fmt == "txt":
        df.to_csv(filepath, index=False, sep="\t", encoding="utf-8-sig")
    elif fmt == "xml":
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(_dataframe_to_xml(df))
    elif fmt == "html":
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(_dataframe_to_html(df, basename, "", ""))
    return filepath




def download_series_data(code: str, start: str, end: str) -> pd.DataFrame:
    """Fetch a BCRP series and return a ``fecha``/value DataFrame.

    Args:
        code: Series code as published by the BCRP (case-insensitive).
        start: Start period, e.g. ``2020-1``.
        end: End period, e.g. ``2024-12``.

    Returns:
        A DataFrame with the period name and the series value.
    """
    from .http import _http_get_json

    url = (
        "https://estadisticas.bcrp.gob.pe/estadisticas/series/api/"
        f"{code}/json/{start}/{end}/esp"
    )
    data = _http_get_json(url)
    return periods_to_dataframe(data, code)


def download_series_file(
    code: str, start: str, end: str, fmt: str = "csv", out_dir: str | None = None
) -> str:
    """Download a series and write it in the requested format."""
    df = download_series_data(code, start, end)
    if df.empty:
        raise ValueError(f"No data for {code} between {start} and {end}")
    return export_series(df, code, start, end, fmt, out_dir=out_dir)
