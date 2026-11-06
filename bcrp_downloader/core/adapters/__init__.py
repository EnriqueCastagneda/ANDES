"""Registro de adaptadores nativos por institución."""

from __future__ import annotations

from .bcrp import BcrpAdapter
from .gobpe import GobpeAdapter
from .inei import IneiAdapter
from .inei_tematico import IneiTematicoAdapter
from .mef import MefAdapter

_ADAPTERS = {
    "bcrp": BcrpAdapter(),
    "mef": MefAdapter(),
    "inei": IneiAdapter(),
    "inei_tematico": IneiTematicoAdapter(),
    "gobpe": GobpeAdapter(),
}


def get_adapter(source_id: str):
    """Devuelve el adaptador de una institución registrada."""
    key = source_id.strip().lower()
    if key.startswith("gobpe:"):
        key = "gobpe"
    try:
        return _ADAPTERS[key]
    except (KeyError, AttributeError) as exc:
        raise ValueError(f"Sin adaptador para: {source_id}") from exc


def registered() -> list[str]:
    """Ids de portales con adaptador."""
    return sorted(_ADAPTERS)
