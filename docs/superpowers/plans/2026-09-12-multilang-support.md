# Multi-Language Support (pt-BR / en-US) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement multi-language support in DiskTriage (`pt-BR` default, `en-US`), persistent first-run language prompt, main menu language switcher, `--lang` CLI flag, and translate all codebase docstrings and comments into English.

**Architecture:** A lightweight pure-Python `i18n` dictionary catalog with fallback to `pt-BR` and keyword formatting, backed by JSON persistence in `%LOCALAPPDATA%\DiskTriage\config.json`. UI elements, tables, rules, and prompts in `pydisktriage` consume localized strings through `t(key, **kwargs)`.

**Tech Stack:** Python 3.10+, Rich, pytest.

**Spec:** `docs/superpowers/specs/2026-09-12-multilang-support-design.md`

## Global Constraints
- Target OS: Windows 11 with PowerShell terminal.
- Default language: `pt-BR`. Secondary language: `en-US`.
- All docstrings and internal code comments in `pydisktriage` must be in English.
- No external runtime dependencies beyond what is already in `pyproject.toml` (Rich).
- All tests must be executed with `.venv\Scripts\pytest`.

---

### Task 1: Internationalization Module (`pydisktriage/i18n.py`)

**Files:**
- Create: `pydisktriage/i18n.py`
- Create: `tests/test_i18n.py`

**Interfaces:**
- Produces:
  - `set_language(lang: str) -> None`
  - `get_language() -> str`
  - `normalize_language(lang: str) -> str`
  - `t(key: str, **kwargs) -> str`
  - `get_available_languages() -> list[tuple[str, str]]`

- [ ] **Step 1: Write failing unit tests for `i18n`**

Create `tests/test_i18n.py`:
```python
import unittest
from pydisktriage.i18n import (
    get_available_languages,
    get_language,
    normalize_language,
    set_language,
    t,
)

class TestI18n(unittest.TestCase):
    def setUp(self):
        set_language("pt-BR")

    def test_normalize_language(self):
        self.assertEqual(normalize_language("pt"), "pt-BR")
        self.assertEqual(normalize_language("pt_BR"), "pt-BR")
        self.assertEqual(normalize_language("pt-br"), "pt-BR")
        self.assertEqual(normalize_language("en"), "en-US")
        self.assertEqual(normalize_language("en_US"), "en-US")
        self.assertEqual(normalize_language("en-us"), "en-US")
        self.assertEqual(normalize_language("unknown"), "pt-BR")

    def test_set_and_get_language(self):
        set_language("en-US")
        self.assertEqual(get_language(), "en-US")
        set_language("pt-BR")
        self.assertEqual(get_language(), "pt-BR")

    def test_translation_pt_and_en(self):
        set_language("pt-BR")
        pt_text = t("menu.exit")
        self.assertEqual(pt_text, "Sair")

        set_language("en-US")
        en_text = t("menu.exit")
        self.assertEqual(en_text, "Exit")

    def test_translation_fallback(self):
        set_language("en-US")
        # If key is completely missing, return key
        self.assertEqual(t("non.existent.key"), "non.existent.key")

    def test_translation_formatting(self):
        set_language("en-US")
        msg = t("actions.freed_space", size="10 GB", files=5)
        self.assertIn("10 GB", msg)
        self.assertIn("5", msg)

    def test_get_available_languages(self):
        langs = get_available_languages()
        self.assertEqual(len(langs), 2)
        codes = [code for code, _ in langs]
        self.assertIn("pt-BR", codes)
        self.assertIn("en-US", codes)

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest tests/test_i18n.py`
Expected: FAIL (`ModuleNotFoundError: No module named 'pydisktriage.i18n'`)

- [ ] **Step 3: Implement `pydisktriage/i18n.py`**

Create `pydisktriage/i18n.py` with dictionary tables for `pt-BR` and `en-US` and all standard keys used across DiskTriage (menu, health, actions, junctions, bulk_delete, export, summary, etc.). All docstrings and comments in English.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\pytest tests/test_i18n.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pydisktriage/i18n.py tests/test_i18n.py
git commit -m "feat(i18n): add internationalization module with pt-BR and en-US"
```

---

### Task 2: Configuration & Persistence Module (`pydisktriage/config.py`)

**Files:**
- Create: `pydisktriage/config.py`
- Create: `tests/test_config.py`

**Interfaces:**
- Consumes: `pydisktriage.i18n.normalize_language`
- Produces:
  - `get_default_config_path() -> Path`
  - `load_config(config_file: Path | None = None) -> dict`
  - `save_config(config: dict, config_file: Path | None = None) -> bool`
  - `get_configured_language(config_file: Path | None = None) -> str | None`
  - `set_configured_language(lang: str, config_file: Path | None = None) -> bool`

- [ ] **Step 1: Write failing unit tests for `config`**

Create `tests/test_config.py`:
```python
import tempfile
import unittest
from pathlib import Path
from pydisktriage.config import (
    get_configured_language,
    load_config,
    save_config,
    set_configured_language,
)

