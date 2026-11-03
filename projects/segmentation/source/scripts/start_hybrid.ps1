$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PidFile = Join-Path $Root "data\cache\hybrid_server.pid"
$LogFile = Join-Path $Root "logs\hybrid_server.log"
$ConfiguredPort = $env:PORT
if (-not $ConfiguredPort -and (Test-Path (Join-Path $Root ".env"))) {
    $PortLine = Get-Content (Join-Path $Root ".env") | Where-Object { $_ -match '^PORT=' } | Select-Object -First 1
    if ($PortLine) { $ConfiguredPort = ($PortLine -split '=', 2)[1].Trim() }
}
if (-not $ConfiguredPort) { $ConfiguredPort = "5002" }
$env:PORT = $ConfiguredPort
$PortOwner = Get-NetTCPConnection -LocalPort ([int]$ConfiguredPort) -State Listen -ErrorAction SilentlyContinue
if ($PortOwner) { throw "Port $ConfiguredPort is already in use by PID $($PortOwner.OwningProcess)." }
New-Item -ItemType Directory -Force -Path (Split-Path $PidFile), (Split-Path $LogFile) | Out-Null
$Python = (& py -3 -c "import sys; print(sys.executable)").Trim()
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Could not resolve the Python interpreter." }
$Process = Start-Process -FilePath $Python -ArgumentList "scripts\run_hybrid_server.py" -WorkingDirectory $Root -RedirectStandardOutput $LogFile -RedirectStandardError (Join-Path $Root "logs\hybrid_server_error.log") -WindowStyle Hidden -PassThru
Set-Content -LiteralPath $PidFile -Value $Process.Id -Encoding ascii
Start-Sleep -Seconds 2
if ($Process.HasExited) { throw "Hybrid server exited during startup. See logs\hybrid_server_error.log." }
Write-Output "Hybrid server started at http://127.0.0.1:$ConfiguredPort/ (PID $($Process.Id))"
