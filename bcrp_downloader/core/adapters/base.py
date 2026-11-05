"""Contrato común de adaptadores de portal."""

from __future__ import annotations

from typing import Protocol

import pandas as pd

from ..portals import PortalSpec


class PortalAdapter(Protocol):
    """Interfaz nativa que implementa cada portal."""

    spec: PortalSpec

    def search(self, query: str, *, filters: dict | None = None,
               limit: int | None = 100, offset: int = 0) -> pd.DataFrame:
        """Busca series en el catálogo local."""

    def fetch(self, codes: list[str], start: str, end: str,
              frequency: str | None = None) -> pd.DataFrame:
        """Descarga series; debe hablar directo con el portal."""
