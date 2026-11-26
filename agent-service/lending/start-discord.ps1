$ErrorActionPreference = 'Stop'
$pythonPath = Join-Path $PSScriptRoot '../runtime/lending/discord-venv/Scripts/python.exe'
& $pythonPath (Join-Path $PSScriptRoot 'discord_pm.py') --agents SA BA FE BE TESTER REVIEW DEVOPS
