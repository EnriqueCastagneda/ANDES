"""Registro de adaptadores nativos por institución."""

from __future__ import annotations

from .bcrp import BcrpAdapter
from .inei import IneiAdapter
from .mef import MefAdapter

_ADAPTERS = {
    "bcrp": BcrpAdapter(),
    "mef": MefAdapter(),
    "inei": IneiAdapter(),
}


def get_adapter(source_id: str):
    """Devuelve el adaptador de una institución registrada."""
    try:
        return _ADAPTERS[source_id.strip().lower()]
    except (KeyError, AttributeError) as exc:
        raise ValueError(f"Sin adaptador para: {source_id}") from exc


def registered() -> list[str]:
    """Ids de portales con adaptador."""
    return sorted(_ADAPTERS)