class TestConfig(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.tmp_dir.name) / "config.json"

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_load_non_existent_config(self):
        cfg = load_config(self.config_path)
        self.assertEqual(cfg, {})
        self.assertIsNone(get_configured_language(self.config_path))

    def test_save_and_load_config(self):
        success = save_config({"language": "en-US"}, self.config_path)
        self.assertTrue(success)
        cfg = load_config(self.config_path)
        self.assertEqual(cfg.get("language"), "en-US")

    def test_set_and_get_configured_language(self):
        set_configured_language("pt-br", self.config_path)
        self.assertEqual(get_configured_language(self.config_path), "pt-BR")

        set_configured_language("en", self.config_path)
        self.assertEqual(get_configured_language(self.config_path), "en-US")

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest tests/test_config.py`
Expected: FAIL (`ModuleNotFoundError: No module named 'pydisktriage.config'`)

- [ ] **Step 3: Implement `pydisktriage/config.py`**

Implement atomic JSON persistence to `%LOCALAPPDATA%\DiskTriage\config.json` (or fallback). Include English comments and docstrings.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\pytest tests/test_config.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pydisktriage/config.py tests/test_config.py
git commit -m "feat(config): add persistent configuration management"
```

---

### Task 3: Localize & Document `catalog.py` and `health.py`

**Files:**
- Modify: `pydisktriage/catalog.py`
- Modify: `pydisktriage/health.py`
- Update: `tests/test_interactive.py` (if needed for category labels)

**Interfaces:**
- Consumes: `pydisktriage.i18n.t`
- Produces:
  - `get_category_label(kind: str) -> str`
  - `get_finding_note(ident: str, default_note: str = "") -> str`
  - `VolumeInfo.verdict_label -> str`

- [ ] **Step 1: Check existing behavior**
Run: `.venv\Scripts\pytest` to verify current status.

- [ ] **Step 2: Refactor `catalog.py`**
- Change all comments and docstrings in `catalog.py` to English.
- Add helper `get_category_label(kind: str) -> str` dynamically retrieving localized category names via `t()`.
- Update `CATEGORY_LABEL` to dynamically return localized labels or maintain backward-compatible proxy.
- Provide English & Portuguese translations for target notes in `i18n` catalog and helper `get_finding_note(ident, default)`.

- [ ] **Step 3: Refactor `health.py`**
- Change all comments and docstrings in `health.py` to English.
- Update `VolumeInfo` with `verdict_label` using `t("health.verdict_critical")`, `t("health.verdict_tight")`, `t("health.verdict_ok")`.

- [ ] **Step 4: Run test suite to verify tests pass**
Run: `.venv\Scripts\pytest`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add pydisktriage/catalog.py pydisktriage/health.py
git commit -m "refactor(catalog,health): localize labels and translate docstrings to English"
```

---

### Task 4: Localize Presentation Layer (`ui.py` and `interactive.py`)

**Files:**
- Modify: `pydisktriage/ui.py`
- Modify: `pydisktriage/interactive.py`
- Modify: `tests/test_interactive.py`

**Interfaces:**
- Consumes: `pydisktriage.i18n.t`, `pydisktriage.catalog.get_category_label`

- [ ] **Step 1: Refactor `pydisktriage/ui.py`**
- Translate all comments and docstrings to English.
- Localize banner tagline: `t("ui.banner_subtitle")`.
- Localize table titles and column headers:
  - `volumes_table`: "Espaço por volume" -> `t("ui.volumes_title")`, columns ("Unidade", "Rótulo", "Livre", "Total", "% livre", "Situação").
  - `latency_table`: "Latência máxima registrada" -> `t("ui.latency_title")`, columns ("Disco", "Leitura", "Escrita", "Flush", "Temp", "Desgaste").
  - `bugchecks_table`: "Telas azuis" -> `t("ui.bugchecks_title")`, columns ("Quando", "Código", "Significado").
  - `findings_table`: columns ("Tamanho", "Item", "Categoria", "Caminho", "Variável").
  - `large_files_table`: "Arquivos únicos grandes" -> `t("ui.large_files_title")`, columns ("Tamanho", "Arquivo").
  - `summary_panel`: "Resumo" -> `t("ui.summary_title")`, "Recuperável sem julgamento humano" -> `t("ui.summary_reclaimable")`.

- [ ] **Step 2: Refactor `pydisktriage/interactive.py`**
- Translate all comments and docstrings to English.
- In `select_menu` and `select_finding`, localize prompt text `t("interactive.choice_prompt")`, footer help `t("interactive.findings_help")`.

- [ ] **Step 3: Update `tests/test_interactive.py`**
Ensure tests pass regardless of active language.

- [ ] **Step 4: Run test suite**
Run: `.venv\Scripts\pytest`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add pydisktriage/ui.py pydisktriage/interactive.py tests/test_interactive.py
git commit -m "refactor(ui,interactive): localize presentation layer and translate docstrings to English"
```

