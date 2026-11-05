"""Adaptador nativo del BCRP (catálogo SQLite + API JSON)."""

from __future__ import annotations

import pandas as pd

from .. import api, metadata
from ..portals import spec_for


class BcrpAdapter:
    spec = spec_for("bcrp")

    def search(self, query: str, *, filters: dict | None = None,
               limit: int | None = 100, offset: int = 0) -> pd.DataFrame:
        return metadata.search_catalog(
            query, filters=filters, limit=limit, offset=offset
        )

    def fetch(self, codes: list[str], start: str, end: str,
              frequency: str | None = None) -> pd.DataFrame:
        return api.download_many(codes, start, end, frequency)
