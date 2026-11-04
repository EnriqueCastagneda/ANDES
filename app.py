# BCRP Downloader
# Copyright (C) 2026 BCRP Downloader contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compatibility entry point for `python app.py` and Flet builds."""

from __future__ import annotations

import flet as ft

from bcrp_downloader.gui.views import main
from bcrp_downloader.runtime import (
    _filter_gdk_cursor_noise,
    _sanitize_ld_library_path,
)

__all__ = ["main"]

if __name__ == "__main__":
    _sanitize_ld_library_path()
    _filter_gdk_cursor_noise()
    ft.run(main)