---

### Task 5: Localize Action Handlers & Supporting Modules (`actions.py`, `junctions.py`, `envvars.py`, `fsutil.py`, `scanner.py`, `cache.py`)

**Files:**
- Modify: `pydisktriage/actions.py`
- Modify: `pydisktriage/junctions.py`
- Modify: `pydisktriage/envvars.py`
- Modify: `pydisktriage/fsutil.py`
- Modify: `pydisktriage/scanner.py`
- Modify: `pydisktriage/cache.py`

**Interfaces:**
- Consumes: `pydisktriage.i18n.t`

- [ ] **Step 1: Refactor `actions.py`**
- Translate all comments and docstrings to English.
- Localize rules, prompts, warnings, error messages, and progress descriptions:
  - `_guard`: protected item message.
  - `action_delete`: confirm prompt, progress task "deleting", success message.
  - `action_move`: drive prompt, insufficient space, merge confirm, progress task "copying", env var prompt & confirmation.
  - `action_set_env`: variable name, value prompt, success.
  - `action_run_clean_cmd`: rule and advice.
  - `action_open`: Explorer open message.
  - `action_move_junction`: junction explanation, progress, success message.
  - `action_manage_junctions`: junction table headers, status (Active/Reverted), revert confirm prompt, progress, success.

- [ ] **Step 2: Refactor `junctions.py`**
- Translate all comments and docstrings to English.
- Localize return messages from `move_and_create_junction` and `revert_junction`.

- [ ] **Step 3: Refactor `envvars.py`, `fsutil.py`, `scanner.py`, `cache.py`**
- Translate all comments and docstrings to English.
- Scanner progress task descriptions ("catalog", "discovery", "large files").

- [ ] **Step 4: Run test suite**
Run: `.venv\Scripts\pytest`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add pydisktriage/actions.py pydisktriage/junctions.py pydisktriage/envvars.py pydisktriage/fsutil.py pydisktriage/scanner.py pydisktriage/cache.py
git commit -m "refactor(actions,junctions,fsutil): localize action strings and translate docstrings to English"
```

---

### Task 6: CLI Loop, First-Run Selection, and Language Switcher (`cli.py`, `__init__.py`, `__main__.py`)

**Files:**
- Modify: `pydisktriage/cli.py`
- Modify: `pydisktriage/__init__.py`
- Modify: `pydisktriage/__main__.py`
- Create/Update: `tests/test_cli_cache.py`

**Interfaces:**
- Consumes: `pydisktriage.i18n`, `pydisktriage.config`

- [ ] **Step 1: Refactor `__init__.py` and `__main__.py`**
- Translate docstrings and comments to English.

- [ ] **Step 2: Refactor `cli.py`**
- Translate all comments and docstrings to English.
- Add `--lang` / `--language` to `build_parser()`.
- Add first-run language prompt:
  - If `--lang` passed: set and save language.
  - Else check `get_configured_language()`.
  - If None (first run):
    - Present language selection menu (`1. Português (Brasil)`, `2. English (US)`).
    - Save selection to config file.
    - Set language in `i18n`.
- Add Main Menu option:
  - `("9", t("menu.change_language"))` (or appropriate slot before Exit).
  - When selected: displays language choices, switches active session language, and updates `config.json`.
- Localize all screens in `cli.py`:
  - `screen_health`
  - `screen_scan`
  - `screen_item_actions`
  - `screen_bulk_delete` (confirm keyword `APAGAR` in `pt-BR`, `DELETE` in `en-US`)
  - `screen_export` (destination prompt, CSV/JSON filenames `triagem`/`triage` or localized export)
  - `get_main_menu`
  - `main` and `run`

- [ ] **Step 3: Run test suite**
Run: `.venv\Scripts\pytest`
Expected: PASS

- [ ] **Step 4: Commit**
```bash
git add pydisktriage/cli.py pydisktriage/__init__.py pydisktriage/__main__.py
git commit -m "feat(cli): add first-run language selection, --lang flag, and menu switcher"
```

---

### Task 7: Full Verification & Integration Testing

**Files:**
- Test scripts and CLI execution

- [ ] **Step 1: Run all unit tests**
Run: `.venv\Scripts\pytest`
Verify 100% tests pass.

- [ ] **Step 2: Verify first-run simulation**
Test with a temporary config path:
- Language prompt appears.
- Selecting `pt-BR` displays Portuguese UI.
- Selecting `en-US` displays English UI.

- [ ] **Step 3: Verify `--lang` CLI argument**
Run: `python -m pydisktriage --health --lang en-US`
Run: `python -m pydisktriage --health --lang pt-BR`
Verify health diagnostic output renders cleanly in both languages.

- [ ] **Step 4: Update README.md if appropriate**
Mention multi-language support (`pt-BR` and `en-US`) and the `--lang` flag in `README.md`.

- [ ] **Step 5: Final Commit**
```bash
git add README.md
git commit -m "docs: update README with multi-language usage"
```
