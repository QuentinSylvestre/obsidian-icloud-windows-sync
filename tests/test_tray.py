import threading
from datetime import datetime
from unittest.mock import MagicMock, patch

from PIL import Image


def test_import():
    from obsidian_sync.tray import run_tray, _shutdown_event
    assert callable(run_tray)
    assert isinstance(_shutdown_event, threading.Event)


def test_tooltip_syncing():
    from obsidian_sync.tray import _tooltip
    engine = MagicMock()
    engine.active_tasks = ["a", "b"]
    engine.last_sync_time = None
    result = _tooltip(engine)
    assert result.startswith("Obsidian iCloud Sync \u2014 ")
    assert "Syncing 2 files" in result


def test_tooltip_idle_with_last_sync():
    from obsidian_sync.tray import _tooltip
    engine = MagicMock()
    engine.active_tasks = []
    engine.last_sync_time = datetime(2024, 1, 1, 14, 30)
    result = _tooltip(engine)
    assert "Idle" in result
    assert "14:30" in result


def test_tooltip_idle():
    from obsidian_sync.tray import _tooltip
    engine = MagicMock()
    engine.active_tasks = []
    engine.last_sync_time = None
    result = _tooltip(engine)
    assert result == "Obsidian iCloud Sync \u2014 Idle"


def test_load_icon_fallback():
    with patch("PIL.Image.open", side_effect=OSError("no icon")):
        from obsidian_sync import tray
        import importlib
        importlib.reload(tray)
        result = tray._load_icon()
    assert isinstance(result, Image.Image)
    assert result.size == (16, 16)
    assert result.mode == "RGBA"
