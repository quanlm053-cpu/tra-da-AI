$ErrorActionPreference='Stop'
Set-Location $PSScriptRoot
Write-Host 'Trà đá AI: http://localhost:8766/lending - backend port 8767'
& npm.cmd run dev
