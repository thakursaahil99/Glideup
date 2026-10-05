#!/usr/bin/env bash
# Build and (re)start the production stack. Safe to re-run for every update:
#   git pull && ./deploy/deploy.sh
set -euo pipefail
cd "$(dirname "$0")/.."

[ -f .env ] || { echo "Missing .env. Run ./deploy/setup-vm.sh first."; exit 1; }
for key in DOMAIN AUTH_SECRET JWT_SECRET POSTGRES_PASSWORD GITHUB_MODELS_TOKEN AUTH_GOOGLE_ID GOOGLE_CLIENT_ID ADMIN_EMAILS; do
  grep -Eq "^${key}=.+" .env || { echo "Set ${key} in .env first."; exit 1; }
done

compose() { docker compose -f docker-compose.yml -f docker-compose.prod.yml "$@"; }

PROFILES=()
[ "${MONITORING:-1}" = "1" ] && PROFILES+=(--profile monitoring)
# The Piston image may not exist for every CPU (e.g. ARM); run without the sandbox if so.
SANDBOX=0
if compose --profile sandbox pull piston; then
  PROFILES+=(--profile sandbox)
  SANDBOX=1
else
  echo "WARN: code sandbox image unavailable for $(uname -m); coding tests will show as unavailable."
fi

echo "==> Building images"
compose "${PROFILES[@]}" build
echo "==> Starting"
compose "${PROFILES[@]}" up -d --remove-orphans

if [ "$SANDBOX" = "1" ]; then
  echo "==> Code sandbox runtimes (first run takes a few minutes)"
  compose exec -T api python -m app.scripts.install_sandbox_runtimes \
    || echo "WARN: sandbox runtimes not installed; coding tests stay unavailable until this succeeds."
fi

domain=$(grep '^DOMAIN=' .env | cut -d= -f2)
echo "==> Waiting for https://${domain}"
for _ in $(seq 1 60); do
  if curl -fsS "https://${domain}/" -o /dev/null; then
    echo "Live: https://${domain}"
    exit 0
  fi
  sleep 5
done
echo "Not reachable yet. Check: docker compose -f docker-compose.yml -f docker-compose.prod.yml logs caddy web api"
exit 1
