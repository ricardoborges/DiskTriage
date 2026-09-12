"""As ações destrutivas, cada uma com sua confirmação e sua barra de progresso.

Regras que valem para tudo neste módulo:

  * nada em `catalog.PROTECTED` é tocado, nem a pedido;
  * apagar exige que o usuário digite o nome da pasta, não só um "s";
  * mover verifica espaço no destino antes de começar, e só remove a origem
    depois que todos os arquivos chegaram.
"""

from __future__ import annotations

from pathlib import Path

from rich.progress import (BarColumn, DownloadColumn, Progress, SpinnerColumn,
                           TextColumn, TimeRemainingColumn, TransferSpeedColumn)
from rich.prompt import Confirm, Prompt

from . import envvars, junctions, ui
from .catalog import Finding
from .fsutil import delete_tree, free_space, human, move_tree


def progress_bar() -> Progress:
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
    """Recusa ações em caminhos protegidos."""
    if finding.protected:
        ui.error(f"{finding.path} é protegido — não vou mexer.")
        ui.info("Use a ferramenta própria: DISM para o WinSxS, PatchCleaner "
                "para o Windows\\Installer.")
        return False
    return True


def action_delete(finding: Finding) -> bool:
    """Apaga o conteúdo do item (ou o arquivo, se for arquivo único)."""
    if not _guard(finding):
        return False

    ui.rule("Excluir")
    ui.console.print(f"  Caminho : [bold]{finding.path}[/bold]")
    ui.console.print(f"  Tamanho : [bold]{human(finding.size)}[/bold] "
                     f"em {finding.files} arquivo(s)")
    if finding.note:
        ui.console.print(f"  Nota    : [dim]{finding.note}[/dim]")
    if finding.clean_cmd:
        ui.console.print()
        ui.warn(f"A ferramenta tem comando próprio para isso: "
                f"[cyan]{finding.clean_cmd}[/cyan]")
        ui.info("Costuma ser mais seguro que apagar arquivos na mão.")

    if finding.kind == "revisar":
        ui.console.print()
        ui.warn("Este item está classificado como 'revisar' — pode conter dados "
                "que você quer manter.")

    ui.console.print()
    expected = finding.path.name
    typed = Prompt.ask(
        f"Para confirmar, digite o nome do item ([bold]{expected}[/bold])",
        default="", show_default=False)
    if typed.strip().lower() != expected.lower():
        ui.info("Cancelado.")
        return False

    with progress_bar() as prog:
        task = prog.add_task("apagando", total=finding.size)
        result = delete_tree(finding.path, progress=lambda n: prog.advance(task, n),
                             keep_root=not finding.is_file)

    if result.errors:
        ui.warn(f"{len(result.errors)} arquivo(s) não puderam ser removidos "
                "(provavelmente em uso).")
        for line in result.errors[:5]:
            ui.info(line)

    ui.ok(f"Liberado {human(result.bytes_done)} em {result.files_done} arquivo(s).")
    finding.size -= result.bytes_done
    return True


def action_move(finding: Finding, default_drive: str | None = None) -> bool:
    """Move o item para outro disco e, se houver, ajusta a variável de ambiente."""
    if not _guard(finding):
        return False

    ui.rule("Mover para outro disco")
    ui.console.print(f"  Origem  : [bold]{finding.path}[/bold]")
    ui.console.print(f"  Tamanho : [bold]{human(finding.size)}[/bold]")

    drive = Prompt.ask("  Disco de destino", default=default_drive or "D").strip()
    letter = drive.rstrip(":\\/").upper()

    try:
        available = free_space(letter)
    except OSError:
        ui.error(f"Unidade {letter}: não existe ou não está acessível.")
        return False

    if available < finding.size * 1.05:
        ui.error(f"Espaço insuficiente em {letter}: "
                 f"({human(available)} livre, precisa de {human(finding.size)}).")
        return False

    dest = Path(f"{letter}:\\caches\\{finding.ident}")
    dest_str = Prompt.ask("  Caminho de destino", default=str(dest))
    dest = Path(dest_str)

    if dest.exists() and any(dest.iterdir()):
        if not Confirm.ask(f"  [yellow]{dest} já existe e não está vazio. "
                           f"Mesclar?[/yellow]", default=False):
            ui.info("Cancelado.")
            return False

    ui.console.print()
    with progress_bar() as prog:
        task = prog.add_task("copiando", total=finding.size)
        result = move_tree(finding.path, dest, progress=lambda n: prog.advance(task, n))

    if not result.ok:
        ui.error(f"A cópia falhou em {len(result.errors)} arquivo(s). "
                 "A origem foi preservada.")
        for line in result.errors[:5]:
            ui.info(line)
        return False

    ui.ok(f"Movido {human(result.bytes_done)} para {dest}.")

    if finding.env_var:
        ui.console.print()
        current = envvars.get_user_env(finding.env_var)
        if current:
            ui.info(f"{finding.env_var} hoje aponta para: {current}")
        if Confirm.ask(f"  Definir [cyan]{finding.env_var}[/cyan] = "
                       f"[bold]{dest}[/bold]?", default=True):
            envvars.set_user_env(finding.env_var, str(dest))
            ui.ok(f"{finding.env_var} definida. Abra um terminal novo para ela valer.")
    else:
        ui.warn("Esta ferramenta não tem variável de ambiente conhecida — "
                "reconfigure o caminho pela GUI dela.")

    finding.path = dest
    return True


