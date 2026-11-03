$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location -LiteralPath $Root
$Existing = @(
    "data\processed\retrieval_documents.jsonl",
    "data\indexes\lexical.sqlite3",
    "data\indexes\local_lsa.npz",
    "data\indexes\local_lsa_metadata.json"
) | ForEach-Object { Join-Path $Root $_ } | Where-Object { Test-Path -LiteralPath $_ }
if ($Existing) {
    $Backup = Join-Path $Root ("backups\index_rebuild_" + (Get-Date -Format "yyyyMMdd-HHmmss"))
    New-Item -ItemType Directory -Path $Backup | Out-Null
    foreach ($Path in $Existing) {
        Copy-Item -LiteralPath $Path -Destination (Join-Path $Backup ([IO.Path]::GetFileName($Path)))
        Add-Content -LiteralPath (Join-Path $Root "logs\generated_replacements.log") -Value "$(Get-Date -Format o) BACKUP_BEFORE_REPLACE $Path -> $Backup"
    }
}
py -3 scripts\build_indexes.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
