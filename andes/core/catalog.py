"""Catálogo local de series (SQLite + FTS5).

Sustituye la carga completa del CSV de metadatos (6.9 MB, ~17k filas) en cada
arranque por una base SQLite con índice de texto completo. La descarga del CSV
se hace una vez al día y la construcción es atómica.

El CSV oficial usa ISO-8859-1 y separador ``;``.
"""

from __future__ import annotations

import os
import re
import sqlite3
import time
from collections.abc import Iterable

import requests

from .paths import DATA_DIR, METADATA_PATH, METADATA_URL

CATALOG_PATH = os.path.join(DATA_DIR, "andes_catalog.sqlite3")
LEGACY_CATALOG_PATH = os.path.join(DATA_DIR, "bcrp_catalog.sqlite3")
if not os.path.exists(CATALOG_PATH) and os.path.exists(LEGACY_CATALOG_PATH):
    # Instalaciones previas: reutiliza el catálogo histórico sin moverlo.
    CATALOG_PATH = LEGACY_CATALOG_PATH
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
    institution TEXT NOT NULL DEFAULT 'bcrp',
    code TEXT NOT NULL UNIQUE,
    category TEXT, group_name TEXT, name TEXT NOT NULL,
    description TEXT, methodology TEXT, unit TEXT, scale TEXT, geo TEXT,
    source TEXT, frequency TEXT, created TEXT, pub_group TEXT,
    area TEXT, updated TEXT, start TEXT, end TEXT, memo TEXT
);
CREATE INDEX IF NOT EXISTS idx_series_freq ON series(frequency);
CREATE INDEX IF NOT EXISTS idx_series_cat ON series(category);
CREATE INDEX IF NOT EXISTS idx_series_inst ON series(institution);
CREATE VIRTUAL TABLE IF NOT EXISTS series_fts USING fts5(
    code, name, group_name, category, unit,
    content='series', content_rowid='id',
    tokenize="unicode61 remove_diacritics 2"
);
PRAGMA user_version = 2;
"""

SCHEMA_VERSION = 2


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
            institution = (
                row.get("Institución") or row.get("institution") or "bcrp"
            ).strip().lower()
            values = tuple((row.get(col) or "").strip() for col in _COLUMNS.values())
            yield (institution, *values)


def build_catalog(csv_path: str = METADATA_PATH, db_path: str = CATALOG_PATH) -> str:
    """Reconstruye el catálogo BCRP sin borrar las demás instituciones."""
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

    preserved: list[tuple] = []
    if os.path.exists(db_path):
        try:
            source = sqlite3.connect(db_path)
            try:
                preserved = source.execute(
                    "SELECT " + ", ".join(_UPSERT_COLUMNS) + " FROM series"
                    " WHERE institution != 'bcrp'"
                ).fetchall()
            finally:
                source.close()
        except sqlite3.Error:
            preserved = []

    tmp = f"{db_path}.part"
    if os.path.exists(tmp):
        os.remove(tmp)

    conn = sqlite3.connect(tmp)
    try:
        conn.executescript(_SCHEMA)
        conn.executemany(
            "INSERT INTO series (" + ", ".join(_UPSERT_COLUMNS) + ") VALUES ("
            + ",".join("?" * len(_UPSERT_COLUMNS)) + ")",
            _rows(csv_path),
        )
        if preserved:
            conn.executemany(
                "INSERT OR REPLACE INTO series ("
                + ", ".join(_UPSERT_COLUMNS)
                + ") VALUES ("
                + ",".join("?" * len(_UPSERT_COLUMNS))
                + ")",
                preserved,
            )
        conn.execute("INSERT INTO series_fts(series_fts) VALUES('rebuild')")
        conn.commit()
    finally:
        conn.close()
    os.replace(tmp, db_path)
    return db_path


def _schema_ok(db_path: str) -> bool:
    """Comprueba que el catálogo existente tiene la versión esperada."""
    try:
        conn = sqlite3.connect(db_path)
        try:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
        finally:
            conn.close()
        return int(version) == SCHEMA_VERSION
    except sqlite3.Error:
        return False


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

    db_stale = (
        not os.path.exists(db_path)
        or not _schema_ok(db_path)
        or os.path.getmtime(csv_path) > os.path.getmtime(db_path)
    )
    if db_stale:
        build_catalog(csv_path, db_path)
    return db_path


_FIELD_ALIASES = {
    "codigo": "code",
    "código": "code",
    "code": "code",
    "nombre": "name",
    "name": "name",
    "serie": "name",
    "grupo": "group_name",
    "group": "group_name",
    "grupo_serie": "group_name",
    "categoria": "category",
    "categoría": "category",
    "category": "category",
    "rubro": "category",
    "unidad": "unit",
    "unit": "unit",
}

_OPERATORS = {"AND", "OR", "NOT"}
_TOKEN_RE = re.compile(r'"(?:[^"\\]|\\.)*"|\(|\)|[^\s()]+')


def _simple_fts(text: str) -> str:
    """Búsqueda tolerante: todos los términos como prefijos unidos por AND."""
    tokens = [
        token
        for token in "".join(
            char if char.isalnum() else " " for char in text
        ).split()
        if token and token.upper() not in _OPERATORS
    ]
    return " ".join(f'"{token}"*' for token in tokens)


def _quote(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _fts_query(text: str) -> str:
    """Traduce operadores booleanos a una expresión MATCH de SQLite FTS5.

    Admite ``AND``, ``OR``, ``NOT``, ``-término``, frases entre comillas,
    paréntesis y prefijos de campo (``nombre:``, ``codigo:``, ``categoria:``,
    ``grupo:``, ``unidad:``). Si la expresión no es válida, vuelve a la
    búsqueda simple por prefijos.
    """
    if not text or not text.strip():
        return ""
    raw = _TOKEN_RE.findall(text)
    if not raw:
        return ""
    parts: list[str] = []
    operand = False
    depth = 0
    index = 0

    def emit(expression: str) -> None:
        nonlocal operand
        if operand:
            parts.append("AND")
        parts.append(expression)
        operand = True

    while index < len(raw):
        token = raw[index]
        if token == "(":
            if operand:
                parts.append("AND")
            parts.append("(")
            operand = False
            depth += 1
            index += 1
            continue
        if token == ")":
            if not operand or depth == 0:
                return _simple_fts(text)
            parts.append(")")
            operand = True
            depth -= 1
            index += 1
            continue

        upper = token.upper()
        if upper in _OPERATORS:
            if upper == "NOT":
                if not operand:
                    if parts and parts[-1] == "AND":
                        parts.pop()
                    else:
                        return _simple_fts(text)
                parts.append("NOT")
                operand = False
            else:
                if not operand:
                    return _simple_fts(text)
                parts.append(upper)
                operand = False
            index += 1
            continue

        column = None
        value = token
        if ":" in token:
            prefix, rest = token.split(":", 1)
            mapped = _FIELD_ALIASES.get(prefix.lower())
            if mapped:
                column = mapped
                value = rest
                if not value:
                    index += 1
                    if index >= len(raw):
                        return _simple_fts(text)
                    value = raw[index]

        negative = False
        if value.startswith("-") and len(value) > 1 and column is None:
            negative = True
            value = value[1:]

        if value.startswith('"'):
            if not (value.endswith('"') and len(value) >= 2):
                return _simple_fts(text)
            inner = value[1:-1].replace('\\"', '"').replace('""', '"')
            if not inner.strip():
                return _simple_fts(text)
            expression = _quote(inner)
        else:
            term = value.replace("*", "").strip()
            if not term:
                return _simple_fts(text)
            expression = _quote(term) + "*"

        if column:
            expression = f"{column}:{expression}"
        if negative:
            if not operand:
                return _simple_fts(text)
            parts.append("NOT")
            operand = False
        emit(expression)
        index += 1

    if depth != 0 or not operand:
        return _simple_fts(text)
    return " ".join(parts)


def search(
    query: str = "",
    *,
    institution: str | None = None,
    frequency: str | None = None,
    category: str | None = None,
    area: str | None = None,
    source: str | None = None,
    pub_group: str | None = None,
    group_name: str | None = None,
    start: str | None = None,
    end: str | None = None,
    created_from: str | None = None,
    created_to: str | None = None,
    updated_from: str | None = None,
    updated_to: str | None = None,
    limit: int | None = 50,
    offset: int = 0,
    db_path: str | None = None,
) -> list[dict]:
    """Busca series por texto (prefijos, sin tildes) y filtros exactos o de rango.

    Reproduce los filtros del CSV oficial directamente en SQL, sin cargar el
    catálogo completo en pandas. ``limit=None`` devuelve todas las coincidencias.
    """
    db_path = db_path or ensure_catalog()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        match = _fts_query(query)
        if match:
            sql = ("SELECT s.*, bm25(series_fts) AS score FROM series_fts"
                   " JOIN series s ON s.id = series_fts.rowid"
                   " WHERE series_fts MATCH ?")
            params: list = [match]
        else:
            sql = "SELECT s.*, 0.0 AS score FROM series s WHERE 1=1"
            params = []

        exact = {
            "s.institution": institution,
            "s.frequency": frequency,
            "s.category": category,
            "s.area": area,
            "s.source": source,
            "s.pub_group": pub_group,
            "s.group_name": group_name,
        }
        for column, value in exact.items():
            if value and value not in ("Todas", "Todos"):
                sql += f" AND {column} = ?"
                params.append(value)

        for column, value in (("s.start", start), ("s.end", end)):
            if value:
                sql += f" AND {column} LIKE ?"
                params.append(f"%{value}%")

        for column, value, operator in (
            ("s.created", created_from, ">="),
            ("s.created", created_to, "<="),
            ("s.updated", updated_from, ">="),
            ("s.updated", updated_to, "<="),
        ):
            if value:
                sql += f" AND {column} IS NOT NULL AND {column} != '' AND {column} {operator} ?"
                params.append(value)

        sql += " ORDER BY score, s.code"
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        try:
            return [dict(row) for row in conn.execute(sql, params)]
        except sqlite3.OperationalError:
            # Expresión avanzada inválida: reintenta con la búsqueda simple.
            simple = _simple_fts(query)
            if not simple or not params:
                raise
            params[0] = simple
            return [dict(row) for row in conn.execute(sql, params)]
    finally:
        conn.close()


def count(*, institution: str | None = None, frequency: str | None = None,
          db_path: str | None = None) -> int:
    """Número de series del catálogo (opcionalmente filtradas)."""
    db_path = db_path or ensure_catalog()
    conn = sqlite3.connect(db_path)
    try:
        where, params = [], []
        if institution:
            where.append("institution = ?")
            params.append(institution)
        if frequency:
            where.append("frequency = ?")
            params.append(frequency)
        sql = "SELECT COUNT(*) FROM series"
        if where:
            sql += " WHERE " + " AND ".join(where)
        return int(conn.execute(sql, params).fetchone()[0])
    finally:
        conn.close()


_DISTINCT_FIELDS = {
    "institution": "institution",
    "category": "category",
    "source": "source",
    "area": "area",
    "pub_group": "pub_group",
    "group_name": "group_name",
    "frequency": "frequency",
    "start": "start",
    "end": "end",
}


def distinct(field: str, limit: int = 10000, *,
             institution: str | None = None,
             db_path: str | None = None) -> list[str]:
    """Valores distintos de una columna, ordenados (para desplegables de la GUI)."""
    try:
        column = _DISTINCT_FIELDS[field]
    except KeyError as exc:
        raise ValueError(f"Campo no permitido: {field}") from exc
    db_path = db_path or ensure_catalog()
    conn = sqlite3.connect(db_path)
    try:
        sql = (
            f"SELECT DISTINCT {column} FROM series"
            f" WHERE {column} IS NOT NULL AND {column} != ''"
        )
        params: list = []
        if institution:
            sql += " AND institution = ?"
            params.append(institution)
        sql += f" ORDER BY {column} LIMIT ?"
        params.append(limit)
        return [r[0] for r in conn.execute(sql, params)]
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


_UPSERT_COLUMNS = (
    "institution", "code", "category", "group_name", "name", "description",
    "methodology", "unit", "scale", "geo", "source", "frequency", "created",
    "pub_group", "area", "updated", "start", "end", "memo",
)


def upsert(rows: Iterable[dict], db_path: str | None = None) -> int:
    """Inserta o actualiza series y reconstruye el índice FTS5.

    Se usa para catálogos que crecen bajo demanda (p. ej. MEF). Devuelve el
    número de filas escritas.
    """
    rows = list(rows)
    if not rows:
        return 0
    db_path = db_path or ensure_catalog()
    conn = sqlite3.connect(db_path)
    try:
        conn.executemany(
            "INSERT OR REPLACE INTO series ("
            + ", ".join(_UPSERT_COLUMNS)
            + ") VALUES ("
            + ",".join("?" * len(_UPSERT_COLUMNS))
            + ")",
            [tuple(row.get(column, "") for column in _UPSERT_COLUMNS) for row in rows],
        )
        conn.execute("INSERT INTO series_fts(series_fts) VALUES('rebuild')")
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def count_prefix(prefix: str, institution: str | None = None,
                 db_path: str | None = None) -> int:
    """Cuenta series cuyo código empieza por ``prefix``."""
    db_path = db_path or ensure_catalog()
    conn = sqlite3.connect(db_path)
    try:
        sql = "SELECT COUNT(*) FROM series WHERE code LIKE ?"
        params: list = [f"{prefix.upper()}%"]
        if institution:
            sql += " AND institution = ?"
            params.append(institution)
        return int(conn.execute(sql, params).fetchone()[0])
    finally:
        conn.close()


def clear_institution(institution: str, db_path: str | None = None) -> int:
    """Borra las series de una institución y reconstruye el índice FTS5."""
    db_path = db_path or ensure_catalog()
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute(
            "DELETE FROM series WHERE institution = ?", (institution,)
        )
        conn.execute("INSERT INTO series_fts(series_fts) VALUES('rebuild')")
        conn.commit()
        return int(cursor.rowcount)
    finally:
        conn.close()


def clear_prefix(prefix: str, db_path: str | None = None) -> int:
    """Borra las series cuyo código empieza por ``prefix``."""
    db_path = db_path or ensure_catalog()
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute(
            "DELETE FROM series WHERE code LIKE ?", (f"{prefix.upper()}%",)
        )
        conn.execute("INSERT INTO series_fts(series_fts) VALUES('rebuild')")
        conn.commit()
        return int(cursor.rowcount)
    finally:
        conn.close()
