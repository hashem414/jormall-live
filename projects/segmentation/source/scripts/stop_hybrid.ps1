$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PidFile = Join-Path $Root "data\cache\hybrid_server.pid"
if (-not (Test-Path -LiteralPath $PidFile)) { Write-Output "No tracked hybrid server PID file found."; exit 0 }
$TrackedPid = [int](Get-Content -LiteralPath $PidFile -Raw).Trim()
$Process = Get-CimInstance Win32_Process -Filter "ProcessId=$TrackedPid" -ErrorAction SilentlyContinue
if (-not $Process) { Remove-Item -LiteralPath $PidFile; Write-Output "Tracked process already stopped."; exit 0 }
$ExpectedRoot = [Regex]::Escape($Root)
if ($Process.CommandLine -notmatch $ExpectedRoot -and $Process.CommandLine -notmatch "scripts\\run_hybrid_server.py") {
    throw "PID $TrackedPid does not belong to this project; refusing to stop it."
}
$Children = Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq $TrackedPid -and $_.CommandLine -match "scripts\\run_hybrid_server.py" }
foreach ($Child in $Children) { Stop-Process -Id $Child.ProcessId -ErrorAction SilentlyContinue }
Stop-Process -Id $TrackedPid
Remove-Item -LiteralPath $PidFile
Write-Output "Stopped tracked hybrid server PID $TrackedPid."
