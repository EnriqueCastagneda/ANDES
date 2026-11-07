#!/usr/bin/env python3
"""Smoke test del cliente web ANDES contra un servidor Flet en marcha.

Levantar ANDES en modo web (``andes gui --web --port 8550``) en otra terminal
y ejecutar este script. Comprueba que el WebSocket del cliente Flet se
conecte y que la página muestre la marca y la lista de series.

Uso:
    python scripts/smoke_web.py --url http://127.0.0.1:8550/ --timeout 90
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import requests
import websocket


def _playwright_chromium():
    """Ruta del chromium empaquetado por Playwright (útil en CI)."""
    env_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if env_path:
        base = Path(env_path)
    else:
        base = Path.home() / ".cache/ms-playwright"
    # Playwright instala "chromium" y, según la versión, solo el
    # "chromium_headless_shell". Acepta ambos layouts.
    patterns = (
        "chromium-*/chrome-linux/chrome",
        "chrome-*/chrome-linux/chrome",
        "chromium_headless_shell-*/chrome-linux/headless_shell",
    )
    for pattern in patterns:
        for path in sorted(base.glob(pattern)):
            return str(path)
    return None


def _cdp(url: str, timeout: float = 90.0):
    """Abre Chromium headless, conecta por CDP y devuelve (ws, proc)."""
    binary = (
        _playwright_chromium()
        or shutil.which("chromium")
        or shutil.which("chromium-browser")
        or shutil.which("google-chrome")
    )
    if not binary:
        raise RuntimeError("No se encontró chromium en PATH")
    port = 0
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    proc = subprocess.Popen(
        [
            binary,
            "--headless=new",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--enable-unsafe-swiftshader",
            "--use-gl=angle",
            "--use-angle=swiftshader",
            f"--remote-debugging-port={port}",
            "--window-size=1280,820",
            f"--user-data-dir=/tmp/andes-smoke-{os.getpid()}",
            url,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    target = None
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            pages = requests.get(f"http://127.0.0.1:{port}/json/list", timeout=1).json()
            target = next((p for p in pages if p.get("type") == "page"), None)
            if target:
                break
        except Exception:
            pass
        time.sleep(0.5)
    if not target:
        proc.terminate()
        raise RuntimeError("Chromium no expuso un target CDP")
    ws = websocket.create_connection(target["webSocketDebuggerUrl"], timeout=timeout)
    return ws, proc


def _send(ws, method, params=None):
    payload = {"id": next(_counter), "method": method, "params": params or {}}
    ws.send(json.dumps(payload))
    return payload["id"]


_counter = (i for i in range(1, 10_000))


def _read_dom(ws, timeout=10.0):
    """Lee el texto visible de la página una vez esté cargada."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = _send(ws, "Runtime.evaluate", {
            "expression": (
                "JSON.stringify([...document.querySelectorAll('*')]"
                ".map(e => (e.textContent || '').trim()).filter(Boolean))"
            )
        })
        while True:
            ws.settimeout(2)
            resp = json.loads(ws.recv())
            if resp.get("id") == result:
                break
        raw = resp.get("result", {}).get("result", {}).get("value")
        try:
            texts = json.loads(raw) if raw else []
        except (TypeError, ValueError):
            texts = []
        joined = " ".join(texts).upper()
        if "ANDES" in joined or "SERIES" in joined or "EXPLORA" in joined:
            return joined
        time.sleep(0.5)
    return ""


def smoke(url: str, timeout: float) -> tuple[bool, str]:
    ws, proc = _cdp(url, timeout)
    try:
        _send(ws, "Runtime.enable")
        _send(ws, "Page.enable")
        deadline = time.time() + timeout
        loaded = False
        while time.time() < deadline:
            try:
                ws.settimeout(2)
                msg = json.loads(ws.recv())
            except Exception:
                continue
            if msg.get("method") == "Runtime.consoleAPICalled":
                args = msg["params"].get("args", [])
                text = " ".join(str(a.get("value", "")) for a in args)
                if "Flutter app loaded" in text:
                    loaded = True
                    break
            if msg.get("method") == "Runtime.exceptionThrown":
                desc = msg["params"]["exceptionDetails"].get("text", "")
                if "Traceback" in desc or "Error" in desc:
                    return False, f"Error en el cliente: {desc}"
        if not loaded:
            return False, "La app no terminó de cargar (sin 'Flutter app loaded')"
        joined = _read_dom(ws, timeout=15.0)
        if "ANDES" in joined or "SERIES" in joined or "EXPLORA" in joined:
            return True, "App cargada y visible"
        return False, "App cargó pero no muestra contenido ANDES"
    finally:
        proc.terminate()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8550/")
    parser.add_argument("--timeout", type=float, default=90.0)
    args = parser.parse_args()
    ok, detail = smoke(args.url, args.timeout)
    print(f"smoke_web: {'OK' if ok else 'FAIL'} — {detail}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())