"""Integridad del registro de portales descubiertos (si existe)."""
from __future__ import annotations

import os

import pytest

from bcrp_downloader.core import gobpe

REGISTRY = gobpe.REGISTRY_PATH


pytestmark = pytest.mark.skipif(
    not os.path.exists(REGISTRY), reason="registro Gob.pe no generado"
)


def test_every_portal_is_well_formed():
    portals = gobpe.load_registry(REGISTRY)
    assert portals, "el registro no puede estar vacío"
    seen: set[str] = set()
    for portal in portals:
        assert portal["id"].startswith("GOBPE-")
        assert portal["url"].startswith(("http://", "https://", "/"))
        assert portal["platform"] in (
            "csv", "excel", "api", "ckan", "tableau", "powerbi",
            "pdf", "web", "gobpe",
        )
        assert portal["name"].strip()
        assert portal["url"] not in seen, f"duplicado: {portal['url']}"
        seen.add(portal["url"])


def test_registry_has_portals_outside_gobpe():
    portals = gobpe.load_registry(REGISTRY)
    assert any(portal["scope"] == "externo" for portal in portals)