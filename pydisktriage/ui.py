"""Presentation layer: console output, banners, tables, panels, and status glyphs.

All terminal drawing and formatting functions live in this module.
"""

from __future__ import annotations

import sys
from pathlib import Path

from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from .catalog import CATEGORY_LABEL, CATEGORY_ORDER, CATEGORY_STYLE, Finding
from .fsutil import human
from .health import Bugcheck, DiskLatency, VolumeInfo
from .i18n import t


def _harden_stdout() -> None:
    """Avoid UnicodeEncodeError in legacy Windows consoles (cp1252/cp850).

    Prevents fatal encoding exceptions on older cmd.exe windows.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def _unicode_ok() -> bool:
    """Determine whether the terminal supports standard Unicode symbols."""
    enc = getattr(sys.stdout, "encoding", None) or "ascii"
    try:
        "✓✗·—↑↓".encode(enc)
        return True
    except (LookupError, UnicodeEncodeError):
        return False


_harden_stdout()
UNICODE = _unicode_ok()

GLYPH_OK = "✓" if UNICODE else "+"
GLYPH_ERR = "✗" if UNICODE else "x"
GLYPH_INFO = "·" if UNICODE else "-"

console = Console()

BANNER = r"""
 ___  _      _     _____    _
|   \(_)___ | |__ |_   _| _(_)__ _ __ _ ___
| |) | (_-< | / /   | || '_| / _` / _` / -_)
|___/|_/__/ |_\_\   |_||_| |_\__,_\__, \___|
                                  |___/
"""


def show_banner() -> None:
    """Display the application ASCII banner and localized tagline."""
    console.print(Text(BANNER, style="bold cyan"))
    console.print(
        Align.center(Text(t("app.tagline"), style="dim")))
    console.print()


def volumes_table(vols: list[VolumeInfo]) -> Table:
    """Render a table showing free and total space for all drive volumes."""
    t_vol = Table(title=t("health.volumes_title"), title_style="bold", header_style="bold",
                  box=None, padding=(0, 2))
    t_vol.add_column(t("health.col_drive"))
    t_vol.add_column(t("health.col_label"))
    t_vol.add_column(t("health.col_free"), justify="right")
    t_vol.add_column(t("health.col_total"), justify="right")
    t_vol.add_column(t("health.col_pct_free"), justify="right")
    t_vol.add_column(t("health.col_status"))

    for v in vols:
        style = "green"
        if v.verdict == "apertado":
            style = "yellow"
        if v.verdict == "CRÍTICO":
            style = "bold red"
        t_vol.add_row(f"{v.letter}:", v.label, human(v.free), human(v.total),
                      f"{v.pct_free}%", Text(v.verdict_label, style=style))
    return t_vol


def latency_table(disks: list[DiskLatency]) -> Table:
    """Render a table displaying maximum physical SSD/HDD latency counters."""
    t_lat = Table(title=t("health.latency_title"), title_style="bold",
                  header_style="bold", box=None, padding=(0, 2))
    t_lat.add_column(t("health.col_disk"))
    t_lat.add_column(t("health.col_read"), justify="right")
    t_lat.add_column(t("health.col_write"), justify="right")
    t_lat.add_column(t("health.col_flush"), justify="right")
    t_lat.add_column(t("health.col_temp"), justify="right")
    t_lat.add_column(t("health.col_wear"), justify="right")

    def ms(value: int | None) -> Text:
        if value is None:
            return Text("—", style="dim")
        style = "green"
        if value > 100:
            style = "yellow"
        if value > 500:
            style = "bold red"
        return Text(f"{value} ms", style=style)

    for d in disks:
        t_lat.add_row(
            d.name, ms(d.read_ms), ms(d.write_ms), ms(d.flush_ms),
            f"{d.temp_c}°C" if d.temp_c is not None else "—",
            f"{d.wear}" if d.wear is not None else "—",
        )
    return t_lat


def bugchecks_table(bugs: list[Bugcheck]) -> Table:
    """Render a table of recent Windows BSOD bugcheck crash events."""
    t_bugs = Table(title=t("health.bugchecks_title", count=len(bugs)), title_style="bold",
                   header_style="bold", box=None, padding=(0, 2))
    t_bugs.add_column(t("health.col_when"))
    t_bugs.add_column(t("health.col_code"))
    t_bugs.add_column(t("health.col_meaning"))
    for b in bugs:
        t_bugs.add_row(b.when, Text(b.code, style="bold red"),
                       Text(b.meaning or "—", style="dim"))
    return t_bugs


def findings_table(findings: list[Finding], title: str,
                   numbered_from: int = 1) -> Table:
    """Render a table of findings found during scanning or loaded from cache."""
    t_find = Table(title=title, title_style="bold", header_style="bold",
                   box=None, padding=(0, 2), show_lines=False)
    t_find.add_column("#", justify="right", style="dim")
    t_find.add_column(t("scan.col_size"), justify="right")
    t_find.add_column(t("scan.col_item"))
    t_find.add_column(t("scan.col_category"))
    t_find.add_column(t("scan.col_path"), overflow="fold")
    t_find.add_column(t("scan.col_env_var"), style="cyan")

    for i, f in enumerate(findings, start=numbered_from):
        cat = Text(CATEGORY_LABEL.get(f.kind, f.kind),
                   style=CATEGORY_STYLE.get(f.kind, "white"))
        size_style = "bold" if f.gb >= 5 else ""
        t_find.add_row(
            str(i),
            Text(human(f.size), style=size_style),
            f.ident,
            cat,
            str(f.path),
            f.env_var or "—",
        )
    return t_find


def summary_panel(findings: list[Finding]) -> Panel:
    """Render summary panel showing total space per category and human-free reclaimable total."""
    rows = Table(box=None, padding=(0, 2), show_header=True, header_style="bold")
    rows.add_column(t("scan.col_category"))
    rows.add_column(t("scan.found_items_title"), justify="right")
    rows.add_column(t("health.col_total"), justify="right")

    total_reclaim = 0
    for kind in CATEGORY_ORDER:
        subset = [f for f in findings if f.kind == kind]
        if not subset:
            continue
        size = sum(f.size for f in subset)
        if kind != "revisar":
            total_reclaim += size
        rows.add_row(
            Text(CATEGORY_LABEL[kind], style=CATEGORY_STYLE[kind]),
            str(len(subset)), human(size),
        )

    body = Group(
        rows,
        Text(""),
        Text(t("scan.summary_reclaimable", size=human(total_reclaim)),
             style="bold green"),
    )
    return Panel(body, title=t("scan.summary_title"), border_style="cyan")


def menu_panel(options: list[tuple[str, str]], title: str) -> Panel:
    """Render a fallback menu panel for non-interactive terminal environments."""
    t_menu = Table(box=None, padding=(0, 2), show_header=False)
    t_menu.add_column("Tecla", style="bold cyan", justify="right")
    t_menu.add_column("Ação")
    for key, label in options:
        t_menu.add_row(key, label)
    return Panel(t_menu, title=title, border_style="cyan", expand=False)


def rule(text: str) -> None:
    """Print a styled section divider rule across the terminal."""
    console.print()
    console.print(Rule(Text(text, style="bold cyan"), style="cyan"))


def warn(message: str) -> None:
    """Print a warning message."""
    console.print(f"[bold yellow]![/bold yellow] {message}")


def error(message: str) -> None:
    """Print an error message."""
    console.print(f"[bold red]{GLYPH_ERR}[/bold red] {message}")


def ok(message: str) -> None:
    """Print a success confirmation message."""
    console.print(f"[bold green]{GLYPH_OK}[/bold green] {message}")


def info(message: str) -> None:
    """Print an informational message."""
    console.print(f"[dim]{GLYPH_INFO}[/dim] {message}")


def large_files_table(files: list[tuple[Path, int]]) -> Table:
    """Render a table of large standalone files discovered during scan."""
    t_lf = Table(title=t("scan.large_files_title"), title_style="bold",
                 header_style="bold", box=None, padding=(0, 2))
    t_lf.add_column(t("scan.col_size"), justify="right")
    t_lf.add_column(t("scan.col_file"), overflow="fold")
    for path, size in files:
        t_lf.add_row(Text(human(size), style="bold"), str(path))
    return t_lf
