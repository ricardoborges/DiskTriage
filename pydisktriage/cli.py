"""Laço principal: menu, estado da sessão e roteamento das ações."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt

from . import actions, health, ui
from .cache import clear_scan_cache, load_scan_cache, save_scan_cache
from .catalog import Finding
from .fsutil import human
from .interactive import select_finding, select_menu
from .scanner import (scan_catalog, scan_discovery,
                      scan_large_files)


@dataclass
class Session:
    home: Path
    min_gb: float
    target_drive: str | None = None
    findings: list[Finding] = field(default_factory=list)
    large_files: list[tuple[Path, int]] = field(default_factory=list)
    scanned: bool = False
    discovery: bool = False
    last_scan_time: str | None = None


def _sync_cache(session: Session) -> None:
    """Atualiza o cache em disco com o estado atual da sessão."""
    if session.scanned:
        save_scan_cache(
            findings=session.findings,
            large_files=session.large_files,
            home=session.home,
            min_gb=session.min_gb,
            discovery=session.discovery,
        )


# --------------------------------------------------------------------------
# telas
# --------------------------------------------------------------------------

def screen_health() -> None:
    ui.rule("Diagnóstico de saúde")

    vols = health.get_volumes()
    ui.console.print()
    ui.console.print(ui.volumes_table(vols))

    for v in vols:
        if v.pct_free < 10:
            ui.console.print()
            ui.error(f"{v.letter}: com apenas {v.pct_free}% livre.")
            ui.info("Abaixo de ~10% o cache SLC do SSD deixa de funcionar e a "
                    "latência dispara. É assim que um disco cheio vira tela azul.")

    disks, elevated = health.get_latency()
    ui.console.print()
    if not elevated:
        ui.info("Latência dos discos indisponível — rode como administrador "
                "para ver esta seção.")
    else:
        ui.console.print(ui.latency_table(disks))
        for d in disks:
            if d.suspicious:
                ui.console.print()
                ui.error(f"{d.name}: pico de {d.read_ms} ms na leitura.")
                ui.info("Um NVMe saudável fica abaixo de 10 ms. Stalls desta "
                        "ordem causam STATUS_IN_PAGE_ERROR e tela azul.")

    pfs = health.get_pagefiles()
    if pfs:
        ui.console.print()
        ui.console.print("[bold]Pagefile[/bold]")
        for p in pfs:
            ui.console.print(f"  {p.get('Caminho')}  "
                             f"[dim]{p.get('TamanhoMB')} MB "
                             f"(pico {p.get('PicoMB')} MB)[/dim]")

    bugs = health.get_bugchecks()
    ui.console.print()
    if not bugs:
        ui.ok("Nenhuma tela azul nos últimos 90 dias.")
    else:
        ui.console.print(ui.bugchecks_table(bugs))
        ui.console.print()
        ui.warn(f"{len(bugs)} bugcheck(s). Dumps em {health.minidump_dir()}")
        ui.info('Analise com: windbgx -z <dump> -c "!analyze -v; q" '
                "-logo %TEMP%\\bsod.txt")
        ui.info("Olhe FAILURE_BUCKET_ID, MODULE_NAME e IMAGE_NAME no resultado.")


def screen_scan(session: Session, discovery: bool) -> None:
    ui.rule("Varredura")

    with Progress(SpinnerColumn(), TextColumn("[bold blue]{task.description}"),
                  BarColumn(bar_width=None),
                  TextColumn("{task.completed}/{task.total}"),
                  console=ui.console) as prog:

        task = prog.add_task("catálogo", total=1)

        def status(label: str, i: int, total: int) -> None:
            prog.update(task, description=f"catálogo · {label}",
                        completed=i, total=total)

        session.findings = scan_catalog(session.home, session.min_gb, status)

        if discovery:
            task2 = prog.add_task("descoberta", total=1)

            def status2(label: str, i: int, total: int) -> None:
                prog.update(task2, description=f"descoberta · {label}",
                            completed=i, total=total)

            extra = scan_discovery(session.home, session.findings,
                                   session.min_gb, status2)
            session.findings.extend(extra)

            task3 = prog.add_task("arquivos grandes", total=1)
            session.large_files = scan_large_files(session.home)
            prog.update(task3, completed=1, total=1)

    session.findings.sort(key=lambda f: f.size, reverse=True)
    session.scanned = True
    session.discovery = discovery
    from datetime import datetime
    session.last_scan_time = datetime.now().strftime("%d/%m/%Y %H:%M")
    _sync_cache(session)

    ui.console.print()
    ui.console.print(ui.findings_table(session.findings, "Itens encontrados"))
    if session.large_files:
        ui.console.print()
        ui.console.print(ui.large_files_table(session.large_files))
    ui.console.print()
    ui.console.print(ui.summary_panel(session.findings))


def screen_item_actions(session: Session) -> None:
    if not session.findings:
        ui.warn("Rode a varredura primeiro (opção 2).")
        return

    ui.rule("Ações sobre itens")
    finding = select_finding(session.findings, "Selecione o item para agir")
    if not finding:
        return

    index = session.findings.index(finding)

    while True:
        action_options = [
            ("1", "Excluir conteúdo"),
            ("2", "Mover para outro disco (e ajustar variável de ambiente)"),
            ("3", "Mover para outro disco via Junção NTFS (mklink /J)"),
            ("4", "Só definir a variável de ambiente"),
            ("5", "Ver o comando nativo de limpeza"),
            ("6", "Abrir no Explorer"),
            ("0", "Voltar"),
        ]

        choice = select_menu(action_options, title=f"{finding.ident} · {human(finding.size)}")
        if choice == "0":
            return
        if choice == "1":
            if actions.action_delete(finding) and finding.size <= 0:
                session.findings.pop(index)
                _sync_cache(session)
                return
            _sync_cache(session)
        elif choice == "2":
            if actions.action_move(finding, session.target_drive):
                session.findings.pop(index)
                _sync_cache(session)
                return
        elif choice == "3":
            if actions.action_move_junction(finding, session.target_drive):
                session.findings.pop(index)
                _sync_cache(session)
                return
        elif choice == "4":
            actions.action_set_env(finding)
        elif choice == "5":
            actions.action_run_clean_cmd(finding)
        elif choice == "6":
            actions.action_open(finding)


def screen_bulk_delete(session: Session) -> None:
    """Apaga de uma vez tudo que é seguramente descartável."""
    targets = [f for f in session.findings
               if f.kind == "descartavel" and not f.protected]
    if not targets:
        ui.warn("Nada classificado como descartável. Rode a varredura primeiro.")
        return

    ui.rule("Limpeza em lote")
    ui.console.print()
    ui.console.print(ui.findings_table(targets, "Serão apagados"))
    total = sum(f.size for f in targets)
    ui.console.print()
    ui.console.print(f"Total a liberar: [bold green]{human(total)}[/bold green]")
    ui.console.print()

    typed = Prompt.ask("Digite [bold]APAGAR[/bold] para confirmar",
                       default="", show_default=False)
    if typed.strip().upper() != "APAGAR":
        ui.info("Cancelado.")
        return

    freed = 0
    for f in targets:
        ui.console.print()
        ui.info(f"{f.ident} — {f.path}")
        from .fsutil import delete_tree
        with actions.progress_bar() as prog:
            task = prog.add_task(f.ident, total=f.size)
            result = delete_tree(f.path, progress=lambda n: prog.advance(task, n),
                                 keep_root=not f.is_file)
        freed += result.bytes_done
        if result.errors:
            ui.warn(f"{len(result.errors)} arquivo(s) em uso, pulados.")

    ui.console.print()
    ui.ok(f"Liberado {human(freed)} no total.")
    session.findings = [f for f in session.findings if f not in targets]
    _sync_cache(session)


def screen_export(session: Session) -> None:
    if not session.findings:
        ui.warn("Rode a varredura primeiro.")
        return

    out_dir = Path(Prompt.ask("Pasta de destino",
                              default=str(Path.home() / "Desktop")))

    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        ui.error(f"Não consegui criar {out_dir}: {exc}")
        return

    csv_path = out_dir / "triagem.csv"
    json_path = out_dir / "triagem.json"

    try:
        with csv_path.open("w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.writer(fh, delimiter=";")
            writer.writerow(["Bytes", "GB", "Categoria", "Item", "Caminho",
                             "Variavel", "Comando", "Observacao"])
            for f in session.findings:
                writer.writerow([f.size, f.gb, f.kind, f.ident, str(f.path),
                                 f.env_var, f.clean_cmd, f.note])

        json_path.write_text(json.dumps([
            {"bytes": f.size, "gb": f.gb, "categoria": f.kind, "item": f.ident,
             "caminho": str(f.path), "variavel": f.env_var,
             "comando": f.clean_cmd, "observacao": f.note}
            for f in session.findings
        ], ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        ui.error(f"Falha ao escrever o relatório: {exc}")
        ui.info("Escolha uma pasta onde você tenha permissão de escrita.")
        return

    ui.ok(f"Exportado:" + chr(10) + f"    {csv_path}" + chr(10) + f"    {json_path}")


# --------------------------------------------------------------------------
# entrada
# --------------------------------------------------------------------------

def get_main_menu(session: Session) -> list[tuple[str, str]]:
    scan_prefix = "Refazer varredura" if session.scanned else "Varredura"
    menu = [
        ("1", "Diagnóstico de saúde (espaço, latência, telas azuis)"),
        ("2", f"{scan_prefix} completa (catálogo + descoberta)"),
        ("3", f"{scan_prefix} rápida (só o catálogo)"),
        ("4", "Agir sobre um item"),
        ("5", "Apagar tudo que é descartável"),
        ("6", "Exportar relatório"),
        ("7", "Gerenciar/Reverter Junções NTFS"),
    ]
    if session.scanned:
        menu.append(("8", "Limpar cache da varredura"))
    menu.append(("0", "Sair"))
    return menu


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="disktriage",
        description="Triagem de espaço em disco no Windows: diagnostica a saúde "
                    "do SSD e mostra o que dá para apagar, mover ou revisar.")
    p.add_argument("--home", type=Path, default=Path.home(),
                   help="perfil a analisar (padrão: o seu)")
    p.add_argument("--min-gb", type=float, default=1.0,
                   help="tamanho mínimo para um item aparecer (padrão: 1)")
    p.add_argument("--drive", dest="target_drive", default=None,
                   help="disco de destino sugerido para mover (ex.: D)")
    p.add_argument("--scan", action="store_true",
                   help="já entra com a varredura completa feita")
    p.add_argument("--rescan", action="store_true",
                   help="ignora o cache da última varredura e força nova leitura")
    p.add_argument("--health", action="store_true",
                   help="só imprime o diagnóstico de saúde e sai")
    return p


def main(argv: list[str] | None = None) -> int:
    if sys.platform != "win32":
        ui.error("Esta ferramenta é específica para Windows.")
        return 1

    args = build_parser().parse_args(argv)
    session = Session(home=args.home, min_gb=args.min_gb,
                      target_drive=args.target_drive)

    if not args.rescan:
        cached = load_scan_cache()
        if cached and cached.home.resolve() == session.home.resolve():
            session.findings = cached.findings
            session.large_files = cached.large_files
            session.scanned = True
            session.discovery = cached.discovery
            session.last_scan_time = cached.formatted_time

    ui.show_banner()

    if args.health:
        screen_health()
        return 0

    screen_health()

    if session.scanned and not args.scan:
        ui.console.print()
        ui.ok(f"Última varredura carregada do cache ({session.last_scan_time} · "
              f"{len(session.findings)} itens encontrados).")
        ui.console.print(ui.findings_table(session.findings, "Itens em cache"))
        if session.large_files:
            ui.console.print()
            ui.console.print(ui.large_files_table(session.large_files))
        ui.console.print()
        ui.console.print(ui.summary_panel(session.findings))

    if args.scan:
        screen_scan(session, discovery=True)

    while True:
        menu = get_main_menu(session)
        default_choice = "4" if session.scanned else "2"
        choice = select_menu(menu, title="Menu", default_key=default_choice)

        if choice == "0":
            ui.console.print("\n[dim]até mais.[/dim]\n")
            return 0
        if choice == "1":
            screen_health()
        elif choice == "2":
            screen_scan(session, discovery=True)
        elif choice == "3":
            screen_scan(session, discovery=False)
        elif choice == "4":
            screen_item_actions(session)
        elif choice == "5":
            screen_bulk_delete(session)
        elif choice == "6":
            screen_export(session)
        elif choice == "7":
            actions.action_manage_junctions()
        elif choice == "8" and session.scanned:
            clear_scan_cache()
            session.findings.clear()
            session.large_files.clear()
            session.scanned = False
            session.last_scan_time = None
            ui.ok("Cache da varredura apagado.")


def run() -> int:
    """Ponto de entrada tolerante: Ctrl+C e fim de stdin nao viram traceback."""
    try:
        return main()
    except KeyboardInterrupt:
        ui.console.print()
        ui.info("Interrompido.")
        return 130
    except EOFError:
        ui.console.print()
        ui.info("Entrada encerrada.")
        return 0


if __name__ == "__main__":
    raise SystemExit(run())
