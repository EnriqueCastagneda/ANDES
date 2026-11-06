#!/usr/bin/env python3
"""Valida los portales descubiertos: URL, plataforma y accesibilidad.

Para cada portal del registro hace una petición HEAD (con respaldo GET) y
guarda el estado HTTP. Sirve como prueba de integridad del directorio y
permite detectar enlaces caídos sin bloquear la aplicación.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; bcrp-downloader/1.0)"}


def probe(url: str, timeout: int = 20) -> dict:
    try:
        response = requests.head(
            url, headers=HEADERS, timeout=timeout, allow_redirects=True
        )
        if response.status_code in (403, 405, 501):
            response = requests.get(
                url, headers=HEADERS, timeout=timeout, stream=True,
                allow_redirects=True,
            )
        response.close()
        return {"url": url, "status": response.status_code,
                "final": response.url}
    except Exception as exc:  # noqa: BLE001
        return {"url": url, "status": None, "error": str(exc)[:120]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", default="data/gobpe/portals.json")
    parser.add_argument("--out", default="data/gobpe/status.json")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from bcrp_downloader.core import gobpe

    portals = gobpe.load_registry(args.registry)
    if not portals:
        print("registro vacío", file=sys.stderr)
        return 1
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(probe, portal["url"]): portal for portal in portals}
        for index, future in enumerate(as_completed(futures), start=1):
            portal = futures[future]
            row = future.result()
            row["id"] = portal["id"]
            row["platform"] = portal["platform"]
            results.append(row)
            if index % 50 == 0:
                print(f"{index}/{len(portals)}", flush=True)
    results.sort(key=lambda row: row["id"])
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump({"count": len(results), "results": results},
                  handle, ensure_ascii=False, indent=2)
    ok = sum(1 for row in results if row.get("status") and row["status"] < 400)
    print(f"ok={ok} total={len(results)} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())