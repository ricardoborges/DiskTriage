<#
.SYNOPSIS
    Triagem de espaco em disco no Windows: diagnostico de saude do SSD e
    inventario do que pode ser apagado, movido ou revisado.

.DESCRIPTION
    Reproduz o metodo usado para diagnosticar um BSOD 0x1E_C0000006 causado por
    um SSD de boot a 2,7% de espaco livre:

      1. SAUDE      - bugchecks recentes, latencia dos discos, espaco livre e
                      localizacao do pagefile. Responde "isso e urgente?".
      2. CATALOGO   - mede ~55 caches conhecidos de ferramentas de dev, IA e
                      jogos, classificados em Descartavel / Movivel / Revisar,
                      com a variavel de ambiente que redireciona cada um.
      3. DESCOBERTA - varredura generica por pastas e arquivos grandes fora do
                      catalogo, para funcionar em maquina desconhecida.
      4. PLANO      - gera um .ps1 de remediacao para revisar antes de rodar.

    Por padrao NAO apaga nada: e somente leitura.

.PARAMETER TargetDrive
    Letra do disco de destino para as sugestoes de mover (ex: 'D'). Sem isso,
    os itens moviveis sao apenas listados com a variavel correspondente.

.PARAMETER MinGB
    Tamanho minimo para um item aparecer no relatorio. Padrao 1 GB.

.PARAMETER Apply
    Executa as limpezas da categoria Descartavel, uma a uma, com confirmacao.
    Itens Movivel e Revisar nunca sao tocados automaticamente.

.PARAMETER SkipDiscovery
    Pula a etapa 3, que e a mais demorada, e roda so o catalogo.

.EXAMPLE
    .\Invoke-DiskTriage.ps1
    Relatorio completo, somente leitura.

.EXAMPLE
    .\Invoke-DiskTriage.ps1 -TargetDrive D
    Relatorio mais plano de remediacao com os comandos de mover para D:.

.EXAMPLE
    .\Invoke-DiskTriage.ps1 -Apply -SkipDiscovery
    Limpa as caches descartaveis, pedindo confirmacao em cada uma.

.NOTES
    Compativel com Windows PowerShell 5.1 e PowerShell 7+.
    A secao de latencia dos discos precisa de elevacao; sem ela, e pulada.
#>
[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'High')]
param(
    [string] $ProfileRoot   = $env:USERPROFILE,
    [string] $TargetDrive,
    [double] $MinGB         = 1.0,
    [int]    $TopN          = 25,
    [double] $LargeFileGB   = 2.0,
    [switch] $SkipDiscovery,
    [switch] $Apply,
    [string] $OutDir        = (Join-Path $env:TEMP 'DiskTriage')
)

$ErrorActionPreference = 'Continue'
$script:SysDrive = $env:SystemDrive

#region ---------------------------- helpers ----------------------------

function Write-Section {
    param([string]$Title)
    Write-Host ''
    Write-Host ('=' * 78) -ForegroundColor DarkCyan
    Write-Host "  $Title" -ForegroundColor Cyan
    Write-Host ('=' * 78) -ForegroundColor DarkCyan
}

function ConvertTo-GB {
    param([double]$Bytes)
    return [math]::Round($Bytes / 1GB, 2)
}

