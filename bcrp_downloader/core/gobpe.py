"""Directorio de portales y servicios estadísticos de Gob.pe.

El buscador de Gob.pe publica resultados paginados en JSON. Este módulo
convierte esos resultados en un registro estable de portales: deduplica por
URL, descarta páginas internas y clasifica el destino (archivo, API, tablero o
web). El registro vive en ``data/gobpe/portals.json`` para que el catálogo no
dependa de la red en cada arranque.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from urllib.parse import urlparse

from .paths import DATA_DIR

REGISTRY_DIR = os.path.join(DATA_DIR, "gobpe")
REGISTRY_PATH = os.path.join(REGISTRY_DIR, "portals.json")
SEARCH_PATH = os.path.join(REGISTRY_DIR, "search.jsonl")
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SEED_PATH = os.path.join(_ROOT, "fixtures", "gobpe", "portals.json")

# Plataformas que entregan datos tabulares descargables.
TABULAR = ("csv", "excel", "api", "ckan")


def classify(url: str) -> str:
    """Clasifica un enlace por plataforma de destino."""
    if not url:
        return "sin-enlace"
    if url.startswith("/"):
        return "gobpe"
    text = url.lower().split("?")[0]
    if text.endswith(".csv"):
        return "csv"
    if re.search(r"\.(xlsx?|xlsm)$", text):
        return "excel"
    if text.endswith(".json") or "/api/" in text:
        return "api"
    if "tableau.com" in text or "/tableau/" in text:
        return "tableau"
    if "powerbi.com" in text or "app.powerbi" in text:
        return "powerbi"
    if text.endswith(".pdf"):
        return "pdf"
    if "/ckan" in text or "datastore_search" in text:
        return "ckan"
    return "web"


def _portal_id(url: str) -> str:
    return "GOBPE-" + hashlib.sha1(url.encode()).hexdigest()[:10].upper()


# Prefijos institucionales repetidos que se agrupan en una sola entrada para
# no inflar el selector. Agregar una regla es una línea.
GROUP_NAMES: dict[str, str] = {
    "municipalidades": "Municipalidades distritales y provinciales",
    "regiones": "Gobiernos y direcciones regionales",
    "ugel": "Unidades de Gestión Educativa Local",
    "redes-de-salud": "Redes de Salud",
}

GROUP_RULES: tuple[tuple[re.Pattern, str, str], ...] = (
    (re.compile(r"^MUNI"), "municipalidades", "Municipalidades"),
    (re.compile(r"^REGION"), "regiones", "Regiones"),
    (re.compile(r"^UGEL"), "ugel", "UGEL"),
    (re.compile(r"^UNIDAD DE GESTION EDUCATIVA LOCAL"), "ugel", "UGEL"),
    (re.compile(r"^RED(?:ES)?\b"), "redes-de-salud", "Redes de Salud"),
)


def _slug(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text or "")
    plain = "".join(ch for ch in plain if not unicodedata.combining(ch))
    value = re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")
    return value[:48] or "otros"


def infer_institution(raw: str, fallback: str) -> tuple[str, str]:
    """Deduce ``(id, etiqueta)`` de la institución a partir del nombre."""
    text = (raw or fallback or "").strip()
    parts = [part.strip() for part in text.split(" - ") if part.strip()]
    label = parts[0] if parts else text
    if len(parts) > 1 and len(parts[-1]) <= 8 and parts[-1].isupper():
        label = parts[-1]
    normalized = unicodedata.normalize("NFKD", label)
    normalized = "".join(
        ch for ch in normalized if not unicodedata.combining(ch)
    )
    for pattern, group_id, group_label in GROUP_RULES:
        if pattern.search(normalized.upper()):
            return group_id, group_label
    return _slug(label), label


def _host(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except ValueError:
        return ""


def build_registry(records: list[dict]) -> list[dict]:
    """Deduplica resultados y conserva solo portales con enlace externo."""
    seen: set[str] = set()
    portals: list[dict] = []
    for item in records:
        url = (item.get("url") or "").strip()
        if url.startswith("/"):
            url = "https://www.gob.pe" + url
        if not url or url in seen:
            continue
        # Solo portales/servicios e instituciones: el buscador mezcla miles
        # de normas y publicaciones (PDF) que no son portales.
        if item.get("kind") != "service" and item.get("type") != "Institution":
            continue
        platform = classify(url)
        if platform == "sin-enlace":
            continue
        seen.add(url)
        inst_id, inst_label = infer_institution(
            item.get("institution", ""), item.get("name", "")
        )
        if inst_label.lower().startswith("contenido de "):
            continue
        portals.append(
            {
                "id": _portal_id(url),
                "name": (item.get("name") or url).strip(),
                "institution": inst_label,
                "institution_id": inst_id,
                "institution_label": inst_label,
                "institution_full": (
                    item.get("institution") or item.get("name") or ""
                ).strip(),
                "kind": item.get("kind") or "",
                "url": url,
                "host": _host(url),
                "platform": platform,
                "scope": "interno" if platform == "gobpe" else "externo",
            }
        )
    portals.sort(
        key=lambda portal: (
            portal["institution_label"], portal["name"]
        )
    )
    return portals


def institutions(portals: list[dict] | None = None) -> list[dict]:
    """Instituciones únicas del registro, ordenadas por etiqueta."""
    portals = portals if portals is not None else load_registry()
    unique: dict[str, dict] = {}
    for portal in portals:
        inst_id = portal.get("institution_id")
        if not inst_id:
            continue
        label = portal.get("institution_label", inst_id)
        full = portal.get("institution_full") or label
        current = unique.get(inst_id)
        if current is None:
            unique[inst_id] = {"label": label, "name": full}
        elif len(full) > len(current["name"]):
            current["name"] = full
    for inst_id, value in unique.items():
        value["name"] = GROUP_NAMES.get(inst_id, value["name"])
    return [
        {"id": inst_id, "label": value["label"], "name": value["name"]}
        for inst_id, value in sorted(
            unique.items(), key=lambda kv: kv[1]["label"]
        )
    ]


def sites(portals: list[dict] | None = None) -> list[dict]:
    """Un sitio por institución: nombre completo y URL representativa."""
    portals = portals if portals is not None else load_registry()
    best: dict[str, dict] = {}
    for portal in portals:
        key = portal.get("institution_id")
        if not key:
            continue
        name = (
            portal.get("institution_full")
            or portal.get("institution_label")
            or key
        ).strip()
        url = portal.get("url", "")
        if not url:
            continue
        score = (url.rstrip("/").count("/"), len(url))
        current = best.get(key)
        if current is None or score < current["score"]:
            best[key] = {"name": name, "url": url, "score": score}
    return [
        {"name": value["name"], "url": value["url"]}
        for value in sorted(best.values(), key=lambda item: item["name"])
    ]


def load_jsonl(path: str | list[str] = SEARCH_PATH) -> list[dict]:
    """Lee los resultados crudos del buscador (una página por línea)."""
    paths = [path] if isinstance(path, str) else list(path)
    rows: list[dict] = []
    for candidate in paths:
        if not os.path.exists(candidate):
            continue
        with open(candidate, encoding="utf-8") as handle:
            for line in handle:
                try:
                    payload = json.loads(line)
                except ValueError:
                    continue
                rows.extend(payload.get("results", []))
    return rows


def save_registry(portals: list[dict], path: str = REGISTRY_PATH) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {
        "count": len(portals),
        "portals": portals,
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    return path


def load_registry(path: str = REGISTRY_PATH) -> list[dict]:
    """Carga el registro; si no existe, usa la semilla versionada."""
    for candidate in (path, SEED_PATH):
        if not candidate or not os.path.exists(candidate):
            continue
        with open(candidate, encoding="utf-8") as handle:
            try:
                payload = json.load(handle)
            except ValueError:
                continue
        return payload.get("portals", [])
    return []


def rebuild(jsonl_path: str | list[str] = SEARCH_PATH,
            registry_path: str = REGISTRY_PATH) -> list[dict]:
    portals = build_registry(load_jsonl(jsonl_path))
    save_registry(portals, registry_path)
    return portals