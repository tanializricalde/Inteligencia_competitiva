#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"

mode="${1:---check}"
skip_browser="${SKIP_PLAYWRIGHT_BROWSER:-false}"

usage() {
  echo "Uso: scripts/dev-bootstrap.sh [--check|--apply]"
  echo "  --check  valida herramientas y estado sin modificar archivos (predeterminado)"
  echo "  --apply  prepara .env, entorno Python, assets, Chromium y migraciones"
  echo "Variable opcional: SKIP_PLAYWRIGHT_BROWSER=true"
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Falta el comando requerido: $1" >&2
    return 1
  fi
}

check_host() {
  local failed=0
  for command_name in python3 corepack; do
    require_command "$command_name" || failed=1
  done
  if command -v docker >/dev/null 2>&1; then
    docker compose version >/dev/null 2>&1 || {
      echo "Docker existe, pero Compose v2 no está disponible" >&2
      failed=1
    }
  else
    echo "Aviso: Docker no está instalado; el flujo nativo seguirá disponible."
  fi
  python3 --version 2>/dev/null || true
  node --version 2>/dev/null || true
  corepack pnpm --version 2>/dev/null || true
  if [[ -f .env ]]; then
    echo ".env: presente"
  else
    echo ".env: ausente; --apply copiará .env.example"
  fi
  return "$failed"
}

case "$mode" in
  --help|-h)
    usage
    ;;
  --check)
    check_host
    ;;
  --apply)
    check_host
    if [[ ! -f .env ]]; then
      cp .env.example .env
      echo "Creado .env desde .env.example; cambia SECRET_KEY antes de compartir el servicio."
    fi
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.lock
    .venv/bin/pip install -e . --no-deps
    NODE_OPTIONS="--max-old-space-size=${NODE_MAX_OLD_SPACE_SIZE:-1536}" \
      corepack pnpm --dir frontend install --frozen-lockfile --network-concurrency 4
    NODE_OPTIONS="--max-old-space-size=${NODE_MAX_OLD_SPACE_SIZE:-1536}" \
      corepack pnpm --dir frontend build
    if [[ "$skip_browser" != "true" ]]; then
      .venv/bin/playwright install chromium
    fi
    mkdir -p data
    .venv/bin/python manage.py migrate
    .venv/bin/python manage.py seed_market_pipeline
    .venv/bin/python manage.py check
    echo "Entorno listo. Crea el primer usuario con: make superuser"
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac

