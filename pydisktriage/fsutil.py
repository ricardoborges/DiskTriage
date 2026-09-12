"""Filesystem traversal, size measurement, file moving, and recursive deletion.

Strictly avoids traversing reparse points (NTFS junctions and symlinks).
Without this precaution, junctions such as `C:\\Users\\All Users` (pointing to `C:\\ProgramData`)
would be double-counted, and recursive deletes could escape the target directory tree.
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
"""Receives the number of bytes processed since the previous invocation."""


def is_reparse_point(entry: os.DirEntry | Path) -> bool:
    """Return True if entry is an NTFS junction, symlink, or other reparse point."""
    try:
        if isinstance(entry, os.DirEntry):
            st = entry.stat(follow_symlinks=False)
        else:
            st = entry.lstat()
    except OSError:
        return False
    return bool(getattr(st, "st_file_attributes", 0) & FILE_ATTRIBUTE_REPARSE_POINT)


def iter_files(root: Path) -> Iterator[tuple[Path, int]]:
    """Traverse `root` yielding (path, file_size) for every regular file.

    Inaccessible folders are silently skipped: scanning a full user profile will
    always encounter locked or unreadable files, and aborting would render the tool unusable.
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
    """Recursive byte summation of a directory or single file size."""
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
    """Free disk space in bytes for specified drive letter (e.g. 'D')."""
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
    """Delete the contents of a directory (or the file if single file).

    `keep_root=True` preserves the root directory itself, as many developer tools
    only recreate their caches if the base folder exists.
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

    # Second pass: remove emptied directories from bottom to top
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
    """Execute folder move using Windows native multi-threaded robocopy."""
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
        result.errors.append(f"Could not execute robocopy: {exc}")
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

    # Robocopy exit codes: 0..7 are success variations, >= 8 indicates copy errors
    if proc.returncode >= 8:
        result.ok = False
        if not result.errors:
            result.errors.append(f"robocopy exited with code {proc.returncode}")
    else:
        if src.exists():
            # If destination already had files (e.g. merging), robocopy leaves identical files in source.
            # Clean up source files that already match destination.
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
                        return False, f_path, f"File missing or size mismatch in {target}"
                    except OSError as exc:
                        return False, f_path, str(exc)

                with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
                    for ok, f_path, err in executor.map(_verify_and_remove, leftover_files):
                        if not ok:
                            result.ok = False
                            result.errors.append(f"{f_path}: {err}")

            # Remove emptied directories
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
                    result.errors.append(f"Some files could not be relocated from {src}")
            except OSError as exc:
                result.errors.append(f"{src}: {exc}")

    return result


def _move_tree_python(src: Path, dst: Path, progress: ProgressFn | None = None) -> OpResult:
    """Multiplatform fallback: multi-threaded copy with folder caching."""
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
    """Move directory tree to another location, possibly on another drive.

    On Windows, uses robocopy with multithreading (/MT:16) for native performance.
    Falls back to parallel Python copy via ThreadPoolExecutor if robocopy is unavailable.
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
    """Format byte size into human-readable representation."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024 or unit == "TB":
            if unit in ("B", "KB"):
                return f"{size:.0f} {unit}"
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"
