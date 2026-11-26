param([Parameter(Mandatory=$true)][ValidatePattern('^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$')][string]$AppRepository)
$ErrorActionPreference='Stop'
Set-Location $PSScriptRoot
function Run-Native([string]$Program,[string[]]$Arguments) {
  & $Program @Arguments
  if ($LASTEXITCODE -ne 0) { throw "Command failed: $Program" }
}
foreach($command in @('python','node','npm.cmd','git','docker')) { Get-Command $command -ErrorAction Stop | Out-Null }
Run-Native 'docker' @('compose','version')
$nodeMajor=[int]((& node -p 'process.versions.node').Split('.')[0])
if($nodeMajor -lt 26){throw 'Use Node.js 26+ for the bundled sample application.'}
New-Item -ItemType Directory -Force .local,workspace | Out-Null
if(!(Test-Path 'infra/.env')) {
  $random=[Security.Cryptography.RandomNumberGenerator]::Create()
  $bytes=New-Object byte[] 48
  $random.GetBytes($bytes);$dbSecret=[Convert]::ToBase64String($bytes)
  $random.GetBytes($bytes);$appSecret=[Convert]::ToBase64String($bytes)
  [IO.File]::WriteAllText((Join-Path $PSScriptRoot 'infra/.env'),"POSTGRES_PASSWORD=$dbSecret`nREDMINE_SECRET_KEY_BASE=$appSecret`n")
  $random.Dispose()
}
Run-Native 'python' @('-m','venv','.venv')
$python=Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
Run-Native $python @('-m','pip','install','-r','agent-service/lending/discord-requirements.txt')
Run-Native $python @('agent-service/provision_tools.py')
Run-Native 'npm.cmd' @('ci','--prefix','agent-office','--ignore-scripts','--no-audit','--no-fund')
Run-Native 'npm.cmd' @('--prefix','agent-office','run','build')
if(!(Test-Path 'workspace/app/.git')) {Run-Native 'git' @('clone',"https://github.com/$AppRepository.git",'workspace/app')}
$remote=(& git -C workspace/app remote get-url origin).Trim()
if($remote -notmatch [regex]::Escape($AppRepository)){throw 'workspace/app belongs to another repo. Use a separate installation directory.'}
Run-Native 'git' @('-C','workspace/app','rev-parse','--verify','origin/main')
Run-Native 'docker' @('compose','--env-file','infra/.env','-f','infra/compose.yaml','up','-d')
$ready=$false
for($i=0;$i -lt 90;$i++) {
  try {$response=Invoke-WebRequest 'http://127.0.0.1:3000/login' -UseBasicParsing -TimeoutSec 3;if($response.StatusCode -eq 200){$ready=$true;break}} catch {}
  Start-Sleep -Seconds 3
}
if(!$ready){throw 'Redmine is not ready. Run docker compose --env-file infra/.env -f infra/compose.yaml logs redmine.'}
if(!(Test-Path '.local/credentials.json')) {
  Run-Native 'docker' @('compose','--env-file','infra/.env','-f','infra/compose.yaml','exec','-T','-e','REDMINE_LANG=en','redmine','bundle','exec','rake','redmine:load_default_data','RAILS_ENV=production')
}
Run-Native 'docker' @('compose','--env-file','infra/.env','-f','infra/compose.yaml','exec','-T','redmine','bundle','exec','rails','runner','-e','production','/opt/trada/bootstrap.rb')
Run-Native 'docker' @('compose','--env-file','infra/.env','-f','infra/compose.yaml','cp','redmine:/tmp/trada-credentials.json','.local/credentials.json')
$config=@{redmine_url='http://localhost:3000';credentials_file=(Join-Path $PSScriptRoot '.local/credentials.json');project_id=2;repository=(Join-Path $PSScriptRoot 'workspace/app');poll_seconds=20;agent_timeout_seconds=1800;max_repair_rounds=2;max_agent_calls_per_story=30;statuses=@{backlog=7;selected=8;in_progress=2;blocked=9;code_review=10;ready_for_test=11;testing=12;todo=13;in_review=14;done=15};trackers=@{story=4;task=5;bug=1};new_task_assignees=@{};github=@{enabled=$true;repository=$AppRepository;base_branch='main'}}
$config | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 agent-service/config.json
if(!(Test-Path 'deployment.local.json')) {
  $deployment=Get-Content deployment.example.json -Raw | ConvertFrom-Json
  $deployment.repository=$AppRepository
  $deployment | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 deployment.local.json
}
Write-Host 'Setup completed. Redmine credentials are in .local/credentials.json; do not publish this file.'
Write-Host 'Next: configure SQL Server, authenticate Codex, then run start.ps1 -Component backend and -Component office in separate terminals.'
