# Obsidian iCloud Windows Sync

> **Original work by [gursimar](https://github.com/gursimar/obsidian-icloud-windows-sync).**
> This repository is a personal fork. All core sync engine code is written by gursimar.
> Additions in this fork: a tray icon and desktop shortcut; and [`SETUP.md`](SETUP.md),
> which documents an alternative Windows installation using a project venv and a direct
> `pythonw.exe` Task Scheduler action instead of the `conhost + powershell` wrapper in
> the original README.
> Raise issues and PRs on the [upstream repo](https://github.com/gursimar/obsidian-icloud-windows-sync).

---

A highly optimized, asynchronous, three-way sync engine designed to solve the notorious issues between Obsidian, iCloud Drive, and Windows.

![terminal image](assets/image.png)

## Installation & Setup
1. Install iCloud for Windows [Link](https://support.apple.com/en-ca/103232)
2. Clone the repository using `git clone https://github.com/QuentinSylvestre/obsidian-icloud-windows-sync.git`
3. Install as a package:
   ```bash
   pip install .
   ```
4. Copy and edit the config file with your actual paths:
   ```bash
   cp config.yaml my-config.yaml
   ```
   ```yaml
   paths:
     local_vault: "C:\\Obsidian\\Vault"
     icloud_vault: "C:\\Users\\user\\iCloudDrive\\iCloud~md~obsidian"
     history_dir: "C:\\Obsidian\\History"
     logs_dir: "C:\\Obsidian\\Logs"
   ```
5. Run:
   ```bash
   obsidian-sync --config config.yaml
   ```
   Or directly:
   ```bash
   python -m obsidian_sync --config config.yaml
   ```

> If you have any trouble in setup, raise issue on git.
> Run natively on Windows, not WSL — iCloud placeholders behave incorrectly under WSL.

## Project Structure

```
obsidian_sync/
├── __main__.py      # Entry point — tray on main thread, sync loop on daemon thread
├── config.py        # YAML config loading & validation
├── logger.py        # Structured logging (console + file)
├── disk_io.py       # Atomic copy, delete, Windows API
├── hasher.py        # SHA-256 hashing with mtime/size cache
├── icloud_status.py # Windows file attributes for iCloud sync state
├── duplicates.py    # Startup duplicate/conflict scanner
├── sync_engine.py   # File watchers + per-file event queues
├── sync_worker.py   # Three-way sync logic with atomic operations
├── tray.py          # System tray icon, status tooltip, and control menu
└── assets/          # Bundled runtime icons (PNG + ICO)
```

### Modes of Operation

| Mode | Config | Behavior |
|---|---|---|
| **One-Shot** | `run_continuously: false` | Single full pass, then exits. Use with Task Scheduler. Tray icon appears; exits automatically when sync pass completes (run_continuously not enforced in engine). |
| **Daemon** | `run_continuously: true` | Runs continuously, polling every `poll_interval` seconds. Displays a system tray icon; auto-launch toggle and Quit available in the tray menu |

#### Autostart via Task Scheduler

> **Alternative approach (this fork):** see [`SETUP.md`](SETUP.md) for a setup that uses
> `pythonw.exe` directly from a project venv — no `run-sync.ps1` wrapper needed, no console
> window, and no charmap encoding issues.

Create `run-sync.ps1`:
```powershell
& py -m obsidian_sync --config "$PSScriptRoot\config.yaml"
```

In `taskschd.msc` → Create Task:
- **Triggers**: At log on, delay 1 minute
- **Actions**: `C:\Windows\System32\conhost.exe` with arguments:
   `--headless powershell.exe -WindowStyle Hidden -NoProfile -NonInteractive -file "C:\PATH\TO\run-sync.ps1"`
- **Settings**: Restart on failure every 1 minute, up to 99 times

---

## How It Works

Three locations are tracked per file:
- **L** = Local vault (`local_vault`)
- **C** = iCloud copy (`icloud_vault`)
- **H** = History snapshot (`history_dir`) — last known good state

Each sync pass walks the union of all three directories and applies these rules:

| State | Action |
|---|---|
| `L` only | New local file → stabilize → push to `C`, seed `H` |
| `C` only | New remote file → stabilize → restore to `L`, seed `H` |
| `L == C == H` | Nothing to do |
| `L != H`, `C == H` | Local changed → push `L` → `C`, update `H` |
| `C != H`, `L == H` | Remote changed → restore `L` from `C`, update `H` |
| `L != H`, `C != H` | Conflict → stabilize → pick newer by mtime, backup loser as `_CONFLICT_TIMESTAMP` |
| `L` missing, `C == H` | Confirmed local delete → remove `C` and `H` |
| `L` missing, `C != H` | Remote changed → restore `L` from `C` |
| `C` missing, `L == H` | Confirmed remote delete → remove `L` and `H` |
| `C` missing, `L != H` | Local changed → push `L` → `C` |
| `L` and `C` missing | Remove orphaned `H` |

### Key Protections

- **Per-file event queues**: each file has dedicated queue and worker task for complete isolation
- **Atomic snapshot propagation**: single source read to temp file, then fan out to all destinations
- **Stabilization** (`stability_window`): waits before acting on creates/deletes to avoid reacting to mid-save or rename workflows
- **Conflict wait** (`stabilize_wait`): longer wait on both-changed scenarios to detect still-active edits
- **Atomic writes**: write to `.tmp` then `os.replace()`, with retries and Win32 `MoveFileEx` fallback
- **Conflict duplicates**: losing side saved as `filename_CONFLICT_TIMESTAMP.ext` before overwrite

---

## Tuning

All settings live in `config.yaml`:

| Setting | Default | Notes |
|---|---|---|
| `stability_window` | `3s` | Increase for slow disks or large files |
| `stabilize_wait` | `8s` | Increase if you edit very slowly |
| `tiny_threshold` | `8 bytes` | Minimum file size to sync (prevents empty/placeholder files) |
| `max_concurrent_io` | `50` | Maximum concurrent I/O operations |
| `ignore.patterns` | `[]` | Exclude folders like `.obsidian/cache` |

---

## Dependencies
- Python ≥ 3.11
- pystray ≥ 0.19.5
- Pillow ≥ 10.0.0
- watchdog ≥ 4.0.0
- aiofiles ≥ 23.2.1