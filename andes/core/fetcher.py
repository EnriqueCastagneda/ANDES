"""Descarga por lotes de series BCRPData.

Optimizaciones sobre el cliente original:

* hasta 10 códigos por petición (límite real del API) y agrupación por frecuencia,
  porque el API descarta en silencio las series de otra frecuencia;
* una sola sesión HTTP con cookies de Imperva y *keep-alive*;
* puerta de rate-limit global (2 hilos, 0.45 s entre peticiones) y reintentos con
  backoff exponencial + jitter: Imperva devuelve HTTP 200 con una página HTML
  cuando detecta ráfagas (~10 % de bloqueos incluso en secuencial);
* caché SQLite por lote, con TTL largo para rangos históricos.
"""

from __future__ import annotations

import json
import os
import random
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import requests

from .paths import DATA_DIR

BASE_URL = "https://estadisticas.bcrp.gob.pe/estadisticas/series/api"
MAX_BATCH = 10
CACHE_PATH = os.path.join(DATA_DIR, "andes_cache.sqlite3")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-PE,es;q=0.9,en;q=0.8",
}

_MONTHS = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "set": 9, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}

# sintaxis de periodo del API, por frecuencia: ver ``period()``
PERIOD_EXAMPLES = {
    "Diaria": "2026-11-05",
    "Mensual": "2026-11",
    "Trimestral": "2026-4",
    "Anual": "2026",
}


class PortalBlocked(RuntimeError):
    """Imperva devolvió una página de desafío en lugar de datos."""


@dataclass
class Stats:
    requests: int = 0
    blocks: int = 0
    retries: int = 0
    cache_hits: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def bump(self, **kw):
        with self.lock:
            for key, value in kw.items():
                setattr(self, key, getattr(self, key) + value)


STATS = Stats()


class _Gate:
    """Serializa el arranque de peticiones para no activar el WAF."""

    def __init__(self, min_interval: float = 0.45):
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self._next_at = 0.0

    def wait(self, penalty: float = 0.0):
        with self._lock:
            now = time.monotonic()
            start = max(now, self._next_at) + penalty
            self._next_at = start + self.min_interval
        delay = start - time.monotonic()
        if delay > 0:
            time.sleep(delay)


_GATE = _Gate()
_SESSION: requests.Session | None = None
_SESSION_LOCK = threading.Lock()


def session() -> requests.Session:
    """Sesión única: reutiliza conexión y cookies de Imperva."""
    global _SESSION
    with _SESSION_LOCK:
        if _SESSION is None:
            s = requests.Session()
            s.headers.update(HEADERS)
            _SESSION = s
        return _SESSION


def _is_block(text: str) -> bool:
    head = text.lstrip()[:200]
    return head.startswith("<!DOCTYPE") or head.startswith("<html")


def _get_json(url: str, attempts: int = 5) -> dict:
    last: Exception | None = None
    for attempt in range(attempts):
        _GATE.wait(penalty=2.0 * attempt if last and isinstance(last, PortalBlocked) else 0.0)
        try:
            resp = session().get(url, timeout=30)
            STATS.bump(requests=1)
            if resp.status_code != 200:
                last = RuntimeError(f"HTTP {resp.status_code}")
            elif _is_block(resp.text):
                STATS.bump(blocks=1)
                last = PortalBlocked(url)
            else:
                return resp.json()
        except (requests.RequestException, ValueError) as exc:
            last = exc
        if attempt + 1 < attempts:
            STATS.bump(retries=1)
            time.sleep(min(8.0, 0.4 * 2**attempt) + random.uniform(0, 0.3))
    raise RuntimeError(f"Sin datos para {url}: {last}")


def _cache_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(CACHE_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(CACHE_PATH, timeout=30)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS payload (key TEXT PRIMARY KEY, body TEXT, fetched_at REAL)"
    )
    return conn


def _cache_get(key: str, ttl: float) -> dict | None:
    try:
        conn = _cache_conn()
        try:
            row = conn.execute(
                "SELECT body, fetched_at FROM payload WHERE key = ?", (key,)
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return None
    if not row or time.time() - row[1] > ttl:
        return None
    STATS.bump(cache_hits=1)
    return json.loads(row[0])


def _cache_put(key: str, payload: dict):
    try:
        conn = _cache_conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO payload (key, body, fetched_at) VALUES (?,?,?)",
                (key, json.dumps(payload, ensure_ascii=False), time.time()),
            )
            conn.commit()
        finally:
            conn.close()
    except sqlite3.Error:
        pass


