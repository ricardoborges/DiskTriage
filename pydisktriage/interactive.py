"""Navegação interativa por teclado para menus e seleção de itens (setas cima/baixo e Enter)."""

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

try:
    import msvcrt
except ImportError:
    msvcrt = None  # type: ignore[assignment]


def _read_key() -> str:
    """Lê uma tecla no terminal Windows. Devolve 'UP', 'DOWN', 'ENTER', 'ESC' ou o caractere digitado."""
    if not msvcrt:
        return ""

    ch = msvcrt.getwch()

    # Teclas especiais no Windows (setas, Home, End, Delete, etc.)
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
    """Renderiza a tabela de menu com a linha ativa destacada de forma contínua."""
    t = Table(box=None, padding=(0, 0), show_header=False)
    t.add_column("Cursor", width=3)
    t.add_column("Item")

    for i, (key, label) in enumerate(options):
        if i == selected_idx:
            t.add_row(
                Text(" > ", style="bold bright_cyan"),
                Text(f" {key:>2}  {label} ", style="bold bright_white on blue"),
            )
        else:
            t.add_row(
                Text("   "),
                Text(f" {key:>2}  ", style="bold cyan") + Text(f"{label} ", style="white"),
            )
    return t


def select_menu(
    options: list[tuple[str, str]],
    title: str = "Menu",
    default_key: str | None = None,
) -> str:
    """Apresenta um menu navegável com setas (↑ / ↓) e confirmação por Enter.

    Permite também teclar diretamente o número da opção ou Esc para sair.
    Caso o terminal não seja interativo (ex.: testes ou scripts), recorre a Prompt.ask.
    """
    if not sys.stdin.isatty() or msvcrt is None:
        ui.console.print()
        ui.console.print(ui.menu_panel(options, title=title))
        choices = [k for k, _ in options]
        return Prompt.ask("Escolha", choices=choices, default=default_key or choices[0])

    # Encontra o índice inicial baseado no default_key
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
                # Se houver opção "0" (sair/voltar), seleciona ela; senão a última
                for k, _ in options:
                    if k == "0":
                        return "0"
                return options[-1][0]
            else:
                # Atalho direto pelo número ou letra
                for idx, (k, _) in enumerate(options):
                    if key.lower() == k.lower():
                        return k


def render_findings_table(
    findings: Sequence[Finding],
    selected_idx: int,
    title: str = "Selecione um item",
    window_size: int = 15,
) -> Table:
    """Renderiza a tabela de findings com a linha ativa destacada e paginação deslizante."""
    t = Table(title=title, title_style="bold", header_style="bold", box=None, padding=(0, 1))
    t.add_column(" ", width=2, justify="right")
    t.add_column("#", justify="right", width=3)
    t.add_column("Tamanho", justify="right", width=11)
    t.add_column("Item", width=18)
    t.add_column("Categoria", width=12)
    t.add_column("Caminho", overflow="fold")

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
            t.add_row(
                Text(" >", style="bold bright_cyan"),
                Text(f" {num_str} ", style="bold bright_white on blue"),
                Text(f" {size_str} ", style="bold bright_white on blue"),
                Text(f" {f.ident} ", style="bold bright_white on blue"),
                Text(f" {cat_label} ", style="bold bright_white on blue"),
                Text(f" {path_str} ", style="bold bright_white on blue"),
            )
        else:
            cat_style = CATEGORY_STYLE.get(f.kind, "white")
            t.add_row(
                Text("  "),
                Text(num_str, style="dim"),
                Text(size_str, style="bold" if f.gb >= 5 else ""),
                Text(f.ident),
                Text(cat_label, style=cat_style),
                Text(path_str, style="dim"),
            )
    return t


def select_finding(
    findings: list[Finding],
    title: str = "Itens encontrados",
) -> Finding | None:
    """Permite ao usuário navegar visualmente pela lista de findings e escolher um com as setas.

    Retorna o Finding selecionado ou None se o usuário teclar Esc ou voltar.
    """
    if not findings:
        return None

    if not sys.stdin.isatty() or msvcrt is None:
        ui.console.print()
        ui.console.print(ui.findings_table(findings, title))
        raw = Prompt.ask("Número do item (ou Enter para voltar)", default="")
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
    panel_title = f"{title} {hint}"

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
                # Digitação numérica opcional (1..len)
                num = int(key)
                if 1 <= num <= len(findings):
                    selected_idx = num - 1
