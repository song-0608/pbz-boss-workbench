@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PBZ_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not exist "%PBZ_PYTHON%" (
  echo Python runtime not found. Please open 37-阿花训练版操作卡.md.
  pause
  exit /b 1
)
"%PBZ_PYTHON%" "%~dp0tools\ahua_practice_window.py"
if errorlevel 1 pause
