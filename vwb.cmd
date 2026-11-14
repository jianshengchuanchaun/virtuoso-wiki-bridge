@echo off
setlocal DisableDelayedExpansion
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
if not exist "%~dp0.venv\Scripts\python.exe" (
    echo Run Install-VirtuosoWiki.cmd first.
    exit /b 2
)
"%~dp0.venv\Scripts\python.exe" -m virtuoso_wiki_bridge.cli --env "%~dp0.env" %*
exit /b %ERRORLEVEL%
