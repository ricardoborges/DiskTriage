"""Persistência em cache da última varredura para inicialização instantânea."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .catalog import Finding


def get_default_cache_path() -> Path:
    """Retorna o caminho padrão do arquivo de cache em %LOCALAPPDATA%\\DiskTriage\\last_scan.json."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        base_dir = Path(local_app_data) / "DiskTriage"
    else:
        base_dir = Path.home() / ".disktriage"
    return base_dir / "last_scan.json"


@dataclass
class CachedScan:
    timestamp: str
    home: Path
    min_gb: float
    discovery: bool
    findings: list[Finding]
    large_files: list[tuple[Path, int]]

    @property
    def formatted_time(self) -> str:
        """Formata o timestamp para exibição amigável (DD/MM/AAAA HH:MM)."""
        try:
            dt = datetime.fromisoformat(self.timestamp)
            return dt.strftime("%d/%m/%Y %H:%M")
        except (ValueError, TypeError):
            return self.timestamp


def save_scan_cache(
    findings: list[Finding],
    large_files: list[tuple[Path, int]],
    home: Path,
    min_gb: float,
    discovery: bool,
    cache_file: Path | None = None,
) -> bool:
    """Salva a varredura atual em disco de forma atômica."""
    target_file = cache_file or get_default_cache_path()

    try:
        target_file.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False

    payload = {
        "timestamp": datetime.now().isoformat(timespec="minutes"),
        "home": str(home),
        "min_gb": min_gb,
        "discovery": discovery,
        "findings": [
            {
                "ident": f.ident,
                "path": str(f.path),
                "kind": f.kind,
                "size": f.size,
                "files": f.files,
                "is_file": f.is_file,
                "env_var": f.env_var,
                "clean_cmd": f.clean_cmd,
                "note": f.note,
                "discovered": f.discovered,
            }
            for f in findings
        ],
        "large_files": [[str(path), size] for path, size in large_files],
    }

    try:
        # Gravação atômica com arquivo temporário no mesmo diretório
        temp_dir = target_file.parent
        with tempfile.NamedTemporaryFile("w", dir=temp_dir, delete=False, encoding="utf-8") as tf:
            json.dump(payload, tf, ensure_ascii=False, indent=2)
            temp_path = Path(tf.name)
        temp_path.replace(target_file)
        return True
    except OSError:
        return False


def load_scan_cache(cache_file: Path | None = None) -> CachedScan | None:
    """Carrega a última varredura do disco. Retorna None se não existir ou estiver corrompido."""
    target_file = cache_file or get_default_cache_path()

    if not target_file.is_file():
        return None

    try:
        data = json.loads(target_file.read_text(encoding="utf-8"))
        findings = [
            Finding(
                ident=item["ident"],
                path=Path(item["path"]),
                kind=item["kind"],
                size=item["size"],
                files=item["files"],
                is_file=item.get("is_file", False),
                env_var=item.get("env_var", ""),
                clean_cmd=item.get("clean_cmd", ""),
                note=item.get("note", ""),
                discovered=item.get("discovered", False),
            )
            for item in data.get("findings", [])
        ]
        large_files = [
            (Path(item[0]), item[1]) for item in data.get("large_files", [])
        ]

        return CachedScan(
            timestamp=data.get("timestamp", ""),
            home=Path(data.get("home", str(Path.home()))),
            min_gb=float(data.get("min_gb", 1.0)),
            discovery=bool(data.get("discovery", False)),
            findings=findings,
            large_files=large_files,
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError, OSError):
        return None


def clear_scan_cache(cache_file: Path | None = None) -> bool:
    """Remove o arquivo de cache se existir."""
    target_file = cache_file or get_default_cache_path()
    try:
        if target_file.exists():
            target_file.unlink()
        return True
    except OSError:
        return False
