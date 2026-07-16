@echo off
rem absoloop — Windows shim. Requires Python 3 on PATH (python or py).
rem Sets ABSOLOOP_HOME to this install so harness + shortcuts work without
rem a manual export when bin\ is on PATH.
set "ABSOLOOP_HOME=%~dp0.."
rem Normalize trailing backslash from %~dp0
if "%ABSOLOOP_HOME:~-1%"=="\" set "ABSOLOOP_HOME=%ABSOLOOP_HOME:~0,-1%"
where python >nul 2>nul && (python "%~dp0absoloop" %* & exit /b %errorlevel%)
py -3 "%~dp0absoloop" %*
