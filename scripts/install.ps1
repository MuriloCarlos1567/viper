$ErrorActionPreference = "Stop"

$rootDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

function Test-Python312OrNewer {
  param([Parameter(Mandatory = $true)][string]$PythonPath)
  & $PythonPath -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)" 2>$null
  return ($LASTEXITCODE -eq 0)
}

function Resolve-PythonForInstall {
  $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
  if ($pythonCmd -and (Test-Python312OrNewer -PythonPath $pythonCmd.Source)) {
    return $pythonCmd.Source
  }

  $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
  if ($pyLauncher) {
    $candidate = (& py -3.12 -c "import sys; print(sys.executable)" 2>$null).Trim()
    if ($candidate -and (Test-Python312OrNewer -PythonPath $candidate)) {
      return $candidate
    }
  }

  throw "Python 3.12+ nao encontrado. Instale Python 3.12 e tente novamente."
}

$pythonForInstall = Resolve-PythonForInstall
Write-Host "Usando Python: $pythonForInstall" -ForegroundColor Cyan

Write-Host "Garantindo pipx neste Python..." -ForegroundColor Yellow
& $pythonForInstall -m pip install --user --upgrade pipx | Out-Host
if ($LASTEXITCODE -ne 0) {
  throw "Falha ao instalar/atualizar pipx."
}

& $pythonForInstall -m pipx ensurepath | Out-Host

$pyTag = (& $pythonForInstall -c "import sys; print(f'{sys.version_info.major}{sys.version_info.minor}')" 2>$null).Trim()
$sessionBinPaths = @(
  (Join-Path $env:USERPROFILE ".local\bin"),
  (Join-Path $env:APPDATA "Python\Python$pyTag\Scripts")
)
foreach ($binPath in $sessionBinPaths) {
  if ((Test-Path $binPath) -and -not (($env:Path -split ';') -contains $binPath)) {
    $env:Path = "$binPath;$env:Path"
  }
}

try {
  $pipxList = & $pythonForInstall -m pipx list 2>$null
  if ($pipxList -match "viper") {
    Write-Host "Removendo instalacao antiga de viper..." -ForegroundColor Yellow
    & $pythonForInstall -m pipx uninstall viper | Out-Host
  }
} catch {
  # best effort
}

Write-Host "Instalando viper via pipx a partir de: $rootDir" -ForegroundColor Cyan
& $pythonForInstall -m pipx install --force --python $pythonForInstall $rootDir | Out-Host
if ($LASTEXITCODE -ne 0) {
  throw "Falha ao instalar viper com pipx."
}

Write-Host "Instalado. Teste com: viper --help" -ForegroundColor Green
Write-Host "Se este terminal ja estava aberto, feche e abra novamente para recarregar o PATH." -ForegroundColor Yellow
