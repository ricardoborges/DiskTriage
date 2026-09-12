"""Main CLI loop: interactive menus, session state, action dispatching, and localization."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt

from . import actions, health, ui
from .cache import clear_scan_cache, load_scan_cache, save_scan_cache
from .catalog import Finding, get_category_label
from .config import get_configured_language, set_configured_language
from .fsutil import human
from .i18n import (
    get_available_languages,
    get_language,
    normalize_language,
    set_language,
    t,
)
from .interactive import select_finding, select_menu
from .scanner import (
    scan_catalog,
    scan_discovery,
    scan_large_files,
)


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
    """Update disk cache with current session findings."""
    if session.scanned:
        save_scan_cache(
            findings=session.findings,
            large_files=session.large_files,
            home=session.home,
            min_gb=session.min_gb,
            discovery=session.discovery,
        )


# --------------------------------------------------------------------------
# Screens
# --------------------------------------------------------------------------

def screen_health() -> None:
    """Display disk space, SSD latency, pagefile, and BSOD bugcheck diagnostic report."""
    ui.rule(t("health.rule_title"))

    vols = health.get_volumes()
    ui.console.print()
    ui.console.print(ui.volumes_table(vols))

    for v in vols:
        if v.pct_free < 10:
            ui.console.print()
            ui.error(t("health.warn_low_space", drive=v.letter, pct=v.pct_free))
            ui.info(t("health.info_slc_cache"))

    disks, elevated = health.get_latency()
    ui.console.print()
    if not elevated:
        ui.info(t("health.latency_admin_required"))
    else:
        ui.console.print(ui.latency_table(disks))
        for d in disks:
            if d.suspicious:
                ui.console.print()
                ui.error(t("health.latency_spike_warn", disk=d.name, read_ms=d.read_ms))
                ui.info(t("health.latency_nvme_info"))

    pfs = health.get_pagefiles()
    if pfs:
        ui.console.print()
        ui.console.print(f"[bold]{t('health.pagefile_title')}[/bold]")
        for p in pfs:
            ui.console.print(f"  {p.get('Caminho')}  "
                             f"[dim]{p.get('TamanhoMB')} MB "
                             f"(peak {p.get('PicoMB')} MB)[/dim]")

    bugs = health.get_bugchecks()
    ui.console.print()
    if not bugs:
        ui.ok(t("health.no_bugchecks"))
    else:
        ui.console.print(ui.bugchecks_table(bugs))
        ui.console.print()
        ui.warn(t("health.bugchecks_found", count=len(bugs), dump_dir=health.minidump_dir()))
        ui.info(t("health.windbg_tip"))
        ui.info(t("health.windbg_fields"))


def screen_scan(session: Session, discovery: bool) -> None:
    """Execute catalog and optional deep discovery scan, updating the cache and session."""
    ui.rule(t("scan.rule_title"))

    with Progress(SpinnerColumn(), TextColumn("[bold blue]{task.description}"),
                  BarColumn(bar_width=None),
                  TextColumn("{task.completed}/{task.total}"),
                  console=ui.console) as prog:

        task_catalog_desc = t("scan.task_catalog")
        task = prog.add_task(task_catalog_desc, total=1)

        def status(label: str, i: int, total: int) -> None:
            prog.update(task, description=f"{task_catalog_desc} · {label}",
                        completed=i, total=total)

        session.findings = scan_catalog(session.home, session.min_gb, status)

        if discovery:
            task_disc_desc = t("scan.task_discovery")
            task2 = prog.add_task(task_disc_desc, total=1)

            def status2(label: str, i: int, total: int) -> None:
                prog.update(task2, description=f"{task_disc_desc} · {label}",
                            completed=i, total=total)

            extra = scan_discovery(session.home, session.findings,
                                   session.min_gb, status2)
            session.findings.extend(extra)

            task3 = prog.add_task(t("scan.task_large_files"), total=1)
            session.large_files = scan_large_files(session.home)
            prog.update(task3, completed=1, total=1)

    session.findings.sort(key=lambda f: f.size, reverse=True)
    session.scanned = True
    session.discovery = discovery
    session.last_scan_time = datetime.now().strftime("%d/%m/%Y %H:%M")
    _sync_cache(session)

    ui.console.print()
    ui.console.print(ui.findings_table(session.findings, t("scan.found_items_title")))
    if session.large_files:
        ui.console.print()
        ui.console.print(ui.large_files_table(session.large_files))
    ui.console.print()
    ui.console.print(ui.summary_panel(session.findings))


def screen_item_actions(session: Session) -> None:
    """Present action menu for a specific chosen finding."""
    if not session.findings:
        ui.warn(t("scan.require_scan_first"))
        return

    ui.rule(t("actions.rule_title"))
    finding = select_finding(session.findings, t("interactive.select_item_title"))
    if not finding:
        return

    index = session.findings.index(finding)

    while True:
        action_options = [
            ("1", t("actions.opt_delete")),
            ("2", t("actions.opt_move")),
            ("3", t("actions.opt_move_junction")),
            ("4", t("actions.opt_set_env")),
            ("5", t("actions.opt_clean_cmd")),
            ("6", t("actions.opt_open_explorer")),
            ("0", t("menu.back")),
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
    """Bulk delete all items classified as safe disposable cache."""
    targets = [f for f in session.findings
               if f.kind == "descartavel" and not f.protected]
    if not targets:
        ui.warn(t("bulk.require_scan"))
        return

    ui.rule(t("bulk.rule_title"))
    ui.console.print()
    ui.console.print(ui.findings_table(targets, t("bulk.table_title")))
    total = sum(f.size for f in targets)
    ui.console.print()
    ui.console.print(t("bulk.total_to_free", size=human(total)))
    ui.console.print()

    keyword = t("bulk.confirm_keyword")
    typed = Prompt.ask(t("bulk.confirm_prompt"), default="", show_default=False)
    if typed.strip().upper() != keyword.upper():
        ui.info(t("status.cancelled"))
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
            ui.warn(t("bulk.files_in_use", count=len(result.errors)))

    ui.console.print()
    ui.ok(t("bulk.freed_total", size=human(freed)))
    session.findings = [f for f in session.findings if f not in targets]
    _sync_cache(session)


def screen_export(session: Session) -> None:
    """Export current scan results to CSV and JSON reports."""
    if not session.findings:
        ui.warn(t("scan.require_scan_first"))
        return

    out_dir = Path(Prompt.ask(t("export.dest_prompt"),
                              default=str(Path.home() / "Desktop")))

    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        ui.error(t("export.dir_create_error", path=out_dir, err=exc))
        return

    stem = "triagem" if get_language() == "pt-BR" else "triage"
    csv_path = out_dir / f"{stem}.csv"
    json_path = out_dir / f"{stem}.json"

    try:
        with csv_path.open("w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.writer(fh, delimiter=";")
            writer.writerow([
                t("export.col_bytes"),
                t("export.col_gb"),
                t("export.col_category"),
                t("export.col_item"),
                t("export.col_path"),
                t("export.col_var"),
                t("export.col_cmd"),
                t("export.col_note"),
            ])
            for f in session.findings:
                writer.writerow([
                    f.size,
                    f.gb,
                    get_category_label(f.kind),
                    f.ident,
                    str(f.path),
                    f.env_var,
                    f.clean_cmd,
                    f.localized_note,
                ])

        json_path.write_text(json.dumps([
            {
                "bytes": f.size,
                "gb": f.gb,
                "categoria": get_category_label(f.kind),
                "item": f.ident,
                "caminho": str(f.path),
                "variavel": f.env_var,
                "comando": f.clean_cmd,
                "observacao": f.localized_note,
            }
            for f in session.findings
        ], ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        ui.error(t("export.write_error", err=exc))
        ui.info(t("export.perm_tip"))
        return

    ui.ok(t("export.success", csv_path=csv_path, json_path=json_path))


def screen_change_language() -> None:
    """Present interactive language selection and persist choice."""
    ui.rule(t("lang.select_title"))
    options = [
        ("1", "Português (Brasil) [pt-BR]"),
        ("2", "English (US) [en-US]"),
        ("0", t("menu.back")),
    ]
    current = get_language()
    default_key = "2" if current == "en-US" else "1"
    choice = select_menu(options, title=t("lang.prompt"), default_key=default_key)
    if choice == "0":
        return

    new_lang = "en-US" if choice == "2" else "pt-BR"
    set_language(new_lang)
    set_configured_language(new_lang)
    ui.ok(t("lang.changed", lang=new_lang))


# --------------------------------------------------------------------------
# Main Menu & CLI Entry
# --------------------------------------------------------------------------

def get_main_menu(session: Session) -> list[tuple[str, str]]:
    """Construct the main interactive menu options list."""
    scan_prefix = t("menu.scan_prefix_redo") if session.scanned else t("menu.scan_prefix_new")
    menu = [
        ("1", t("menu.health")),
        ("2", t("menu.full_scan", prefix=scan_prefix)),
        ("3", t("menu.fast_scan", prefix=scan_prefix)),
        ("4", t("menu.item_actions")),
        ("5", t("menu.bulk_delete")),
        ("6", t("menu.export")),
        ("7", t("menu.manage_junctions")),
    ]
    if session.scanned:
        menu.append(("8", t("menu.clear_cache")))
    menu.append(("9", t("menu.change_lang")))
    menu.append(("0", t("menu.exit")))
    return menu


def build_parser() -> argparse.ArgumentParser:
    """Build command line argument parser."""
    p = argparse.ArgumentParser(
        prog="disktriage",
        description="Disk space triage and SSD health diagnostics for Windows.")
    p.add_argument("--home", type=Path, default=Path.home(),
                   help="user profile path to analyze (default: current user)")
    p.add_argument("--min-gb", type=float, default=1.0,
                   help="minimum item size in gigabytes to display (default: 1.0)")
    p.add_argument("--drive", dest="target_drive", default=None,
                   help="suggested target drive letter for moving files (e.g. D)")
    p.add_argument("--lang", "--language", dest="language", default=None,
                   help="language code override (pt-BR or en-US)")
    p.add_argument("--scan", action="store_true",
                   help="immediately execute full scan upon launch")
    p.add_argument("--rescan", action="store_true",
                   help="ignore cached scan and force full rescan")
    p.add_argument("--health", action="store_true",
                   help="print system health diagnostics and exit")
    return p


def main(argv: list[str] | None = None) -> int:
    """Main execution controller."""
    if sys.platform != "win32":
        ui.error(t("app.win_only"))
        return 1

    args = build_parser().parse_args(argv)

    # 1. Resolve language preference
    if args.language:
        lang = normalize_language(args.language)
        set_language(lang)
        set_configured_language(lang)
    else:
        configured = get_configured_language()
        if configured is None:
            # First run: prompt user to choose language and persist preference
            ui.show_banner()
            lang_options = [
                ("1", "Português (Brasil) [pt-BR] (padrão)"),
                ("2", "English (US) [en-US]"),
            ]
            choice = select_menu(lang_options, title="Language / Idioma", default_key="1")
            chosen = "en-US" if choice == "2" else "pt-BR"
            set_language(chosen)
            set_configured_language(chosen)
        else:
            set_language(configured)

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
        ui.ok(t("scan.cache_loaded", time=session.last_scan_time, count=len(session.findings)))
        ui.console.print(ui.findings_table(session.findings, t("scan.cached_items_title")))
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
        choice = select_menu(menu, title=t("menu.title"), default_key=default_choice)

        if choice == "0":
            ui.console.print(f"\n[dim]{t('app.goodbye')}[/dim]\n")
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
            ui.ok(t("scan.cache_cleared"))
        elif choice == "9":
            screen_change_language()


def run() -> int:
    """Tolerant entrypoint catching interrupts cleanly."""
    try:
        return main()
    except KeyboardInterrupt:
        ui.console.print()
        ui.info(t("app.interrupted"))
        return 130
    except EOFError:
        ui.console.print()
        ui.info(t("app.input_closed"))
        return 0


if __name__ == "__main__":
    raise SystemExit(run())
