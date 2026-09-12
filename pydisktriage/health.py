"""Diagnóstico de saúde: espaço, latência dos discos, pagefile e telas azuis.

Os dados vêm do PowerShell, porque `Get-StorageReliabilityCounter` e
`Get-WinEvent` não têm equivalente decente em Python puro. Cada consulta devolve
JSON, então o parsing é trivial e não depende do idioma do Windows.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

_PS_PRELUDE = "$ProgressPreference='SilentlyContinue';[Console]::OutputEncoding=[Text.Encoding]::UTF8;"


def _run_ps(script: str, timeout: int = 90) -> list[dict]:
    """Roda um trecho de PowerShell que emite JSON e devolve lista de dicts."""
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS_PRELUDE + script],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []

    out = (proc.stdout or "").strip()
    if not out:
        return []
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return [d for d in data if isinstance(d, dict)]
    return []


@dataclass
class VolumeInfo:
    letter: str
    label: str
    free: int
    total: int

    @property
    def pct_free(self) -> float:
        if not self.total:
            return 0.0
        return round(100 * self.free / self.total, 1)

    @property
    def verdict(self) -> str:
        pct = self.pct_free
        if pct < 10:
            return "CRÍTICO"
        if pct < 20:
            return "apertado"
        return "ok"


@dataclass
class DiskLatency:
    name: str
    read_ms: int | None
    write_ms: int | None
    flush_ms: int | None
    temp_c: int | None
    wear: int | None

    @property
    def suspicious(self) -> bool:
        return (self.read_ms or 0) > 500 or (self.flush_ms or 0) > 500


@dataclass
class Bugcheck:
    when: str
    code: str

    #: Tradução dos códigos que mais aparecem em máquina de desenvolvimento.
    MEANINGS = {
        "0x0000001e": "KMODE_EXCEPTION_NOT_HANDLED — exceção não tratada em kernel",
        "0x0000004e": "PFN_LIST_CORRUPT — corrupção de lista de páginas (suspeite da RAM)",
        "0x00000050": "PAGE_FAULT_IN_NONPAGED_AREA",
        "0x0000007e": "SYSTEM_THREAD_EXCEPTION_NOT_HANDLED",
        "0x000000c2": "BAD_POOL_CALLER — driver liberando memória errada",
        "0x000000d1": "DRIVER_IRQL_NOT_LESS_OR_EQUAL",
        "0x0000010d": "WDF_VIOLATION — bug em driver do framework",
        "0x00000133": "DPC_WATCHDOG_VIOLATION — driver travou a CPU",
        "0x00000139": "KERNEL_SECURITY_CHECK_FAILURE — corrupção de estrutura",
        "0x000000ef": "CRITICAL_PROCESS_DIED",
    }

    @property
    def meaning(self) -> str:
        return self.MEANINGS.get(self.code.lower(), "")


def get_volumes() -> list[VolumeInfo]:
    """Espaço livre por volume, via shutil (não depende do PowerShell)."""
    vols: list[VolumeInfo] = []
    labels = {d.get("Letra"): d.get("Rotulo") or ""
              for d in _run_ps(
                  "Get-Volume | Where-Object DriveLetter | "
                  "Select-Object @{n='Letra';e={$_.DriveLetter}},"
                  "@{n='Rotulo';e={$_.FileSystemLabel}} | ConvertTo-Json -Compress")}

    for letter in "CDEFGHIJKLMNOPQRSTUVWXYZAB":
        root = f"{letter}:\\"
        try:
            usage = shutil.disk_usage(root)
        except OSError:
            continue
        if usage.total == 0:
            continue
        vols.append(VolumeInfo(letter, labels.get(letter, ""), usage.free, usage.total))
    return vols


def get_latency() -> tuple[list[DiskLatency], bool]:
    """Contadores de latência por disco físico.

    Precisa de elevação. Devolve (lista, elevado) — lista vazia com elevado=False
    significa que a consulta foi negada, não que os discos estão bem.
    """
    rows = _run_ps(
        "Get-PhysicalDisk | ForEach-Object { $d=$_; "
        "try { $r = $d | Get-StorageReliabilityCounter -ErrorAction Stop; "
        "[PSCustomObject]@{Nome=$d.FriendlyName; Read=$r.ReadLatencyMax; "
        "Write=$r.WriteLatencyMax; Flush=$r.FlushLatencyMax; "
        "Temp=$r.Temperature; Wear=$r.Wear} } catch { } } | ConvertTo-Json -Compress"
    )
    if not rows:
        return [], False

    disks = [
        DiskLatency(
            name=str(r.get("Nome", "?")),
            read_ms=r.get("Read"),
            write_ms=r.get("Write"),
            flush_ms=r.get("Flush"),
            temp_c=r.get("Temp"),
            wear=r.get("Wear"),
        )
        for r in rows
    ]
    return disks, True


def get_pagefiles() -> list[dict]:
    return _run_ps(
        "Get-CimInstance Win32_PageFileUsage | "
        "Select-Object @{n='Caminho';e={$_.Name}},"
        "@{n='TamanhoMB';e={$_.AllocatedBaseSize}},"
        "@{n='PicoMB';e={$_.PeakUsage}} | ConvertTo-Json -Compress"
    )


def get_bugchecks(days: int = 90) -> list[Bugcheck]:
    rows = _run_ps(
        "Get-WinEvent -FilterHashtable @{LogName='System';Id=1001;"
        "ProviderName='Microsoft-Windows-WER-SystemErrorReporting';"
        f"StartTime=(Get-Date).AddDays(-{days})}} -ErrorAction SilentlyContinue | "
        "Select-Object @{n='Quando';e={$_.TimeCreated.ToString('yyyy-MM-dd HH:mm')}},"
        "@{n='Msg';e={$_.Message}} | ConvertTo-Json -Compress"
    )
    result: list[Bugcheck] = []
    for r in rows:
        msg = str(r.get("Msg", ""))
        match = re.search(r"0x[0-9a-fA-F]{8}", msg)
        result.append(Bugcheck(str(r.get("Quando", "?")),
                               match.group(0) if match else "?"))
    return result


def minidump_dir() -> Path:
    import os
    return Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Minidump"
