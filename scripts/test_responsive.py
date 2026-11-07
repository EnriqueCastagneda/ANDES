#!/usr/bin/env python3
"""Pruebas responsivas de ANDES en los anchos de referencia.

Comprueba que la app carga, que la marca está presente y que no hay
desbordamiento horizontal. Guarda capturas por dispositivo.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from eval_web_gui import Browser  # noqa: E402

DEVICES = (
    ("movil-320", 320, 640),
    ("movil-375", 375, 812),
    ("movil-430", 430, 932),
    ("tablet-768", 768, 1024),
    ("portatil-1366", 1366, 768),
    ("escritorio-1920", 1920, 1080),
)


def main() -> int:
    url = "http://127.0.0.1:8550/"
    out = Path("/tmp/opencode/responsive")
    out.mkdir(parents=True, exist_ok=True)
    browser = Browser(url, out)
    failures = 0
    try:
        for name, width, height in DEVICES:
            browser.cmd(
                "Emulation.setDeviceMetricsOverride",
                {
                    "width": width,
                    "height": height,
                    "deviceScaleFactor": 1,
                    "mobile": width < 600,
                },
            )
            browser.cmd("Page.navigate", {"url": url})
            ready = False
            for _ in range(25):
                browser.js(
                    "document.querySelector('flt-semantics-placeholder')?.click()"
                )
                time.sleep(1)
                texts = " ".join(browser.texts()).upper()
                title = (browser.js("document.title") or "").upper()
                if "SERIES" in texts and "ANDES" in title:
                    ready = True
                    break
            overflow = browser.js(
                "Math.max(0, document.documentElement.scrollWidth - window.innerWidth)"
            )
            ok = ready and (overflow or 0) <= 1
            failures += 0 if ok else 1
            print(
                f"{'PASS' if ok else 'FAIL'} {name:16} {width}x{height} "
                f"ready={ready} overflow={overflow}"
            )
            browser.shot(f"{name}.png")
    finally:
        browser.close()
    print(f"fallos={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())