"""Catálogo de caches conhecidos.

Cada entrada descreve um diretório (ou arquivo) que costuma acumular gigabytes
numa máquina de desenvolvimento, junto com:

  * a categoria — se dá para apagar sem pensar, mover para outro disco, ou se
    exige julgamento humano;
  * a variável de ambiente que redireciona a ferramenta para um novo caminho;
  * o comando nativo da ferramenta para limpar (quase sempre preferível a sair
    apagando arquivo na mão).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

DISCARD = "descartavel"
MOVE = "movivel"
REVIEW = "revisar"

CATEGORY_ORDER = [DISCARD, MOVE, REVIEW]

CATEGORY_STYLE = {
    DISCARD: "green",
    MOVE: "yellow",
    REVIEW: "magenta",
}

CATEGORY_LABEL = {
    DISCARD: "Descartável",
    MOVE: "Movível",
    REVIEW: "Revisar",
}

#: Caminhos que o programa se recusa a apagar ou mover, aconteça o que acontecer.
#: Mexer neles à mão quebra o Windows ou a desinstalação de programas.
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
    """Uma entrada do catálogo, ainda sem medição."""

    ident: str
    path: Path
    kind: str
    env_var: str = ""
    clean_cmd: str = ""
    note: str = ""


@dataclass
class Finding:
    """Uma entrada do catálogo depois de medida no disco."""

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


def build_catalog(home: Path | None = None) -> list[Target]:
    """Monta o catálogo já resolvido para o perfil informado."""

    u = Path(home or Path.home())
    la = u / "AppData" / "Local"
    ra = u / "AppData" / "Roaming"
    win = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    sysdrive = Path(os.environ.get("SystemDrive", "C:") + "\\")
    progdata = Path(os.environ.get("ProgramData", r"C:\ProgramData"))

    t: list[Target] = []
    add = t.append

    # ------------------------------ lixo puro ------------------------------
    add(Target("temp-user", la / "Temp", DISCARD, note="Temporários do usuário"))
    add(Target("temp-win", win / "Temp", DISCARD, note="Temporários do Windows"))
    add(Target("crashdumps", la / "CrashDumps", DISCARD, note="Dumps de processos que travaram"))
    add(Target("winre-agent", sysdrive / "$WinREAgent", DISCARD, note="Resto de servicing de update"))
    add(Target("wu-download", win / "SoftwareDistribution" / "Download", DISCARD,
               clean_cmd="Stop-Service wuauserv,bits", note="Updates já aplicados"))
    add(Target("d3dcache", la / "D3DSCache", DISCARD, note="Cache de shader DirectX"))
    add(Target("nv-dxcache", la / "NVIDIA" / "DXCache", DISCARD, note="Cache de shader NVIDIA"))
    add(Target("nv-glcache", la / "NVIDIA" / "GLCache", DISCARD, note="Cache de shader OpenGL"))
    add(Target("choco-bad", progdata / "chocolatey" / "lib-bad", DISCARD,
               note="Instalações falhas do Chocolatey"))

    # ------------- caches de dev: apagáveis E redirecionáveis --------------
    add(Target("npm-cache", la / "npm-cache", MOVE, "npm_config_cache",
               "npm cache clean --force", "Cache do npm"))
    add(Target("yarn-cache", la / "Yarn" / "Cache", MOVE, "YARN_CACHE_FOLDER",
               "yarn cache clean", "Cache do Yarn"))
    add(Target("pnpm-store", la / "pnpm-store", MOVE, "PNPM_HOME",
               "pnpm store prune", "Store do pnpm"))
    add(Target("pip-cache", la / "pip" / "Cache", MOVE, "PIP_CACHE_DIR",
               "pip cache purge", "Cache do pip"))
    add(Target("uv-cache", la / "uv" / "cache", MOVE, "UV_CACHE_DIR",
               "uv cache clean", "Cache do uv"))
    add(Target("poetry", la / "pypoetry" / "Cache", MOVE, "POETRY_CACHE_DIR",
               "poetry cache clear --all .", "Cache do Poetry"))
    add(Target("nuget", u / ".nuget" / "packages", MOVE, "NUGET_PACKAGES",
               "dotnet nuget locals all --clear", "Pacotes NuGet"))
    add(Target("gradle", u / ".gradle", MOVE, "GRADLE_USER_HOME",
               note="Cache do Gradle"))
    add(Target("maven", u / ".m2" / "repository", MOVE,
               note="Repositório Maven (ajuste settings.xml)"))
    add(Target("cargo", u / ".cargo", MOVE, "CARGO_HOME",
               note="Registry e binários do Cargo"))
    add(Target("rustup", u / ".rustup", MOVE, "RUSTUP_HOME",
               "rustup toolchain list", "Toolchains do Rust"))
    add(Target("go-mod", u / "go" / "pkg" / "mod", MOVE, "GOMODCACHE",
               "go clean -modcache", "Módulos Go"))
    add(Target("pyenv", u / ".pyenv", MOVE, "PYENV_ROOT",
               "pyenv versions", "Versões do Python"))
    add(Target("conda-pkgs", u / "anaconda3" / "pkgs", MOVE, "CONDA_PKGS_DIRS",
               "conda clean --all", "Pacotes conda"))
    add(Target("playwright", la / "ms-playwright", MOVE, "PLAYWRIGHT_BROWSERS_PATH",
               note="Navegadores do Playwright"))
    add(Target("puppeteer", la / "Puppeteer", MOVE, "PUPPETEER_CACHE_DIR",
               note="Navegadores do Puppeteer"))
    add(Target("scoop-cache", u / "scoop" / "cache", MOVE, "SCOOP_CACHE",
               "scoop cache rm *", "Cache do Scoop"))
    add(Target("vcpkg-arch", la / "vcpkg" / "archives", MOVE, "VCPKG_DEFAULT_BINARY_CACHE",
               note="Cache binário do vcpkg"))

    # ---------------- modelos de IA: os maiores ofensores -------------------
    add(Target("hf-cache", u / ".cache" / "huggingface", MOVE, "HF_HOME",
               note="Modelos Hugging Face"))
    add(Target("torch-cache", u / ".cache" / "torch", MOVE, "TORCH_HOME",
               note="Modelos PyTorch"))
    add(Target("whisper", u / ".cache" / "whisper", MOVE, "XDG_CACHE_HOME",
               note="Modelos Whisper"))
    add(Target("clip-cache", u / ".cache" / "clip", MOVE, "XDG_CACHE_HOME",
               note="Modelos CLIP"))
    add(Target("ollama", u / ".ollama" / "models", MOVE, "OLLAMA_MODELS",
               "ollama list", "Modelos do Ollama"))
    add(Target("lmstudio", u / ".lmstudio" / "models", REVIEW,
               note="Modelos do LM Studio — mova pela GUI do app"))

    # ------------------------- containers e VMs ----------------------------
    add(Target("docker", la / "Docker", REVIEW, clean_cmd="docker system prune -a",
               note="Docker Desktop: Settings > Resources > Advanced > Disk image location"))
    add(Target("wsl-pkgs", la / "Packages", REVIEW,
               note="Pode conter ext4.vhdx de distros WSL — mova com wsl --export / --import"))

    # ------------------------ mobile e game dev ----------------------------
    add(Target("android-sdk", la / "Android" / "Sdk", MOVE, "ANDROID_SDK_ROOT",
               note="SDK do Android"))
    add(Target("android-avd", u / ".android" / "avd", MOVE, "ANDROID_AVD_HOME",
               note="Emuladores Android"))
    add(Target("unity-cache", la / "Unity" / "cache", MOVE, "UNITY_CACHE_PATH",
               note="Cache do Unity"))
    add(Target("unreal-ddc", la / "UnrealEngine" / "Common" / "DerivedDataCache", DISCARD,
               note="Derived Data Cache da Unreal"))

    # ------------------------------ editores -------------------------------
    add(Target("vscode-cache", ra / "Code" / "Cache", DISCARD, note="Cache do VS Code"))
    add(Target("vscode-cd", ra / "Code" / "CachedData", DISCARD, note="CachedData do VS Code"))
    add(Target("vscode-ext", u / ".vscode" / "extensions", REVIEW,
               clean_cmd="code --list-extensions", note="Extensões do VS Code"))
    add(Target("vscode-ipch", la / "Microsoft" / "vscode-cpptools" / "ipch", DISCARD,
               note="Cabeçalhos pré-compilados C/C++ do VS Code"))
    add(Target("vscode-cpptools", la / "Microsoft" / "vscode-cpptools", MOVE,
               note="IntelliSense e bancos C/C++ do VS Code (mova via Junção NTFS)"))
    add(Target("jetbrains", la / "JetBrains", REVIEW, note="Caches e índices JetBrains"))
    add(Target("postman", la / "Postman", REVIEW,
               note="Versões instaladas do Postman (verifique versões antigas)"))

    # ----------------------------- navegadores -----------------------------
    add(Target("chrome-cache", la / "Google" / "Chrome" / "User Data" / "Default" / "Cache",
               DISCARD, note="Cache do Chrome"))
    add(Target("chrome-codecache", la / "Google" / "Chrome" / "User Data" / "Default" / "Code Cache",
               DISCARD, note="Code Cache de scripts do Chrome"))
    add(Target("chrome-userdata", la / "Google" / "Chrome" / "User Data", MOVE,
               note="Perfil completo do Chrome (mova via Junção NTFS)"))
    add(Target("edge-cache", la / "Microsoft" / "Edge" / "User Data" / "Default" / "Cache",
               DISCARD, note="Cache do Edge"))

    # -------------------------- ferramentas e IA ---------------------------
    add(Target("ollama-updates", la / "Ollama" / "updates_v2", DISCARD,
               note="Instaladores de atualizações antigas do Ollama"))
    add(Target("datalab", la / "datalab", MOVE,
               note="Modelos e caches de IA (OCR/Marker/Surya) do Datalab"))

    # -------------------------------- jogos --------------------------------
    add(Target("msfs-rolling", ra / "Microsoft Flight Simulator" / "ROLLINGCACHE.CCC",
               DISCARD, note="Rolling cache do MSFS — prefira apagar pelo jogo"))
    add(Target("msfs-store",
               la / "Packages" / "Microsoft.FlightSimulator_8wekyb3d8bbwe" / "LocalCache",
               REVIEW, note="Cache do MSFS (versão Store)"))

    # ------------- pastas do sistema com ferramenta própria -----------------
    add(Target("winsxs", win / "WinSxS", REVIEW,
               clean_cmd="Dism /Online /Cleanup-Image /StartComponentCleanup /ResetBase",
               note="NÃO apague na mão — use o DISM"))
    add(Target("win-installer", win / "Installer", REVIEW,
               note="NÃO apague na mão — use o PatchCleaner"))

    return t
