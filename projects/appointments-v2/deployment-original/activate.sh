#!/usr/bin/env bash
set -euo pipefail
cd /opt/jormall/apps/appointments-v2
rollback() {
  docker compose stop web worker || true
  docker start jormall-appointments-web || true
  install -m 644 /home/ubuntu/jormall-deploy-20260906/nginx-before-contents.conf /etc/nginx/sites-available/appointments.jormallapp.com
  nginx -t && systemctl reload nginx
}
trap rollback ERR
curl --fail --silent --max-time 30 http://127.0.0.1:18200/ar/login >/dev/null
docker compose exec -T web node /tmp/preflight.mjs
install -m 644 /home/ubuntu/jormall-deploy-20260906/nginx-v2.conf /etc/nginx/sites-available/appointments.jormallapp.com
nginx -t
systemctl reload nginx
curl --fail --silent --max-time 45 --resolve appointments.jormallapp.com:443:127.0.0.1 https://appointments.jormallapp.com/ar/login >/dev/null
trap - ERR
echo 'HTTPS route activated; previous container and data retained.'
