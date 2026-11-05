"""Catálogo local de series (SQLite + FTS5).

Sustituye la carga completa del CSV de metadatos (6.9 MB, ~17k filas) en cada
arranque por una base SQLite con índice de texto completo. La descarga del CSV
se hace una vez al día y la construcción es atómica.

El CSV oficial usa ISO-8859-1 y separador ``;``.
"""

from __future__ import annotations

import os
import sqlite3
import time
from collections.abc import Iterable

import requests

from .paths import DATA_DIR, METADATA_PATH, METADATA_URL

CATALOG_PATH = os.path.join(DATA_DIR, "bcrp_catalog.sqlite3")
CATALOG_MAX_AGE = 24 * 3600  # segundos

_CSV_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/csv,application/vnd.ms-excel,*/*",
}

# columnas del CSV -> columnas de la tabla
_COLUMNS = {
    "code": "Código de serie",
    "category": "Categoría de serie",
    "group_name": "Grupo de serie",
    "name": "Nombre de serie",
    "description": "Descripción de la serie",
    "methodology": "Metodología de la serie",
    "unit": "Unidad de medida",
    "scale": "Escala",
    "geo": "Geografía (País, Región de Perú)",
    "source": "Fuente",
    "frequency": "Frecuencia",
    "created": "Fecha de creación",
    "pub_group": "Grupo de publicación",
    "area": "Área que publica",
    "updated": "Fecha de actualización",
    "start": "Fecha de inicio",
    "end": "Fecha de fin",
    "memo": "Memo",
}

COLUMNS = _COLUMNS

_SCHEMA = """
CREATE TABLE IF NOT EXISTS series (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    category TEXT, group_name TEXT, name TEXT NOT NULL,
    description TEXT, methodology TEXT, unit TEXT, scale TEXT, geo TEXT,
    source TEXT, frequency TEXT, created TEXT, pub_group TEXT,
    area TEXT, updated TEXT, start TEXT, end TEXT, memo TEXT
);
CREATE INDEX IF NOT EXISTS idx_series_freq ON series(frequency);
CREATE INDEX IF NOT EXISTS idx_series_cat ON series(category);
CREATE VIRTUAL TABLE IF NOT EXISTS series_fts USING fts5(
    code, name, group_name, category, unit,
    content='series', content_rowid='id',
    tokenize="unicode61 remove_diacritics 2"
);
"""


def download_catalog_csv(dest: str = METADATA_PATH, force: bool = False) -> str:
    """Descarga el CSV de metadatos si falta o si superó su vigencia."""
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    fresh = os.path.exists(dest) and (time.time() - os.path.getmtime(dest) < CATALOG_MAX_AGE)
    if fresh and not force:
        return dest
    tmp = f"{dest}.part"
    with requests.get(METADATA_URL, headers=_CSV_HEADERS, timeout=120, stream=True) as resp:
        resp.raise_for_status()
        with open(tmp, "wb") as fh:
            for chunk in resp.iter_content(1 << 16):
                if chunk:
                    fh.write(chunk)
    os.replace(tmp, dest)
    return dest


def _rows(csv_path: str) -> Iterable[tuple]:
    import csv

    with open(csv_path, encoding="latin-1", newline="") as fh:
        reader = csv.DictReader(fh, delimiter=";")
        for row in reader:
            code = (row.get(_COLUMNS["code"]) or "").strip()
            if not code:
                continue
            yield tuple((row.get(col) or "").strip() for col in _COLUMNS.values())


def build_catalog(csv_path: str = METADATA_PATH, db_path: str = CATALOG_PATH) -> str:
    """Reconstruye el catálogo SQLite desde el CSV, de forma atómica."""
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    tmp = f"{db_path}.part"
    if os.path.exists(tmp):
        os.remove(tmp)

    conn = sqlite3.connect(tmp)
    try:
        conn.executescript(_SCHEMA)
        conn.executemany(
            "INSERT INTO series (code, category, group_name, name, description,"
            " methodology, unit, scale, geo, source, frequency, created,"
            " pub_group, area, updated, start, end, memo)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            _rows(csv_path),
        )
        conn.execute("INSERT INTO series_fts(series_fts) VALUES('rebuild')")
        conn.commit()
    finally:
        conn.close()
    os.replace(tmp, db_path)
    return db_path


def ensure_catalog(csv_path: str | None = None, db_path: str | None = None,
                   max_age: int = CATALOG_MAX_AGE) -> str:
    """Garantiza un catálogo utilizable; descarga y reindexa solo si hace falta."""
    csv_path = csv_path or METADATA_PATH
    db_path = db_path or CATALOG_PATH

    csv_stale = not os.path.exists(csv_path) or (
        time.time() - os.path.getmtime(csv_path) > max_age
    )
    if csv_stale:
        try:
            download_catalog_csv(csv_path)
        except Exception:
            if os.path.exists(db_path):
                return db_path  # se sigue usando el catálogo anterior
            raise

    db_stale = not os.path.exists(db_path) or (
        os.path.getmtime(csv_path) > os.path.getmtime(db_path)
    )
    if db_stale:
        build_catalog(csv_path, db_path)
    return db_path


def _fts_query(text: str) -> str:
    tokens = [t for t in "".join(c if c.isalnum() else " " for c in text).split() if t]
    return " ".join(f'"{t}"*' for t in tokens)


def search(query: str = "", *, frequency: str | None = None,
           category: str | None = None, limit: int = 50,
           offset: int = 0, db_path: str | None = None) -> list[dict]:
    """Busca series por texto (prefijos, sin distinguir tildes) y filtros exactos."""
    db_path = db_path or ensure_catalog()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        where, params = [], []
        match = _fts_query(query)
        if match:
            sql = ("SELECT s.*, bm25(series_fts) AS score FROM series_fts"
                   " JOIN series s ON s.id = series_fts.rowid"
                   " WHERE series_fts MATCH ?")
            params.append(match)
        else:
            sql = "SELECT s.*, 0.0 AS score FROM series s WHERE 1=1"
        if frequency:
            where.append("s.frequency = ?")
            params.append(frequency)
        if category:
            where.append("s.category = ?")
            params.append(category)
        if where:
            sql += " AND " + " AND ".join(where)
        sql += " ORDER BY score, s.code LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        return [dict(row) for row in conn.execute(sql, params)]
    finally:
        conn.close()


def frequencies(db_path: str | None = None) -> list[tuple[str, int]]:
    db_path = db_path or ensure_catalog()
    conn = sqlite3.connect(db_path)
    try:
        return [(r[0], r[1]) for r in conn.execute(
            "SELECT frequency, COUNT(*) FROM series GROUP BY frequency ORDER BY 2 DESC")]
    finally:
        conn.close()


def get(code: str, db_path: str | None = None) -> dict | None:
    """Devuelve una serie por código (sin distinguir mayúsculas) o ``None``."""
    db_path = db_path or ensure_catalog()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM series WHERE code = ?", (code.strip().upper(),)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()
