@echo off
rem One-click shooter start: double-click this file. No terminal or PYTHONPATH setup needed.
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 (
  python "%~dp0play.py" %*
  if errorlevel 1 pause
  exit /b %errorlevel%
)
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 "%~dp0play.py" %*
  if errorlevel 1 pause
  exit /b %errorlevel%
)
echo Shooter could not start.
echo Why: no Python found on PATH.
echo Fix: install Python 3.10+ from https://www.python.org/downloads/ and try again.
pause
exit /b 1
