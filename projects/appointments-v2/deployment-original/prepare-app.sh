#!/usr/bin/env bash
set -euo pipefail
cd /opt/jormall/apps/appointments-v2
rollback() {
  docker compose stop web worker || true
  docker start jormall-appointments-web >/dev/null || true
}
trap rollback ERR
if [ ! -e PREVIEW_INITIALIZED ]; then
  docker compose run --rm --no-deps --env NODE_ENV=development --workdir /app/apps/web --volume /home/ubuntu/jormall-deploy-20260906/seed.mjs:/app/apps/web/seed.mjs:ro web node seed.mjs
  touch PREVIEW_INITIALIZED
fi
docker compose up --detach --wait --wait-timeout 300 web worker
docker compose cp /home/ubuntu/jormall-deploy-20260906/preflight.mjs web:/tmp/preflight.mjs
docker compose exec -T web node /tmp/preflight.mjs
trap - ERR
echo 'Server preflight complete; ready for HTTPS activation.'
