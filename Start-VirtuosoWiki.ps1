param([switch]$Offline, [switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$scripts = Join-Path $root '.venv\Scripts'
$python = Join-Path $scripts 'python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'Run Install-VirtuosoWiki.cmd first to create the local Python environment.'
}
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:Path = $scripts + ';' + $env:Path
[Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$OutputEncoding = [Console]::OutputEncoding
Set-Location -LiteralPath $root
$global:VirtuosoWikiRoot = $root
function global:vwb {
    & (Join-Path $global:VirtuosoWikiRoot '.venv\Scripts\python.exe') -m virtuoso_wiki_bridge.cli --env (Join-Path $global:VirtuosoWikiRoot '.env') @args
}
if ($Offline) { vwb start --offline } else { vwb start }
if ($CheckOnly) { exit $LASTEXITCODE }
if ($LASTEXITCODE -ne 0) {
    Write-Warning 'Startup check failed. Local wiki commands remain available; use vwb doctor for diagnostics.'
}
