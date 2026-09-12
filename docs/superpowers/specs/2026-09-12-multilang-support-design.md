# Multi-Language Support (pt-BR / en-US) Design Specification

## Overview
Transform DiskTriage into a multi-language CLI tool with initial support for Portuguese (`pt-BR`, default) and English (`en-US`).
On the first run, the tool asks the user to pick a language and persists the choice so they are not prompted again. The language can also be changed at any time via a Main Menu option or a `--lang` / `--language` CLI parameter.
All code comments and docstrings across the codebase are refactored into English to facilitate open-source collaboration.

---

## 1. Internationalization Architecture (`pydisktriage/i18n.py`)

### 1.1 Supported Locales
- `pt-BR` (Português - Brasil) [Default]
- `en-US` (English - US)
- Normalization: `"pt"`, `"pt_br"`, `"pt-br"` normalize to `"pt-BR"`. `"en"`, `"en_us"`, `"en-us"` normalize to `"en-US"`.

### 1.2 Core Functions
- `get_language() -> str`: Returns current active language code.
- `set_language(lang: str) -> None`: Sets active language code after normalization.
- `t(key: str, **kwargs) -> str`: Looks up the translation string for `key` in the active dictionary. If missing, falls back to `pt-BR`. If still missing, returns `key`. Replaces `{keyword}` parameters with provided `kwargs`.
- `get_available_languages() -> list[tuple[str, str]]`: Returns `[("pt-BR", "Português (Brasil)"), ("en-US", "English (US)")]`.

### 1.3 Translation Catalog
Translation tables for `pt-BR` and `en-US` covering:
- **General UI**: Banner tagline, summaries, status indicators (`ok`, `warn`, `error`, `info`), confirmation messages.
- **Health Diagnostics**: Volume table headers and verdicts (`CRÍTICO`/`CRITICAL`, `apertado`/`tight`, `ok`), latency table headers, SSD latency warnings, pagefiles, bugchecks.
- **Main Menu**: All menu items, titles, prompts, exit greeting.
- **Item Actions**: Action selection menu, delete confirmation prompt, move prompts, environment variable prompts, NTFS junction prompts, Explorer open.
- **Bulk Delete**: Warnings, confirmation keyword prompt (`APAGAR` vs `DELETE`), progress, freed space summary.
- **Export**: Output path prompt, table headers for CSV/JSON, export success.
- **NTFS Junction Management**: Table headers, status (`Ativa`/`Active`, `Revertida`/`Reverted`), revert confirmation and progress.
- **Categories & Catalog Notes**: Category labels (`Descartável`/`Disposable`, `Movível`/`Relocatable`, `Revisar`/`Review`), notes for known caches.

---

## 2. Configuration & First-Run Flow (`pydisktriage/config.py`)

### 2.1 File Location
- `%LOCALAPPDATA%\DiskTriage\config.json` (or `~/.disktriage/config.json`).

### 2.2 Schema
```json
{
  "language": "pt-BR"
}
```

### 2.3 Language Resolution Priority
1. `--lang <codecode>` CLI flag (overrides configuration for the current run).
2. Saved `language` field in `config.json`.
3. **First-Run Interactive Prompt**:
   - If `config.json` does not exist or has no valid `language` setting:
     - Display a clean language selection prompt:
       - `1` - Português (Brasil) (padrão)
       - `2` - English (US)
     - Save choice to `config.json`.
     - Set active language in `i18n`.

### 2.4 Switching Language Later
- **CLI Flag**: `disktriage --lang en-US`
- **Main Menu**: Add a new option (e.g. `9: Mudar idioma / Change language`). When selected:
  - Presents language selection list.
  - Updates active session language immediately.
  - Persists new choice to `config.json`.

---

## 3. Codebase Docstrings & Comments Refactoring

All Portuguese docstrings and comments across `pydisktriage` will be converted to clear, professional English:
- `__init__.py`, `__main__.py`
- `actions.py`
- `cache.py`
- `catalog.py`
- `cli.py`
- `config.py`
- `envvars.py`
- `fsutil.py`
- `health.py`
- `interactive.py`
- `junctions.py`
- `scanner.py`
- `ui.py`

---

## 4. Verification & Testing

1. **Unit Tests**:
   - `tests/test_i18n.py`: Test normalization, translations, missing key fallback, and interpolation in both `pt-BR` and `en-US`.
   - `tests/test_config.py`: Test loading, saving, and defaults.
   - Update existing tests (`test_interactive.py`, `test_actions.py`, etc.) to ensure independence from language state.
2. **Automated Suite**: Run `.venv\Scripts\pytest` to verify 100% pass rate.
3. **Manual Verification**: Run CLI via PowerShell testing first-run prompt, language change, and `--lang` flag.
