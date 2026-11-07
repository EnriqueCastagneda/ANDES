# ANDES — Open Data Platform
# Copyright (C) 2026 ANDES contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Entrada para `flet publish` (web estática) y ejecución directa."""

from __future__ import annotations

import flet as ft

from andes.core.paths import ASSETS_DIR
from andes.gui.views import main

__all__ = ["main"]

if __name__ == "__main__":
    ft.run(main, assets_dir=ASSETS_DIR)
