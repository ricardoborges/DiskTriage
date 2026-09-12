"""Catalog of known cache and temporary directories.

Each entry describes a directory (or file) that commonly accumulates gigabytes
on a development machine, along with:

  * category — whether it can be safely discarded, moved to another disk, or
    requires human review;
  * environment variable that redirects the tool to a new path;
  * native clean command (almost always preferred over manual file deletion).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .i18n import t

DISCARD = "descartavel"
MOVE = "movivel"
REVIEW = "revisar"

CATEGORY_ORDER = [DISCARD, MOVE, REVIEW]

CATEGORY_STYLE = {
    DISCARD: "green",
    MOVE: "yellow",
    REVIEW: "magenta",
}


def get_category_label(kind: str) -> str:
    """Return the localized label for a category kind."""
    if kind == DISCARD:
        return t("category.discard")
    if kind == MOVE:
        return t("category.move")
    if kind == REVIEW:
        return t("category.review")
    return kind


class _CategoryLabelProxy(dict):
    """Proxy dictionary for backward compatibility with CATEGORY_LABEL[kind]."""

    def __getitem__(self, key: str) -> str:
        return get_category_label(key)

    def get(self, key: str, default: str | None = None) -> str:
        if key in CATEGORY_ORDER:
            return get_category_label(key)
        return default if default is not None else key


CATEGORY_LABEL = _CategoryLabelProxy({
    DISCARD: "Descartável",
    MOVE: "Movível",
    REVIEW: "Revisar",
})

#: System-protected paths that the tool refuses to delete or move under any circumstances.
#: Modifying them manually damages Windows or software uninstallation integrity.
PROTECTED = (
    "windows\\winsxs",
    "windows\\installer",
    "windows\\system32",
    "windows\\syswow64",
    "program files",
    "program files (x86)",
)


@dataclass(frozen=True)
class Target:
    """A catalog entry before disk measurement."""

    ident: str
    path: Path
    kind: str
    env_var: str = ""
    clean_cmd: str = ""
    note: str = ""


@dataclass
class Finding:
    """A catalog entry after disk measurement."""

    ident: str
    path: Path
    kind: str
    size: int
    files: int
    is_file: bool
    env_var: str = ""
    clean_cmd: str = ""
    note: str = ""
    discovered: bool = False

    @property
    def gb(self) -> float:
        return round(self.size / 1024**3, 2)

    @property
    def protected(self) -> bool:
        low = str(self.path).lower()
        return any(p in low for p in PROTECTED)

    @property
    def localized_note(self) -> str:
        """Return localized note if available, otherwise return raw note."""
        key = "catalog.note." + self.ident.replace("-", "_")
        localized = t(key)
        if localized != key:
            return localized
        return self.note


def build_catalog(home: Path | None = None) -> list[Target]:
    """Build the catalog resolved for the specified user profile directory."""
    u = Path(home or Path.home())
    la = u / "AppData" / "Local"
    ra = u / "AppData" / "Roaming"
    win = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    sysdrive = Path(os.environ.get("SystemDrive", "C:") + "\\")
    progdata = Path(os.environ.get("ProgramData", r"C:\ProgramData"))

    t_list: list[Target] = []
    add = t_list.append

    # ------------------------------ Pure cache / disposable ------------------------------
    add(Target("temp-user", la / "Temp", DISCARD, note="User temporary files"))
    add(Target("temp-win", win / "Temp", DISCARD, note="Windows temporary files"))
    add(Target("crashdumps", la / "CrashDumps", DISCARD, note="Crashed process core dumps"))
    add(Target("winre-agent", sysdrive / "$WinREAgent", DISCARD, note="Windows Update servicing leftovers"))
    add(Target("wu-download", win / "SoftwareDistribution" / "Download", DISCARD,
               clean_cmd="Stop-Service wuauserv,bits", note="Already installed Windows Updates"))
    add(Target("d3dcache", la / "D3DSCache", DISCARD, note="DirectX shader cache"))
    add(Target("nv-dxcache", la / "NVIDIA" / "DXCache", DISCARD, note="NVIDIA shader cache"))
    add(Target("nv-glcache", la / "NVIDIA" / "GLCache", DISCARD, note="OpenGL shader cache"))
    add(Target("choco-bad", progdata / "chocolatey" / "lib-bad", DISCARD,
               note="Failed Chocolatey package installations"))

    # ------------- Developer caches: disposable AND relocatable --------------
    add(Target("npm-cache", la / "npm-cache", MOVE, "npm_config_cache",
               "npm cache clean --force", "npm package cache"))
    add(Target("yarn-cache", la / "Yarn" / "Cache", MOVE, "YARN_CACHE_FOLDER",
               "yarn cache clean", "Yarn cache"))
    add(Target("pnpm-store", la / "pnpm-store", MOVE, "PNPM_HOME",
               "pnpm store prune", "pnpm global store"))
    add(Target("pip-cache", la / "pip" / "Cache", MOVE, "PIP_CACHE_DIR",
               "pip cache purge", "pip download cache"))
    add(Target("uv-cache", la / "uv" / "cache", MOVE, "UV_CACHE_DIR",
               "uv cache clean", "uv cache"))
    add(Target("poetry", la / "pypoetry" / "Cache", MOVE, "POETRY_CACHE_DIR",
               "poetry cache clear --all .", "Poetry cache"))
    add(Target("nuget", u / ".nuget" / "packages", MOVE, "NUGET_PACKAGES",
               "dotnet nuget locals all --clear", "NuGet packages"))
    add(Target("gradle", u / ".gradle", MOVE, "GRADLE_USER_HOME",
               note="Gradle cache"))
    add(Target("maven", u / ".m2" / "repository", MOVE,
               note="Maven repository (configure in settings.xml)"))
    add(Target("cargo", u / ".cargo", MOVE, "CARGO_HOME",
               note="Cargo registry and prebuilt binaries"))
    add(Target("rustup", u / ".rustup", MOVE, "RUSTUP_HOME",
               "rustup toolchain list", "Rust toolchains"))
    add(Target("go-mod", u / "go" / "pkg" / "mod", MOVE, "GOMODCACHE",
               "go clean -modcache", "Go module cache"))
    add(Target("pyenv", u / ".pyenv", MOVE, "PYENV_ROOT",
               "pyenv versions", "Installed Python versions"))
    add(Target("conda-pkgs", u / "anaconda3" / "pkgs", MOVE, "CONDA_PKGS_DIRS",
               "conda clean --all", "Conda package cache"))
    add(Target("playwright", la / "ms-playwright", MOVE, "PLAYWRIGHT_BROWSERS_PATH",
               note="Playwright headless browsers"))
    add(Target("puppeteer", la / "Puppeteer", MOVE, "PUPPETEER_CACHE_DIR",
               note="Puppeteer headless browsers"))
    add(Target("scoop-cache", u / "scoop" / "cache", MOVE, "SCOOP_CACHE",
               "scoop cache rm *", "Scoop download cache"))
    add(Target("vcpkg-arch", la / "vcpkg" / "archives", MOVE, "VCPKG_DEFAULT_BINARY_CACHE",
               note="vcpkg binary archives"))

    # ---------------- AI models: highest disk usage offenders -------------------
    add(Target("hf-cache", u / ".cache" / "huggingface", MOVE, "HF_HOME",
               note="Hugging Face AI models"))
    add(Target("torch-cache", u / ".cache" / "torch", MOVE, "TORCH_HOME",
               note="PyTorch AI models"))
    add(Target("whisper", u / ".cache" / "whisper", MOVE, "XDG_CACHE_HOME",
               note="Whisper audio models"))
    add(Target("clip-cache", u / ".cache" / "clip", MOVE, "XDG_CACHE_HOME",
               note="CLIP vision models"))
    add(Target("ollama", u / ".ollama" / "models", MOVE, "OLLAMA_MODELS",
               "ollama list", "Ollama local models"))
    add(Target("lmstudio", u / ".lmstudio" / "models", REVIEW,
               note="LM Studio models — relocate via app GUI"))

    # ------------------------- Containers and VMs ----------------------------
    add(Target("docker", la / "Docker", REVIEW, clean_cmd="docker system prune -a",
               note="Docker Desktop: Settings > Resources > Advanced > Disk image location"))
    add(Target("wsl-pkgs", la / "Packages", REVIEW,
               note="May contain WSL ext4.vhdx disks — move with wsl --export / --import"))

    # ------------------------ Mobile and game dev ----------------------------
    add(Target("android-sdk", la / "Android" / "Sdk", MOVE, "ANDROID_SDK_ROOT",
               note="Android SDK"))
    add(Target("android-avd", u / ".android" / "avd", MOVE, "ANDROID_AVD_HOME",
               note="Android Virtual Devices (emulators)"))
    add(Target("unity-cache", la / "Unity" / "cache", MOVE, "UNITY_CACHE_PATH",
               note="Unity cache"))
    add(Target("unreal-ddc", la / "UnrealEngine" / "Common" / "DerivedDataCache", DISCARD,
               note="Unreal Engine Derived Data Cache"))

    # ------------------------------ Editors -------------------------------
    add(Target("vscode-cache", ra / "Code" / "Cache", DISCARD, note="VS Code cache"))
    add(Target("vscode-cd", ra / "Code" / "CachedData", DISCARD, note="VS Code CachedData"))
    add(Target("vscode-ext", u / ".vscode" / "extensions", REVIEW,
               clean_cmd="code --list-extensions", note="VS Code extensions"))
    add(Target("vscode-ipch", la / "Microsoft" / "vscode-cpptools" / "ipch", DISCARD,
               note="VS Code C/C++ precompiled headers"))
    add(Target("vscode-cpptools", la / "Microsoft" / "vscode-cpptools", MOVE,
               note="VS Code C/C++ IntelliSense databases (relocate via NTFS Junction)"))
    add(Target("jetbrains", la / "JetBrains", REVIEW, note="JetBrains caches and indexing data"))
    add(Target("postman", la / "Postman", REVIEW,
               note="Installed Postman versions (check for legacy versions)"))

    # ----------------------------- Browsers -----------------------------
    add(Target("chrome-cache", la / "Google" / "Chrome" / "User Data" / "Default" / "Cache",
               DISCARD, note="Google Chrome cache"))
    add(Target("chrome-codecache", la / "Google" / "Chrome" / "User Data" / "Default" / "Code Cache",
               DISCARD, note="Google Chrome script code cache"))
    add(Target("chrome-userdata", la / "Google" / "Chrome" / "User Data", MOVE,
               note="Full Chrome user profile (relocate via NTFS Junction)"))
    add(Target("edge-cache", la / "Microsoft" / "Edge" / "User Data" / "Default" / "Cache",
               DISCARD, note="Microsoft Edge cache"))

    # -------------------------- Tools and AI utilities ---------------------------
    add(Target("ollama-updates", la / "Ollama" / "updates_v2", DISCARD,
               note="Legacy Ollama update installers"))
    add(Target("datalab", la / "datalab", MOVE,
               note="Datalab AI models and OCR caches"))

    # -------------------------------- Games --------------------------------
    add(Target("msfs-rolling", ra / "Microsoft Flight Simulator" / "ROLLINGCACHE.CCC",
               DISCARD, note="MSFS rolling cache — preferred removal via in-game settings"))
    add(Target("msfs-store",
               la / "Packages" / "Microsoft.FlightSimulator_8wekyb3d8bbwe" / "LocalCache",
               REVIEW, note="MSFS cache (Microsoft Store version)"))

    # ------------- System folders with their own cleanup tools -----------------
    add(Target("winsxs", win / "WinSxS", REVIEW,
               clean_cmd="Dism /Online /Cleanup-Image /StartComponentCleanup /ResetBase",
               note="DO NOT delete manually — run DISM"))
    add(Target("win-installer", win / "Installer", REVIEW,
               note="DO NOT delete manually — run PatchCleaner"))

    return t_list
