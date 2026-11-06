#!/usr/bin/env python3
"""Descubre los portales/servicios de gob.pe para un término de búsqueda.

Recorre todas las páginas del buscador (``/busquedas.json?term=...&sheet=N``),
guarda cada resultado y clasifica el destino (API, archivo, tablero o HTML).
El archivo de salida es reanudable: omite las páginas ya guardadas.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bcrp_downloader.core.gobpe import classify  # noqa: E402

BASE = "https://www.gob.pe/busquedas.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ANDES/2.0)"}


def fetch_sheet(term: str, sheet: int, contenido: str = "",
                retries: int = 4) -> dict:
    params = {"term": term, "sheet": sheet}
    if contenido:
        params["contenido"] = contenido
    last: Exception | None = None
    for attempt in range(retries):
        try:
            response = requests.get(
                BASE, params=params, headers=HEADERS, timeout=60
            )
            if response.status_code == 404:
                # Gob.pe devuelve 404 transitorios bajo carga: reintentar.
                if attempt < retries - 1:
                    time.sleep(1.0 + attempt)
                    continue
                return {"results": []}
            response.raise_for_status()
            return response.json().get("data", {}).get("attributes", {})
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"sheet {sheet}: {last}")


def normalize(item: dict) -> dict:
    action = item.get("action_url") or ""
    return {
        "id": item.get("id"),
        "name": (item.get("name_with_parent") or "").strip(),
        "institution": (item.get("content_sub_title_card") or "").strip(),
        "type": item.get("searchable_type") or "",
        "kind": item.get("page_kind") or "",
        "url": action,
        "platform": classify(action),
        "score": item.get("score"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--term", default="estadisticas")
    parser.add_argument("--out", default="data/gobpe/search.jsonl")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int, default=0, help="máximo de páginas")
    parser.add_argument(
        "--contenido", default="",
        help="faceta de contenido: servicios, instituciones, publicaciones...",
    )
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    first = fetch_sheet(args.term, 1, args.contenido)
    total = int(first.get("total_count") or 0)
    pages = math.ceil(total / 25)
    if args.limit:
        pages = min(pages, args.limit)
    print(
        f"term={args.term} contenido={args.contenido or 'todos'} "
        f"total={total} páginas={pages}",
        flush=True,
    )

    done: set[int] = set()
    if os.path.exists(args.out):
        with open(args.out, encoding="utf-8") as handle:
            for line in handle:
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                # Reintentar páginas que quedaron vacías por un 404 transitorio.
                if record.get("results"):
                    done.add(record["sheet"])
    print(f"reanudando: {len(done)} páginas ya guardadas", flush=True)

    pending = [sheet for sheet in range(1, pages + 1) if sheet not in done]
    errors = 0
    with open(args.out, "a", encoding="utf-8") as handle:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {
                pool.submit(
                    fetch_sheet, args.term, sheet, args.contenido
                ): sheet
                for sheet in pending
            }
            for index, future in enumerate(as_completed(futures), start=1):
                sheet = futures[future]
                try:
                    payload = future.result()
                except Exception as exc:  # noqa: BLE001
                    errors += 1
                    print(f"ERROR sheet {sheet}: {exc}", flush=True)
                    continue
                record = {
                    "sheet": sheet,
                    "total_count": int(payload.get("total_count") or total),
                    "results": [
                        normalize(item) for item in payload.get("results", [])
                    ],
                }
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                if index % 100 == 0:
                    handle.flush()
                    print(f"{index}/{len(pending)} páginas", flush=True)
    print(f"listo: {len(pending) - errors} páginas nuevas, {errors} errores", flush=True)

    from bcrp_downloader.core import gobpe

    portals = gobpe.rebuild(args.out)
    print(f"registro: {len(portals)} portales únicos", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())