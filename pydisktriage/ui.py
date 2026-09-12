"""Camada de apresentação: tudo que desenha na tela vive aqui."""

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


def _harden_stdout() -> None:
    """Evita UnicodeEncodeError em console legado (cp1252).

    Sem isso, um simples marcador de sucesso derruba o programa numa janela de
    cmd.exe antiga -- que e exatamente onde alguem vai rodar isto na primeira vez.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def _unicode_ok() -> bool:
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
    console.print(Text(BANNER, style="bold cyan"))
    console.print(
        Align.center(Text("triagem de disco para Windows  ·  o que apagar, o que mover",
                          style="dim")))
    console.print()


def volumes_table(vols: list[VolumeInfo]) -> Table:
    t = Table(title="Espaço por volume", title_style="bold", header_style="bold",
              box=None, padding=(0, 2))
    t.add_column("Unidade")
    t.add_column("Rótulo")
    t.add_column("Livre", justify="right")
    t.add_column("Total", justify="right")
    t.add_column("% livre", justify="right")
    t.add_column("Situação")

    for v in vols:
        style = "green"
        if v.verdict == "apertado":
            style = "yellow"
        if v.verdict == "CRÍTICO":
            style = "bold red"
        t.add_row(f"{v.letter}:", v.label, human(v.free), human(v.total),
                  f"{v.pct_free}%", Text(v.verdict, style=style))
    return t


def latency_table(disks: list[DiskLatency]) -> Table:
    t = Table(title="Latência máxima registrada", title_style="bold",
              header_style="bold", box=None, padding=(0, 2))
    t.add_column("Disco")
    t.add_column("Leitura", justify="right")
    t.add_column("Escrita", justify="right")
    t.add_column("Flush", justify="right")
    t.add_column("Temp", justify="right")
    t.add_column("Desgaste", justify="right")

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
        t.add_row(
            d.name, ms(d.read_ms), ms(d.write_ms), ms(d.flush_ms),
            f"{d.temp_c}°C" if d.temp_c is not None else "—",
            f"{d.wear}" if d.wear is not None else "—",
        )
    return t


def bugchecks_table(bugs: list[Bugcheck]) -> Table:
    t = Table(title=f"Telas azuis ({len(bugs)})", title_style="bold",
              header_style="bold", box=None, padding=(0, 2))
    t.add_column("Quando")
    t.add_column("Código")
    t.add_column("Significado")
    for b in bugs:
        t.add_row(b.when, Text(b.code, style="bold red"),
                  Text(b.meaning or "—", style="dim"))
    return t


def findings_table(findings: list[Finding], title: str,
                   numbered_from: int = 1) -> Table:
    t = Table(title=title, title_style="bold", header_style="bold",
              box=None, padding=(0, 2), show_lines=False)
    t.add_column("#", justify="right", style="dim")
    t.add_column("Tamanho", justify="right")
    t.add_column("Item")
    t.add_column("Categoria")
    t.add_column("Caminho", overflow="fold")
    t.add_column("Variável", style="cyan")

    for i, f in enumerate(findings, start=numbered_from):
        cat = Text(CATEGORY_LABEL.get(f.kind, f.kind),
                   style=CATEGORY_STYLE.get(f.kind, "white"))
        size_style = "bold" if f.gb >= 5 else ""
        t.add_row(
            str(i),
            Text(human(f.size), style=size_style),
            f.ident,
            cat,
            str(f.path),
            f.env_var or "—",
        )
    return t


def summary_panel(findings: list[Finding]) -> Panel:
    rows = Table(box=None, padding=(0, 2), show_header=True, header_style="bold")
    rows.add_column("Categoria")
    rows.add_column("Itens", justify="right")
    rows.add_column("Total", justify="right")

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
        Text(f"Recuperável sem julgamento humano: {human(total_reclaim)}",
             style="bold green"),
    )
    return Panel(body, title="Resumo", border_style="cyan")


def menu_panel(options: list[tuple[str, str]], title: str) -> Panel:
    t = Table(box=None, padding=(0, 2), show_header=False)
    t.add_column("Tecla", style="bold cyan", justify="right")
    t.add_column("Ação")
    for key, label in options:
        t.add_row(key, label)
    return Panel(t, title=title, border_style="cyan", expand=False)


def rule(text: str) -> None:
    console.print()
    console.print(Rule(Text(text, style="bold cyan"), style="cyan"))


def warn(message: str) -> None:
    console.print(f"[bold yellow]![/bold yellow] {message}")


def error(message: str) -> None:
    console.print(f"[bold red]{GLYPH_ERR}[/bold red] {message}")


def ok(message: str) -> None:
    console.print(f"[bold green]{GLYPH_OK}[/bold green] {message}")


def info(message: str) -> None:
    console.print(f"[dim]{GLYPH_INFO}[/dim] {message}")


def large_files_table(files: list[tuple[Path, int]]) -> Table:
    t = Table(title="Arquivos únicos grandes", title_style="bold",
              header_style="bold", box=None, padding=(0, 2))
    t.add_column("Tamanho", justify="right")
    t.add_column("Arquivo", overflow="fold")
    for path, size in files:
        t.add_row(Text(human(size), style="bold"), str(path))
    return t
