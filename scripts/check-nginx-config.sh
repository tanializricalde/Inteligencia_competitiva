#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"

for command_name in docker openssl; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Falta el comando requerido: $command_name" >&2
    exit 1
  fi
done

temporary_dir="$(mktemp -d)"
trap 'rm -rf "$temporary_dir"' EXIT
mkdir -p "$temporary_dir/tls" "$temporary_dir/acme"

openssl req -x509 -newkey rsa:2048 -nodes -days 1 \
  -subj "/CN=market-watch.example.com" \
  -keyout "$temporary_dir/tls/privkey.pem" \
  -out "$temporary_dir/tls/fullchain.pem" >/dev/null 2>&1

docker run --rm \
  --volume "$project_dir/deploy/nginx.conf:/etc/nginx/conf.d/default.conf:ro" \
  --volume "$temporary_dir/tls:/etc/nginx/tls:ro" \
  --volume "$temporary_dir/acme:/var/www/letsencrypt:ro" \
  nginx:1.27-alpine nginx -t

