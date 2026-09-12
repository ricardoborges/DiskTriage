# DiskTriage

A simple CLI tool to reclaim space on your Windows `C:` drive safely.

It checks SSD health, tracks down bloat (dev tools, AI models, package caches, game stores), and helps you either delete it or move it to another drive — with an interactive terminal menu and built-in safety checks.

Built after a full boot SSD (2.7% free space) caused 1.5-second disk read freezes and triggered a Windows `0x1E_C0000006` (`nt!HvpGetCellPaged`) blue screen.

---

## Quick Start

```powershell
git clone https://github.com/ricardoborges/DiskTriage.git
cd DiskTriage

# Install dependencies and the `disktriage` CLI
pip install -e .
```

Run it:
```powershell
disktriage
```

> **Tip:** Run PowerShell as Administrator to see physical SSD read/write latency counters via `Get-StorageReliabilityCounter`.

---

## What It Does

1. **System Health**: Checks free space across drives, SSD latency, pagefile location, and recent Windows BSOD bugchecks (last 90 days).
2. **Cache Catalog**: Scans 50+ known dev and gaming caches (`pip`, `npm`, `cargo`, `docker`, `huggingface`, `pyenv`, `gradle`, `steam`, etc.).
3. **Smart Discovery**: Finds large unexpected folders in your user profile and `AppData`.
4. **Actionable Fixes**:
   - **Delete**: Safely wipe disposable, rebuildable caches.
   - **Move + Env Var**: Move folder to another drive (e.g. `D:`) and update user environment variable in registry (`HKCU\Environment`).
   - **Move + NTFS Junction**: Move folder and create an NTFS directory junction (`mklink /J`), keeping full tracking and 1-click rollback.
   - **Scan Persistence**: Remembers scan results so you don't have to wait for rescans every time you launch.

---

## CLI Options

```powershell
disktriage                  # Interactive menu (arrow keys + Enter)
disktriage --health         # Health check only (space, latency, BSODs)
disktriage --scan --drive D # Auto-scan and suggest D: as target drive
disktriage --min-gb 1.0     # Only show items larger than 1 GB
disktriage --lang pt-BR     # Force Portuguese (Brasil)
disktriage --lang en-US     # Force English (US)
```

---

## Multi-Language Support (i18n)

DiskTriage supports **Português (Brasil)** (default) and **English (US)**.
- On your first run, DiskTriage will prompt you to choose your preferred language and remember it for subsequent runs.
- You can switch languages at any time from the Main Menu (`Option 9`) or by passing the `--lang <codecode>` CLI parameter.

---

## Safety First

- **Explicit confirmation**: You must type the item name to delete; no accidental single-key deletes.
- **Protected paths**: `WinSxS`, `System32`, `Windows\Installer`, and `Program Files` are strictly blocked.
- **Safe file moves**: Multi-threaded `robocopy` with pre-flight destination free space checks. Source files are only removed after the copy verifies successfully.
- **No symlink loops**: Never recursively follows junctions or symlinks.

---

## License

GPL-3.0
