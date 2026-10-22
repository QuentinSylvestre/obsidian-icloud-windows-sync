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
    """on_quit: thread for Stop-ScheduledTask is STARTED (thread.start called) before
    icon.stop() is called — verifying F-05 code ordering, not background execution order."""
    import time
    from obsidian_sync import tray as tray_mod

    tray_mod._shutdown_event.clear()
    mock_engine = MagicMock()
    mock_engine.log = MagicMock()
    mock_shutdown = MagicMock()
    mock_icon = MagicMock()
    mock_item = MagicMock()

    call_order = []
    captured = {}

    def capturing_MenuItem(text, action=None, **kwargs):
        m = MagicMock()
        m.text = text
        captured[str(text)] = action
        return m

    orig_thread_start = threading.Thread.start

    def recording_thread_start(self):
        # Record daemon-thread start; don't actually start thread to avoid ps_run call
        call_order.append("thread_started")
        # Do start so the daemon thread runs (its target is ps_run which is also patched)
        orig_thread_start(self)

    mock_icon.stop.side_effect = lambda: call_order.append("icon_stop")

    with patch.object(pystray, "MenuItem", side_effect=capturing_MenuItem), \
         patch.object(pystray, "Menu", return_value=MagicMock()), \
         patch.object(tray_mod, "_ps_run") as mock_ps_run, \
         patch.object(tray_mod, "_task_enabled", return_value=True), \
         patch.object(threading.Thread, "start", recording_thread_start):
        tray_mod._build_menu(mock_engine, mock_shutdown)
        assert "Quit" in captured, "Could not find quit callback"
        on_quit = captured["Quit"]
        on_quit(mock_icon, mock_item)
        time.sleep(0.1)  # wait for background thread to call _ps_run

    assert tray_mod._shutdown_event.is_set()
    mock_shutdown.assert_called_once()
    assert "icon_stop" in call_order, "icon.stop() was not called"
    assert "thread_started" in call_order, "Stop-ScheduledTask daemon thread was not started"

    # F-05: thread must be STARTED before icon.stop() is CALLED (code ordering check)
    thread_pos = call_order.index("thread_started")
    stop_pos = call_order.index("icon_stop")
    assert thread_pos < stop_pos, (
        f"F-05 violation: Stop-ScheduledTask thread.start() must precede icon.stop() call. "
        f"Got order: {call_order}"
    )

    # Verify Stop-ScheduledTask PS command was dispatched
    calls = [str(c) for c in mock_ps_run.call_args_list]
    assert any("Stop-ScheduledTask" in c for c in calls), \
        f"Expected Stop-ScheduledTask _ps_run call, got: {calls}"
    tray_mod._shutdown_event.clear()


def test_autolaunch_toggle_invalidates_cache():
    """on_toggle_autolaunch resets _task_state_cache after dispatching the PS command (C-01)."""
    from obsidian_sync import tray as tray_mod

    tray_mod._shutdown_event.clear()
    mock_engine = MagicMock()
    mock_engine.log = MagicMock()

    # Pre-seed a cache value so we can verify it is cleared
    tray_mod._task_state_cache = "Ready"
    tray_mod._task_state_cache_time = 9999.0

    with patch.object(tray_mod, "_ps_run"), \
         patch.object(tray_mod, "_task_enabled", return_value=True):
        tray_mod.on_toggle_autolaunch(MagicMock(), MagicMock(), mock_engine)

    assert tray_mod._task_state_cache is None, (
        "Cache must be cleared after toggle so the next menu render reflects new state"
    )
    assert tray_mod._task_state_cache_time == 0.0

    tray_mod._shutdown_event.clear()


def test_headless_fallback_engine_survives_tray_error():
    """SC-5: __main__.main() contains engine_thread.join() with no timeout for the headless fallback.
    Verified by source inspection — the except branch must call join() without timeout=N,
    so that the main thread stays alive indefinitely when run_tray raises."""
    import inspect
    import obsidian_sync.__main__ as m
    src = inspect.getsource(m.main)
    # SC-5 contract: engine_thread.join() without timeout= must exist in main()
    # (not join(timeout=10) which would kill the engine after 10 seconds)
    assert any(
        "engine_thread.join()" in line and "timeout=" not in line
        for line in src.splitlines()
        if not line.strip().startswith("#")  # exclude comment-only lines
    ), (
        "SC-5 contract violated: engine_thread.join() with no timeout not found in __main__.main(). "
        "The headless fallback requires an unbounded join to keep the main thread alive indefinitely."
    )


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
