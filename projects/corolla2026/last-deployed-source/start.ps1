$ErrorActionPreference = "Stop"

function Read-DotEnvValue([string]$Name, [string]$DefaultValue) {
    if (!(Test-Path -LiteralPath ".env")) { return $DefaultValue }
    $match = Get-Content -LiteralPath ".env" | Where-Object { $_ -match "^$([regex]::Escape($Name))=(.*)$" } | Select-Object -First 1
    if (!$match) { return $DefaultValue }
    return ($match -replace "^$([regex]::Escape($Name))=", "").Trim()
}

if (!(Test-Path -LiteralPath ".env")) {
    $answer = Read-Host ".env is missing. Copy .env.example to .env now? (y/N)"
    if ($answer -match "^(y|yes)$") {
        Copy-Item -LiteralPath ".env.example" -Destination ".env"
        Write-Host "Created .env. Edit passwords, secrets, and OPENAI_API_KEY, then run .\start.ps1 again."
    }
    exit 1
}

$hostPort = Read-DotEnvValue "HOST_PORT" "3001"
if (!$hostPort) { $hostPort = "3001" }
$tcp = Get-NetTCPConnection -LocalPort ([int]$hostPort) -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($tcp) {
    Write-Host "Port $hostPort is already in use by process $($tcp.OwningProcess)."
    $containers = docker ps --format "{{.Names}}`t{{.Ports}}" | Select-String -Pattern ":$hostPort->"
    if ($containers) {
        Write-Host "Docker container using this port:"
        $containers | ForEach-Object { Write-Host $_.Line }
    }
    Write-Host "Choose another HOST_PORT in .env or stop the unrelated service yourself. This script will not stop it."
    exit 1
}

docker compose config | Out-Host
docker compose up --build -d

$deadline = (Get-Date).AddSeconds(120)
do {
    Start-Sleep -Seconds 3
    $status = docker compose ps chatbot --format json 2>$null | ConvertFrom-Json | Select-Object -ExpandProperty Health -ErrorAction SilentlyContinue
    if ($status -eq "healthy") { break }
} while ((Get-Date) -lt $deadline)

Write-Host ""
Write-Host "Chatbot: http://127.0.0.1:$hostPort/central-trade-auto-co-markazia-toyota-jordan/"
Write-Host "Shared login: http://127.0.0.1:$hostPort/central-trade-auto-co-markazia-toyota-jordan/admin/login"
Write-Host "Sales callbacks: http://127.0.0.1:$hostPort/central-trade-auto-co-markazia-toyota-jordan/sales-callbacks/"
Write-Host "Chat history: http://127.0.0.1:$hostPort/central-trade-auto-co-markazia-toyota-jordan/chat-history/"
Write-Host "Health: http://127.0.0.1:$hostPort/health"
