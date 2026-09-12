"""NTFS Junction (mklink /J) management: relocation, persistence, and rollback."""

from __future__ import annotations

import json
import os
import subprocess
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from .fsutil import is_reparse_point, move_tree, ProgressFn
from .i18n import t


def get_default_junctions_file() -> Path:
    """Return default tracking JSON file path in %LOCALAPPDATA%\\DiskTriage\\junctions.json."""
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
    """Load tracked junction records from JSON file."""
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
    """Safely save junction records list to JSON file."""
    file_path = path or get_default_junctions_file()
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(r) for r in records]
        file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except OSError:
        return False


def create_junction_link(src: Path, dst: Path) -> tuple[bool, str]:
    """Create an NTFS Junction point at `src` pointing to `dst`.

    On Windows, `cmd /c mklink /J` does not require administrator privileges.
    """
    if src.exists():
        return False, f"Source path already exists: {src}"

    if not dst.exists():
        return False, f"Destination path does not exist: {dst}"

    cmd = ["cmd", "/c", "mklink", "/J", str(src).rstrip("\\/"), str(dst).rstrip("\\/")]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="cp850", errors="replace")
        if proc.returncode != 0:
            err = proc.stderr.strip() or proc.stdout.strip()
            return False, t("junctions.mklink_failed", err=err)

        if not (src.exists() and is_reparse_point(src)):
            return False, f"Junction executed but could not be verified at {src}"

        return True, f"Junction created: {src} -> {dst}"
    except OSError as exc:
        return False, t("junctions.mklink_failed", err=str(exc))


def remove_junction_link(src: Path) -> tuple[bool, str]:
    """Safely remove the junction reparse link without touching destination data."""
    if not src.exists():
        return False, f"Path does not exist: {src}"

    if not is_reparse_point(src):
        return False, f"Path is not a valid junction/reparse point: {src}"

    try:
        # On Windows, os.rmdir on an NTFS junction removes ONLY the link, preserving target contents.
        os.rmdir(src)
        return True, f"Junction link removed: {src}"
    except OSError as exc:
        return False, t("junctions.rmdir_failed", src=src, err=str(exc))


def move_and_create_junction(
    src: Path,
    dst: Path,
    name: str,
    size: int = 0,
    progress: ProgressFn | None = None,
    junctions_file: Path | None = None,
) -> tuple[bool, str, str | None]:
    """Move folder to another disk and establish an NTFS directory junction at the original location.

    Returns: (success, message, junction_id).
    """
    if is_reparse_point(src):
        return False, f"{src} is already an NTFS junction.", None

    # 1. Relocate files
    move_result = move_tree(src, dst, progress=progress)
    if not move_result.ok:
        err_msg = "; ".join(move_result.errors[:3]) if move_result.errors else "Unknown error"
        return False, f"File relocation failed: {err_msg}", None

    # 2. Create junction link
    link_ok, link_msg = create_junction_link(src, dst)
    if not link_ok:
        # Rollback: attempt to move files back
        move_tree(dst, src)
        return False, f"Failed to create junction ({link_msg}). Files restored to source.", None

    # 3. Track junction for rollback support
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

    return True, f"Junction successfully created for {name}.", junction_id


def revert_junction(
    junction_id: str,
    progress: ProgressFn | None = None,
    junctions_file: Path | None = None,
) -> tuple[bool, str]:
    """Revert an NTFS junction: remove link and move files back to original location."""
    records = load_junctions(junctions_file)
    target_record: JunctionRecord | None = None
    for r in records:
        if r.id == junction_id and r.active:
            target_record = r
            break

    if not target_record:
        return False, t("junctions.not_found_by_id", jid=junction_id)

    src = Path(target_record.src)
    dst = Path(target_record.dst)

    if not src.exists():
        return False, t("junctions.src_missing", src=src)

    if not is_reparse_point(src):
        return False, t("junctions.src_not_reparse", src=src)

    if not dst.exists():
        return False, t("junctions.dst_missing", dst=dst)

    # 1. Remove junction link at source
    rem_ok, rem_msg = remove_junction_link(src)
    if not rem_ok:
        return False, rem_msg

    # 2. Move data back from dst to src
    move_result = move_tree(dst, src, progress=progress)
    if not move_result.ok:
        # Re-create junction link so destination is not orphaned
        create_junction_link(src, dst)
        errs = "; ".join(move_result.errors[:3])
        return False, f"Failed to restore files to {src}: {errs}"

    # 3. Update record status
    target_record.active = False
    target_record.reverted_at = datetime.now().isoformat(timespec="minutes")
    save_junctions(records, junctions_file)

    return True, t("junctions.revert_success", src=src)
