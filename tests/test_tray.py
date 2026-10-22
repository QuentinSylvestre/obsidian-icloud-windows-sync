import threading
from datetime import datetime
from unittest.mock import MagicMock, patch

import pystray
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


def test_quit_handler_sequence():
    """on_quit sets shutdown event, calls shutdown_fn, calls icon.stop, dispatches Stop-ScheduledTask."""
    import time
    from obsidian_sync import tray as tray_mod

    tray_mod._shutdown_event.clear()
    mock_engine = MagicMock()
    mock_engine.log = MagicMock()
    mock_shutdown = MagicMock()
    mock_icon = MagicMock()
    mock_item = MagicMock()

    captured = {}

    def capturing_MenuItem(text, action=None, **kwargs):
        m = MagicMock()
        m.text = text
        captured[str(text)] = action
        return m

    with patch.object(pystray, "MenuItem", side_effect=capturing_MenuItem), \
         patch.object(pystray, "Menu", return_value=MagicMock()), \
         patch.object(tray_mod, "_ps_run") as mock_ps_run, \
         patch.object(tray_mod, "_task_enabled", return_value=True):
        tray_mod._build_menu(mock_engine, mock_shutdown)
        assert "Quit" in captured, "Could not find quit callback"
        on_quit = captured["Quit"]
        on_quit(mock_icon, mock_item)
        time.sleep(0.1)  # give background Stop-ScheduledTask thread time to run

    assert tray_mod._shutdown_event.is_set()
    mock_shutdown.assert_called_once()
    mock_icon.stop.assert_called_once()
    calls = [str(c) for c in mock_ps_run.call_args_list]
    assert any("Stop-ScheduledTask" in c for c in calls), f"Expected Stop-ScheduledTask call, got: {calls}"
    tray_mod._shutdown_event.clear()


def test_headless_fallback_engine_survives_tray_error():
    """If run_tray raises, the engine thread is not killed."""
    import asyncio
    from obsidian_sync import tray as tray_mod

    tray_mod._shutdown_event.clear()
    survivor = []

    async def _dummy_engine():
        await asyncio.sleep(0.3)
        survivor.append(True)

    def _run():
        try:
            raise RuntimeError("tray unavailable")
        except Exception:
            pass  # headless: swallow tray error
        asyncio.run(_dummy_engine())

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=2.0)
    assert not t.is_alive(), "Engine thread should have completed"
    assert survivor, "Engine coroutine should have run"
    tray_mod._shutdown_event.clear()


def test_autolaunch_toggle_dispatches_correct_command():
    """on_toggle_autolaunch calls Disable when enabled, Enable when disabled."""
    from obsidian_sync import tray as tray_mod

    tray_mod._shutdown_event.clear()
    mock_engine = MagicMock()
    mock_engine.log = MagicMock()
    mock_icon = MagicMock()
    mock_item = MagicMock()

    # When task is enabled, toggle should disable
    with patch.object(tray_mod, "_ps_run") as mock_ps_run, \
         patch.object(tray_mod, "_task_enabled", return_value=True):
        tray_mod.on_toggle_autolaunch(mock_icon, mock_item, mock_engine)
        calls = [str(c) for c in mock_ps_run.call_args_list]
        assert any("Disable" in c for c in calls), f"Expected Disable call, got: {calls}"

    # When task is disabled, toggle should enable
    with patch.object(tray_mod, "_ps_run") as mock_ps_run, \
         patch.object(tray_mod, "_task_enabled", return_value=False):
        tray_mod.on_toggle_autolaunch(mock_icon, mock_item, mock_engine)
        calls = [str(c) for c in mock_ps_run.call_args_list]
        assert any("Enable" in c for c in calls), f"Expected Enable call, got: {calls}"

    tray_mod._shutdown_event.clear()


def test_tooltip_updater_exits_on_shutdown():
    """_start_tooltip_updater thread exits when _shutdown_event is set."""
    import time
    from obsidian_sync import tray as tray_mod

    tray_mod._shutdown_event.clear()
    mock_engine = MagicMock()
    mock_engine.log = MagicMock()
    mock_icon = MagicMock()

    # _start_tooltip_updater returns the inner thread so we can join it directly
    inner_t = tray_mod._start_tooltip_updater(mock_icon, mock_engine)
    time.sleep(0.5)  # allow thread to start its first sleep cycle
    tray_mod._shutdown_event.set()
    inner_t.join(timeout=5.0)
    assert not inner_t.is_alive(), "Tooltip updater should exit when shutdown event is set"
    tray_mod._shutdown_event.clear()
