$ErrorActionPreference = 'Stop'
$pythonPath = (Get-Command python -ErrorAction Stop).Source
& $pythonPath -u (Join-Path $PSScriptRoot 'office.py')
