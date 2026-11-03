$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$LogPath = Join-Path $Root "logs\cleanup_actions.log"
New-Item -ItemType Directory -Force -Path (Split-Path $LogPath) | Out-Null
$PidFile = Join-Path $Root "data\cache\hybrid_server.pid"
if (Test-Path -LiteralPath $PidFile) { throw "Stop the tracked hybrid server before cleaning generated files." }
$Targets = @(
    (Join-Path $Root "data\processed\list_profiles.jsonl"),
    (Join-Path $Root "data\processed\list_profiles.csv"),
    (Join-Path $Root "data\processed\retrieval_documents.jsonl"),
    (Join-Path $Root "data\indexes\lexical.sqlite3"),
    (Join-Path $Root "data\indexes\local_lsa.npz"),
    (Join-Path $Root "data\indexes\local_lsa_metadata.json")
)
foreach ($Target in $Targets) {
    $Full = [IO.Path]::GetFullPath($Target)
    if (-not $Full.StartsWith($Root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw "Unsafe cleanup target: $Full" }
    if (Test-Path -LiteralPath $Full) {
        Add-Content -LiteralPath $LogPath -Value "$(Get-Date -Format o) DELETE $Full"
        Remove-Item -LiteralPath $Full
    }
}
Write-Output "Generated profile/index files removed. Raw data, manifests, code, tests, reports, logs, and backups were preserved."
