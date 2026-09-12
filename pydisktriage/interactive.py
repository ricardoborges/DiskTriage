"""Interactive keyboard navigation for menus and item selection (arrow keys and Enter)."""

from __future__ import annotations

import sys
from typing import Sequence

from rich.live import Live
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from . import ui
from .catalog import CATEGORY_LABEL, CATEGORY_STYLE, Finding
from .fsutil import human
from .i18n import t

try:
    import msvcrt
except ImportError:
    msvcrt = None  # type: ignore[assignment]


def _read_key() -> str:
    """Read a single key press in Windows terminal. Returns 'UP', 'DOWN', 'ENTER', 'ESC', or character."""
    if not msvcrt:
        return ""

    ch = msvcrt.getwch()

    # Special keys in Windows console (arrow keys, Home, End, Delete, etc.)
    if ch in ("\x00", "\xe0"):
        ch2 = msvcrt.getwch()
        if ch2 == "H":
            return "UP"
        if ch2 == "P":
            return "DOWN"
        if ch2 == "K":
            return "LEFT"
        if ch2 == "M":
            return "RIGHT"
        if ch2 == "G":
            return "HOME"
        if ch2 == "O":
            return "END"
        return ""

    if ch in ("\r", "\n"):
        return "ENTER"
    if ch == "\x1b":
        return "ESC"
    if ch == "\x03":
        raise KeyboardInterrupt
    return ch


def render_menu_table(options: list[tuple[str, str]], selected_idx: int) -> Table:
    """Render the menu table with the active item highlighted with a cursor marker."""
    t_table = Table(box=None, padding=(0, 0), show_header=False)
    t_table.add_column("Cursor", width=3)
    t_table.add_column("Item")

    for i, (key, label) in enumerate(options):
        if i == selected_idx:
            t_table.add_row(
                Text(" > ", style="bold bright_cyan"),
                Text(f" {key:>2}  {label} ", style="bold bright_white on blue"),
            )
        else:
            t_table.add_row(
                Text("   "),
                Text(f" {key:>2}  ", style="bold cyan") + Text(f"{label} ", style="white"),
            )
    return t_table


def select_menu(
    options: list[tuple[str, str]],
    title: str = "Menu",
    default_key: str | None = None,
) -> str:
    """Present an interactive menu navigable with arrow keys (↑ / ↓) and confirmed with Enter.

    Also supports typing option shortcut numbers directly or Esc to exit.
    Falls back to Prompt.ask if stdin is non-interactive (e.g. scripts or tests).
    """
    if not sys.stdin.isatty() or msvcrt is None:
        ui.console.print()
        ui.console.print(ui.menu_panel(options, title=title))
        choices = [k for k, _ in options]
        return Prompt.ask(t("interactive.choice_prompt"), choices=choices, default=default_key or choices[0])

    selected_idx = 0
    if default_key:
        for idx, (k, _) in enumerate(options):
            if k == default_key:
                selected_idx = idx
                break

    hint = "(↑/↓ e Enter)" if ui.UNICODE else "(Setas e Enter)"
    panel_title = f"{title} {hint}"

    with Live(
        Panel(render_menu_table(options, selected_idx), title=panel_title, border_style="cyan", expand=False),
        console=ui.console,
        auto_refresh=False,
        transient=True,
    ) as live:
        while True:
            live.update(
                Panel(render_menu_table(options, selected_idx), title=panel_title, border_style="cyan", expand=False),
                refresh=True,
            )

            key = _read_key()

            if key == "UP":
                selected_idx = (selected_idx - 1) % len(options)
            elif key == "DOWN":
                selected_idx = (selected_idx + 1) % len(options)
            elif key == "HOME":
                selected_idx = 0
            elif key == "END":
                selected_idx = len(options) - 1
            elif key == "ENTER":
                return options[selected_idx][0]
            elif key in ("ESC", "q", "Q"):
                # If there is a "0" (back/exit) option, select it; otherwise select the last option
                for k, _ in options:
                    if k == "0":
                        return "0"
                return options[-1][0]
            else:
                # Direct numeric/alphanumeric shortcut
                for idx, (k, _) in enumerate(options):
                    if key.lower() == k.lower():
                        return k


