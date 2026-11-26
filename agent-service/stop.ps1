$runtimeRoot = Join-Path $PSScriptRoot 'runtime'
New-Item -ItemType Directory -Force -Path $runtimeRoot | Out-Null
Set-Content -LiteralPath (Join-Path $runtimeRoot 'STOP') -Value 'Stop requested by PM'
Write-Output 'Stop requested. The controller will cancel any active agent and preserve progress.'
