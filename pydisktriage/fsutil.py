"""Travessia de sistema de arquivos, medição, cópia e remoção.

Tudo aqui evita seguir reparse points (junctions e symlinks). Sem esse cuidado,
`C:\\Users\\Todos os Usuários` — que aponta para `C:\\ProgramData` — é contado duas
vezes, e uma remoção recursiva pode sair da árvore pretendida.
"""

from __future__ import annotations

import concurrent.futures
import os
import shutil
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

FILE_ATTRIBUTE_REPARSE_POINT = 0x400

ProgressFn = Callable[[int], None]
"""Recebe o número de bytes processados desde a última chamada."""


def is_reparse_point(entry: os.DirEntry | Path) -> bool:
    """True para junction, symlink ou qualquer outro reparse point."""
    try:
        if isinstance(entry, os.DirEntry):
            st = entry.stat(follow_symlinks=False)
        else:
            st = entry.lstat()
    except OSError:
        return False
    return bool(getattr(st, "st_file_attributes", 0) & FILE_ATTRIBUTE_REPARSE_POINT)


def iter_files(root: Path) -> Iterator[tuple[Path, int]]:
    """Percorre `root` e devolve (caminho, tamanho) de cada arquivo.

    Diretórios inacessíveis são pulados em silêncio: numa varredura de perfil
    inteiro sempre há algo que o usuário não pode ler, e abortar por causa disso
    tornaria a ferramenta inútil.
    """
    stack: list[Path] = [root]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if not is_reparse_point(entry):
                                stack.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            yield Path(entry.path), entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            continue


@dataclass
class Measurement:
    size: int = 0
    files: int = 0


def measure(path: Path, progress: ProgressFn | None = None) -> Measurement:
    """Soma recursiva de um diretório, ou o tamanho de um arquivo único."""
    try:
        st = path.lstat()
    except OSError:
        return Measurement()

    if not stat.S_ISDIR(st.st_mode):
        return Measurement(size=st.st_size, files=1)

    total = 0
    count = 0
    for _, size in iter_files(path):
        total += size
        count += 1
        if progress is not None:
            progress(size)
    return Measurement(size=total, files=count)


def free_space(drive: str) -> int:
    """Bytes livres na letra de unidade informada (ex.: 'D')."""
    letter = drive.rstrip(":/\\")
    return shutil.disk_usage(letter + ":\\").free


@dataclass
class OpResult:
    ok: bool
    bytes_done: int = 0
    files_done: int = 0
    errors: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []


def delete_tree(path: Path, progress: ProgressFn | None = None,
                keep_root: bool = True) -> OpResult:
    """Apaga o conteúdo de um diretório (ou o arquivo, se for arquivo).

    `keep_root=True` preserva a pasta em si — várias ferramentas só recriam o
    cache se o diretório continuar existindo.
    """
    result = OpResult(ok=True)

    try:
        st = path.lstat()
    except OSError as exc:
        return OpResult(ok=False, errors=[f"{path}: {exc}"])

    if not stat.S_ISDIR(st.st_mode):
        try:
            size = st.st_size
            os.chmod(path, stat.S_IWRITE)
            path.unlink()
            result.bytes_done += size
            result.files_done += 1
            if progress:
                progress(size)
        except OSError as exc:
            result.ok = False
            result.errors.append(f"{path}: {exc}")
        return result

    files = list(iter_files(path))

    def _delete_file(item: tuple[Path, int]) -> tuple[bool, Path, int, str | None]:
        file_path, size = item
        try:
            os.chmod(file_path, stat.S_IWRITE)
            file_path.unlink()
            return True, file_path, size, None
        except OSError as exc:
            return False, file_path, size, str(exc)

    if files:
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
            for ok, file_path, size, err in executor.map(_delete_file, files):
                if ok:
                    result.bytes_done += size
                    result.files_done += 1
                else:
                    result.ok = False
                    result.errors.append(f"{file_path}: {err}")
                if progress:
                    progress(size)

    # Segunda passada: remove os diretórios que ficaram vazios, de baixo para cima.
    for current, dirs, _ in os.walk(path, topdown=False):
        for d in dirs:
            target = Path(current) / d
            if is_reparse_point(target):
                continue
            try:
                target.rmdir()
            except OSError:
                pass

    if not keep_root:
        try:
            path.rmdir()
        except OSError as exc:
            result.errors.append(f"{path}: {exc}")

    return result


