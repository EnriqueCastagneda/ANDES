#!/usr/bin/env python3
"""Pruebas aleatorias de selección y descarga por institución.

Elige series al azar del catálogo, las descarga con el adaptador de su
institución, exporta en el formato permitido y valida el archivo. Al final
borra las descargas y la caché creada para dejar limpio el directorio.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import shutil
import sqlite3
import sys
import xml.etree.ElementTree as ET

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TMP = "/tmp/opencode/random-downloads"
MONTHS = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "set": 9, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}


def _period(value: str) -> str:
    text = (value or "").strip()
    month = re.fullmatch(r"([A-Za-z]{3})-(\d{4})", text)
    if month:
        return f"{month.group(2)}-{MONTHS.get(month.group(1).lower(), 1)}"
    day = re.fullmatch(r"(\d{1,2})-([A-Za-z]{3})-(\d{4})", text)
    if day:
        number = MONTHS.get(day.group(2).lower(), 1)
        return f"{day.group(3)}-{number}-{int(day.group(1))}"
    year = re.fullmatch(r"(\d{4})", text)
    if year:
        return year.group(1)
    return text


def _window(frequency: str, end: str) -> tuple[str, str]:
    parsed = _period(end)
    year = int(parsed[:4]) if parsed[:4].isdigit() else 2025
    freq = (frequency or "").lower()
    if freq.startswith("anual"):
        return str(year - 4), str(year)
    if freq.startswith("trimestral"):
        return f"{year - 1}-1", f"{year}-4"
    if freq.startswith("diaria"):
        return f"{year}-01-01", f"{year}-12-31"
    return f"{year - 1}-1", f"{year}-12"


def _valid(path: str, fmt: str) -> tuple[bool, str]:
    try:
        if fmt == "json":
            data = json.load(open(path, encoding="utf-8"))
            return isinstance(data, list) and len(data) > 0, f"{len(data)} filas"
        if fmt == "xml":
            root = ET.parse(path).getroot()
            return root.tag == "serie" and len(root) > 0, f"{len(root)} periodos"
        if fmt == "xls":
            frame = pd.read_excel(path)
            return len(frame) > 0, f"{len(frame)} filas"
        if fmt == "html":
            text = open(path, encoding="utf-8").read()
            return "<table" in text and "<tr>" in text, "tabla"
        text = open(path, encoding="utf-8-sig").read().splitlines()
        return len(text) > 1, f"{len(text) - 1} filas"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:80]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--per", type=int, default=4, help="series por institución")
    args = parser.parse_args()

    from andes.core import catalog
    from andes.core.adapters import get_adapter
    from andes.core.api import export_series
    from andes.core.sources import sources

    rng = random.Random(args.seed)
    db = catalog.ensure_catalog()
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            "SELECT code, institution, frequency, start, end FROM series"
        ).fetchall()
    finally:
        conn.close()

    grouped: dict[str, list[tuple]] = {}
    for row in rows:
        grouped.setdefault(row[1], []).append(row)

    os.makedirs(TMP, exist_ok=True)
    report: list[dict] = []
    clean = os.environ.get("KEEP", "") != "1"

    for institution in sources():
        pool = grouped.get(institution.id, [])
        if not pool:
            continue
        size = 1 if institution.id.startswith("gobpe:") else args.per
        sample = rng.sample(pool, min(size, len(pool)))
        adapter = get_adapter(institution.id)
        formats = institution.formats or ("csv", "json", "xls", "xml", "txt", "html")
        for code, _inst, frequency, start, end in sample:
            item = {
                "institution": institution.id,
                "code": code,
                "frequency": frequency,
                "format": None,
                "rows": 0,
                "ok": False,
                "detail": "",
            }
            try:
                if institution.id.startswith("gobpe:"):
                    r_start, r_end = "archivo", "unico"
                elif institution.id == "inei_tematico":
                    r_start, r_end = "archivo", "unico"
                elif institution.id == "inei":
                    r_start, r_end = start or "2018-01-01", end or "2026-01-01"
                elif institution.id == "bcrp":
                    r_start, r_end = _window(frequency, end)
                else:
                    r_start, r_end = start, end
                frame = adapter.fetch([code], r_start, r_end, frequency)
                item["rows"] = int(len(frame))
                fmt = rng.choice(list(formats))
                item["format"] = fmt
                if frame.empty:
                    item["detail"] = "sin datos en el rango"
                else:
                    path = export_series(
                        frame, code, r_start, r_end, fmt, out_dir=TMP
                    )
                    ok, detail = _valid(path, fmt)
                    item["ok"] = ok
                    item["detail"] = detail
            except Exception as exc:  # noqa: BLE001
                item["detail"] = f"error: {exc}"[:120]
            report.append(item)
            status = "OK" if item["ok"] else "SKIP" if not item["rows"] else "FAIL"
            print(
                f"{status:4} {institution.id:18} {code:16} "
                f"{item['format'] or '-':5} {item['rows']:5} {item['detail']}"
            )

    report_path = os.path.join(ROOT, "data", "random_report.json")
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)

    total = len(report)
    ok = sum(1 for row in report if row["ok"])
    empty = sum(1 for row in report if not row["rows"])
    failed = total - ok - empty
    print(f"\ntotal={total} ok={ok} sin_datos={empty} fallos={failed}")

    if clean:
        shutil.rmtree(TMP, ignore_errors=True)
        for cache in ("data/mef", "data/inei_tematico/files", "data/gobpe/files"):
            path = os.path.join(ROOT, cache)
            if os.path.isdir(path):
                for name in os.listdir(path):
                    target = os.path.join(path, name)
                    if os.path.isdir(target):
                        shutil.rmtree(target, ignore_errors=True)
                    else:
                        os.remove(target)
        print("limpieza: OK")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())