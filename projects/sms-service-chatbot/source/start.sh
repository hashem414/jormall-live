set -eu
if [ ! -f .env ]; then echo 'Copy .env.example to .env before starting.'; exit 1; fi
docker-compose up -d --build
docker-compose ps