# Soma recursiva via .NET (bem mais rapido que Get-ChildItem -Recurse), pulando
# junctions e symlinks para nao contar a mesma arvore duas vezes -- e o caso de
# C:\Users\Todos os Usuarios, que aponta para C:\ProgramData.
function Get-FolderSize {
    param([Parameter(Mandatory = $true)][string]$Path)

    $total = [long]0
    $count = [long]0
    $stack = New-Object System.Collections.Stack
    $stack.Push($Path)

    while ($stack.Count -gt 0) {
        $dir = $stack.Pop()
        try {
            foreach ($f in [System.IO.Directory]::EnumerateFiles($dir)) {
                try {
                    $total += (New-Object System.IO.FileInfo $f).Length
                    $count++
                } catch { }
            }
            foreach ($d in [System.IO.Directory]::EnumerateDirectories($dir)) {
                try {
                    $info = New-Object System.IO.DirectoryInfo $d
                    if (-not ($info.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
                        $stack.Push($d)
                    }
                } catch { }
            }
        } catch { }
    }

    return [PSCustomObject]@{ Bytes = $total; Files = $count }
}

function Get-ItemSizeBytes {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
    if ($null -eq $item) { return $null }
    if ($item.PSIsContainer) { return (Get-FolderSize -Path $item.FullName).Bytes }
    return $item.Length
}

#endregion

#region ------------------------- 1. saude ------------------------------

function Get-HealthReport {
    Write-Section '1. SAUDE DO SISTEMA'

    Write-Host ''
    Write-Host '-- Espaco por volume --' -ForegroundColor Yellow
    $vols = Get-Volume -ErrorAction SilentlyContinue |
        Where-Object { $_.DriveLetter -and $_.Size -gt 0 } |
        ForEach-Object {
            $pct = [math]::Round(100 * $_.SizeRemaining / $_.Size, 1)
            $verdict = 'ok'
            if ($pct -lt 20) { $verdict = 'APERTADO' }
            if ($pct -lt 10) { $verdict = 'CRITICO' }
            [PSCustomObject]@{
                Letra    = $_.DriveLetter
                Rotulo   = $_.FileSystemLabel
                LivreGB  = [math]::Round($_.SizeRemaining / 1GB, 1)
                TotalGB  = [math]::Round($_.Size / 1GB, 1)
                PctLivre = $pct
                Situacao = $verdict
            }
        }
    $vols | Sort-Object PctLivre | Format-Table -AutoSize | Out-Host

    foreach ($v in $vols) {
        if ($v.PctLivre -lt 10) {
            Write-Host ('  !! {0}: apenas {1}% livre. Abaixo de ~10% o cache SLC do SSD deixa' -f $v.Letra, $v.PctLivre) -ForegroundColor Red
            Write-Host '     de funcionar e a latencia de leitura e escrita dispara.' -ForegroundColor Red
        }
    }

    Write-Host ''
    Write-Host '-- Latencia maxima registrada por disco --' -ForegroundColor Yellow
    $lat = Get-PhysicalDisk -ErrorAction SilentlyContinue | ForEach-Object {
        $d  = $_
        $rc = $null
        try { $rc = $d | Get-StorageReliabilityCounter -ErrorAction Stop } catch { }
        if ($null -ne $rc) {
            [PSCustomObject]@{
                Disco      = $d.FriendlyName
                ReadMaxMs  = $rc.ReadLatencyMax
                WriteMaxMs = $rc.WriteLatencyMax
                FlushMaxMs = $rc.FlushLatencyMax
                TempC      = $rc.Temperature
                Desgaste   = $rc.Wear
            }
        }
    }
    if ($null -eq $lat -or @($lat).Count -eq 0) {
        Write-Host '  (indisponivel -- rode como administrador para ver esta secao)' -ForegroundColor DarkGray
    }
    else {
        $lat | Format-Table -AutoSize | Out-Host
        foreach ($l in $lat) {
            if ($l.ReadMaxMs -gt 500) {
                Write-Host ('  !! {0}: leitura maxima de {1} ms. Um NVMe saudavel fica abaixo de 10 ms.' -f $l.Disco, $l.ReadMaxMs) -ForegroundColor Red
                Write-Host '     Stalls desta ordem causam STATUS_IN_PAGE_ERROR e tela azul.' -ForegroundColor Red
            }
        }
    }

    Write-Host ''
    Write-Host '-- Pagefile --' -ForegroundColor Yellow
    Get-CimInstance Win32_PageFileUsage -ErrorAction SilentlyContinue |
        Select-Object Name, AllocatedBaseSize, PeakUsage |
        Format-Table -AutoSize | Out-Host

    Write-Host ''
    Write-Host '-- Telas azuis nos ultimos 90 dias --' -ForegroundColor Yellow
    $bugs = Get-WinEvent -FilterHashtable @{
        LogName      = 'System'
        Id           = 1001
        ProviderName = 'Microsoft-Windows-WER-SystemErrorReporting'
        StartTime    = (Get-Date).AddDays(-90)
    } -ErrorAction SilentlyContinue

    if ($null -eq $bugs -or @($bugs).Count -eq 0) {
        Write-Host '  Nenhuma. Bom sinal.' -ForegroundColor Green
    }
    else {
        $bugs | ForEach-Object {
            $code = 'desconhecido'
            $m = [regex]::Match($_.Message, '0x[0-9a-fA-F]{8}')
            if ($m.Success) { $code = $m.Value }
            [PSCustomObject]@{ Quando = $_.TimeCreated; Bugcheck = $code }
        } | Format-Table -AutoSize | Out-Host

        Write-Host ('  {0} bugcheck(s) no periodo. Dumps em C:\Windows\Minidump.' -f @($bugs).Count) -ForegroundColor Yellow
        Write-Host '  Para identificar o driver culpado, num prompt elevado:' -ForegroundColor DarkGray
        Write-Host '    windbgx -z <dump> -c "!analyze -v; q" -logo $env:TEMP\bsod.txt' -ForegroundColor DarkGray
        Write-Host '  Olhe FAILURE_BUCKET_ID, MODULE_NAME e IMAGE_NAME no resultado.' -ForegroundColor DarkGray
    }
}

#endregion

#region ----------------------- 2. catalogo -----------------------------

function New-Target {
    param(
        [string]$Id,
        [string]$Path,
        [ValidateSet('Descartavel', 'Movivel', 'Revisar')][string]$Kind,
        [string]$EnvVar = '',
        [string]$Clean  = '',
        [string]$Note   = ''
    )
    [PSCustomObject]@{
        Id     = $Id
        Path   = $Path
        Kind   = $Kind
        EnvVar = $EnvVar
        Clean  = $Clean
        Note   = $Note
    }
}

function Get-Catalog {
    $u    = $ProfileRoot
    $la   = Join-Path $u 'AppData\Local'
    $ra   = Join-Path $u 'AppData\Roaming'
    $winre = $script:SysDrive + '\$WinREAgent'

    @(
        # ---------------- lixo puro ----------------
        (New-Target 'temp-user'   "$la\Temp"                                       'Descartavel' '' '' 'Temporarios do usuario'),
        (New-Target 'temp-win'    "$env:SystemRoot\Temp"                           'Descartavel' '' '' 'Temporarios do Windows'),
        (New-Target 'crashdumps'  "$la\CrashDumps"                                 'Descartavel' '' '' 'Dumps de processos que travaram'),
        (New-Target 'winre-agent' $winre                                           'Descartavel' '' '' 'Resto de servicing de update'),
        (New-Target 'wu-download' "$env:SystemRoot\SoftwareDistribution\Download"   'Descartavel' '' 'Stop-Service wuauserv,bits' 'Updates ja aplicados'),
        (New-Target 'd3dcache'    "$la\D3DSCache"                                  'Descartavel' '' '' 'Cache de shader DirectX'),
        (New-Target 'nv-dxcache'  "$la\NVIDIA\DXCache"                             'Descartavel' '' '' 'Cache de shader NVIDIA'),
        (New-Target 'nv-glcache'  "$la\NVIDIA\GLCache"                             'Descartavel' '' '' 'Cache de shader OpenGL'),
        (New-Target 'choco-bad'   "$env:ProgramData\chocolatey\lib-bad"            'Descartavel' '' '' 'Instalacoes falhas do Chocolatey'),

        # ------- caches de dev: apagaveis E redirecionaveis -------
        (New-Target 'npm-cache'   "$la\npm-cache"                    'Movivel' 'npm_config_cache'           'npm cache clean --force'         'Cache do npm'),
        (New-Target 'yarn-cache'  "$la\Yarn\Cache"                   'Movivel' 'YARN_CACHE_FOLDER'          'yarn cache clean'                'Cache do Yarn'),
        (New-Target 'pnpm-store'  "$la\pnpm-store"                   'Movivel' 'PNPM_HOME'                  'pnpm store prune'                'Store do pnpm'),
        (New-Target 'pip-cache'   "$la\pip\Cache"                    'Movivel' 'PIP_CACHE_DIR'              'pip cache purge'                 'Cache do pip'),
        (New-Target 'uv-cache'    "$la\uv\cache"                     'Movivel' 'UV_CACHE_DIR'               'uv cache clean'                  'Cache do uv'),
        (New-Target 'poetry'      "$la\pypoetry\Cache"               'Movivel' 'POETRY_CACHE_DIR'           'poetry cache clear --all .'      'Cache do Poetry'),
        (New-Target 'nuget'       "$u\.nuget\packages"               'Movivel' 'NUGET_PACKAGES'             'dotnet nuget locals all --clear' 'Pacotes NuGet'),
        (New-Target 'gradle'      "$u\.gradle"                       'Movivel' 'GRADLE_USER_HOME'           ''                                'Cache do Gradle'),
        (New-Target 'maven'       "$u\.m2\repository"                'Movivel' ''                           ''                                'Repositorio Maven (ajuste settings.xml)'),
        (New-Target 'cargo'       "$u\.cargo"                        'Movivel' 'CARGO_HOME'                 ''                                'Registry e binarios do Cargo'),
        (New-Target 'rustup'      "$u\.rustup"                       'Movivel' 'RUSTUP_HOME'                'rustup toolchain list'           'Toolchains do Rust'),
        (New-Target 'go-mod'      "$u\go\pkg\mod"                    'Movivel' 'GOMODCACHE'                 'go clean -modcache'              'Modulos Go'),
        (New-Target 'pyenv'       "$u\.pyenv"                        'Movivel' 'PYENV_ROOT'                 'pyenv versions'                  'Versoes do Python'),
        (New-Target 'conda-pkgs'  "$u\anaconda3\pkgs"                'Movivel' 'CONDA_PKGS_DIRS'            'conda clean --all'               'Pacotes conda'),
        (New-Target 'playwright'  "$la\ms-playwright"                'Movivel' 'PLAYWRIGHT_BROWSERS_PATH'   ''                                'Navegadores do Playwright'),
        (New-Target 'puppeteer'   "$la\Puppeteer"                    'Movivel' 'PUPPETEER_CACHE_DIR'        ''                                'Navegadores do Puppeteer'),
        (New-Target 'scoop-cache' "$u\scoop\cache"                   'Movivel' 'SCOOP_CACHE'                'scoop cache rm *'                'Cache do Scoop'),
        (New-Target 'vcpkg-arch'  "$la\vcpkg\archives"               'Movivel' 'VCPKG_DEFAULT_BINARY_CACHE' ''                                'Cache binario do vcpkg'),

        # ------- modelos de IA: costumam ser os maiores ofensores -------
        (New-Target 'hf-cache'    "$u\.cache\huggingface"            'Movivel' 'HF_HOME'        '' 'Modelos Hugging Face'),
        (New-Target 'torch-cache' "$u\.cache\torch"                  'Movivel' 'TORCH_HOME'     '' 'Modelos PyTorch'),
        (New-Target 'whisper'     "$u\.cache\whisper"                'Movivel' 'XDG_CACHE_HOME' '' 'Modelos Whisper'),
        (New-Target 'clip-cache'  "$u\.cache\clip"                   'Movivel' 'XDG_CACHE_HOME' '' 'Modelos CLIP'),
        (New-Target 'ollama'      "$u\.ollama\models"                'Movivel' 'OLLAMA_MODELS'  'ollama list' 'Modelos do Ollama'),
        (New-Target 'lmstudio'    "$u\.lmstudio\models"              'Revisar' '' '' 'Modelos do LM Studio -- mova pela GUI do app'),

        # ------- containers e VMs -------
        (New-Target 'docker'      "$la\Docker"                       'Revisar' '' 'docker system prune -a' 'Docker Desktop: Settings > Resources > Advanced > Disk image location'),
        (New-Target 'wsl-pkgs'    "$la\Packages"                     'Revisar' '' ''                       'Pode conter ext4.vhdx de distros WSL -- mova com wsl --export / --import'),

        # ------- mobile e game dev -------
        (New-Target 'android-sdk' "$la\Android\Sdk"                  'Movivel' 'ANDROID_SDK_ROOT' '' 'SDK do Android'),
        (New-Target 'android-avd' "$u\.android\avd"                  'Movivel' 'ANDROID_AVD_HOME' '' 'Emuladores Android'),
        (New-Target 'unity-cache' "$la\Unity\cache"                  'Movivel' 'UNITY_CACHE_PATH' '' 'Cache do Unity'),
        (New-Target 'unreal-ddc'  "$la\UnrealEngine\Common\DerivedDataCache" 'Descartavel' '' '' 'Derived Data Cache da Unreal'),

        # ------- editores -------
        (New-Target 'vscode-cache' "$ra\Code\Cache"                  'Descartavel' '' '' 'Cache do VS Code'),
        (New-Target 'vscode-cd'    "$ra\Code\CachedData"             'Descartavel' '' '' 'CachedData do VS Code'),
        (New-Target 'vscode-ext'   "$u\.vscode\extensions"           'Revisar' '' 'code --list-extensions' 'Extensoes do VS Code'),
        (New-Target 'jetbrains'    "$la\JetBrains"                   'Revisar' '' ''                      'Caches e indices JetBrains'),

        # ------- navegadores -------
        (New-Target 'chrome-cache' "$la\Google\Chrome\User Data\Default\Cache"  'Descartavel' '' '' 'Cache do Chrome'),
        (New-Target 'edge-cache'   "$la\Microsoft\Edge\User Data\Default\Cache" 'Descartavel' '' '' 'Cache do Edge'),

        # ------- jogos -------
        (New-Target 'msfs-rolling' "$ra\Microsoft Flight Simulator\ROLLINGCACHE.CCC" 'Descartavel' '' '' 'Rolling cache do MSFS -- prefira apagar pelo jogo'),
        (New-Target 'msfs-store'   "$la\Packages\Microsoft.FlightSimulator_8wekyb3d8bbwe\LocalCache" 'Revisar' '' '' 'Cache do MSFS (versao Store)'),

        # ------- pastas do sistema que exigem ferramenta propria -------
        (New-Target 'winsxs'       "$env:SystemRoot\WinSxS"          'Revisar' '' 'Dism /Online /Cleanup-Image /StartComponentCleanup /ResetBase' 'NAO apague na mao -- use o DISM'),
        (New-Target 'win-installer' "$env:SystemRoot\Installer"      'Revisar' '' ''                                                             'NAO apague na mao -- use o PatchCleaner')
    )
}

function Invoke-CatalogScan {
    Write-Section '2. CATALOGO DE CACHES CONHECIDOS'

    $catalog = @(Get-Catalog)
    $found   = New-Object System.Collections.ArrayList
    $i = 0

    foreach ($t in $catalog) {
        $i++
        Write-Progress -Activity 'Medindo caches conhecidos' -Status $t.Id `
            -PercentComplete (100 * $i / $catalog.Count)

        $paths = @()
        if ($t.Path -match '\*') {
            $paths = @(Resolve-Path -Path $t.Path -ErrorAction SilentlyContinue | ForEach-Object { $_.Path })
        }
        elseif (Test-Path -LiteralPath $t.Path) {
            $paths = @($t.Path)
        }

        foreach ($p in $paths) {
            $bytes = Get-ItemSizeBytes -Path $p
            if ($null -eq $bytes) { continue }
            $gb = ConvertTo-GB $bytes
            if ($gb -lt $MinGB) { continue }

            # Alvos podem ser arquivo unico (ex: ROLLINGCACHE.CCC) ou pasta.
            # Pasta limpa o conteudo e preserva a pasta; arquivo apaga o arquivo.
            $isFile = $false
            $probe = Get-Item -LiteralPath $p -Force -ErrorAction SilentlyContinue
            if ($null -ne $probe -and -not $probe.PSIsContainer) { $isFile = $true }

            $null = $found.Add([PSCustomObject]@{
                GB        = $gb
                Categoria = $t.Kind
                Item      = $t.Id
                Caminho   = $p
                Arquivo   = $isFile
                Variavel  = $t.EnvVar
                Comando   = $t.Clean
                Obs       = $t.Note
            })
        }
    }
    Write-Progress -Activity 'Medindo caches conhecidos' -Completed

    foreach ($kind in @('Descartavel', 'Movivel', 'Revisar')) {
        $set = @($found | Where-Object { $_.Categoria -eq $kind } | Sort-Object GB -Descending)
        if ($set.Count -eq 0) { continue }
        $sum   = [math]::Round((($set | Measure-Object GB -Sum).Sum), 1)
        $color = 'Green'
        if ($kind -eq 'Movivel') { $color = 'Yellow' }
        if ($kind -eq 'Revisar') { $color = 'Magenta' }
        Write-Host ''
        Write-Host ('-- {0}: {1} itens, {2} GB --' -f $kind, $set.Count, $sum) -ForegroundColor $color
        $set | Select-Object GB, Item, Caminho, Obs | Format-Table -AutoSize -Wrap | Out-Host
    }

    return $found
}

#endregion

#region ---------------------- 3. descoberta ----------------------------

function Invoke-Discovery {
    param([System.Collections.ArrayList]$Known)

    Write-Section '3. DESCOBERTA GENERICA'
    Write-Host 'Varrendo pastas grandes fora do catalogo. Pode levar alguns minutos...' -ForegroundColor DarkGray

    $knownPaths = @($Known | ForEach-Object { $_.Caminho.TrimEnd('\').ToLower() })
    $results    = New-Object System.Collections.ArrayList

    $roots = @(
        (Join-Path $ProfileRoot 'AppData\Local'),
        (Join-Path $ProfileRoot 'AppData\Roaming'),
        $ProfileRoot
    )

    foreach ($root in $roots) {
        if (-not (Test-Path -LiteralPath $root)) { continue }

        $dirs = @(Get-ChildItem -LiteralPath $root -Directory -Force -ErrorAction SilentlyContinue |
                  Where-Object { -not ($_.Attributes -band [System.IO.FileAttributes]::ReparsePoint) })
        $j = 0
        foreach ($d in $dirs) {
            $j++
            Write-Progress -Activity "Varrendo $root" -Status $d.Name `
                -PercentComplete (100 * $j / [Math]::Max($dirs.Count, 1))

            $lower = $d.FullName.TrimEnd('\').ToLower()
            $skip  = $false
            foreach ($k in $knownPaths) {
                if ($lower -eq $k -or $k.StartsWith($lower + '\')) { $skip = $true; break }
            }
            if ($skip) { continue }

            $gb = ConvertTo-GB (Get-FolderSize -Path $d.FullName).Bytes
            if ($gb -ge $MinGB) {
                $null = $results.Add([PSCustomObject]@{ GB = $gb; Caminho = $d.FullName })
            }
        }
        Write-Progress -Activity "Varrendo $root" -Completed
    }

    Write-Host ''
    Write-Host '-- Pastas grandes nao catalogadas --' -ForegroundColor Yellow
    $results | Sort-Object GB -Descending | Select-Object -First $TopN |
        Format-Table -AutoSize -Wrap | Out-Host

    Write-Host ''
    Write-Host ('-- Arquivos unicos acima de {0} GB --' -f $LargeFileGB) -ForegroundColor Yellow
    $threshold = $LargeFileGB * 1GB
    $big   = New-Object System.Collections.ArrayList
    $stack = New-Object System.Collections.Stack
    $stack.Push($ProfileRoot)

    while ($stack.Count -gt 0) {
        $dir = $stack.Pop()
        try {
            foreach ($f in [System.IO.Directory]::EnumerateFiles($dir)) {
                try {
                    $fi = New-Object System.IO.FileInfo $f
                    if ($fi.Length -ge $threshold) {
                        $null = $big.Add([PSCustomObject]@{ GB = ConvertTo-GB $fi.Length; Arquivo = $f })
                    }
                } catch { }
            }
            foreach ($d in [System.IO.Directory]::EnumerateDirectories($dir)) {
                try {
                    $di = New-Object System.IO.DirectoryInfo $d
                    if (-not ($di.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) { $stack.Push($d) }
                } catch { }
            }
        } catch { }
    }

    $big | Sort-Object GB -Descending | Select-Object -First $TopN |
        Format-Table -AutoSize -Wrap | Out-Host

    return $results
}

#endregion

#region ------------------------- 4. plano ------------------------------

function New-RemediationPlan {
    param([System.Collections.ArrayList]$Found)

    if (-not (Test-Path -LiteralPath $OutDir)) {
        $null = New-Item -ItemType Directory -Path $OutDir -Force
    }
    $planPath = Join-Path $OutDir 'plano-limpeza.ps1'

    $sb = New-Object System.Text.StringBuilder
    $null = $sb.AppendLine('# Plano de limpeza gerado por Invoke-DiskTriage.ps1')
    $null = $sb.AppendLine('# Gerado em: ' + (Get-Date -Format 'yyyy-MM-dd HH:mm'))
    $null = $sb.AppendLine('#')
    $null = $sb.AppendLine('# REVISE cada linha antes de executar. Nada aqui roda sozinho.')
    $null = $sb.AppendLine('')
    $null = $sb.AppendLine('$ok = Read-Host "Digite EXECUTAR para aplicar este plano"')
    $null = $sb.AppendLine('if ($ok -ne "EXECUTAR") { Write-Host "Cancelado."; return }')
    $null = $sb.AppendLine('')
    $null = $sb.AppendLine('# ------------------- descartavel -------------------')

    foreach ($f in ($Found | Where-Object { $_.Categoria -eq 'Descartavel' } | Sort-Object GB -Descending)) {
        $null = $sb.AppendLine('')
        $null = $sb.AppendLine('# [' + $f.GB + ' GB] ' + $f.Obs)
        if ($f.Comando) { $null = $sb.AppendLine('# rode antes: ' + $f.Comando) }
        if ($f.Arquivo) {
            $null = $sb.AppendLine("Remove-Item -LiteralPath '" + $f.Caminho + "' -Force -ErrorAction SilentlyContinue")
        }
        else {
            $null = $sb.AppendLine("Remove-Item -LiteralPath '" + $f.Caminho + "\*' -Recurse -Force -ErrorAction SilentlyContinue")
        }
    }

    $null = $sb.AppendLine('')
    $null = $sb.AppendLine('# ------------------- movivel -------------------')
    if (-not $TargetDrive) {
        $null = $sb.AppendLine('# (rode de novo com -TargetDrive D para gerar os comandos de mover)')
    }

    foreach ($f in ($Found | Where-Object { $_.Categoria -eq 'Movivel' } | Sort-Object GB -Descending)) {
        $null = $sb.AppendLine('')
        $null = $sb.AppendLine('# [' + $f.GB + ' GB] ' + $f.Obs)
        if ($f.Comando) { $null = $sb.AppendLine('# alternativa, limpar em vez de mover: ' + $f.Comando) }

        if ($TargetDrive) {
            $dest = $TargetDrive + ':\caches\' + $f.Item
            $null = $sb.AppendLine("robocopy '" + $f.Caminho + "' '" + $dest + "' /E /MOVE /NFL /NDL /NJH /NJS")
            if ($f.Variavel) {
                $null = $sb.AppendLine("[Environment]::SetEnvironmentVariable('" + $f.Variavel + "','" + $dest + "','User')")
            }
            else {
                $null = $sb.AppendLine('# sem variavel de ambiente -- reconfigure pela GUI da ferramenta')
            }
        }
        else {
            $null = $sb.AppendLine('# ' + $f.Caminho + '   ->   variavel: ' + $f.Variavel)
        }
    }

    $null = $sb.AppendLine('')
    $null = $sb.AppendLine('# ------------- revisar a mao (NAO automatizado) -------------')
    foreach ($f in ($Found | Where-Object { $_.Categoria -eq 'Revisar' } | Sort-Object GB -Descending)) {
        $null = $sb.AppendLine('# [' + $f.GB + ' GB] ' + $f.Caminho)
        $null = $sb.AppendLine('#     ' + $f.Obs)
        if ($f.Comando) { $null = $sb.AppendLine('#     comando: ' + $f.Comando) }
    }

    Set-Content -LiteralPath $planPath -Value $sb.ToString() -Encoding UTF8
    return $planPath
}

#endregion

#region ------------------------ 5. aplicar -----------------------------

function Invoke-Cleanup {
    [CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'High')]
    param([System.Collections.ArrayList]$Found)

    Write-Section '5. APLICANDO LIMPEZA (somente categoria Descartavel)'

    $targets = @($Found | Where-Object { $_.Categoria -eq 'Descartavel' } | Sort-Object GB -Descending)
    if ($targets.Count -eq 0) {
        Write-Host 'Nada a limpar.' -ForegroundColor Green
        return
    }

    $freed = 0.0
    foreach ($t in $targets) {
        $label = $t.Caminho + '  [' + $t.GB + ' GB]'
        if ($PSCmdlet.ShouldProcess($label, 'Remover conteudo')) {
            try {
                if ($t.Arquivo) {
                    Remove-Item -LiteralPath $t.Caminho -Force -ErrorAction SilentlyContinue
                }
                else {
                    Remove-Item -LiteralPath (Join-Path $t.Caminho '*') -Recurse -Force -ErrorAction SilentlyContinue
                }
                $freed += $t.GB
                Write-Host ('  limpo: ' + $label) -ForegroundColor Green
            }
            catch {
                Write-Host ('  falhou: ' + $label + ' -- ' + $_.Exception.Message) -ForegroundColor Red
            }
        }
    }
    Write-Host ''
    Write-Host ('Liberado aproximadamente {0} GB.' -f [math]::Round($freed, 1)) -ForegroundColor Green
}

#endregion

#region -------------------------- main ---------------------------------

Write-Host ''
Write-Host '  TRIAGEM DE DISCO' -ForegroundColor White
Write-Host ('  perfil: {0}    limiar: {1} GB' -f $ProfileRoot, $MinGB) -ForegroundColor DarkGray

Get-HealthReport
$found = Invoke-CatalogScan

if (-not $SkipDiscovery) {
    $null = Invoke-Discovery -Known $found
}

Write-Section '4. RESUMO'

$found | Group-Object Categoria | ForEach-Object {
    [PSCustomObject]@{
        Categoria = $_.Name
        Itens     = $_.Count
        GB        = [math]::Round((($_.Group | Measure-Object GB -Sum).Sum), 1)
    }
} | Sort-Object GB -Descending | Format-Table -AutoSize | Out-Host

$recuperavel = ($found | Where-Object { $_.Categoria -ne 'Revisar' } | Measure-Object GB -Sum).Sum
if ($null -eq $recuperavel) { $recuperavel = 0 }
Write-Host ('Recuperavel sem julgamento humano: ~{0} GB' -f [math]::Round($recuperavel, 1)) -ForegroundColor Green

if (-not (Test-Path -LiteralPath $OutDir)) { $null = New-Item -ItemType Directory -Path $OutDir -Force }
$csv = Join-Path $OutDir 'triagem.csv'
$found | Sort-Object GB -Descending | Export-Csv -LiteralPath $csv -NoTypeInformation -Encoding UTF8

$plan = New-RemediationPlan -Found $found

Write-Host ''
Write-Host ('Inventario : ' + $csv)  -ForegroundColor Cyan
Write-Host ('Plano      : ' + $plan) -ForegroundColor Cyan
Write-Host ''
Write-Host 'Revise o plano antes de rodar. Ele pede confirmacao por escrito.' -ForegroundColor Yellow

if ($Apply) { Invoke-Cleanup -Found $found }

#endregion
