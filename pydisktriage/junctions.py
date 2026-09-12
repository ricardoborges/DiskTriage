"""Gerenciamento de Junções NTFS (mklink /J): movimentação, persistência e reversibilidade."""

from __future__ import annotations

import json
import os
import subprocess
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from .fsutil import is_reparse_point, move_tree, ProgressFn


def get_default_junctions_file() -> Path:
    """Retorna o caminho padrão do arquivo de rastreamento de junções em %LOCALAPPDATA%\\DiskTriage\\junctions.json."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        base_dir = Path(local_app_data) / "DiskTriage"
    else:
        base_dir = Path.home() / ".disktriage"
    return base_dir / "junctions.json"


@dataclass
class JunctionRecord:
    id: str
    name: str
    src: str
    dst: str
    created_at: str
    size_bytes: int
    active: bool = True
    reverted_at: str | None = None


def load_junctions(path: Path | None = None) -> list[JunctionRecord]:
    """Carrega o histórico de junções do arquivo JSON."""
    file_path = path or get_default_junctions_file()
    if not file_path.is_file():
        return []

    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
        records = []
        for item in data:
            records.append(
                JunctionRecord(
                    id=item["id"],
                    name=item["name"],
                    src=item["src"],
                    dst=item["dst"],
                    created_at=item["created_at"],
                    size_bytes=int(item.get("size_bytes", 0)),
                    active=bool(item.get("active", True)),
                    reverted_at=item.get("reverted_at"),
                )
            )
        return records
    except (json.JSONDecodeError, KeyError, OSError, TypeError):
        return []


def save_junctions(records: list[JunctionRecord], path: Path | None = None) -> bool:
    """Salva a lista de junções no arquivo JSON de forma segura."""
    file_path = path or get_default_junctions_file()
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(r) for r in records]
        file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except OSError:
        return False


def create_junction_link(src: Path, dst: Path) -> tuple[bool, str]:
    """Cria um Junction Point NTFS no caminho `src` apontando para `dst`.

    No Windows, `cmd /c mklink /J` não exige privilégios de administrador.
    """
    if src.exists():
        return False, f"O caminho de origem já existe: {src}"

    if not dst.exists():
        return False, f"O caminho de destino não existe: {dst}"

    cmd = ["cmd", "/c", "mklink", "/J", str(src).rstrip("\\/"), str(dst).rstrip("\\/")]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="cp850", errors="replace")
        if proc.returncode != 0:
            err = proc.stderr.strip() or proc.stdout.strip()
            return False, f"Falha ao criar junção: {err}"

        if not (src.exists() and is_reparse_point(src)):
            return False, f"A junção foi executada mas não pôde ser confirmada em {src}"

        return True, f"Junção criada: {src} -> {dst}"
    except OSError as exc:
        return False, f"Erro ao executar mklink: {exc}"


def remove_junction_link(src: Path) -> tuple[bool, str]:
    """Remove com segurança o link de junção sem apagar os dados do destino."""
    if not src.exists():
        return False, f"O caminho não existe: {src}"

    if not is_reparse_point(src):
        return False, f"O caminho não é uma junção/reparse point: {src}"

    try:
        # No Windows, rmdir em um junction point remove APENAS o link, preservando o destino intacto.
        os.rmdir(src)
        return True, f"Link de junção removido: {src}"
    except OSError as exc:
        return False, f"Não foi possível remover o link da junção: {exc}"


def move_and_create_junction(
    src: Path,
    dst: Path,
    name: str,
    size: int = 0,
    progress: ProgressFn | None = None,
    junctions_file: Path | None = None,
) -> tuple[bool, str, str | None]:
    """Move a pasta para outro disco e cria uma junção NTFS no lugar original.

    Retorna: (sucesso, mensagem, junction_id).
    """
    if is_reparse_point(src):
        return False, f"{src} já é uma junção NTFS.", None

    # 1. Mover os arquivos
    move_result = move_tree(src, dst, progress=progress)
    if not move_result.ok:
        err_msg = "; ".join(move_result.errors[:3]) if move_result.errors else "Erro desconhecido"
        return False, f"A movimentação dos arquivos falhou: {err_msg}", None

    # 2. Criar a junção
    link_ok, link_msg = create_junction_link(src, dst)
    if not link_ok:
        # Rollback: tenta mover de volta
        move_tree(dst, src)
        return False, f"Falha ao criar junção ({link_msg}). Arquivos restaurados na origem.", None

    # 3. Registrar a junção para persistência e rastreamento
    junction_id = str(uuid.uuid4())[:8]
    record = JunctionRecord(
        id=junction_id,
        name=name,
        src=str(Path(os.path.abspath(src))),
        dst=str(Path(os.path.abspath(dst))),
        created_at=datetime.now().isoformat(timespec="minutes"),
        size_bytes=size or move_result.bytes_done,
        active=True,
    )

    records = load_junctions(junctions_file)
    records.append(record)
    save_junctions(records, junctions_file)

    return True, f"Junção criada com sucesso para {name}.", junction_id


def revert_junction(
    junction_id: str,
    progress: ProgressFn | None = None,
    junctions_file: Path | None = None,
) -> tuple[bool, str]:
    """Reverte uma junção: remove o link e move os arquivos de volta para a origem."""
    records = load_junctions(junctions_file)
    target_record: JunctionRecord | None = None
    for r in records:
        if r.id == junction_id and r.active:
            target_record = r
            break

    if not target_record:
        return False, f"Junção ativa com ID '{junction_id}' não encontrada."

    src = Path(target_record.src)
    dst = Path(target_record.dst)

    if not src.exists():
        return False, f"Caminho da junção não existe: {src}"

    if not is_reparse_point(src):
        return False, f"{src} não é uma junção válida."

    if not dst.exists():
        return False, f"Pasta de destino com os dados não foi encontrada: {dst}"

    # 1. Remove o link da junção na origem
    rem_ok, rem_msg = remove_junction_link(src)
    if not rem_ok:
        return False, f"Falha ao remover o link da junção: {rem_msg}"

    # 2. Move os dados de volta de dst para src
    move_result = move_tree(dst, src, progress=progress)
    if not move_result.ok:
        # Tenta recriar o link para não deixar órfão
        create_junction_link(src, dst)
        errs = "; ".join(move_result.errors[:3])
        return False, f"Falha ao mover os arquivos de volta para {src}: {errs}"

    # 3. Atualiza o registro
    target_record.active = False
    target_record.reverted_at = datetime.now().isoformat(timespec="minutes")
    save_junctions(records, junctions_file)

    return True, f"Junção de {target_record.name} revertida com sucesso. Arquivos restaurados em {src}."
