# disktriage

Triagem de espaço em disco no Windows. Diagnostica a saúde do SSD e mostra o que
dá para apagar, o que dá para mover para outro disco, e o que exige julgamento
humano — com menu interativo para executar cada ação.

Nasceu de um diagnóstico real: um BSOD `0x1E_C0000006` (`nt!HvpGetCellPaged`)
causado por um SSD de boot a 2,7% de espaço livre. O disco travava por 1,5 s numa
leitura, o kernel não conseguia paginar uma célula do registro, e o Windows caía.
A ferramenta automatiza o caminho que levou até essa conclusão.

## Instalação

```powershell
cd C:\Users\<voce>\Tools\DiskTriage
pip install -r requirements.txt      # só precisa de rich

# ou, para ter o comando `disktriage` no PATH:
pip install -e .
```

## Uso

```powershell
python -m pydisktriage                  # menu interativo
python -m pydisktriage --health         # só o diagnóstico, sem menu
python -m pydisktriage --scan --drive D # já entra varrido, sugerindo mover p/ D:
python -m pydisktriage --min-gb 0.5     # baixa o limiar de exibição
```

Em console legado (cmd.exe antigo), a saída é convertida para UTF-8
automaticamente e os marcadores caem para ASCII se o codepage não der conta.
Para o visual completo, use o Windows Terminal ou rode `chcp 65001` antes.

Rode **como administrador** para ver a seção de latência dos discos —
`Get-StorageReliabilityCounter` exige elevação, e é ela que denuncia um SSD
travando.

## As quatro etapas

**1. Saúde.** Espaço por volume, latência máxima de leitura/escrita/flush por
disco físico, localização do pagefile, e o histórico de telas azuis dos últimos
90 dias com o significado de cada código. Responde: *isso é urgente?*

**2. Catálogo.** Mede ~50 caches conhecidos de ferramentas de dev, IA e jogos.
Cada entrada já vem classificada e, quando existe, traz a variável de ambiente
que redireciona a ferramenta para outro disco.

**3. Descoberta.** Varredura genérica por pastas e arquivos grandes que o
catálogo não cobre. É o que mantém a ferramenta útil numa máquina com programas
que o catálogo nunca viu.

**4. Ações.** Menu por item: excluir, mover para outro disco com ajuste
automático da variável, só definir a variável, ver o comando nativo da
ferramenta, ou abrir no Explorer.

## Categorias

| Categoria | Significado |
|---|---|
| **Descartável** | Cache reconstruível. Apagar não custa nada além de um re-download. |
| **Movível** | Cache grande que aceita ser redirecionado por variável de ambiente. |
| **Revisar** | Precisa de decisão humana, ou exige ferramenta própria (DISM, PatchCleaner). |

## Segurança

- Nada é apagado sem que você digite o nome do item — não basta um "s".
- `WinSxS`, `Windows\Installer`, `System32` e `Program Files` são recusados
  sempre, mesmo se você pedir. Eles têm ferramenta própria; apagar na mão quebra
  o Windows ou a desinstalação de programas.
- Mover verifica espaço no destino antes de começar e só remove a origem depois
  que todos os arquivos chegaram. Se qualquer cópia falhar, a origem fica
  intacta.
- Junctions e symlinks nunca são seguidos. Sem isso,
  `C:\Users\Todos os Usuários` (que aponta para `C:\ProgramData`) seria contado
  duas vezes, e uma remoção recursiva sairia da árvore pretendida.
- Variáveis são gravadas em `HKCU\Environment` via `winreg`, não via `setx`, que
  trunca silenciosamente valores acima de 1024 caracteres.

## Estrutura

```
pydisktriage/
├── catalog.py   # o catálogo de caches conhecidos e as regras de proteção
├── fsutil.py    # travessia, medição, cópia e remoção com progresso
├── health.py    # espaço, latência, pagefile e bugchecks
├── envvars.py   # leitura e escrita de variáveis do usuário
├── scanner.py   # catálogo + descoberta
├── ui.py        # tudo que desenha na tela
└── cli.py       # menu e roteamento
```

## Versão PowerShell

`Invoke-DiskTriage.ps1`, no diretório acima, faz o diagnóstico e gera um plano
`.ps1` de remediação, sem interatividade. Útil quando não há Python na máquina.

```powershell
.\Invoke-DiskTriage.ps1 -TargetDrive D
```
