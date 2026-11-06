"""Compatibilidad del nombre histórico ``bcrp_downloader``."""
from __future__ import annotations


def test_shim_reexports_andes():
    import andes
    import bcrp_downloader

    assert bcrp_downloader.APP_NAME == andes.APP_NAME == "ANDES"
    assert bcrp_downloader.__version__ == andes.__version__


def test_shim_submodules_alias_real_modules():
    from bcrp_downloader.core.api import export_series

    assert export_series.__module__ == "andes.core.api"

    import bcrp_downloader.core.catalog as legacy

    import andes.core.catalog as current

    assert legacy is current