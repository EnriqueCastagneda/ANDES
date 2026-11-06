#!/usr/bin/env python3
"""Prueba de descarga de cada portal del registro Gob.pe.

Para destinos tabulares descarga y exporta el archivo; para el resto comprueba
que el portal responde y entrega contenido.Al final borra los archivos
descargados y la caché para dejar el directorio de trabajo limpio.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMP = "/tmp/opencode/portal-tests"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; bcrp-downloader/1.0)"}


def probe(url: str) -> dict:
    started = time.perf_counter()
    try:
        response = requests.get(
            url, headers=HEADERS, timeout=30, stream=True, allow_redirects=True
        )
        chunk = next(response.iter_content(4096), b"")
        response.close()
        return {
            "status": response.status_code,
            "bytes": len(chunk),
            "type": response.headers.get("content-type", ""),
            "elapsed": round(time.perf_counter() - started, 2),
        }
    except Exception as exc:  # noqa: BLE001
        return {"status": None, "error": str(exc)[:120]}


def main() -> int:
    from bcrp_downloader.core import gobpe
    from bcrp_downloader.core.adapters import get_adapter
    from bcrp_downloader.core.api import export_series

    portals = gobpe.load_registry()
    if not portals:
        print("registro vacío", file=sys.stderr)
        return 1
    adapter = get_adapter("gobpe")
    os.makedirs(TMP, exist_ok=True)
    results: list[dict] = []

    # Fase 1: portales no tabulares -> comprobar respuesta HTTP real.
    web = [p for p in portals if p["platform"] not in gobpe.TABULAR]
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(probe, p["url"]): p for p in web}
        for future in as_completed(futures):
            portal = futures[future]
            row = future.result()
            row.update(id=portal["id"], platform=portal["platform"],
                       name=portal["name"], url=portal["url"])
            results.append(row)

    # Fase 2: destinos tabulares -> descarga completa y exportación.
    tabular = [p for p in portals if p["platform"] in gobpe.TABULAR]
    for portal in tabular:
        row = {"id": portal["id"], "platform": portal["platform"],
               "name": portal["name"], "url": portal["url"]}
        try:
            frame = adapter.fetch([portal["id"]], "archivo", "unico")
            row["rows"] = int(len(frame))
            if not frame.empty:
                path = export_series(
                    frame, portal["id"], "archivo", "unico", "csv", out_dir=TMP
                )
                row["file"] = os.path.basename(path)
                row["file_bytes"] = os.path.getsize(path)
        except Exception as exc:  # noqa: BLE001
            row["error"] = str(exc)[:120]
        results.append(row)

    results.sort(key=lambda item: item["id"])
    ok = sum(1 for row in results if row.get("status") and row["status"] < 400)
    report = {
        "total": len(results),
        "ok": ok,
        "failed": len(results) - ok,
        "by_platform": {},
        "results": results,
    }
    for row in results:
        key = row["platform"]
        report["by_platform"].setdefault(key, {"total": 0, "ok": 0})
        report["by_platform"][key]["total"] += 1
        if row.get("status") and row["status"] < 400:
            report["by_platform"][key]["ok"] += 1

    report_path = os.path.join(ROOT, "data", "gobpe", "download_report.json")
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)

    print(f"portales={len(results)} ok={ok} fallidos={len(results) - ok}")
    for platform, stats in sorted(report["by_platform"].items()):
        print(f"  {platform}: {stats['ok']}/{stats['total']}")
    if tabular:
        print(f"  tabulares descargados: {len(tabular)}")

    # Limpieza: archivos descargados y caché.
    shutil.rmtree(TMP, ignore_errors=True)
    cache = os.path.join(ROOT, "data", "gobpe", "files")
    if os.path.isdir(cache):
        for name in os.listdir(cache):
            os.remove(os.path.join(cache, name))
    clean = not os.path.exists(TMP) and (
        not os.path.isdir(cache) or not os.listdir(cache)
    )
    print(f"limpieza: {'OK' if clean else 'PENDIENTE'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())