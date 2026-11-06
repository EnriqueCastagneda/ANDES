"""Icono de aplicación: tamaños, colores y paquetes .ico/.icns."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
ICON_DIR = ROOT / "assets" / "icon"
SIZES = {
    ROOT / "assets" / "icon.png": 256,
    ROOT / "assets" / "favicon.png": 32,
    ROOT / "assets" / "icons" / "icon-192.png": 192,
    ROOT / "assets" / "icons" / "icon-512.png": 512,
    ROOT / "assets" / "icons" / "icon-maskable-192.png": 192,
    ROOT / "assets" / "icons" / "icon-maskable-512.png": 512,
    ROOT / "assets" / "icons" / "apple-touch-icon-192.png": 192,
}


@pytest.mark.parametrize("path,size", list(SIZES.items()), ids=lambda p: getattr(p, "name", str(p)))
def test_png_icons_have_expected_size_and_color(path, size):
    with Image.open(path) as image:
        assert image.size == (size, size)
        assert image.mode in ("RGB", "RGBA")
        colors = image.convert("RGB").getcolors(maxcolors=100000)
        assert colors is not None and len(colors) > 4, "icono sin color"


def test_all_scaled_icons_exist():
    for size in (16, 32, 48, 64, 128, 256, 512, 1024):
        path = ICON_DIR / f"andes_icono_{size}.png"
        with Image.open(path) as image:
            assert image.size == (size, size)


def _has_color(image: Image.Image, target: tuple[int, int, int], tolerance: int = 18) -> bool:
    colors = image.convert("RGB").getcolors(maxcolors=1_000_000) or []
    return any(
        abs(red - target[0]) <= tolerance
        and abs(green - target[1]) <= tolerance
        and abs(blue - target[2]) <= tolerance
        for _, (red, green, blue) in colors
    )


def test_icon_uses_brand_colors():
    with Image.open(ROOT / "assets" / "icon" / "andes_icono_512.png") as image:
        assert _has_color(image, (0x1A, 0x1C, 0x33)), "falta el azul noche"
        assert _has_color(image, (0xE3, 0xA9, 0x4F)), "falta el dorado"


def test_ico_contains_required_sizes():
    path = ICON_DIR / "andes_icono.ico"
    with Image.open(path) as image:
        sizes = set(image.info.get("sizes", set()))
    expected = {(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)}
    assert expected <= sizes


def test_icns_header_is_valid():
    data = (ICON_DIR / "andes_icono.icns").read_bytes()
    assert data[:4] == b"icns"
    assert len(data) > 1000


def test_svg_source_is_not_black():
    svg = (ICON_DIR / "andes_icono.svg").read_text(encoding="utf-8")
    assert "#1A1C33" in svg
    assert "#E3A94F" in svg or "<path" in svg
    assert 'fill="#000000"' not in svg

def test_loading_animation_uses_app_icon():
    source = (ICON_DIR / "andes_icono_512.png").read_bytes()
    loading = (ROOT / "assets" / "icons" / "loading-animation.png").read_bytes()
    assert hashlib.sha256(source).digest() == hashlib.sha256(loading).digest()


def test_manifest_uses_ande_branding():
    data = json.loads(
        (ROOT / "assets" / "manifest.json").read_text(encoding="utf-8")
    )
    assert data["name"].startswith("ANDES")
    assert data["short_name"] == "ANDES"
    assert data["background_color"] == "#1A1C33"
    assert data["theme_color"] == "#1A1C33"
    icons = {icon["src"] for icon in data["icons"]}
    assert "icons/icon-192.png" in icons
    assert "icons/icon-512.png" in icons
