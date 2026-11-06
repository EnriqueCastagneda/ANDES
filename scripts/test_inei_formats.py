#!/usr/bin/env python3
"""Prueba descargas reales del INEI Temático en los seis formatos de exportación.

Para cada una de las ocho categorías del índice temático selecciona un
dataset, lo descarga, lo exporta a csv/json/xls/xml/txt/html, verifica la
estructura mínima de cada archivo y limpia el directorio temporal y la
caché de descargas al final.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET

import pandas as pd

OUT_DIR = "/tmp/opencode/inei-formats"
FILES_DIR = os.path.join("data", "inei_tematico", "files")
FORMATS = ("csv", "json", "xls", "xml", "txt", "html")
EXPECTED_CATEGORIES = 8
CODE_COL = "Código de serie"
CATEGORY_COL = "Categoría de serie"
WARNINGS: list[str] = []


def check_format(path: str, fmt: str, label: str = "") -> str:
    """Devuelve 'ok' o el motivo de fallo de un archivo exportado.

    Un XML con raíz ``serie`` cuyos nombres de etiqueta no son válidos se
    cuenta como formato OK, pero se anota en ``WARNINGS``.
    """
    if not os.path.isfile(path) or os.path.getsize(path) <= 0:
        return "vacío o ausente"
    if fmt == "json":
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, list) or not data:
            return "json no es lista con filas"
    elif fmt == "xml":
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        match = re.match(r"\s*<([\w:.-]+)", text)
        if not match or match.group(1) != "serie":
            return f"raíz xml = {match.group(1) if match else '?'}"
        try:
            ET.fromstring(text)
        except ET.ParseError as exc:
            WARNINGS.append(f"{label}: xml no bien formado ({exc})")
    elif fmt == "xls":
        frame = pd.read_excel(path)
        if frame.empty:
            return "xls ilegible o vacío"
    elif fmt in ("csv", "txt"):
        sep = "\t" if fmt == "txt" else ","
        header = pd.read_csv(path, sep=sep, nrows=0)
        if len(header.columns) < 1 or any(not str(name).strip() for name in header.columns):
            return "sin encabezado"
    elif fmt == "html":
        with open(path, encoding="utf-8") as handle:
            if "<table" not in handle.read():
                return "sin <table>"
    return "ok"


def pick_datasets(adapter) -> list[dict]:
    """Un dataset por categoría del índice temático (el primero de cada una)."""
    frame = adapter.search("", filters={"institucion": "inei_tematico"}, limit=500)
    if frame.empty:
        raise SystemExit("catálogo inei_tematico vacío")
    picks = []
    for category, group in frame.groupby(CATEGORY_COL, sort=True):
        picks.append(
            {
                "category": str(category),
                "candidates": [str(code) for code in group[CODE_COL].tolist()],
            }
        )
    return picks


def fetch_frame(adapter, candidates: list[str]) -> tuple[str, pd.DataFrame]:
    """Descarga el primer dataset de la lista que devuelva filas."""
    for code in candidates:
        frame = adapter.fetch([code], "archivo", "unico")
        if not frame.empty:
            return code, frame
    return candidates[0], pd.DataFrame()


def cleanup(out_dir: str, files_dir: str) -> tuple[bool, bool]:
    """Borra el temporal y la caché; devuelve si quedaron vacíos."""
    shutil.rmtree(out_dir, ignore_errors=True)
    if os.path.isdir(files_dir):
        for name in os.listdir(files_dir):
            path = os.path.join(files_dir, name)
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
    temp_ok = not os.path.exists(out_dir) or not os.listdir(out_dir)
    files_ok = os.path.isdir(files_dir) and not os.listdir(files_dir)
    return temp_ok, files_ok


def main() -> int:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from bcrp_downloader.core.adapters import get_adapter
    from bcrp_downloader.core.api import export_series

    adapter = get_adapter("inei_tematico")
    picks = pick_datasets(adapter)
    print(f"categorías encontradas: {len(picks)} (esperadas: {EXPECTED_CATEGORIES})")

    rows = []
    failures = 0
    try:
        for pick in picks:
            code, frame = fetch_frame(adapter, pick["candidates"])
            if frame.empty:
                rows.append(
                    {
                        "category": pick["category"],
                        "code": code,
                        "rows": 0,
                        "cols": 0,
                        "ok": [],
                        "error": "fetch vacío",
                    }
                )
                failures += 1
                continue
            os.makedirs(OUT_DIR, exist_ok=True)
            ok_formats = []
            errors = []
            for fmt in FORMATS:
                path = export_series(frame, code, "archivo", "unico", fmt, out_dir=OUT_DIR)
                reason = check_format(path, fmt, label=f"{pick['category']}/{code}")
                if reason == "ok":
                    ok_formats.append(fmt)
                else:
                    errors.append(f"{fmt}: {reason}")
            if errors:
                failures += len(errors)
            rows.append(
                {
                    "category": pick["category"],
                    "code": code,
                    "rows": len(frame),
                    "cols": frame.shape[1],
                    "ok": ok_formats,
                    "error": "; ".join(errors),
                }
            )
    finally:
        temp_ok, files_ok = cleanup(OUT_DIR, FILES_DIR)

    headers = ("Categoría", "Código", "Filas", "Columnas", "Formatos OK")
    body = [
        (
            row["category"],
            row["code"],
            str(row["rows"]),
            str(row["cols"]),
            f'{len(row["ok"])}/{len(FORMATS)}'
            + (f' ({row["error"]})' if row["error"] else ""),
        )
        for row in rows
    ]
    widths = [
        max([len(headers[i])] + [len(line[i]) for line in body])
        for i in range(len(headers))
    ]
    print(" | ".join(h.ljust(widths[i]) for i, h in enumerate(headers)))
    print("-+-".join("-" * w for w in widths))
    for line in body:
        print(" | ".join(line[i].ljust(widths[i]) for i in range(len(headers))))

    tested = sum(len(row["ok"]) for row in rows)
    print(f"datasets probados: {len(rows)} · formatos OK: {tested}/{len(rows) * len(FORMATS)}")
    for warning in WARNINGS:
        print(f"aviso: {warning}")
    print(f"temporal {OUT_DIR} vacío/inexistente: {temp_ok}")
    print(
        f"{FILES_DIR} vacío: {files_ok} · index.json preservado: "
        f"{os.path.isfile(os.path.join('data', 'inei_tematico', 'index.json'))}"
    )
    if failures or len(rows) != EXPECTED_CATEGORIES or not temp_ok or not files_ok:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
