"""Disk scanner: measures catalog entries and discovers uncataloged directories."""

from __future__ import annotations

import stat
from pathlib import Path
from typing import Callable, Iterable

from .catalog import Finding, Target, build_catalog
from .fsutil import iter_files, measure

StatusFn = Callable[[str, int, int], None]
"""Receives (label, current_index, total) to update scan progress."""


def scan_catalog(home: Path, min_gb: float = 1.0,
                 status: StatusFn | None = None) -> list[Finding]:
    """Measure each catalog target that exists on the system."""
    targets: list[Target] = build_catalog(home)
    found: list[Finding] = []

    for i, t in enumerate(targets, start=1):
        if status:
            status(t.ident, i, len(targets))
        if not t.path.exists():
            continue

        try:
            st = t.path.lstat()
        except OSError:
            continue

        is_file = not stat.S_ISDIR(st.st_mode)
        m = measure(t.path)
        if m.size / 1024**3 < min_gb:
            continue

        found.append(Finding(
            ident=t.ident, path=t.path, kind=t.kind, size=m.size, files=m.files,
            is_file=is_file, env_var=t.env_var, clean_cmd=t.clean_cmd, note=t.note,
        ))

    found.sort(key=lambda f: f.size, reverse=True)
    return found


def scan_discovery(home: Path, known: Iterable[Finding], min_gb: float = 1.0,
                   status: StatusFn | None = None) -> list[Finding]:
    """Search for large folders not covered by the predefined catalog.

    Provides deep discovery for newly installed tools and uncataloged directories.
    """
    known_paths = {str(f.path).rstrip("\\").lower() for f in known}
    roots = [home / "AppData" / "Local", home / "AppData" / "Roaming", home]

    candidates: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        try:
            for entry in root.iterdir():
                if not entry.is_dir():
                    continue
                candidates.append(entry)
        except OSError:
            continue

    results: list[Finding] = []
    for i, d in enumerate(candidates, start=1):
        if status:
            status(d.name, i, len(candidates))

        low = str(d).rstrip("\\").lower()
        if low in known_paths:
            continue
        # Skip if directory is parent of an already measured catalog entry
        # to avoid double-counting bytes in the summary totals.
        if any(k.startswith(low + "\\") for k in known_paths):
            continue

        m = measure(d)
        if m.size / 1024**3 < min_gb:
            continue

        results.append(Finding(
            ident=d.name, path=d, kind="revisar", size=m.size, files=m.files,
            is_file=False, note="Discovered by generic scan", discovered=True,
        ))

    results.sort(key=lambda f: f.size, reverse=True)
    return results


def scan_large_files(home: Path, min_gb: float = 2.0,
                     limit: int = 25) -> list[tuple[Path, int]]:
    """Scan for standalone large files (e.g. .vhdx, .gguf, VM images, loose AI models)."""
    threshold = int(min_gb * 1024**3)
    big = [(p, s) for p, s in iter_files(home) if s >= threshold]
    big.sort(key=lambda t: t[1], reverse=True)
    return big[:limit]


def reclaimable(findings: Iterable[Finding]) -> int:
    """Calculate total reclaimable bytes without requiring manual review (disposable + relocatable)."""
    return sum(f.size for f in findings if f.kind != "revisar")
