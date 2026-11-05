"""Mide el catálogo SQLite/FTS5 y la descarga por lotes contra el cliente actual."""

from __future__ import annotations

import os
import sys
import time

os.environ.setdefault("BCRP_DATA_DIR", "/tmp/bcrpdata")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bcrp_downloader.core import catalog, fetcher  # noqa: E402

CODES = [f"PN{i:05d}MM" for i in range(1, 21)]
START, END, FREQ = "2024-1", "2024-12", "Mensual"


def bench_catalog():
    t0 = time.perf_counter()
    db = catalog.ensure_catalog()
    t1 = time.perf_counter()
    print(f"catálogo listo en {t1 - t0:.2f}s -> {db}")

    for term in ("tipo de cambio", "inflacion", "pbi", "credito"):
        t0 = time.perf_counter()
        hits = catalog.search(term, limit=10)
        t1 = time.perf_counter()
        print(f"  búsqueda '{term}': {(t1 - t0) * 1000:.1f} ms, {len(hits)} resultados")

    t0 = time.perf_counter()
    rows = catalog.search("", frequency="Diaria", limit=50)
    t1 = time.perf_counter()
    print(f"  filtro frecuencia Diaria: {(t1 - t0) * 1000:.1f} ms, {len(rows)} filas")
    print("  frecuencias:", catalog.frequencies())


def bench_legacy():
    from bcrp_downloader.core.api import download_series_data

    done = 0
    t0 = time.perf_counter()
    for code in CODES:
        try:
            download_series_data(code, START, END)
            done += 1
        except RuntimeError:
            break
    elapsed = time.perf_counter() - t0
    return elapsed, done


def bench_batched():
    t0 = time.perf_counter()
    data = fetcher.fetch_series(CODES, START, END, FREQ)
    return time.perf_counter() - t0, data


if __name__ == "__main__":
    bench_catalog()

    t_legacy, done = bench_legacy()
    print(f"cliente actual (1 petición/serie): {t_legacy:.2f}s "
          f"para {done}/{len(CODES)} series antes del bloqueo")

    if os.path.exists(fetcher.CACHE_PATH):
        os.remove(fetcher.CACHE_PATH)  # fuerza una ejecución en frío
    fetcher.STATS = fetcher.Stats()
    t_cold, data = bench_batched()
    print(f"cliente por lotes en frío ({len(CODES)} series): {t_cold:.2f}s "
          f"({len(data)} series, {fetcher.STATS.requests} peticiones, "
          f"{fetcher.STATS.blocks} bloqueos, {fetcher.STATS.retries} reintentos)")

    fetcher.STATS = fetcher.Stats()
    t_warm, _ = bench_batched()
    print(f"cliente por lotes con caché caliente: {t_warm:.2f}s "
          f"({fetcher.STATS.requests} peticiones, {fetcher.STATS.cache_hits} aciertos)")
    print(f"aceleración en frío: {t_legacy / t_cold:.1f}x")
    sample = data["PN00001MM"][:2]
    print("muestra:", sample)
