"""Compatibilidad: alias histórico de :mod:`andes`.

Permite que ``import bcrp_downloader.core.api`` siga funcionando después del
renombrado del paquete a :mod:`andes`. No contiene lógica propia: delega en
los módulos reales de ``andes``.
"""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.util
import sys

import andes as _andes
from andes import APP_NAME, APP_TAGLINE, APP_VERSION, __version__  # noqa: F401
from andes import *  # noqa: F401,F403


class _AndesAliasFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Resuelve ``bcrp_downloader.*`` como ``andes.*``."""

    prefix = "bcrp_downloader"

    def find_spec(self, fullname, path=None, target=None):
        if fullname != self.prefix and not fullname.startswith(
            self.prefix + "."
        ):
            return None
        real = "andes" + fullname[len(self.prefix):]
        try:
            real_spec = importlib.util.find_spec(real)
        except (ImportError, AttributeError, ValueError):
            return None
        if real_spec is None:
            return None
        return importlib.util.spec_from_loader(
            fullname,
            self,
            is_package=real_spec.submodule_search_locations is not None,
        )

    def create_module(self, spec):
        real = "andes" + spec.name[len(self.prefix):]
        module = importlib.import_module(real)
        sys.modules[spec.name] = module
        return module

    def exec_module(self, module):
        return None


if not any(isinstance(finder, _AndesAliasFinder) for finder in sys.meta_path):
    sys.meta_path.insert(0, _AndesAliasFinder())