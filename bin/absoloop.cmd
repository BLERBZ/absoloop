@echo off
rem absoloop — Windows shim. Requires Python 3 on PATH (python or py).
where python >nul 2>nul && (python "%~dp0absoloop" %* & exit /b %errorlevel%)
py -3 "%~dp0absoloop" %*
