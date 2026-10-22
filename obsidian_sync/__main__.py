import asyncio
import argparse
import os
import sys
import threading

from .config import SyncConfig
from .logger import SyncLogger
from .hasher import FileHasher
from .disk_io import DiskIO
from .duplicates import DuplicateScanner
from .sync_engine import SyncEngine
from obsidian_sync.tray import run_tray


def main():
    """
    Entry point for the Obsidian iCloud Windows Sync.
    """
    parser = argparse.ArgumentParser(description="Obsidian iCloud Windows Sync")
    parser.add_argument("-c", "--config", default="config.yaml", help="Path to config YAML file (default: config.yaml)")
    args = parser.parse_args()

    try:
        config = SyncConfig.from_yaml(args.config)
    except Exception as e:
        print(f"Unexpected error while loading config from {args.config}: {e}", file=sys.stderr)
        sys.exit(1)

    logger = SyncLogger(config)
    hasher = FileHasher(config, logger)
    disk_io = DiskIO(config, logger)
    duplicates = DuplicateScanner(config, logger, disk_io)
    duplicates.scan_and_clean()
    engine = SyncEngine(config, logger, hasher, disk_io, duplicates)

    _engine_ready = threading.Event()
    loop = asyncio.new_event_loop()
    _engine_task: list[asyncio.Task] = []

    def _run_engine():
        asyncio.set_event_loop(loop)
        t = loop.create_task(engine.run())
        _engine_task.append(t)
        _engine_ready.set()
        try:
            loop.run_until_complete(t)
        except asyncio.CancelledError:
            pass
        finally:
            loop.close()

    engine_thread = threading.Thread(target=_run_engine, daemon=True)
    engine_thread.start()
    _engine_ready.wait(timeout=5)

    def _shutdown_engine():
        if _engine_task and not loop.is_closed():
            try:
                loop.call_soon_threadsafe(_engine_task[0].cancel)
            except RuntimeError:
                pass

    try:
        run_tray(engine, config, _shutdown_engine)
        engine_thread.join(timeout=10)
    except Exception:
        engine.log.warn("TRAY", "Tray failed to start, running headlessly")
        engine_thread.join()   # no timeout — SC-5 headless contract


if __name__ == "__main__":
    main()
