#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"

mode=""
local_http="false"

usage() {
  echo "Uso: scripts/deploy-production.sh [--check|--apply] [--local-http]"
  echo "  --check  valida archivos, entorno, Compose y Nginx; no despliega"
  echo "  --apply  exige .env seguro, crea backup si hay web activa, migra y actualiza servicios"
  echo "  --local-http  limita el despliegue a loopback y permite HTTP/cookies locales; nunca usar públicamente"
}

for argument in "$@"; do
  case "$argument" in
    --check|--apply)
      if [[ -n "$mode" ]]; then
        echo "Usa sólo una operación: --check o --apply" >&2
        exit 2
      fi
      mode="$argument"
      ;;
    --local-http)
      local_http="true"
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
done
mode="${mode:---check}"
export ALLOW_INSECURE_LOCAL_HTTP="$local_http"

env_value() {
  local key="$1"
  local file="$2"
  sed -n "s/^${key}=//p" "$file" | tail -n 1
}

validate_env() {
  local file="$1"
  local profile="$2"
  local failed=0
  local required=(SECRET_KEY ALLOWED_HOSTS CSRF_TRUSTED_ORIGINS APP_BASE_URL DATABASE_PATH)
  for key in "${required[@]}"; do
    if [[ -z "$(env_value "$key" "$file")" ]]; then
      echo "Falta $key en $file" >&2
      failed=1
    fi
  done
  if [[ "$profile" == "strict" || "$profile" == "local-http" ]]; then
    local secret_key
    secret_key="$(env_value SECRET_KEY "$file")"
    if [[ ${#secret_key} -lt 50 || "$secret_key" == *CHANGE_ME* || "$secret_key" == *replace-with* ]]; then
      echo "SECRET_KEY debe ser aleatoria, no placeholder y tener al menos 50 caracteres" >&2
      failed=1
    fi
    [[ "$(env_value ALLOWED_HOSTS "$file")" != *"*"* ]] || {
      echo "ALLOWED_HOSTS no puede contener wildcard" >&2
      failed=1
    }
    [[ "$(env_value SCRAPER_ALLOW_PRIVATE_HOSTS "$file")" == "false" ]] || {
      echo "SCRAPER_ALLOW_PRIVATE_HOSTS debe ser false" >&2
      failed=1
    }
  fi
  if [[ "$profile" == "strict" ]]; then
    [[ "$(env_value DEBUG "$file")" == "false" ]] || {
      echo "DEBUG debe ser false" >&2
      failed=1
    }
    [[ "$(env_value SECURE_SSL_REDIRECT "$file")" == "true" ]] || {
      echo "SECURE_SSL_REDIRECT debe ser true" >&2
      failed=1
    }
    [[ "$(env_value SESSION_COOKIE_SECURE "$file")" == "true" ]] || {
      echo "SESSION_COOKIE_SECURE debe ser true" >&2
      failed=1
    }
    [[ "$(env_value CSRF_COOKIE_SECURE "$file")" == "true" ]] || {
      echo "CSRF_COOKIE_SECURE debe ser true" >&2
      failed=1
    }
    [[ "$(env_value CSRF_TRUSTED_ORIGINS "$file")" == https://* ]] || {
      echo "CSRF_TRUSTED_ORIGINS debe comenzar con https://" >&2
      failed=1
    }
    [[ "$(env_value APP_BASE_URL "$file")" == https://* ]] || {
      echo "APP_BASE_URL debe comenzar con https://" >&2
      failed=1
    }
  fi
  if [[ "$profile" == "local-http" ]]; then
    [[ "$(env_value SECURE_SSL_REDIRECT "$file")" == "false" ]] || {
      echo "SECURE_SSL_REDIRECT debe ser false con --local-http" >&2
      failed=1
    }
    [[ "$(env_value SESSION_COOKIE_SECURE "$file")" == "false" ]] || {
      echo "SESSION_COOKIE_SECURE debe ser false con --local-http" >&2
      failed=1
    }
    [[ "$(env_value CSRF_COOKIE_SECURE "$file")" == "false" ]] || {
      echo "CSRF_COOKIE_SECURE debe ser false con --local-http" >&2
      failed=1
    }
    local -a local_hosts local_origins
    IFS=',' read -r -a local_hosts <<<"$(env_value ALLOWED_HOSTS "$file")"
    for host in "${local_hosts[@]}"; do
      host="${host//[[:space:]]/}"
      if [[ "$host" != "localhost" && "$host" != "127.0.0.1" ]]; then
        echo "ALLOWED_HOSTS sólo puede contener localhost y 127.0.0.1 con --local-http" >&2
        failed=1
      fi
    done
    local key origin
    for key in CSRF_TRUSTED_ORIGINS APP_BASE_URL; do
      IFS=',' read -r -a local_origins <<<"$(env_value "$key" "$file")"
      for origin in "${local_origins[@]}"; do
        origin="${origin//[[:space:]]/}"
        if [[ ! "$origin" =~ ^http://(localhost|127\.0\.0\.1)(:[0-9]+)?$ ]]; then
          echo "$key sólo puede usar http://localhost o http://127.0.0.1 con --local-http" >&2
          failed=1
        fi
      done
    done
  fi
  return "$failed"
}

validate_proxy_hosts() {
  local file="$1"
  local expected_hosts
  expected_hosts="$(env_value ALLOWED_HOSTS "$file")"
  expected_hosts="${expected_hosts//,/ }"
  for nginx_file in deploy/nginx-bootstrap.conf deploy/nginx.conf; do
    if ! grep -Fq "server_name ${expected_hosts};" "$nginx_file"; then
      echo "$nginx_file debe contener: server_name ${expected_hosts};" >&2
      return 1
    fi
  done
}

check_common() {
  local requested_profile="$1"
  command -v docker >/dev/null 2>&1 || {
    echo "Docker no está instalado" >&2
    return 1
  }
  docker compose version >/dev/null
  local validation_env=".env"
  local profile="$requested_profile"
  if [[ ! -f "$validation_env" ]]; then
    if [[ "$requested_profile" == "local-http" ]]; then
      echo "Falta .env; --local-http requiere una configuración local explícita" >&2
      return 1
    fi
    validation_env=".env.production.example"
    profile="template"
    echo "Aviso: .env no existe; se valida la plantilla $validation_env."
  fi
  validate_env "$validation_env" "$profile"
  if [[ "$profile" == "strict" ]]; then
    validate_proxy_hosts "$validation_env"
  fi
  docker compose --env-file "$validation_env" config --quiet
  if [[ "$profile" == "local-http" ]]; then
    echo "Aviso: perfil local HTTP limitado a loopback; se omiten Nginx, certificado y políticas HTTPS."
  else
    scripts/check-nginx-config.sh
  fi
}

case "$mode" in
  --check)
    if [[ "$local_http" == "true" ]]; then
      check_common "local-http"
      echo "Configuración local HTTP válida. No es apta para exposición pública."
    elif [[ -f .env ]]; then
      check_common "strict"
      echo "Configuración de despliegue válida."
    else
      check_common "strict"
      echo "Plantilla de despliegue válida. Antes de --apply crea .env con secretos y dominio reales."
    fi
    ;;
  --apply)
    [[ -f .env ]] || {
      echo "Falta .env; parte de .env.production.example y agrega secretos reales" >&2
      exit 1
    }
    if [[ "$local_http" == "true" ]]; then
      check_common "local-http"
      echo "Aplicando perfil local HTTP; el servicio debe permanecer accesible sólo por loopback."
    else
      check_common "strict"
    fi
    if docker compose ps --status running --services | grep -qx web; then
      echo "Creando backup previo a la migración..."
      docker compose exec -T web python manage.py backup_sqlite
    else
      echo "No hay web activa; si es una actualización, confirma que existe un backup externo reciente."
    fi
    export IMAGE_TAG="${IMAGE_TAG:-$(date -u +%Y%m%d%H%M%S)}"
    echo "Construyendo release $IMAGE_TAG..."
    COMPOSE_PARALLEL_LIMIT="${COMPOSE_PARALLEL_LIMIT:-1}" docker compose build
    docker compose run --rm web python manage.py migrate
    docker compose run --rm web python manage.py seed_market_pipeline
    docker compose up -d web scheduler
    for _ in $(seq 1 20); do
      if docker compose exec -T web python -c \
        "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/public/ready', timeout=3)" \
        >/dev/null 2>&1; then
        running_services="$(docker compose ps --status running --services)"
        if grep -qx web <<<"$running_services" && grep -qx scheduler <<<"$running_services"; then
          echo "Release $IMAGE_TAG saludable: web y scheduler activos."
          exit 0
        fi
      fi
      sleep 3
    done
    docker compose logs --no-color --tail=100 web scheduler >&2
    echo "El despliegue no alcanzó readiness; los contenedores se dejan disponibles para diagnóstico" >&2
    exit 1
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
