# Local Setup Notes

> The sync engine is written by [gursimar](https://github.com/gursimar/obsidian-icloud-windows-sync).
> This file documents an alternative Windows installation approach contributed by this fork.

This documents how to install and run the sync daemon on Windows using a project venv
and a direct `pythonw.exe` Task Scheduler action. It deviates from the upstream README
in three ways: a project venv instead of system Python, `pythonw.exe` launched directly
from Task Scheduler instead of the `conhost + powershell` wrapper the README describes,
and a system tray icon for status and control.

---

## Paths (fill in yours)

| Role | Example |
|---|---|
| Local vault (Obsidian opens this) | `C:\Users\<username>\Documents\qs-obsidian` |
| iCloud vault (iOS reads/writes this) | `C:\Users\<username>\iCloudDrive\iCloud~md~obsidian\<vault-name>` |
| History snapshots | `<this-repo>\history\` |
| Logs | `<this-repo>\logs\` |
| Config | `<this-repo>\my-config.yaml` |
| Venv | `<this-repo>\.venv\` |

`my-config.yaml`, `history/` and `logs/` are all gitignored locally via `.git/info/exclude`.

---

## Install

```powershell
cd <this-repo>
python -m venv .venv
.venv\Scripts\pip install .
```

Copy and edit the config:

```powershell
cp config.yaml my-config.yaml
# Edit my-config.yaml with your actual paths
```

---

## Task Scheduler setup

This approach uses `pythonw.exe` directly rather than the upstream README's
`conhost + powershell` wrapper. `pythonw.exe` is the windowless Python interpreter —
no console window, no Unicode/charmap encoding issues, one fewer process in the chain.

**To register the task** (run as your user, not admin — substituting your actual paths):

```powershell
$pythonw = "<this-repo>\.venv\Scripts\pythonw.exe"
$config  = "<this-repo>\my-config.yaml"
$syncDir = "<this-repo>"

$action   = New-ScheduledTaskAction -Execute $pythonw -Argument "-m obsidian_sync --config `"$config`"" -WorkingDirectory $syncDir
$trigger  = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$trigger.Delay = "PT1M"   # 1 minute after logon — gives iCloud time to connect
$settings = New-ScheduledTaskSettingsSet -RestartInterval (New-TimeSpan -Minutes 1) -RestartCount 99 -StartWhenAvailable

Register-ScheduledTask -TaskName "Obsidian iCloud Sync" -Action $action -Trigger $trigger -Settings $settings -RunLevel Limited -Force
```

Settings: restarts on crash up to 99 times at 1-minute intervals; starts as soon as
possible if the logon trigger was missed.

---

## Day-to-day management

```powershell
# Check status
(Get-ScheduledTask -TaskName "Obsidian iCloud Sync").State

# Start / stop / restart
Start-ScheduledTask  -TaskName "Obsidian iCloud Sync"
Stop-ScheduledTask   -TaskName "Obsidian iCloud Sync"
Stop-ScheduledTask   -TaskName "Obsidian iCloud Sync"; Start-ScheduledTask -TaskName "Obsidian iCloud Sync"

# Read latest log
Get-ChildItem ".\logs\*.log" | Sort-Object LastWriteTime -Descending | Select-Object -First 1 | Get-Content
```

---

## Updating

```powershell
git pull
.venv\Scripts\pip install .
Stop-ScheduledTask "Obsidian iCloud Sync"; Start-ScheduledTask "Obsidian iCloud Sync"
```

---

## Config notes

Key non-default settings used in `my-config.yaml`:

```yaml
ignore:
  dirs:
    - cache   # skips .obsidian/cache/ — auto-regenerated, no value syncing between devices
```

`workspace.json` and `workspace-mobile.json` are excluded by default in the package config
(`config.py`). Tab layouts are intentionally device-specific and should not sync.

---

## Tray Icon

When the sync daemon is running, a system tray icon appears in the Windows notification area.

**Status tooltip** — hover over the icon to see current status:
- "Syncing N files…" while files are being processed
- "Idle · Last sync HH:MM" after the most recent sync completes
- "Idle" if no sync has occurred yet in this session

**Menu items:**
- **Logs** — opens the current log file in the default text editor
- **Auto-launch** — toggles whether the Task Scheduler task "Obsidian iCloud Sync" starts
  at logon. Checked when the task is enabled; uses `Enable-ScheduledTask` /
  `Disable-ScheduledTask` under the hood. The toggle does not start or stop a running
  instance — it only controls future logon behaviour.
- **Quit** — cancels the sync engine, stops the tray icon, and stops the scheduled task
  (`Stop-ScheduledTask`)

---

## Desktop Shortcut

Phase 3 creates a shortcut at `%USERPROFILE%\Desktop\Obsidian Sync.lnk`.

Clicking the shortcut runs `Start-ScheduledTask -TaskName "Obsidian iCloud Sync"`, which
starts the sync service without opening a console window (the Task Scheduler task already
uses `pythonw.exe`).

> **Note:** The `IconLocation` path embedded in the shortcut points to the `icon.ico` file
> inside the cloned repository. If you move or rename the repo folder after the shortcut is
> created, the icon will go missing (the shortcut still works, but shows a generic icon).
> Re-run the shortcut creation step to fix it.

---

## Why this exists

Obsidian with a vault stored in `iCloudDrive` takes ~60 seconds to start on Windows.
The cause is iCloud for Windows' file system filter driver, which intercepts all I/O on
managed folders — even for locally-present files — to maintain sync state. "Always keep on
this device" (pinning files) does not remove the driver.

Moving the vault to a plain local folder drops startup to ~1 second. iOS still syncs via
iCloud natively; this daemon mirrors changes between the local copy and the iCloud copy,
keeping both sides current without Obsidian ever touching iCloud at runtime.
