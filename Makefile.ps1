[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('help', 'check', 'dev-check', 'setup', 'lock', 'dev', 'scheduler', 'assets', 'migrate',
        'superuser', 'test', 'test-playwright', 'lint', 'format', 'status', 'backup',
        'build', 'docker-migrate', 'docker-up', 'docker-down', 'docker-logs',
        'deploy-check', 'deploy', 'nginx-check', 'docs-check', 'cli-dist', 'verify')]
    [string]$Task = 'help'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot
$Python = Join-Path $RepoRoot '.venv\Scripts\python.exe'

function Assert-LastExitCode {
    param([string]$Description)
    if ($LASTEXITCODE -ne 0) {
        throw "$Description falló con código $LASTEXITCODE."
    }
}

function Require-Venv {
    if (-not (Test-Path $Python)) {
        throw 'Falta .venv. Ejecuta .\scripts\dev-bootstrap.ps1 -Apply.'
    }
}

function Invoke-Task {
    param([string]$Name)
    & $PSCommandPath $Name
    if (-not $?) {
        throw "Tarea $Name falló."
    }
}

switch ($Task) {
    'help' {
        Write-Host 'Uso: .\Makefile.ps1 <tarea>'
        Write-Host 'Tareas: check dev-check setup lock dev scheduler assets migrate superuser test test-playwright lint format status backup build docker-migrate docker-up docker-down docker-logs deploy-check deploy nginx-check docs-check cli-dist verify'
    }
    'check' { & "$RepoRoot\scripts\dev-bootstrap.ps1" -Check }
    'dev-check' { & "$RepoRoot\scripts\dev-bootstrap.ps1" -Check }
    'setup' { & "$RepoRoot\scripts\dev-bootstrap.ps1" -Apply }
    'lock' {
        Require-Venv
        $ResolvedRequirements = & $Python -m pip freeze --exclude-editable
        Assert-LastExitCode 'Resolución de dependencias'
        $Utf8NoBom = [System.Text.UTF8Encoding]::new($false)
        [System.IO.File]::WriteAllLines(
            (Join-Path $RepoRoot 'requirements.lock'),
            [string[]]$ResolvedRequirements,
            $Utf8NoBom
        )
    }
    'dev' { Require-Venv; & $Python manage.py runserver; Assert-LastExitCode 'Django' }
    'scheduler' { Require-Venv; & $Python manage.py run_scheduler; Assert-LastExitCode 'Scheduler' }
    'assets' {
        $env:NODE_OPTIONS = '--max-old-space-size=1536'
        & corepack pnpm --dir frontend install --frozen-lockfile --network-concurrency 4
        Assert-LastExitCode 'Instalación frontend'
        & corepack pnpm --dir frontend build
        Assert-LastExitCode 'Build frontend'
    }
    'migrate' {
        Require-Venv
        New-Item -ItemType Directory -Force data | Out-Null
        & $Python manage.py migrate
        Assert-LastExitCode 'Migraciones'
        & $Python manage.py seed_market_pipeline
        Assert-LastExitCode 'Catálogo inicial del pipeline'
    }
    'superuser' { Require-Venv; & $Python manage.py createsuperuser; Assert-LastExitCode 'Creación de usuario' }
    'test' { Require-Venv; & $Python -m pytest -m 'not playwright'; Assert-LastExitCode 'Pruebas offline' }
    'test-playwright' { Require-Venv; & $Python -m pytest -m playwright; Assert-LastExitCode 'Pruebas Playwright' }
    'lint' { Require-Venv; & $Python -m ruff check src tests manage.py; Assert-LastExitCode 'Ruff check' }
    'format' { Require-Venv; & $Python -m ruff format src tests manage.py; Assert-LastExitCode 'Ruff format' }
    'status' {
        & git status --short
        Assert-LastExitCode 'Git status'
        Select-String -Path docs\IMPLEMENTATION_PLAN.md -Pattern '^- \[-\]'
        Get-Content docs\PROGRESS.md -TotalCount 12
    }
    'backup' { Require-Venv; & $Python manage.py backup_sqlite; Assert-LastExitCode 'Backup SQLite' }
    'build' { & docker compose build; Assert-LastExitCode 'Docker build' }
    'docker-migrate' {
        & docker compose run --rm web python manage.py migrate
        Assert-LastExitCode 'Migración Docker'
        & docker compose run --rm web python manage.py seed_market_pipeline
        Assert-LastExitCode 'Catálogo inicial Docker'
    }
    'docker-up' { & docker compose up -d web scheduler; Assert-LastExitCode 'Docker up' }
    'docker-down' { & docker compose down; Assert-LastExitCode 'Docker down' }
    'docker-logs' { & docker compose logs --no-color --tail=100 web scheduler; Assert-LastExitCode 'Docker logs' }
    'deploy-check' { & "$RepoRoot\scripts\deploy-production.ps1" -Check }
    'deploy' { & "$RepoRoot\scripts\deploy-production.ps1" -Apply }
    'nginx-check' { throw 'La validación Nginx requiere Docker/Bash en Linux. Consulta docs\operations\DEPLOYMENT_NGINX.md.' }
    'docs-check' {
        Require-Venv
        $RequiredDocs = @(
            'docs\README.md',
            'docs\development\LINUX.md',
            'docs\development\WINDOWS.md',
            'docs\development\ENVIRONMENT_VARIABLES.md',
            'docs\operations\PRODUCTION.md',
            'docs\operations\DEPLOYMENT_NGINX.md',
            'docs\cli\CLI_USAGE.md',
            'docs\data\DATA_PIPELINE.md'
        )
        foreach ($Document in $RequiredDocs) {
            if (-not (Test-Path $Document)) {
                throw "Falta documento requerido: $Document"
            }
        }
        & $Python scripts\check_doc_links.py
        Assert-LastExitCode 'Enlaces de documentación'
        & docker compose --env-file .env.production.example config --quiet
        Assert-LastExitCode 'Configuración Compose'
    }
    'cli-dist' { Require-Venv; & $Python scripts\build_cli_dist.py --output dist\scraper-cli; Assert-LastExitCode 'Distribuible CLI' }
    'verify' {
        Invoke-Task 'lint'
        Invoke-Task 'test'
        Invoke-Task 'assets'
        Invoke-Task 'test-playwright'
        Invoke-Task 'build'
    }
}
