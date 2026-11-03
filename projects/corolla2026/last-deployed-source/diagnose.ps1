$ErrorActionPreference = "Continue"

function Read-DotEnvValue([string]$Name, [string]$DefaultValue) {
    if (!(Test-Path -LiteralPath ".env")) { return $DefaultValue }
    $match = Get-Content -LiteralPath ".env" | Where-Object { $_ -match "^$([regex]::Escape($Name))=(.*)$" } | Select-Object -First 1
    if (!$match) { return $DefaultValue }
    return ($match -replace "^$([regex]::Escape($Name))=", "").Trim()
}

Write-Host "Compose services"
docker compose ps -a

$hostPort = Read-DotEnvValue "HOST_PORT" "3001"
Write-Host ""
Write-Host "Resolved host port: $hostPort"
Write-Host "Expected project name: markazia-toyota-jordan-standalone-v3"
Write-Host "Expected volumes:"
Write-Host "  markazia-toyota-jordan-standalone-v3_chatbot_db"
Write-Host "  markazia-toyota-jordan-standalone-v3_chatbot_conversations"

Write-Host ""
Write-Host "Environment presence"
foreach ($name in @("OPENAI_API_KEY","OPENAI_CHAT_MODEL","OPENAI_EMBEDDING_MODEL","OPENAI_EMBEDDING_DIMENSIONS","POSTGRES_USER","POSTGRES_PASSWORD","POSTGRES_DB","POSTGRES_HOST","POSTGRES_PORT","DASHBOARD_PASSWORD","SESSION_SECRET","CSRF_SECRET")) {
    $value = Read-DotEnvValue $name ""
    Write-Host ("  " + $name + "=" + $(if ($value) { "<set>" } else { "<missing>" }))
}

Write-Host ""
Write-Host "Resolved compose config"
docker compose config | Select-String -Pattern "name:|published:|POSTGRES_|source:|chatbot_db|chatbot_conversations"

Write-Host ""
Write-Host "Health response"
try { Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$hostPort/health" | Select-Object StatusCode,Content } catch { Write-Host $_.Exception.Message }

Write-Host ""
Write-Host "Chatbot logs tail"
docker compose logs --tail 80 chatbot

Write-Host ""
Write-Host "PostgreSQL logs tail"
docker compose logs --tail 80 postgres
