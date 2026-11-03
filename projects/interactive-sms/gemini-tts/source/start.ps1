if (!(Test-Path .env)) { Write-Error 'Copy .env.example to .env before starting.'; exit 1 }
docker compose up -d --build
docker compose ps
