param([switch]$SingleBatch)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Report = Join-Path $Root "reports\legacy_benchmark_baseline.json"
Set-Location -LiteralPath $Root

$PreviousCount = -1
for ($Batch = 1; $Batch -le 20; $Batch++) {
    py -3 -m benchmarks.benchmark_runner
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $State = Get-Content -LiteralPath $Report -Raw | ConvertFrom-Json
    Write-Output "Legacy benchmark progress: $($State.campaigns)/$($State.full_campaign_count)"
    if ($State.coverage_complete -or $SingleBatch) { exit 0 }
    if ($State.campaigns -le $PreviousCount) { throw "Legacy benchmark made no progress in batch $Batch." }
    $PreviousCount = $State.campaigns
    $env:SKIP_HYBRID_BENCHMARK = "1"
    $env:SKIP_SCOPE_BENCHMARK = "1"
}

throw "Legacy benchmark did not complete within 20 bounded batches."
