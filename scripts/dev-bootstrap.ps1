[CmdletBinding()]
param(
    [switch]$Apply,
    [switch]$Check,
    [switch]$SkipPlaywrightBrowser
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

if ($Apply -and $Check) {
    throw 'Usa -Apply o -Check, no ambos.'
}

function Assert-LastExitCode {
    param([string]$Description)
    if ($LASTEXITCODE -ne 0) {
        throw "$Description falló con código $LASTEXITCODE."
    }
}

function Require-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Falta el comando requerido: $Name"
    }
}

function Select-PythonVersion {
    Require-Command 'py'
    foreach ($Version in @('-3.12', '-3.13')) {
        & py $Version --version *> $null
        if ($LASTEXITCODE -eq 0) {
            return $Version
        }
    }
    throw 'Se requiere Python 3.12 o 3.13 registrado en el launcher py.'
}

function Test-Host {
    $Version = Select-PythonVersion
    Require-Command 'node'
    Require-Command 'corepack'
    $CommandOutput = & py $Version --version
    Assert-LastExitCode 'Python'
    Write-Host $CommandOutput
    $CommandOutput = & node --version
    Assert-LastExitCode 'Node.js'
    Write-Host $CommandOutput
    $CommandOutput = & corepack pnpm --version
    Assert-LastExitCode 'pnpm'
    Write-Host $CommandOutput
    if (Get-Command docker -ErrorAction SilentlyContinue) {
        $CommandOutput = & docker compose version
        Assert-LastExitCode 'Docker Compose'
        Write-Host $CommandOutput
    } else {
        Write-Warning 'Docker no está instalado; el flujo nativo sigue disponible.'
    }
    if (Test-Path '.env') {
        Write-Host '.env: presente'
    } else {
        Write-Host '.env: ausente; -Apply copiará .env.example'
    }
    return $Version
}

$PythonVersion = Test-Host
if (-not $Apply) {
    Write-Host 'Comprobación terminada sin modificar archivos.'
    exit 0
}

if (-not (Test-Path '.env')) {
    Copy-Item '.env.example' '.env'
    Write-Host 'Creado .env desde .env.example; cambia SECRET_KEY.'
}

& py $PythonVersion -m venv .venv
Assert-LastExitCode 'Creación de .venv'
$Python = Join-Path $RepoRoot '.venv\Scripts\python.exe'
& $Python -m pip install -r requirements.lock
Assert-LastExitCode 'Instalación de requirements.lock'
& $Python -m pip install -e . --no-deps
Assert-LastExitCode 'Instalación editable'
$env:NODE_OPTIONS = '--max-old-space-size=1536'
& corepack pnpm --dir frontend install --frozen-lockfile --network-concurrency 4
Assert-LastExitCode 'Instalación frontend'
& corepack pnpm --dir frontend build
Assert-LastExitCode 'Build frontend'
if (-not $SkipPlaywrightBrowser) {
    & $Python -m playwright install chromium
    Assert-LastExitCode 'Instalación de Chromium'
}
New-Item -ItemType Directory -Force data | Out-Null
& $Python manage.py migrate
Assert-LastExitCode 'Migraciones'
& $Python manage.py seed_market_pipeline
Assert-LastExitCode 'Catálogo inicial del pipeline'
& $Python manage.py check
Assert-LastExitCode 'Check Django'
Write-Host 'Entorno listo. Crea el primer usuario con: .\Makefile.ps1 superuser'
