param([ValidateSet('office','backend','discord','preview')][string]$Component='office')
$ErrorActionPreference='Stop'
Set-Location $PSScriptRoot
$python=Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if(!(Test-Path $python)){throw 'Run setup.ps1 first.'}
if($Component -eq 'office') {
  Set-Location agent-office
  & npm.cmd run dev
} elseif($Component -eq 'backend') {
  & $python -u agent-service/lending/office.py
} elseif($Component -eq 'discord') {
  & $python -u agent-service/lending/discord_pm.py --agents SA BA FE BE TESTER REVIEW DEVOPS
} else {
  & $python -u agent-service/lending/preview.py
}
if($LASTEXITCODE -ne 0){throw "Component $Component stopped with an error."}
