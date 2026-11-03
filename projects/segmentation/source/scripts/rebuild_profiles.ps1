$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location -LiteralPath $Root
$Existing = @("data\processed\list_profiles.jsonl", "data\processed\list_profiles.csv") | ForEach-Object { Join-Path $Root $_ } | Where-Object { Test-Path -LiteralPath $_ }
if ($Existing) {
    $Backup = Join-Path $Root ("backups\profile_rebuild_" + (Get-Date -Format "yyyyMMdd-HHmmss"))
    New-Item -ItemType Directory -Path $Backup | Out-Null
    foreach ($Path in $Existing) {
        Copy-Item -LiteralPath $Path -Destination (Join-Path $Backup ([IO.Path]::GetFileName($Path)))
        Add-Content -LiteralPath (Join-Path $Root "logs\generated_replacements.log") -Value "$(Get-Date -Format o) BACKUP_BEFORE_REPLACE $Path -> $Backup"
    }
}
py -3 scripts\rebuild_profiles.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
