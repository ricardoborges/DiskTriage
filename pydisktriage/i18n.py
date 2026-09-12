"""Internationalization (i18n) subsystem for DiskTriage.

Supports Portuguese (pt-BR, default) and English (en-US).
Provides translation lookups with fallback and keyword formatting.
"""

from __future__ import annotations

import re
from typing import Any

DEFAULT_LANGUAGE = "pt-BR"
SUPPORTED_LANGUAGES = {
    "pt-BR": "Português (Brasil)",
    "en-US": "English (US)",
}

# Current session language state
_CURRENT_LANGUAGE = DEFAULT_LANGUAGE

# Translation catalogs
_STRINGS: dict[str, dict[str, str]] = {
    "pt-BR": {
        # App & Banner
        "app.name": "disktriage",
        "app.tagline": "triagem de disco para Windows  ·  o que apagar, o que mover",
        "app.win_only": "Esta ferramenta é específica para Windows.",
        "app.goodbye": "até mais.",
        "app.interrupted": "Interrompido.",
        "app.input_closed": "Entrada encerrada.",

        # Language selection
        "lang.select_title": "Escolha o idioma / Choose language",
        "lang.prompt": "Selecione o idioma",
        "lang.current": "Idioma atual: {lang}",
        "lang.changed": "Idioma alterado para: {lang}",

        # Common glyphs & status
        "status.ok": "OK",
        "status.error": "Erro",
        "status.warning": "Aviso",
        "status.info": "Informação",
        "status.cancelled": "Cancelado.",
        "status.active": "Ativa",
        "status.reverted": "Revertida",

        # Menus
        "menu.title": "Menu",
        "menu.choice": "Escolha",
        "menu.health": "Diagnóstico de saúde (espaço, latência, telas azuis)",
        "menu.full_scan": "{prefix} completa (catálogo + descoberta)",
        "menu.fast_scan": "{prefix} rápida (só o catálogo)",
        "menu.scan_prefix_new": "Varredura",
        "menu.scan_prefix_redo": "Refazer varredura",
        "menu.item_actions": "Agir sobre um item",
        "menu.bulk_delete": "Apagar tudo que é descartável",
        "menu.export": "Exportar relatório",
        "menu.manage_junctions": "Gerenciar/Reverter Junções NTFS",
        "menu.clear_cache": "Limpar cache da varredura",
        "menu.change_lang": "Mudar idioma / Change language",
        "menu.exit": "Sair",
        "menu.back": "Voltar",

        # Interactive prompts
        "interactive.choice_prompt": "Escolha",
        "interactive.select_item_title": "Selecione o item para agir",
        "interactive.filter_prompt": "Filtro (ou Enter)",
        "interactive.nav_help": "↑/↓ navegar  ·  Enter confirmar  ·  Esc voltar",

        # Health screen
        "health.rule_title": "Diagnóstico de saúde",
        "health.volumes_title": "Espaço por volume",
        "health.col_drive": "Unidade",
        "health.col_label": "Rótulo",
        "health.col_free": "Livre",
        "health.col_total": "Total",
        "health.col_pct_free": "% livre",
        "health.col_status": "Situação",
        "health.verdict_critical": "CRÍTICO",
        "health.verdict_tight": "apertado",
        "health.verdict_ok": "ok",
        "health.warn_low_space": "{drive}: com apenas {pct}% livre.",
        "health.info_slc_cache": "Abaixo de ~10% o cache SLC do SSD deixa de funcionar e a latência dispara. É assim que um disco cheio vira tela azul.",
        "health.col_disk": "Disco",
        "health.col_read": "Leitura",
        "health.col_write": "Escrita",
        "health.col_flush": "Flush",
        "health.col_temp": "Temp",
        "health.col_wear": "Desgaste",
        "health.latency_title": "Latência máxima registrada",
        "health.latency_admin_required": "Latência dos discos indisponível — rode como administrador para ver esta seção.",
        "health.latency_spike_warn": "{disk}: pico de {read_ms} ms na leitura.",
        "health.latency_nvme_info": "Um NVMe saudável fica abaixo de 10 ms. Stalls desta ordem causam STATUS_IN_PAGE_ERROR e tela azul.",
        "health.pagefile_title": "Pagefile",
        "health.bugchecks_title": "Telas azuis ({count})",
        "health.col_when": "Quando",
        "health.col_code": "Código",
        "health.col_meaning": "Significado",
        "health.no_bugchecks": "Nenhuma tela azul nos últimos 90 dias.",
        "health.bugchecks_found": "{count} bugcheck(s). Dumps em {dump_dir}",
        "health.windbg_tip": 'Analise com: windbgx -z <dump> -c "!analyze -v; q" -logo %TEMP%\\bsod.txt',
        "health.windbg_fields": "Olhe FAILURE_BUCKET_ID, MODULE_NAME e IMAGE_NAME no resultado.",

        # Scan screen
        "scan.rule_title": "Varredura",
        "scan.task_catalog": "catálogo",
        "scan.task_discovery": "descoberta",
        "scan.task_large_files": "arquivos grandes",
        "scan.found_items_title": "Itens encontrados",
        "scan.cached_items_title": "Itens em cache",
        "scan.cache_loaded": "Última varredura carregada do cache ({time} · {count} itens encontrados).",
        "scan.cache_cleared": "Cache da varredura apagado.",
        "scan.require_scan_first": "Rode a varredura primeiro (opção 2).",
        "scan.large_files_title": "Arquivos únicos grandes",
        "scan.col_size": "Tamanho",
        "scan.col_file": "Arquivo",
        "scan.col_item": "Item",
        "scan.col_category": "Categoria",
        "scan.col_path": "Caminho",
        "scan.col_env_var": "Variável",
        "scan.summary_title": "Resumo",
        "scan.summary_reclaimable": "Recuperável sem julgamento humano: {size}",

        # Categories
        "category.discard": "Descartável",
        "category.move": "Movível",
        "category.review": "Revisar",

        # Item Actions
        "actions.rule_title": "Ações sobre itens",
        "actions.opt_delete": "Excluir conteúdo",
        "actions.opt_move": "Mover para outro disco (e ajustar variável de ambiente)",
        "actions.opt_move_junction": "Mover para outro disco via Junção NTFS (mklink /J)",
        "actions.opt_set_env": "Só definir a variável de ambiente",
        "actions.opt_clean_cmd": "Ver o comando nativo de limpeza",
        "actions.opt_open_explorer": "Abrir no Explorer",
        "actions.protected_path": "{path} é protegido — não vou mexer.",
        "actions.protected_tip": "Use a ferramenta própria: DISM para o WinSxS, PatchCleaner para o Windows\\Installer.",
        "actions.delete_title": "Excluir",
        "actions.col_path_label": "  Caminho : [bold]{path}[/bold]",
        "actions.col_size_label": "  Tamanho : [bold]{size}[/bold] em {files} arquivo(s)",
        "actions.note_label": "  Nota    : [dim]{note}[/dim]",
        "actions.clean_cmd_available": "A ferramenta tem comando próprio para isso: [cyan]{cmd}[/cyan]",
        "actions.clean_cmd_tip": "Costuma ser mais seguro que apagar arquivos na mão.",
        "actions.review_warning": "Este item está classificado como 'revisar' — pode conter dados que você quer manter.",
        "actions.confirm_delete_prompt": "Para confirmar, digite o nome do item ([bold]{expected}[/bold])",
        "actions.task_deleting": "apagando",
        "actions.busy_files_skipped": "{count} arquivo(s) não puderam ser removidos (provavelmente em uso).",
        "actions.freed_space": "Liberado {size} em {files} arquivo(s).",

        # Move action
        "actions.move_title": "Mover para outro disco",
        "actions.source_label": "  Origem  : [bold]{path}[/bold]",
        "actions.target_drive_prompt": "  Disco de destino",
        "actions.drive_not_found": "Unidade {drive}: não existe ou não está acessível.",
        "actions.insufficient_space": "Espaço insuficiente em {drive}: ({available} livre, precisa de {needed}).",
        "actions.target_path_prompt": "  Caminho de destino",
        "actions.dest_exists_confirm": "  [yellow]{dest} já existe e não está vazio. Mesclar?[/yellow]",
        "actions.task_copying": "copiando",
        "actions.copy_failed": "A cópia falhou em {count} arquivo(s). A origem foi preservada.",
        "actions.moved_success": "Movido {size} para {dest}.",
        "actions.env_current_val": "{var} hoje aponta para: {val}",
        "actions.set_env_confirm": "  Definir [cyan]{var}[/cyan] = [bold]{dest}[/bold]?",
        "actions.env_set_success": "{var} definida. Abra um terminal novo para ela valer.",
        "actions.no_env_var": "Esta ferramenta não tem variável de ambiente conhecida — reconfigure o caminho pela GUI dela.",

        # Set env action
        "actions.set_env_title": "Definir variável de ambiente",
        "actions.env_var_name_prompt": "  Nome da variável",
        "actions.current_value": "Valor atual: {val}",
        "actions.new_value_prompt": "  Novo valor",
        "actions.env_applied_info": "Processos já abertos não enxergam a mudança; abra um terminal novo.",

        # Clean cmd action
        "actions.clean_cmd_title": "Comando nativo da ferramenta",
        "actions.no_clean_cmd": "Esta entrada não tem comando de limpeza próprio.",
        "actions.run_clean_cmd_info": "Rode num terminal seu — assim você vê a saída e mantém o controle.",

        # Explorer action
        "actions.opening_explorer": "Abrindo {path}",

        # Junction action
        "junctions.file_not_dir": "{path} é um arquivo único. Junções NTFS funcionam apenas em pastas.",
        "junctions.move_title": "Mover via Junção NTFS (mklink /J)",
        "junctions.desc_line1": "Uma junção NTFS move os dados físicos para outro disco, mas mantém um link",
        "junctions.desc_line2": "transparente na origem para o aplicativo continuar funcionando normalmente.",
        "junctions.task_moving": "movendo e criando junção",
        "junctions.created_success": "Junção NTFS criada em {src} (ID: [bold cyan]{jid}[/bold cyan]).",
        "junctions.revertible_tip": "A junção está ativa e registrada. Você pode revertê-la a qualquer momento pelo menu.",
        "junctions.manage_title": "Gerenciar Junções NTFS",
        "junctions.table_title": "Junções Registradas",
        "junctions.no_registered": "Nenhuma junção NTFS registrada até o momento.",
        "junctions.no_active": "Não há junções ativas para reverter.",
        "junctions.revert_prompt": "Digite o ID da junção para REVERTER (ou Enter para voltar)",
        "junctions.id_not_found": "Nenhuma junção ativa encontrada com o ID '{jid}'.",
        "junctions.revert_confirm": "Deseja reverter a junção de [bold]{name}[/bold] e mover os dados de volta para [bold]{src}[/bold]?",
        "junctions.task_reverting": "revertendo junção",
        "junctions.src_not_reparse": "A origem {src} não é uma junção NTFS válida. Abortando por segurança.",
        "junctions.src_missing": "A pasta de origem {src} não existe mais.",
        "junctions.dst_missing": "A pasta de destino {dst} não existe.",
        "junctions.mklink_failed": "Falha ao executar mklink /J: {err}",
        "junctions.revert_success": "Junção desfeita e dados movidos de volta para {src} com sucesso!",
        "junctions.not_found_by_id": "Junção com ID {jid} não encontrada ou já revertida.",
        "junctions.rmdir_failed": "Falha ao remover a junção {src}: {err}",

        # Bulk delete
        "bulk.require_scan": "Nada classificado como descartável. Rode a varredura primeiro.",
        "bulk.rule_title": "Limpeza em lote",
        "bulk.table_title": "Serão apagados",
        "bulk.total_to_free": "Total a liberar: [bold green]{size}[/bold green]",
        "bulk.confirm_prompt": "Digite [bold]APAGAR[/bold] para confirmar",
        "bulk.confirm_keyword": "APAGAR",
        "bulk.files_in_use": "{count} arquivo(s) em uso, pulados.",
        "bulk.freed_total": "Liberado {size} no total.",

        # Export
        "export.dest_prompt": "Pasta de destino",
        "export.dir_create_error": "Não consegui criar {path}: {err}",
        "export.write_error": "Falha ao escrever o relatório: {err}",
        "export.perm_tip": "Escolha uma pasta onde você tenha permissão de escrita.",
        "export.success": "Exportado:\n    {csv_path}\n    {json_path}",
        "export.col_bytes": "Bytes",
        "export.col_gb": "GB",
        "export.col_category": "Categoria",
        "export.col_item": "Item",
        "export.col_path": "Caminho",
        "export.col_var": "Variavel",
        "export.col_cmd": "Comando",
        "export.col_note": "Observacao",

        # Catalog Notes
        "catalog.note.temp_user": "Temporários do usuário",
        "catalog.note.temp_win": "Temporários do Windows",
        "catalog.note.crashdumps": "Dumps de processos que travaram",
        "catalog.note.winre_agent": "Resto de servicing de update",
        "catalog.note.wu_download": "Updates já aplicados",
        "catalog.note.d3dcache": "Cache de shader DirectX",
        "catalog.note.nv_dxcache": "Cache de shader NVIDIA",
        "catalog.note.nv_glcache": "Cache de shader OpenGL",
        "catalog.note.choco_bad": "Instalações falhas do Chocolatey",
        "catalog.note.npm_cache": "Cache do npm",
        "catalog.note.yarn_cache": "Cache do Yarn",
        "catalog.note.pnpm_store": "Store do pnpm",
        "catalog.note.pip_cache": "Cache do pip",
        "catalog.note.uv_cache": "Cache do uv",
        "catalog.note.poetry": "Cache do Poetry",
        "catalog.note.nuget": "Pacotes NuGet",
        "catalog.note.gradle": "Cache do Gradle",
        "catalog.note.maven": "Repositório Maven (ajuste settings.xml)",
        "catalog.note.cargo": "Registry e binários do Cargo",
        "catalog.note.rustup": "Toolchains do Rust",
        "catalog.note.go_mod": "Módulos Go",
        "catalog.note.pyenv": "Versões do Python",
        "catalog.note.conda_pkgs": "Pacotes conda",
        "catalog.note.playwright": "Navegadores do Playwright",
        "catalog.note.puppeteer": "Navegadores do Puppeteer",
        "catalog.note.scoop_cache": "Cache do Scoop",
        "catalog.note.vcpkg_arch": "Cache binário do vcpkg",
        "catalog.note.hf_cache": "Modelos Hugging Face",
        "catalog.note.torch_cache": "Modelos PyTorch",
        "catalog.note.whisper": "Modelos Whisper",
        "catalog.note.clip_cache": "Modelos CLIP",
        "catalog.note.ollama": "Modelos do Ollama",
        "catalog.note.lmstudio": "Modelos do LM Studio — mova pela GUI do app",
        "catalog.note.docker": "Docker Desktop: Settings > Resources > Advanced > Disk image location",
        "catalog.note.wsl_pkgs": "Pode conter ext4.vhdx de distros WSL — mova com wsl --export / --import",
        "catalog.note.android_sdk": "SDK do Android",
        "catalog.note.android_avd": "Emuladores Android",
        "catalog.note.unity_cache": "Cache do Unity",
        "catalog.note.unreal_ddc": "Derived Data Cache da Unreal",
        "catalog.note.vscode_cache": "Cache do VS Code",
        "catalog.note.vscode_cd": "CachedData do VS Code",
        "catalog.note.vscode_ext": "Extensões do VS Code",
        "catalog.note.vscode_ipch": "Cabeçalhos pré-compilados C/C++ do VS Code",
        "catalog.note.vscode_cpptools": "IntelliSense e bancos C/C++ do VS Code (mova via Junção NTFS)",
        "catalog.note.jetbrains": "Caches e índices JetBrains",
        "catalog.note.postman": "Versões instaladas do Postman (verifique versões antigas)",
        "catalog.note.chrome_cache": "Cache do Chrome",
        "catalog.note.chrome_codecache": "Code Cache de scripts do Chrome",
        "catalog.note.chrome_userdata": "Perfil completo do Chrome (mova via Junção NTFS)",
        "catalog.note.edge_cache": "Cache do Edge",
        "catalog.note.ollama_updates": "Instaladores de atualizações antigas do Ollama",
        "catalog.note.datalab": "Modelos e caches de IA (OCR/Marker/Surya) do Datalab",
        "catalog.note.msfs_rolling": "Rolling cache do MSFS — prefira apagar pelo jogo",
        "catalog.note.msfs_store": "Cache do MSFS (versão Store)",
        "catalog.note.winsxs": "NÃO apague na mão — use o DISM",
        "catalog.note.win_installer": "NÃO apague na mão — use o PatchCleaner",
    },
    "en-US": {
        # App & Banner
        "app.name": "disktriage",
        "app.tagline": "Windows disk triage  ·  what to clean, what to move",
        "app.win_only": "This tool is specific to Windows.",
        "app.goodbye": "see you later.",
        "app.interrupted": "Interrupted.",
        "app.input_closed": "Input closed.",

        # Language selection
        "lang.select_title": "Choose language / Escolha o idioma",
        "lang.prompt": "Select language",
        "lang.current": "Current language: {lang}",
        "lang.changed": "Language changed to: {lang}",

        # Common glyphs & status
        "status.ok": "OK",
        "status.error": "Error",
        "status.warning": "Warning",
        "status.info": "Information",
        "status.cancelled": "Cancelled.",
        "status.active": "Active",
        "status.reverted": "Reverted",

        # Menus
        "menu.title": "Menu",
        "menu.choice": "Choice",
        "menu.health": "System health diagnostics (free space, SSD latency, BSODs)",
        "menu.full_scan": "{prefix} full scan (catalog + discovery)",
        "menu.fast_scan": "{prefix} quick scan (catalog only)",
        "menu.scan_prefix_new": "Start",
        "menu.scan_prefix_redo": "Repeat",
        "menu.item_actions": "Take action on an item",
        "menu.bulk_delete": "Bulk delete all disposable caches",
        "menu.export": "Export report",
        "menu.manage_junctions": "Manage / Revert NTFS Junctions",
        "menu.clear_cache": "Clear scan cache",
        "menu.change_lang": "Change language / Mudar idioma",
        "menu.exit": "Exit",
        "menu.back": "Back",

        # Interactive prompts
        "interactive.choice_prompt": "Choice",
        "interactive.select_item_title": "Select an item to act upon",
        "interactive.filter_prompt": "Filter (or press Enter)",
        "interactive.nav_help": "↑/↓ navigate  ·  Enter confirm  ·  Esc go back",

        # Health screen
        "health.rule_title": "Health Diagnostics",
        "health.volumes_title": "Volume Free Space",
        "health.col_drive": "Drive",
        "health.col_label": "Label",
        "health.col_free": "Free",
        "health.col_total": "Total",
        "health.col_pct_free": "% Free",
        "health.col_status": "Status",
        "health.verdict_critical": "CRITICAL",
        "health.verdict_tight": "tight",
        "health.verdict_ok": "ok",
        "health.warn_low_space": "{drive}: has only {pct}% free space remaining.",
        "health.info_slc_cache": "Below ~10% free space, SSD SLC caching shuts off and disk latency spikes. This is how a full disk triggers blue screens.",
        "health.col_disk": "Disk",
        "health.col_read": "Read",
        "health.col_write": "Write",
        "health.col_flush": "Flush",
        "health.col_temp": "Temp",
        "health.col_wear": "Wear",
        "health.latency_title": "Maximum Disk Latency Recorded",
        "health.latency_admin_required": "Disk latency metrics unavailable — run PowerShell as Administrator to view this section.",
        "health.latency_spike_warn": "{disk}: spike of {read_ms} ms on disk read.",
        "health.latency_nvme_info": "A healthy NVMe SSD stays well under 10 ms. Stalls of this magnitude cause STATUS_IN_PAGE_ERROR and blue screens.",
        "health.pagefile_title": "Pagefile",
        "health.bugchecks_title": "Blue Screen Bugchecks ({count})",
        "health.col_when": "When",
        "health.col_code": "Code",
        "health.col_meaning": "Meaning",
        "health.no_bugchecks": "No blue screens recorded in the last 90 days.",
        "health.bugchecks_found": "{count} bugcheck(s). Crash dumps in {dump_dir}",
        "health.windbg_tip": 'Analyze with: windbgx -z <dump> -c "!analyze -v; q" -logo %TEMP%\\bsod.txt',
        "health.windbg_fields": "Inspect FAILURE_BUCKET_ID, MODULE_NAME, and IMAGE_NAME in the output.",

        # Scan screen
        "scan.rule_title": "Disk Scan",
        "scan.task_catalog": "catalog",
        "scan.task_discovery": "discovery",
        "scan.task_large_files": "large files",
        "scan.found_items_title": "Items Found",
        "scan.cached_items_title": "Cached Scan Results",
        "scan.cache_loaded": "Loaded last scan from cache ({time} · {count} items found).",
        "scan.cache_cleared": "Scan cache cleared.",
        "scan.require_scan_first": "Run a scan first (Option 2).",
        "scan.large_files_title": "Large Single Files",
        "scan.col_size": "Size",
        "scan.col_file": "File",
        "scan.col_item": "Item",
        "scan.col_category": "Category",
        "scan.col_path": "Path",
        "scan.col_env_var": "Variable",
        "scan.summary_title": "Summary",
        "scan.summary_reclaimable": "Reclaimable without human review: {size}",

        # Categories
        "category.discard": "Disposable",
        "category.move": "Relocatable",
        "category.review": "Review",

        # Item Actions
        "actions.rule_title": "Item Actions",
        "actions.opt_delete": "Delete contents",
        "actions.opt_move": "Move to another drive (and update environment variable)",
        "actions.opt_move_junction": "Move to another drive via NTFS Junction (mklink /J)",
        "actions.opt_set_env": "Set environment variable only",
        "actions.opt_clean_cmd": "View tool native clean command",
        "actions.opt_open_explorer": "Open in Windows Explorer",
        "actions.protected_path": "{path} is protected — skipping.",
        "actions.protected_tip": "Use designated tools: DISM for WinSxS, PatchCleaner for Windows\\Installer.",
        "actions.delete_title": "Delete",
        "actions.col_path_label": "  Path    : [bold]{path}[/bold]",
        "actions.col_size_label": "  Size    : [bold]{size}[/bold] in {files} file(s)",
        "actions.note_label": "  Note    : [dim]{note}[/dim]",
        "actions.clean_cmd_available": "This tool has a built-in clean command: [cyan]{cmd}[/cyan]",
        "actions.clean_cmd_tip": "Usually safer than manual file deletion.",
        "actions.review_warning": "This item is classified as 'Review' — it may contain data you wish to keep.",
        "actions.confirm_delete_prompt": "To confirm deletion, type the folder/item name ([bold]{expected}[/bold])",
        "actions.task_deleting": "deleting",
        "actions.busy_files_skipped": "{count} file(s) could not be removed (likely in use).",
        "actions.freed_space": "Reclaimed {size} in {files} file(s).",

        # Move action
        "actions.move_title": "Move to Another Drive",
        "actions.source_label": "  Source  : [bold]{path}[/bold]",
        "actions.target_drive_prompt": "  Destination drive",
        "actions.drive_not_found": "Drive {drive}: does not exist or is not accessible.",
        "actions.insufficient_space": "Insufficient space on drive {drive}: ({available} free, requires {needed}).",
        "actions.target_path_prompt": "  Destination path",
        "actions.dest_exists_confirm": "  [yellow]{dest} already exists and is not empty. Merge contents?[/yellow]",
        "actions.task_copying": "copying",
        "actions.copy_failed": "Copy failed on {count} file(s). Original source files were preserved.",
        "actions.moved_success": "Successfully moved {size} to {dest}.",
        "actions.env_current_val": "{var} currently points to: {val}",
        "actions.set_env_confirm": "  Set [cyan]{var}[/cyan] = [bold]{dest}[/bold]?",
        "actions.env_set_success": "{var} set successfully. Open a new terminal session to take effect.",
        "actions.no_env_var": "This tool has no known environment variable — configure the path via its settings GUI.",

        # Set env action
        "actions.set_env_title": "Set Environment Variable",
        "actions.env_var_name_prompt": "  Variable name",
        "actions.current_value": "Current value: {val}",
        "actions.new_value_prompt": "  New value",
        "actions.env_applied_info": "Active running processes will not inherit this change; open a new terminal.",

        # Clean cmd action
        "actions.clean_cmd_title": "Tool Native Clean Command",
        "actions.no_clean_cmd": "This item does not have a dedicated clean command.",
        "actions.run_clean_cmd_info": "Run this command in your own terminal to view output and maintain control.",

        # Explorer action
        "actions.opening_explorer": "Opening {path}",

        # Junction action
        "junctions.file_not_dir": "{path} is a single file. NTFS Junctions only work on directories.",
        "junctions.move_title": "Move via NTFS Junction (mklink /J)",
        "junctions.desc_line1": "An NTFS junction moves physical data to another disk while preserving a transparent",
        "junctions.desc_line2": "junction link at the source so apps continue working uninterrupted.",
        "junctions.task_moving": "moving and creating junction",
        "junctions.created_success": "NTFS Junction created at {src} (ID: [bold cyan]{jid}[/bold cyan]).",
        "junctions.revertible_tip": "The junction is active and tracked. You can revert it at any time via the menu.",
        "junctions.manage_title": "Manage NTFS Junctions",
        "junctions.table_title": "Tracked Junctions",
        "junctions.no_registered": "No NTFS junctions recorded so far.",
        "junctions.no_active": "No active junctions available to revert.",
        "junctions.revert_prompt": "Enter the Junction ID to REVERT (or press Enter to go back)",
        "junctions.id_not_found": "No active junction found with ID '{jid}'.",
        "junctions.revert_confirm": "Revert junction for [bold]{name}[/bold] and move data back to [bold]{src}[/bold]?",
        "junctions.task_reverting": "reverting junction",
        "junctions.src_not_reparse": "Source path {src} is not a valid NTFS junction. Aborting for safety.",
        "junctions.src_missing": "Source folder {src} no longer exists.",
        "junctions.dst_missing": "Destination folder {dst} does not exist.",
        "junctions.mklink_failed": "Failed to execute mklink /J: {err}",
        "junctions.revert_success": "Junction removed and data successfully moved back to {src}!",
        "junctions.not_found_by_id": "Junction with ID {jid} not found or already reverted.",
        "junctions.rmdir_failed": "Failed to remove junction {src}: {err}",

        # Bulk delete
        "bulk.require_scan": "No disposable items found. Run a disk scan first.",
        "bulk.rule_title": "Bulk Clean",
        "bulk.table_title": "Items to be Removed",
        "bulk.total_to_free": "Total space to reclaim: [bold green]{size}[/bold green]",
        "bulk.confirm_prompt": "Type [bold]DELETE[/bold] to confirm",
        "bulk.confirm_keyword": "DELETE",
        "bulk.files_in_use": "{count} file(s) in use, skipped.",
        "bulk.freed_total": "Reclaimed {size} in total.",

        # Export
        "export.dest_prompt": "Destination folder",
        "export.dir_create_error": "Could not create directory {path}: {err}",
        "export.write_error": "Failed to write report files: {err}",
        "export.perm_tip": "Please choose a folder where you have write permissions.",
        "export.success": "Exported:\n    {csv_path}\n    {json_path}",
        "export.col_bytes": "Bytes",
        "export.col_gb": "GB",
        "export.col_category": "Category",
        "export.col_item": "Item",
        "export.col_path": "Path",
        "export.col_var": "Variable",
        "export.col_cmd": "Command",
        "export.col_note": "Note",

        # Catalog Notes
        "catalog.note.temp_user": "User temporary files",
        "catalog.note.temp_win": "Windows temporary files",
        "catalog.note.crashdumps": "Crashed process core dumps",
        "catalog.note.winre_agent": "Windows Update servicing leftovers",
        "catalog.note.wu_download": "Already installed Windows Updates",
        "catalog.note.d3dcache": "DirectX shader cache",
        "catalog.note.nv_dxcache": "NVIDIA shader cache",
        "catalog.note.nv_glcache": "OpenGL shader cache",
        "catalog.note.choco_bad": "Failed Chocolatey package installations",
        "catalog.note.npm_cache": "npm package cache",
        "catalog.note.yarn_cache": "Yarn cache",
        "catalog.note.pnpm_store": "pnpm global store",
        "catalog.note.pip_cache": "pip download cache",
        "catalog.note.uv_cache": "uv cache",
        "catalog.note.poetry": "Poetry cache",
        "catalog.note.nuget": "NuGet packages",
        "catalog.note.gradle": "Gradle cache",
        "catalog.note.maven": "Maven repository (configure in settings.xml)",
        "catalog.note.cargo": "Cargo registry and prebuilt binaries",
        "catalog.note.rustup": "Rust toolchains",
        "catalog.note.go_mod": "Go module cache",
        "catalog.note.pyenv": "Installed Python versions",
        "catalog.note.conda_pkgs": "Conda package cache",
        "catalog.note.playwright": "Playwright headless browsers",
        "catalog.note.puppeteer": "Puppeteer headless browsers",
        "catalog.note.scoop_cache": "Scoop download cache",
        "catalog.note.vcpkg_arch": "vcpkg binary archives",
        "catalog.note.hf_cache": "Hugging Face AI models",
        "catalog.note.torch_cache": "PyTorch AI models",
        "catalog.note.whisper": "Whisper audio models",
        "catalog.note.clip_cache": "CLIP vision models",
        "catalog.note.ollama": "Ollama local models",
        "catalog.note.lmstudio": "LM Studio models — relocate via app GUI",
        "catalog.note.docker": "Docker Desktop: Settings > Resources > Advanced > Disk image location",
        "catalog.note.wsl_pkgs": "May contain WSL ext4.vhdx disks — move with wsl --export / --import",
        "catalog.note.android_sdk": "Android SDK",
        "catalog.note.android_avd": "Android Virtual Devices (emulators)",
        "catalog.note.unity_cache": "Unity cache",
        "catalog.note.unreal_ddc": "Unreal Engine Derived Data Cache",
        "catalog.note.vscode_cache": "VS Code cache",
        "catalog.note.vscode_cd": "VS Code CachedData",
        "catalog.note.vscode_ext": "VS Code extensions",
        "catalog.note.vscode_ipch": "VS Code C/C++ precompiled headers",
        "catalog.note.vscode_cpptools": "VS Code C/C++ IntelliSense databases (relocate via NTFS Junction)",
        "catalog.note.jetbrains": "JetBrains caches and indexing data",
        "catalog.note.postman": "Installed Postman versions (check for legacy versions)",
        "catalog.note.chrome_cache": "Google Chrome cache",
        "catalog.note.chrome_codecache": "Google Chrome script code cache",
        "catalog.note.chrome_userdata": "Full Chrome user profile (relocate via NTFS Junction)",
        "catalog.note.edge_cache": "Microsoft Edge cache",
        "catalog.note.ollama_updates": "Legacy Ollama update installers",
        "catalog.note.datalab": "Datalab AI models and OCR caches",
        "catalog.note.msfs_rolling": "MSFS rolling cache — preferred removal via in-game settings",
        "catalog.note.msfs_store": "MSFS cache (Microsoft Store version)",
        "catalog.note.winsxs": "DO NOT delete manually — run DISM",
        "catalog.note.win_installer": "DO NOT delete manually — run PatchCleaner",
    },
}


