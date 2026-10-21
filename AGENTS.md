# AGENTS.md — obsidian-icloud-sync

## Doc & Test Guidelines

- Update README.md when adding user-facing features, new dependencies, or changes to the project structure.
- Update SETUP.md when operational setup steps change (Task Scheduler configuration, startup steps).
- Do not create new documentation files unless explicitly requested.
- Update existing tests when implementation changes affect their coverage.
- Do not introduce new test files unless the user requests them or a regression fix requires one.
- When the user requests something that contradicts these guidelines, apply the request AND propose a durable update to this section so future sessions follow the new policy.

## Terminology

- **Auto-launch**: whether the Task Scheduler task "Obsidian iCloud Sync" runs at logon, controlled via `Enable-ScheduledTask` / `Disable-ScheduledTask`. Rejected synonyms: "autostart", "startup shortcut" (those imply a `%APPDATA%\Startup\` folder `.lnk`, the mechanism used by SamWhispers and PowerAtlas; this project uses Task Scheduler instead).
