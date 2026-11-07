"""Linux runtime tweaks for the Flet desktop client."""

from __future__ import annotations

import os
import sys


def _sanitize_ld_library_path():
    """Drop stale library dirs that shadow system GLib/GTK.

    Tools like rig install an old libglib in ``~/.local/share/rig/lib`` and
    leave it in ``LD_LIBRARY_PATH``.  That copy lacks symbols required by the
    system libgio (``g_source_set_static_name``), which breaks GTK and the
    Flutter desktop client.  Keep every other entry untouched.
    """
    current = os.environ.get("LD_LIBRARY_PATH")
    if not current:
        return
    bad_markers = ("/.local/share/rig/lib",)
    kept = [
        p
        for p in current.split(":")
        if p and not any(marker in p for marker in bad_markers)
    ]
    os.environ["LD_LIBRARY_PATH"] = ":".join(kept)


def _running_in_pyodide() -> bool:
    """Pyodide (Flet web estático) no soporta hilos Python."""
    if sys.platform in {"emscripten", "wasi"}:
        return True
    try:
        import pyodide  # noqa: F401
    except ImportError:
        return False
    return True


def _filter_gdk_cursor_noise():
    """Suppress harmless Flutter/GTK teardown noise on stderr.

    The prebuilt Flet desktop client prints a few warnings that look alarming
    but are not errors:

    - ``Gdk-Message: ... Unable to load  from the cursor theme`` — Flutter asks
      GDK for a cursor with an empty name.
    - ``embedder.cc ... 'FlutterEngineRemoveView' returned 'kInvalidArguments'
      ... The implicit view cannot be removed.`` — the engine refuses to remove
      its implicit view during shutdown.
    - ``Attempted to set message handler on an FlBinaryMessenger without an
      engine`` — plugin teardown after the engine is gone.
    - ``Atk-CRITICAL ... atk_socket_embed: assertion 'plug_id != NULL' failed``
      — GTK accessibility warning at window creation.

    Every other line is forwarded unchanged.
    """
    if not sys.platform.startswith("linux"):
        return
    if not os.environ.get("WAYLAND_DISPLAY"):
        return
    if _running_in_pyodide():
        return

    noise = (
        b"Unable to load  from the cursor theme",
        b"'FlutterEngineRemoveView' returned 'kInvalidArguments'",
        b"The implicit view cannot be removed",
        b"Attempted to set message handler on an FlBinaryMessenger without an engine",
        b"atk_socket_embed: assertion 'plug_id != NULL' failed",
    )

    def is_noise(line):
        return any(token in line for token in noise)

    real_stderr_fd = os.dup(2)
    read_fd, write_fd = os.pipe()
    os.dup2(write_fd, 2)
    os.close(write_fd)

    import threading

    def pump():
        with os.fdopen(read_fd, "rb", buffering=0) as reader:
            pending = b""
            for chunk in iter(lambda: reader.read(4096), b""):
                pending += chunk
                while b"\n" in pending:
                    line, pending = pending.split(b"\n", 1)
                    if not is_noise(line):
                        os.write(real_stderr_fd, line + b"\n")
            if pending and not is_noise(pending):
                os.write(real_stderr_fd, pending)

    # Daemon thread: never blocks interpreter shutdown; the pipe closes with
    # the process, so any final client lines are simply dropped.
    threading.Thread(target=pump, daemon=True).start()