def normalize_language(lang: str | None) -> str:
    """Normalize language tags into canonical supported codes ('pt-BR' or 'en-US')."""
    if not lang:
        return DEFAULT_LANGUAGE

    clean = lang.strip().replace("_", "-").lower()
    if clean in ("pt", "pt-br", "pt-pt", "portuguese"):
        return "pt-BR"
    if clean in ("en", "en-us", "en-gb", "english"):
        return "en-US"

    return DEFAULT_LANGUAGE


def get_language() -> str:
    """Return the current session language code."""
    return _CURRENT_LANGUAGE


def set_language(lang: str) -> None:
    """Set the current session language code after normalization."""
    global _CURRENT_LANGUAGE
    _CURRENT_LANGUAGE = normalize_language(lang)


def get_available_languages() -> list[tuple[str, str]]:
    """Return list of supported language (code, display_name) pairs."""
    return list(SUPPORTED_LANGUAGES.items())


def t(key: str, **kwargs: Any) -> str:
    """Retrieve translated string by key with fallback and keyword formatting.

    Lookup hierarchy:
    1. Active language dictionary.
    2. Default language ('pt-BR') dictionary.
    3. Literal key as fallback.
    """
    lang = get_language()
    catalog = _STRINGS.get(lang, _STRINGS[DEFAULT_LANGUAGE])

    raw = catalog.get(key)
    if raw is None and lang != DEFAULT_LANGUAGE:
        raw = _STRINGS[DEFAULT_LANGUAGE].get(key)

    if raw is None:
        return key

    if kwargs:
        try:
            return raw.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return raw

    return raw
