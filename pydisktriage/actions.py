"""Destructive actions: deletion, relocations, environment variable updates, and junction tracking.

Safety rules strictly enforced across this module:
  * paths in `catalog.PROTECTED` are never touched under any circumstances;
  * deletion requires explicitly typing the item name;
  * file relocation checks destination drive free space before proceeding,
    and removes source files only after copy verification succeeds.
"""

from __future__ import annotations

from pathlib import Path

from rich.progress import (BarColumn, DownloadColumn, Progress, SpinnerColumn,
                           TextColumn, TimeRemainingColumn, TransferSpeedColumn)
from rich.prompt import Confirm, Prompt

from . import envvars, junctions, ui
from .catalog import Finding
from .fsutil import delete_tree, free_space, human, move_tree
from .i18n import t


def progress_bar() -> Progress:
    """Instantiate a standardized Rich progress bar."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=None),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=ui.console,
        transient=False,
    )


def _guard(finding: Finding) -> bool:
    """Block actions on system-protected paths."""
    if finding.protected:
        ui.error(t("actions.protected_path", path=finding.path))
        ui.info(t("actions.protected_tip"))
        return False
    return True


def action_delete(finding: Finding) -> bool:
    """Delete the content of the finding (or the file if single file)."""
    if not _guard(finding):
        return False

    ui.rule(t("actions.delete_title"))
    ui.console.print(t("actions.col_path_label", path=finding.path))
    ui.console.print(t("actions.col_size_label", size=human(finding.size), files=finding.files))
    if finding.localized_note:
        ui.console.print(t("actions.note_label", note=finding.localized_note))
    if finding.clean_cmd:
        ui.console.print()
        ui.warn(t("actions.clean_cmd_available", cmd=finding.clean_cmd))
        ui.info(t("actions.clean_cmd_tip"))

    if finding.kind == "revisar":
        ui.console.print()
        ui.warn(t("actions.review_warning"))

    ui.console.print()
    expected = finding.path.name
    typed = Prompt.ask(
        t("actions.confirm_delete_prompt", expected=expected),
        default="", show_default=False)
    if typed.strip().lower() != expected.lower():
        ui.info(t("status.cancelled"))
        return False

    with progress_bar() as prog:
        task = prog.add_task(t("actions.task_deleting"), total=finding.size)
        result = delete_tree(finding.path, progress=lambda n: prog.advance(task, n),
                             keep_root=not finding.is_file)

    if result.errors:
        ui.warn(t("actions.busy_files_skipped", count=len(result.errors)))
        for line in result.errors[:5]:
            ui.info(line)

    ui.ok(t("actions.freed_space", size=human(result.bytes_done), files=result.files_done))
    finding.size -= result.bytes_done
    return True


def action_move(finding: Finding, default_drive: str | None = None) -> bool:
    """Move item to another drive and update corresponding user environment variable if known."""
    if not _guard(finding):
        return False

    ui.rule(t("actions.move_title"))
    ui.console.print(t("actions.source_label", path=finding.path))
    ui.console.print(t("actions.col_size_label", size=human(finding.size), files=finding.files))

    drive = Prompt.ask(t("actions.target_drive_prompt"), default=default_drive or "D").strip()
    letter = drive.rstrip(":\\/").upper()

    try:
        available = free_space(letter)
    except OSError:
        ui.error(t("actions.drive_not_found", drive=letter))
        return False

    if available < finding.size * 1.05:
        ui.error(t("actions.insufficient_space",
                   drive=letter, available=human(available), needed=human(finding.size)))
        return False

    dest = Path(f"{letter}:\\caches\\{finding.ident}")
    dest_str = Prompt.ask(t("actions.target_path_prompt"), default=str(dest))
    dest = Path(dest_str)

    if dest.exists() and any(dest.iterdir()):
        if not Confirm.ask(t("actions.dest_exists_confirm", dest=dest), default=False):
            ui.info(t("status.cancelled"))
            return False

    ui.console.print()
    with progress_bar() as prog:
        task = prog.add_task(t("actions.task_copying"), total=finding.size)
        result = move_tree(finding.path, dest, progress=lambda n: prog.advance(task, n))

    if not result.ok:
        ui.error(t("actions.copy_failed", count=len(result.errors)))
        for line in result.errors[:5]:
            ui.info(line)
        return False

    ui.ok(t("actions.moved_success", size=human(result.bytes_done), dest=dest))

    if finding.env_var:
        ui.console.print()
        current = envvars.get_user_env(finding.env_var)
        if current:
            ui.info(t("actions.env_current_val", var=finding.env_var, val=current))
        if Confirm.ask(t("actions.set_env_confirm", var=finding.env_var, dest=dest), default=True):
            envvars.set_user_env(finding.env_var, str(dest))
            ui.ok(t("actions.env_set_success", var=finding.env_var))
    else:
        ui.warn(t("actions.no_env_var"))

    finding.path = dest
    return True


def action_set_env(finding: Finding) -> bool:
    """Set the environment variable without moving files."""
    ui.rule(t("actions.set_env_title"))

    var = finding.env_var
    if not var:
        var = Prompt.ask(t("actions.env_var_name_prompt")).strip()
        if not var:
            ui.info(t("status.cancelled"))
            return False

    current = envvars.get_user_env(var)
    if current:
        ui.info(t("actions.current_value", val=current))

    value = Prompt.ask(t("actions.new_value_prompt"), default=str(finding.path))
    if not value.strip():
        ui.info(t("status.cancelled"))
        return False

    envvars.set_user_env(var, value.strip())
    ui.ok(f"{var} = {value.strip()}")
    ui.info(t("actions.env_applied_info"))
    return True


def action_run_clean_cmd(finding: Finding) -> bool:
    """Display native clean command for the tool so the user can execute it directly."""
    if not finding.clean_cmd:
        ui.info(t("actions.no_clean_cmd"))
        return False
    ui.rule(t("actions.clean_cmd_title"))
    ui.console.print(f"\n  [bold cyan]{finding.clean_cmd}[/bold cyan]\n")
    ui.info(t("actions.run_clean_cmd_info"))
    return False


def action_open(finding: Finding) -> bool:
    """Open the item path in Windows Explorer."""
    import subprocess
    try:
        subprocess.Popen(["explorer", str(finding.path)])
        ui.ok(t("actions.opening_explorer", path=finding.path))
    except OSError as exc:
        ui.error(str(exc))
    return False


def action_move_junction(finding: Finding, default_drive: str | None = None) -> bool:
    """Move item to another drive and create an NTFS directory junction (mklink /J) at the source."""
    if not _guard(finding):
        return False

    if finding.is_file:
        ui.error(t("junctions.file_not_dir", path=finding.path))
        return False

    ui.rule(t("junctions.move_title"))
    ui.console.print(t("actions.source_label", path=finding.path))
    ui.console.print(t("actions.col_size_label", size=human(finding.size), files=finding.files))
    ui.info(t("junctions.desc_line1"))
    ui.info(t("junctions.desc_line2"))

    drive = Prompt.ask(t("actions.target_drive_prompt"), default=default_drive or "D").strip()
    letter = drive.rstrip(":\\/").upper()

    try:
        available = free_space(letter)
    except OSError:
        ui.error(t("actions.drive_not_found", drive=letter))
        return False

    if available < finding.size * 1.05:
        ui.error(t("actions.insufficient_space",
                   drive=letter, available=human(available), needed=human(finding.size)))
        return False

    dest = Path(f"{letter}:\\caches\\{finding.ident}")
    dest_str = Prompt.ask(t("actions.target_path_prompt"), default=str(dest))
    dest = Path(dest_str)

    if dest.exists() and any(dest.iterdir()):
        if not Confirm.ask(t("actions.dest_exists_confirm", dest=dest), default=False):
            ui.info(t("status.cancelled"))
            return False

    ui.console.print()
    with progress_bar() as prog:
        task = prog.add_task(t("junctions.task_moving"), total=finding.size)
        ok, msg, jid = junctions.move_and_create_junction(
            src=finding.path,
            dst=dest,
            name=finding.ident,
            size=finding.size,
            progress=lambda n: prog.advance(task, n),
        )

    if not ok:
        ui.error(msg)
        return False

    ui.ok(t("actions.moved_success", size=human(finding.size), dest=dest))
    ui.ok(t("junctions.created_success", src=finding.path, jid=jid))
    ui.info(t("junctions.revertible_tip"))
    return True


def action_manage_junctions() -> None:
    """List and manage active NTFS junctions with revert support."""
    ui.rule(t("junctions.manage_title"))
    records = junctions.load_junctions()
    if not records:
        ui.info(t("junctions.no_registered"))
        return

    from rich.table import Table
    table = Table(title=t("junctions.table_title"), box=None, padding=(0, 1), header_style="bold")
    table.add_column("ID", style="bold cyan")
    table.add_column(t("scan.col_item"))
    table.add_column(t("health.col_status"))
    table.add_column(t("scan.col_size"), justify="right")
    table.add_column(t("actions.source_label").strip().split(":")[0], overflow="fold")
    table.add_column(t("actions.target_drive_prompt").strip().split(":")[0], overflow="fold")
    table.add_column(t("health.col_when"))

    active_records = []
    for r in records:
        status_text = f"[bold green]{t('status.active')}[/bold green]" if r.active else f"[dim]{t('status.reverted')}[/dim]"
        table.add_row(
            r.id,
            r.name,
            status_text,
            human(r.size_bytes),
            r.src,
            r.dst,
            r.created_at,
        )
        if r.active:
            active_records.append(r)

    ui.console.print()
    ui.console.print(table)
    ui.console.print()

    if not active_records:
        ui.info(t("junctions.no_active"))
        return

    jid = Prompt.ask(t("junctions.revert_prompt"), default="").strip()
    if not jid:
        return

    matching = [r for r in active_records if r.id.lower() == jid.lower()]
    if not matching:
        ui.error(t("junctions.id_not_found", jid=jid))
        return

    target = matching[0]
    if not Confirm.ask(t("junctions.revert_confirm", name=target.name, src=target.src), default=False):
        ui.info(t("status.cancelled"))
        return

    ui.console.print()
    with progress_bar() as prog:
        task = prog.add_task(t("junctions.task_reverting"), total=target.size_bytes)
        ok, msg = junctions.revert_junction(target.id, progress=lambda n: prog.advance(task, n))

    if ok:
        ui.ok(msg)
    else:
        ui.error(msg)
