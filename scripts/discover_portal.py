#!/usr/bin/env python3
"""Descubre la jerarquía de un portal con Chromium local (sin TinyFish).

Abre la URL, captura peticiones XHR/fetch y los ``<select>`` del DOM, y escribe
un borrador JSON. Luego se cura a mano en ``fixtures/<portal>/hierarchy.json``.

Uso:
    python scripts/discover_portal.py https://portal.gob.pe/ruta --out fixtures/mi/descubierto.json
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

try:
    import websocket
except ImportError:  # pragma: no cover
    raise SystemExit("Falta websocket-client: pip install websocket-client") from None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--out", required=True)
    parser.add_argument("--wait", type=float, default=12.0)
    parser.add_argument("--port", type=int, default=9333)
    args = parser.parse_args()

    proc = subprocess.Popen(
        [
            os.environ.get("CHROMIUM", "chromium"),
            "--headless=new",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--enable-unsafe-swiftshader",
            f"--remote-debugging-port={args.port}",
            "--window-size=1366,900",
            args.url,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        target = None
        for _ in range(80):
            try:
                pages = requests.get(
                    f"http://127.0.0.1:{args.port}/json/list", timeout=1
                ).json()
                target = next((p for p in pages if p.get("type") == "page"), None)
                if target:
                    break
            except Exception:
                pass
            time.sleep(0.5)
        if not target:
            raise SystemExit("Chromium no expuso un target CDP")

        ws = websocket.create_connection(target["webSocketDebuggerUrl"], timeout=40)
        counter = {"id": 0}
        requests_seen: list[dict] = []
        events: list[dict] = []

        def cmd(method: str, params: dict | None = None) -> dict:
            counter["id"] += 1
            ws.send(json.dumps({"id": counter["id"], "method": method,
                                "params": params or {}}))
            while True:
                message = json.loads(ws.recv())
                if message.get("id") == counter["id"]:
                    return message
                events.append(message)

        cmd("Page.enable")
        cmd("Network.enable")
        cmd("Runtime.enable")
        time.sleep(1.0)
        cmd("Page.reload")
        time.sleep(args.wait)

        for event in events:
            if event.get("method") != "Network.requestWillBeSent":
                continue
            params = event.get("params", {})
            request = params.get("request", {})
            kind = params.get("type", "")
            if kind not in ("XHR", "Fetch", "Document", "Other"):
                continue
            requests_seen.append(
                {
                    "url": request.get("url", ""),
                    "method": request.get("method", ""),
                    "type": kind,
                }
            )

        def walk_frames(node):
            yield node.get("frame", {})
            for child in node.get("childFrames", []) or []:
                yield from walk_frames(child)

        tree = cmd("Page.getFrameTree")
        frames = list(walk_frames(tree["result"]["frameTree"]))
        selects: list[dict] = []
        inputs: list[dict] = []
        page = {
            "title": "",
            "url": tree["result"]["frameTree"]["frame"].get("url", ""),
        }
        for frame in frames:
            world = cmd(
                "Page.createIsolatedWorld",
                {"frameId": frame["id"], "worldName": "discover"},
            )
            context_id = world.get("result", {}).get("executionContextId")
            if not context_id:
                continue
            dom = cmd(
                "Runtime.evaluate",
                {
                    "contextId": context_id,
                    "expression": """JSON.stringify({
                    title: document.title,
                    url: location.href,
                    selects: [...document.querySelectorAll('select')].map(s => ({
                        id: s.id, name: s.name,
                        options: [...s.options].slice(0, 60).map(o => ({
                            value: o.value, text: o.textContent.trim()
                        }))
                    })),
                    inputs: [...document.querySelectorAll('input')].map(i => ({
                        id: i.id, name: i.name, type: i.type
                    })).slice(0, 80)
                })""",
                    "returnByValue": True,
                },
            )
            data = json.loads(dom["result"]["result"].get("value") or "{}")
            if not page["title"]:
                page["title"] = data.get("title", "")
            for select in data.get("selects", []):
                select["frame_url"] = frame.get("url", "")
                selects.append(select)
            for field in data.get("inputs", []):
                field["frame_url"] = frame.get("url", "")
                inputs.append(field)
        # Deduplica endpoints y descarta estáticos.
        unique = []
        seen = set()
        for item in requests_seen:
            url = item["url"]
            if any(url.endswith(ext) for ext in (".js", ".css", ".png", ".jpg", ".svg", ".woff", ".woff2")):
                continue
            if url in seen:
                continue
            seen.add(url)
            unique.append(item)

        report = {
            "source_url": args.url,
            "final_url": page.get("url", ""),
            "title": page.get("title", ""),
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "requests": unique,
            "selects": selects,
            "inputs": inputs,
        }

        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
        print(json.dumps({
            "out": str(out),
            "requests": len(unique),
            "selects": len(report["selects"]),
            "title": report["title"],
        }, ensure_ascii=False))
        ws.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)


if __name__ == "__main__":
    main()