def period(freq: str, year: int, month: int = 1, day: int = 1, quarter: int = 1) -> str:
    """Construye el periodo en la sintaxis exacta del API."""
    if freq == "Diaria":
        return f"{year}-{month}-{day}"
    if freq == "Mensual":
        return f"{year}-{month}"
    if freq == "Trimestral":
        return f"{year}-{quarter}"
    if freq == "Anual":
        return f"{year}"
    raise ValueError(f"Frecuencia no soportada: {freq}")


def _year(text: str) -> int:
    """Convierte ``97`` -> 1997 y ``05`` -> 2005 (pivote 70)."""
    year = int(text)
    if len(text) == 2:
        year += 1900 if year >= 70 else 2000
    return year


def parse_period(label: str, freq: str) -> str | None:
    """Normaliza la etiqueta del API (``Ene.2024``, ``01.Ene.97``) a ISO."""
    label = (label or "").strip()
    try:
        if freq == "Anual":
            return f"{_year(label):04d}-01-01"
        if freq == "Trimestral":
            q, year = label.upper().replace("T", "").split(".")
            month = (int(q) - 1) * 3 + 1
            return f"{_year(year):04d}-{month:02d}-01"
        if freq == "Mensual":
            mon, year = label.lower().split(".")
            return f"{_year(year):04d}-{_MONTHS[mon[:3]]:02d}-01"
        if freq == "Diaria":
            day, mon, year = label.lower().split(".")
            return f"{_year(year):04d}-{_MONTHS[mon[:3]]:02d}-{int(day):02d}"
    except (ValueError, KeyError, IndexError):
        return None
    return None


def _to_float(value: str) -> float | None:
    text = (value or "").strip()
    if text in ("", "n.d.", "nd", "-"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _ttl(start: str, end: str) -> float:
    """Histórico: 30 días. Rango abierto o del año en curso: 1 hora."""
    try:
        end_year = int(end.split("-")[0])
    except (AttributeError, ValueError):
        return 3600
    return 30 * 86400 if end_year < time.localtime().tm_year else 3600


def fetch_chunk(codes: list[str], start: str, end: str, freq: str,
                lang: str = "esp") -> dict[str, list[dict]]:
    """Descarga un lote (<=10) y devuelve ``{codigo: [{fecha, valor}]}``."""
    key = f"{freq}|{lang}|{'-'.join(codes)}|{start}|{end}"
    payload = _cache_get(key, _ttl(start, end))
    if payload is None:
        url = f"{BASE_URL}/{'-'.join(codes)}/json/{start}/{end}/{lang}"
        payload = _get_json(url)
        _cache_put(key, payload)

    series = (payload.get("config") or {}).get("series") or []
    if len(series) != len(codes):
        # El API puede descartar códigos; se resuelven individualmente.
        if len(codes) == 1:
            return {}
        out: dict[str, list[dict]] = {}
        for code in codes:
            out.update(fetch_chunk([code], start, end, freq, lang))
        return out

    periods = payload.get("periods") or []
    out = {}
    for index, code in enumerate(codes):
        out[code] = [
            {"fecha": parse_period(p.get("name", ""), freq),
             "periodo": p.get("name"),
             "valor": _to_float((p.get("values") or [None] * len(codes))[index])}
            for p in periods
        ]
    return out


def fetch_series(codes: list[str], start: str, end: str, frequency: str,
                 lang: str = "esp", workers: int = 2) -> dict[str, list[dict]]:
    """Descarga varias series agrupándolas en lotes de 10.

    Todas las series deben compartir frecuencia: el API ignora las demás.
    """
    codes = [c.strip().upper() for c in codes if c and c.strip()]
    unique = list(dict.fromkeys(codes))
    chunks = [unique[i:i + MAX_BATCH] for i in range(0, len(unique), MAX_BATCH)]
    result: dict[str, list[dict]] = {}
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 2))) as pool:
        futures = [pool.submit(fetch_chunk, chunk, start, end, frequency, lang)
                   for chunk in chunks]
        for future in futures:
            result.update(future.result())
    return result
