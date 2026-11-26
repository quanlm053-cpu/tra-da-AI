$ErrorActionPreference = 'Stop'
$serviceRoot = $PSScriptRoot
$runtimeRoot = Join-Path $serviceRoot 'runtime'
New-Item -ItemType Directory -Force -Path $runtimeRoot | Out-Null
$pythonPath = (Get-Command python -ErrorAction Stop).Source
function Start-DemoDashboard {
    $dashboardIdFile = Join-Path $runtimeRoot 'dashboard.pid'
    $dashboardRunning = $false
    if (Test-Path -LiteralPath $dashboardIdFile) {
        $dashboardProcessId = [int](Get-Content -LiteralPath $dashboardIdFile)
        $dashboardProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$dashboardProcessId" -ErrorAction SilentlyContinue
        $dashboardRunning = $dashboardProcess -and $dashboardProcess.CommandLine -like '*dashboard.py*'
    }
    if (-not $dashboardRunning) {
        Start-Process -FilePath $pythonPath -ArgumentList @('-u','dashboard.py') -WorkingDirectory $serviceRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtimeRoot 'dashboard.log') -RedirectStandardError (Join-Path $runtimeRoot 'dashboard-error.log') | Out-Null
    }
    Write-Output 'Demo console: http://localhost:8765'
}
$pidPath = Join-Path $runtimeRoot 'pid'
if (Test-Path -LiteralPath $pidPath) {
    $runningServiceId = [int](Get-Content -LiteralPath $pidPath)
    $runningService = Get-CimInstance Win32_Process -Filter "ProcessId=$runningServiceId" -ErrorAction SilentlyContinue
    if ($runningService -and $runningService.CommandLine -like '*controller.py*run*') {
        Write-Output "Agent service already running, PID $runningServiceId"
        Start-DemoDashboard
        exit 0
    }
}
& $pythonPath (Join-Path $serviceRoot 'controller.py') doctor
if ($LASTEXITCODE -ne 0) { throw 'Preflight failed' }
$processInfo = Start-Process -FilePath $pythonPath -ArgumentList @('-u', 'controller.py', 'run') -WorkingDirectory $serviceRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtimeRoot 'service.log') -RedirectStandardError (Join-Path $runtimeRoot 'service-error.log') -PassThru
Start-Sleep -Seconds 3
$processInfo.Refresh()
if ($processInfo.HasExited) { throw 'Service exited; inspect runtime/service-error.log' }
Write-Output "Agent service started, PID $($processInfo.Id)"
Start-DemoDashboard
