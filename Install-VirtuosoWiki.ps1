param(
    [string]$VaultPath = '',
    [ValidateSet('Ask', 'Yes', 'No')][string]$Desktop = 'Ask',
    [string]$Python = '',
    [switch]$WithBridge,
    [switch]$SkipInstall
)
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$OutputEncoding = [Console]::OutputEncoding
Set-Location -LiteralPath $PSScriptRoot
$venvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'

if (-not $SkipInstall) {
    if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
        if ($Python) {
            & $Python -m venv (Join-Path $PSScriptRoot '.venv')
        } elseif (Get-Command py -ErrorAction SilentlyContinue) {
            & py -3 -m venv (Join-Path $PSScriptRoot '.venv')
        } elseif (Get-Command python -ErrorAction SilentlyContinue) {
            & python -m venv (Join-Path $PSScriptRoot '.venv')
        } else {
            throw 'Python 3.9+ is required. Install Python, then rerun this installer.'
        }
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    & $venvPython -m pip install -e '.[books]'
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    if ($WithBridge) {
        & $venvPython -m pip install 'virtuoso-bridge[ssh] @ git+https://github.com/Arcadia-1/virtuoso-bridge-lite.git'
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
}
if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    throw 'The local .venv is missing. Rerun without -SkipInstall.'
}
$setupArgs = @('-m', 'virtuoso_wiki_bridge.cli', '--env', (Join-Path $PSScriptRoot '.env'), 'setup', '--desktop', $Desktop.ToLowerInvariant())
if ($VaultPath) { $setupArgs += $VaultPath }
& $venvPython @setupArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host ''
Write-Host 'Setup complete. Open Start-VirtuosoWiki.cmd or read USER_GUIDE.zh-CN.md.' -ForegroundColor Cyan
Write-Host 'Existing notes and .env were preserved. Configure your own VM before using live bridge commands.'