def render_findings_table(
    findings: Sequence[Finding],
    selected_idx: int,
    title: str = "Selecione um item",
    window_size: int = 15,
) -> Table:
    """Render findings table with active row highlighted and sliding window pagination."""
    t_find = Table(title=title, title_style="bold", header_style="bold", box=None, padding=(0, 1))
    t_find.add_column(" ", width=2, justify="right")
    t_find.add_column("#", justify="right", width=3)
    t_find.add_column(t("scan.col_size"), justify="right", width=11)
    t_find.add_column(t("scan.col_item"), width=18)
    t_find.add_column(t("scan.col_category"), width=12)
    t_find.add_column(t("scan.col_path"), overflow="fold")

    total = len(findings)
    if total <= window_size:
        start_idx = 0
        end_idx = total
    else:
        half = window_size // 2
        start_idx = max(0, selected_idx - half)
        end_idx = start_idx + window_size
        if end_idx > total:
            end_idx = total
            start_idx = max(0, end_idx - window_size)

    for i in range(start_idx, end_idx):
        f = findings[i]
        num_str = str(i + 1)
        size_str = human(f.size)
        cat_label = CATEGORY_LABEL.get(f.kind, f.kind)
        path_str = str(f.path)

        if i == selected_idx:
            t_find.add_row(
                Text(" >", style="bold bright_cyan"),
                Text(f" {num_str} ", style="bold bright_white on blue"),
                Text(f" {size_str} ", style="bold bright_white on blue"),
                Text(f" {f.ident} ", style="bold bright_white on blue"),
                Text(f" {cat_label} ", style="bold bright_white on blue"),
                Text(f" {path_str} ", style="bold bright_white on blue"),
            )
        else:
            cat_style = CATEGORY_STYLE.get(f.kind, "white")
            t_find.add_row(
                Text("  "),
                Text(num_str, style="dim"),
                Text(size_str, style="bold" if f.gb >= 5 else ""),
                Text(f.ident),
                Text(cat_label, style=cat_style),
                Text(path_str, style="dim"),
            )
    return t_find


def select_finding(
    findings: list[Finding],
    title: str | None = None,
) -> Finding | None:
    """Allow the user to navigate the findings list interactively using arrow keys.

    Returns the selected Finding or None if the user presses Esc or cancels.
    """
    if not findings:
        return None

    display_title = title or t("interactive.select_item_title")

    if not sys.stdin.isatty() or msvcrt is None:
        ui.console.print()
        ui.console.print(ui.findings_table(findings, display_title))
        raw = Prompt.ask(t("interactive.choice_prompt"), default="")
        if not raw.strip():
            return None
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(findings):
                return findings[idx]
        except ValueError:
            pass
        return None

    hint = "(↑/↓ navegar, Enter escolher, Esc voltar)" if ui.UNICODE else "(Setas navegar, Enter escolher, Esc voltar)"
    panel_title = f"{display_title} {hint}"

    selected_idx = 0
    with Live(
        render_findings_table(findings, selected_idx, title=panel_title),
        console=ui.console,
        auto_refresh=False,
        transient=True,
    ) as live:
        while True:
            live.update(
                render_findings_table(findings, selected_idx, title=panel_title),
                refresh=True,
            )

            key = _read_key()

            if key == "UP":
                selected_idx = (selected_idx - 1) % len(findings)
            elif key == "DOWN":
                selected_idx = (selected_idx + 1) % len(findings)
            elif key == "HOME":
                selected_idx = 0
            elif key == "END":
                selected_idx = len(findings) - 1
            elif key == "ENTER":
                return findings[selected_idx]
            elif key in ("ESC", "q", "Q"):
                return None
            elif key.isdigit():
                # Direct numeric entry
                num = int(key)
                if 1 <= num <= len(findings):
                    selected_idx = num - 1
