[CmdletBinding()]
param(
    [switch]$Check,
    [switch]$Apply,
    [switch]$LocalHttp
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $RepoRoot

if ($Check -and $Apply) {
    throw 'Usa sólo una opción: -Check o -Apply.'
}
$Mode = if ($Apply) { 'Apply' } else { 'Check' }
$env:ALLOW_INSECURE_LOCAL_HTTP = if ($LocalHttp) { 'true' } else { 'false' }

function Assert-LastExitCode {
    param([string]$Description)
    if ($LASTEXITCODE -ne 0) {
        throw "$Description falló con código $LASTEXITCODE."
    }
}

function Get-EnvValue {
    param(
        [string]$Key,
        [string]$Path
    )
    $Pattern = '^\s*' + [regex]::Escape($Key) + '=(.*)$'
    $Match = Get-Content $Path | Select-String -Pattern $Pattern | Select-Object -Last 1
    if ($null -eq $Match) {
        return ''
    }
    return $Match.Matches[0].Groups[1].Value.Trim()
}

function Test-ProductionEnvironment {
    param(
        [string]$Path,
        [ValidateSet('Template', 'Strict', 'LocalHttp')]
        [string]$Profile
    )
    $Errors = [System.Collections.Generic.List[string]]::new()
    foreach ($Key in @('SECRET_KEY', 'ALLOWED_HOSTS', 'CSRF_TRUSTED_ORIGINS', 'APP_BASE_URL', 'DATABASE_PATH')) {
        if ([string]::IsNullOrWhiteSpace((Get-EnvValue $Key $Path))) {
            $Errors.Add("Falta $Key en $Path.")
        }
    }

    if ($Profile -in @('Strict', 'LocalHttp')) {
        $Secret = Get-EnvValue 'SECRET_KEY' $Path
        if ($Secret.Length -lt 50 -or $Secret -match 'CHANGE_ME|replace-with') {
            $Errors.Add('SECRET_KEY debe ser aleatoria, no placeholder y tener al menos 50 caracteres.')
        }
        if ((Get-EnvValue 'ALLOWED_HOSTS' $Path).Contains('*')) {
            $Errors.Add('ALLOWED_HOSTS no puede contener wildcard.')
        }
        if ((Get-EnvValue 'SCRAPER_ALLOW_PRIVATE_HOSTS' $Path) -cne 'false') {
            $Errors.Add('SCRAPER_ALLOW_PRIVATE_HOSTS debe ser false.')
        }
    }

    if ($Profile -eq 'Strict') {
        $RequiredValues = @{
            DEBUG                       = 'false'
            SECURE_SSL_REDIRECT         = 'true'
            SESSION_COOKIE_SECURE       = 'true'
            CSRF_COOKIE_SECURE          = 'true'
            SCRAPER_ALLOW_PRIVATE_HOSTS = 'false'
        }
        foreach ($Key in $RequiredValues.Keys) {
            if ((Get-EnvValue $Key $Path) -cne $RequiredValues[$Key]) {
                $Errors.Add("$Key debe ser $($RequiredValues[$Key]).")
            }
        }
        if ((Get-EnvValue 'CSRF_TRUSTED_ORIGINS' $Path) -notlike 'https://*') {
            $Errors.Add('CSRF_TRUSTED_ORIGINS debe comenzar con https://.')
        }
        if ((Get-EnvValue 'APP_BASE_URL' $Path) -notlike 'https://*') {
            $Errors.Add('APP_BASE_URL debe comenzar con https://.')
        }
    }

    if ($Profile -eq 'LocalHttp') {
        $LocalValues = @{
            SECURE_SSL_REDIRECT   = 'false'
            SESSION_COOKIE_SECURE = 'false'
            CSRF_COOKIE_SECURE    = 'false'
        }
        foreach ($Key in $LocalValues.Keys) {
            if ((Get-EnvValue $Key $Path) -cne $LocalValues[$Key]) {
                $Errors.Add("$Key debe ser false con -LocalHttp.")
            }
        }
        foreach ($HostName in ((Get-EnvValue 'ALLOWED_HOSTS' $Path) -split ',')) {
            if ($HostName.Trim() -notin @('localhost', '127.0.0.1')) {
                $Errors.Add('ALLOWED_HOSTS sólo puede contener localhost y 127.0.0.1 con -LocalHttp.')
            }
        }
        foreach ($Key in @('CSRF_TRUSTED_ORIGINS', 'APP_BASE_URL')) {
            foreach ($Origin in ((Get-EnvValue $Key $Path) -split ',')) {
                if ($Origin.Trim() -notmatch '^http://(localhost|127\.0\.0\.1)(:\d+)?$') {
                    $Errors.Add("$Key sólo puede usar http://localhost o http://127.0.0.1 con -LocalHttp.")
                }
            }
        }
    }

    if ($Errors.Count -gt 0) {
        throw ($Errors -join [Environment]::NewLine)
    }
}

if ($null -eq (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Docker no está instalado o no está disponible en PATH.'
}
& docker compose version | Out-Null
Assert-LastExitCode 'Docker Compose'

$ValidationEnv = Join-Path $RepoRoot '.env'
$HasEnvironment = Test-Path $ValidationEnv
if (-not $HasEnvironment) {
    if ($LocalHttp) {
        throw 'Falta .env; -LocalHttp requiere una configuración local explícita.'
    }
    $ValidationEnv = Join-Path $RepoRoot '.env.production.example'
    Write-Warning 'No existe .env; se validará la plantilla .env.production.example.'
}
$Profile = if ($LocalHttp) { 'LocalHttp' } elseif ($HasEnvironment) { 'Strict' } else { 'Template' }
Test-ProductionEnvironment -Path $ValidationEnv -Profile $Profile
& docker compose --env-file $ValidationEnv config --quiet
Assert-LastExitCode 'Configuración Compose'

if ($LocalHttp) {
    Write-Warning 'Perfil local HTTP limitado a loopback; se omiten certificado y políticas HTTPS.'
}

if ($Mode -eq 'Check') {
    if ($LocalHttp) {
        Write-Host 'Configuración local HTTP válida. No es apta para exposición pública.'
    }
    elseif ($HasEnvironment) {
        Write-Host 'Configuración de despliegue Windows válida.'
    }
    else {
        Write-Host 'Plantilla de despliegue válida. Antes de -Apply crea .env con secretos y dominio reales.'
    }
    exit 0
}

if (-not $HasEnvironment) {
    throw 'Falta .env; parte de .env.production.example y agrega secretos y dominio reales.'
}

if ($LocalHttp) {
    Write-Warning 'Aplicando perfil local HTTP; el servicio debe permanecer accesible sólo por loopback.'
}

$RunningServices = @(& docker compose ps --status running --services)
Assert-LastExitCode 'Consulta de servicios activos'
if ($RunningServices -contains 'web') {
    Write-Host 'Creando backup previo a la migración...'
    & docker compose exec -T web python manage.py backup_sqlite
    Assert-LastExitCode 'Backup previo'
}
else {
    Write-Warning 'No hay web activa; si es una actualización, confirma que existe un backup externo reciente.'
}

if (-not (Test-Path Env:IMAGE_TAG) -or [string]::IsNullOrWhiteSpace($env:IMAGE_TAG)) {
    $env:IMAGE_TAG = (Get-Date).ToUniversalTime().ToString('yyyyMMddHHmmss')
}
if (-not (Test-Path Env:COMPOSE_PARALLEL_LIMIT)) {
    $env:COMPOSE_PARALLEL_LIMIT = '1'
}

Write-Host "Construyendo release $($env:IMAGE_TAG)..."
& docker compose build
Assert-LastExitCode 'Docker build'
& docker compose run --rm web python manage.py migrate
Assert-LastExitCode 'Migraciones'
& docker compose run --rm web python manage.py seed_market_pipeline
Assert-LastExitCode 'Catálogo inicial del pipeline'
& docker compose up -d web scheduler
Assert-LastExitCode 'Arranque de servicios'

for ($Attempt = 1; $Attempt -le 20; $Attempt++) {
    & docker compose exec -T web python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/public/ready', timeout=3)" 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $ActiveServices = @(& docker compose ps --status running --services)
        if ($LASTEXITCODE -eq 0 -and $ActiveServices -contains 'web' -and $ActiveServices -contains 'scheduler') {
            Write-Host "Release $($env:IMAGE_TAG) saludable: web y scheduler activos."
            exit 0
        }
    }
    Start-Sleep -Seconds 3
}

& docker compose logs --no-color --tail=100 web scheduler
throw 'El despliegue no alcanzó readiness; los contenedores se dejan disponibles para diagnóstico.'