def _move_tree_robocopy(src: Path, dst: Path, progress: ProgressFn | None = None) -> OpResult:
    """Executa a movimentação usando o utilitário nativo robocopy do Windows em modo multithread."""
    result = OpResult(ok=True)
    dst.mkdir(parents=True, exist_ok=True)

    cmd = [
        "robocopy",
        str(src).rstrip("\\/"),
        str(dst).rstrip("\\/"),
        "/E",
        "/MOVE",
        "/MT:16",
        "/BYTES",
        "/NP",
        "/NJH",
        "/NJS",
        "/NDL",
        "/R:1",
        "/W:1",
        "/XJ",
        "/IS",
        "/IT",
    ]

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="cp850",
            errors="replace",
        )
    except OSError as exc:
        result.ok = False
        result.errors.append(f"Não foi possível executar o robocopy: {exc}")
        return result

    try:
        if proc.stdout is not None:
            for raw_line in proc.stdout:
                line = raw_line.strip()
                if not line:
                    continue
                parts = [p.strip() for p in line.split("\t") if p.strip()]
                if len(parts) >= 3 and parts[1].isdigit():
                    size = int(parts[1])
                    result.bytes_done += size
                    result.files_done += 1
                    if progress:
                        progress(size)
                elif "erro" in line.lower() or "error" in line.lower():
                    result.errors.append(line)
    finally:
        if proc.stdout is not None:
            proc.stdout.close()

    proc.wait()

    # Códigos do robocopy: 0..7 são variações de sucesso, >= 8 indica erro de cópia
    if proc.returncode >= 8:
        result.ok = False
        if not result.errors:
            result.errors.append(f"robocopy retornou código de erro {proc.returncode}")
    else:
        if src.exists():
            # Quando a pasta de destino já continha arquivos (ex.: mesclagem ou tentativa anterior),
            # o robocopy não apaga da origem os arquivos que já eram idênticos no destino.
            # Verificamos se os arquivos restantes na origem já estão idênticos no destino para limpá-los.
            leftover_files = list(iter_files(src))
            if leftover_files:
                def _verify_and_remove(item: tuple[Path, int]) -> tuple[bool, Path, str | None]:
                    f_path, f_size = item
                    rel = f_path.relative_to(src)
                    target = dst / rel
                    try:
                        if target.is_file() and target.stat().st_size == f_size:
                            os.chmod(f_path, stat.S_IWRITE)
                            f_path.unlink()
                            return True, f_path, None
                        return False, f_path, f"Arquivo ausente ou com tamanho diferente em {target}"
                    except OSError as exc:
                        return False, f_path, str(exc)

                with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
                    for ok, f_path, err in executor.map(_verify_and_remove, leftover_files):
                        if not ok:
                            result.ok = False
                            result.errors.append(f"{f_path}: {err}")

            # Remove os diretórios que ficaram vazios
            for current, dirs, _ in os.walk(src, topdown=False):
                for d in dirs:
                    d_path = Path(current) / d
                    if is_reparse_point(d_path):
                        continue
                    try:
                        d_path.rmdir()
                    except OSError:
                        pass

            try:
                if not any(src.iterdir()):
                    src.rmdir()
                elif result.ok:
                    result.ok = False
                    result.errors.append(f"Alguns arquivos não puderam ser movidos de {src}")
            except OSError as exc:
                result.errors.append(f"{src}: {exc}")

    return result


def _move_tree_python(src: Path, dst: Path, progress: ProgressFn | None = None) -> OpResult:
    """Fallback multiplataforma: cópia multithread com cache de diretórios."""
    result = OpResult(ok=True)
    created_dirs: set[Path] = set()
    files = list(iter_files(src))

    def _copy_worker(item: tuple[Path, int]) -> tuple[bool, Path, int, str | None]:
        file_path, size = item
        rel = file_path.relative_to(src)
        target = dst / rel
        try:
            parent = target.parent
            if parent not in created_dirs:
                parent.mkdir(parents=True, exist_ok=True)
                created_dirs.add(parent)
            shutil.copy2(file_path, target)
            return True, file_path, size, None
        except OSError as exc:
            return False, file_path, size, str(exc)

    if files:
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
            for ok, file_path, size, err in executor.map(_copy_worker, files):
                if ok:
                    result.bytes_done += size
                    result.files_done += 1
                else:
                    result.ok = False
                    result.errors.append(f"{file_path}: {err}")
                if progress:
                    progress(size)

    if result.ok:
        removal = delete_tree(src, keep_root=False)
        if not removal.ok:
            result.errors.extend(removal.errors)

    return result


def move_tree(src: Path, dst: Path, progress: ProgressFn | None = None) -> OpResult:
    """Move uma árvore para outro caminho, possivelmente em outro volume.

    No Windows, utiliza o robocopy com multithreading (/MT:16) para velocidade nativa máxima.
    Caso o robocopy não esteja disponível, recorre a cópia paralela via ThreadPoolExecutor.
    """
    result = OpResult(ok=True)

    try:
        src_stat = src.lstat()
    except OSError as exc:
        return OpResult(ok=False, errors=[f"{src}: {exc}"])

    dst.mkdir(parents=True, exist_ok=True)

    if not stat.S_ISDIR(src_stat.st_mode):
        try:
            shutil.copy2(src, dst / src.name)
            result.bytes_done += src_stat.st_size
            result.files_done += 1
            if progress:
                progress(src_stat.st_size)
            os.chmod(src, stat.S_IWRITE)
            src.unlink()
        except OSError as exc:
            result.ok = False
            result.errors.append(f"{src}: {exc}")
        return result

    if os.name == "nt" and shutil.which("robocopy"):
        return _move_tree_robocopy(src, dst, progress)
    return _move_tree_python(src, dst, progress)


def human(size: float) -> str:
    """Formata bytes de forma legível."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024 or unit == "TB":
            if unit in ("B", "KB"):
                return f"{size:.0f} {unit}"
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"
