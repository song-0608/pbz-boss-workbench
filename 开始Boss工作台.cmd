@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PBZ_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not exist "%PBZ_PYTHON%" (
  echo Python runtime not found. Please open 74-Boss工作台v5操作说明.md.
  pause
  exit /b 1
)
"%PBZ_PYTHON%" -B -X utf8 "%~dp0tools\boss_workbench_v5_window.py"
if errorlevel 1 pause
