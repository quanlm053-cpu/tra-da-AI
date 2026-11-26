param(
    [ValidateSet('codex','claude','gemini')][string]$Provider = 'codex',
    [ValidateSet('status','login','install')][string]$Action = 'status'
)
$ErrorActionPreference = 'Stop'
$serviceRoot = Split-Path $PSScriptRoot -Parent
if ($Action -eq 'install') {
    if ($Provider -eq 'codex') { throw 'Codex dùng bản đã cài trên máy.' }
    $package = if ($Provider -eq 'claude') { '@anthropic-ai/claude-code@2.1.332' } else { '@google/gemini-cli@0.71.1' }
    & (Join-Path $serviceRoot 'tools/bin/npm.cmd') install --prefix (Join-Path $serviceRoot 'tools/providers') --save-exact --no-audit --no-fund $package
    if ($LASTEXITCODE -ne 0) { throw 'Không cài được CLI.' }
    $Action = 'status'
}
& python (Join-Path $PSScriptRoot 'agent_providers.py') $Provider $Action
if ($LASTEXITCODE -ne 0) { throw 'Thao tác nhà cung cấp chưa hoàn tất.' }
