@echo off
setlocal DisableDelayedExpansion
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-VirtuosoWiki.ps1" %*
set "setup_result=%errorlevel%"
echo.
pause
exit /b %setup_result%