def action_set_env(finding: Finding) -> bool:
    """Só define a variável, sem mover nada."""
    ui.rule("Definir variável de ambiente")

    var = finding.env_var
    if not var:
        var = Prompt.ask("  Nome da variável").strip()
        if not var:
            ui.info("Cancelado.")
            return False

    current = envvars.get_user_env(var)
    if current:
        ui.info(f"Valor atual: {current}")

    value = Prompt.ask("  Novo valor", default=str(finding.path))
    if not value.strip():
        ui.info("Cancelado.")
        return False

    envvars.set_user_env(var, value.strip())
    ui.ok(f"{var} = {value.strip()}")
    ui.info("Processos já abertos não enxergam a mudança; abra um terminal novo.")
    return True


def action_run_clean_cmd(finding: Finding) -> bool:
    """Mostra o comando nativo da ferramenta, para o usuário rodar por fora."""
    if not finding.clean_cmd:
        ui.info("Esta entrada não tem comando de limpeza próprio.")
        return False
    ui.rule("Comando nativo da ferramenta")
    ui.console.print(f"\n  [bold cyan]{finding.clean_cmd}[/bold cyan]\n")
    ui.info("Rode num terminal seu — assim você vê a saída e mantém o controle.")
    return False


def action_open(finding: Finding) -> bool:
    """Abre o caminho no Explorer."""
    import subprocess
    try:
        subprocess.Popen(["explorer", str(finding.path)])
        ui.ok(f"Abrindo {finding.path}")
    except OSError as exc:
        ui.error(str(exc))
    return False


def action_move_junction(finding: Finding, default_drive: str | None = None) -> bool:
    """Move o item para outro disco e cria uma junção NTFS (mklink /J) no lugar original."""
    if not _guard(finding):
        return False

    if finding.is_file:
        ui.error(f"{finding.path} é um arquivo único. Junções NTFS funcionam apenas em pastas.")
        return False

    ui.rule("Mover via Junção NTFS (mklink /J)")
    ui.console.print(f"  Origem  : [bold]{finding.path}[/bold]")
    ui.console.print(f"  Tamanho : [bold]{human(finding.size)}[/bold]")
    ui.info("Uma junção NTFS move os dados físicos para outro disco, mas mantém um link")
    ui.info("transparente na origem para o aplicativo continuar funcionando normalmente.")

    drive = Prompt.ask("  Disco de destino", default=default_drive or "D").strip()
    letter = drive.rstrip(":\\/").upper()

    try:
        available = free_space(letter)
    except OSError:
        ui.error(f"Unidade {letter}: não existe ou não está acessível.")
        return False

    if available < finding.size * 1.05:
        ui.error(f"Espaço insuficiente em {letter}: "
                 f"({human(available)} livre, precisa de {human(finding.size)}).")
        return False

    dest = Path(f"{letter}:\\caches\\{finding.ident}")
    dest_str = Prompt.ask("  Caminho de destino", default=str(dest))
    dest = Path(dest_str)

    if dest.exists() and any(dest.iterdir()):
        if not Confirm.ask(f"  [yellow]{dest} já existe e não está vazio. "
                           f"Mesclar?[/yellow]", default=False):
            ui.info("Cancelado.")
            return False

    ui.console.print()
    with progress_bar() as prog:
        task = prog.add_task("movendo e criando junção", total=finding.size)
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

    ui.ok(f"Movido com sucesso para {dest}!")
    ui.ok(f"Junção NTFS criada em {finding.path} (ID: [bold cyan]{jid}[/bold cyan]).")
    ui.info("A junção está ativa e registrada. Você pode revertê-la a qualquer momento pelo menu.")
    return True


def action_manage_junctions() -> None:
    """Lista e gerencia as junções NTFS criadas, com opção de reversão."""
    ui.rule("Gerenciar Junções NTFS")
    records = junctions.load_junctions()
    if not records:
        ui.info("Nenhuma junção NTFS registrada até o momento.")
        return

    from rich.table import Table
    table = Table(title="Junções Registradas", box=None, padding=(0, 1), header_style="bold")
    table.add_column("ID", style="bold cyan")
    table.add_column("Nome")
    table.add_column("Status")
    table.add_column("Tamanho", justify="right")
    table.add_column("Origem (C:)", overflow="fold")
    table.add_column("Destino", overflow="fold")
    table.add_column("Data")

    active_records = []
    for r in records:
        status_text = "[bold green]Ativa[/bold green]" if r.active else "[dim]Revertida[/dim]"
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
        ui.info("Não há junções ativas para reverter.")
        return

    jid = Prompt.ask("Digite o ID da junção para REVERTER (ou Enter para voltar)", default="").strip()
    if not jid:
        return

    matching = [r for r in active_records if r.id.lower() == jid.lower()]
    if not matching:
        ui.error(f"Nenhuma junção ativa encontrada com o ID '{jid}'.")
        return

    target = matching[0]
    if not Confirm.ask(f"Deseja reverter a junção de [bold]{target.name}[/bold] e mover os dados de volta para [bold]{target.src}[/bold]?", default=False):
        ui.info("Cancelado.")
        return

    ui.console.print()
    with progress_bar() as prog:
        task = prog.add_task("revertendo junção", total=target.size_bytes)
        ok, msg = junctions.revert_junction(target.id, progress=lambda n: prog.advance(task, n))

    if ok:
        ui.ok(msg)
    else:
        ui.error(msg)

