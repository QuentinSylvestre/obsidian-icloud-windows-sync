"""System tray icon, status tooltip, and control menu for obsidian-icloud-sync."""

import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

from PIL import Image
import pystray

from obsidian_sync.sync_engine import SyncEngine


_shutdown_event: threading.Event = threading.Event()
_TASK_NAME = "Obsidian iCloud Sync"

_task_state_cache: str | None = None
_task_state_cache_time: float = 0.0
_TASK_STATE_TTL: float = 5.0


def _load_icon() -> Image.Image:
    try:
        return Image.open(Path(__file__).parent / "assets" / "icon.png")
    except OSError:
        return Image.new("RGBA", (16, 16), (60, 130, 200, 255))


def _tooltip(engine: SyncEngine, engine_failed: threading.Event | None = None) -> str:
    if engine_failed is not None and engine_failed.is_set():
        return "Obsidian iCloud Sync \u2014 Sync stopped \u2014 see logs"
    n = len(engine.active_tasks)  # capture ONCE, never read active_tasks again
    if n > 0:
        return f"Obsidian iCloud Sync \u2014 Syncing {n} files\u2026"
    elif engine.last_sync_time is not None:
        return f"Obsidian iCloud Sync \u2014 Idle \u00b7 Last sync {engine.last_sync_time.strftime('%H:%M')}"
    else:
        return "Obsidian iCloud Sync \u2014 Idle"


def _ps_run(cmd: str, engine: SyncEngine) -> None:
    try:
        subprocess.run(
            ["powershell", "-NonInteractive", "-Command", cmd],
            capture_output=True,
            timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW,
            check=False,
        )
    except Exception as e:
        engine.log.warn("TRAY", f"PowerShell command failed: {type(e).__name__}: {cmd[:60]}")


def _ps_query(cmd: str, engine: SyncEngine) -> str:
    try:
        result = subprocess.run(
            ["powershell", "-NonInteractive", "-Command", cmd],
            capture_output=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
            check=False,
        )
        return result.stdout.decode("utf-8", errors="replace").strip()
    except Exception:
        engine.log.warn("TRAY", f"PowerShell query failed: {cmd[:60]}")
        return ""


def _task_enabled(engine: SyncEngine) -> bool:
    global _task_state_cache, _task_state_cache_time
    now = time.monotonic()
    if _task_state_cache is not None and (now - _task_state_cache_time) < _TASK_STATE_TTL:
        return _task_state_cache.lower() != "disabled"
    try:
        state = _ps_query(
            "(Get-ScheduledTask -TaskName '" + _TASK_NAME + "' -ErrorAction SilentlyContinue).State",
            engine,
        )
        _task_state_cache = state
        _task_state_cache_time = now
        return state.lower() != "disabled"
    except Exception:
        return False


def on_toggle_autolaunch(icon: pystray.Icon, item: pystray.MenuItem, engine: SyncEngine) -> None:
    """Toggle the Task Scheduler task's auto-launch state."""
    global _task_state_cache, _task_state_cache_time
    if _task_enabled(engine):
        _ps_run(f"Disable-ScheduledTask -TaskName '{_TASK_NAME}'", engine)
    else:
        _ps_run(f"Enable-ScheduledTask -TaskName '{_TASK_NAME}'", engine)
    # Invalidate cache immediately so the checkmark reflects the new state on next render
    _task_state_cache = None
    _task_state_cache_time = 0.0


def _start_tooltip_updater(
    icon: pystray.Icon,
    engine: SyncEngine,
    engine_failed: threading.Event | None = None,
) -> threading.Thread:
    def _run():
        while True:
            time.sleep(2)
            if _shutdown_event.is_set():  # check AFTER sleep — not before
                break
            try:
                # pystray allows icon.title to be set from any thread on Windows;
                # behaviour on Linux/macOS is undocumented.
                icon.title = _tooltip(engine, engine_failed)
            except Exception as e:
                engine.log.warn("TRAY", f"Tooltip updater exiting: {e}")
                break

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t


def _build_menu(engine: SyncEngine, shutdown_fn: Callable[[], None]) -> pystray.Menu:
    def on_logs(icon: pystray.Icon, item: pystray.MenuItem) -> None:
        if engine.log.log_file and Path(engine.log.log_file).exists():
            os.startfile(str(engine.log.log_file))

    def on_quit(icon: pystray.Icon, item: pystray.MenuItem) -> None:
        _shutdown_event.set()
        shutdown_fn()
        threading.Thread(
            target=lambda: _ps_run(
                f"Stop-ScheduledTask -TaskName '{_TASK_NAME}' -ErrorAction SilentlyContinue",
                engine,
            ),
            daemon=True,
        ).start()
        icon.stop()

    return pystray.Menu(
        pystray.MenuItem("Logs", on_logs),
        pystray.MenuItem(
            "Auto-launch",
            lambda icon, item: on_toggle_autolaunch(icon, item, engine),
            checked=lambda item: _task_enabled(engine),
        ),
        pystray.MenuItem("Quit", on_quit),
    )


def run_tray(
    engine: SyncEngine,
    shutdown_fn: Callable[[], None],
    engine_failed: threading.Event | None = None,
) -> None:
    icon = pystray.Icon(
        "obsidian-sync",
        _load_icon(),
        _tooltip(engine, engine_failed),
        _build_menu(engine, shutdown_fn),
    )

    def _setup(i: pystray.Icon) -> None:
        # pystray: when a custom setup is provided, the caller must set
        # visible = True (the default setup does this automatically).
        i.visible = True
        _start_tooltip_updater(i, engine, engine_failed)

    icon.run(setup=_setup)
