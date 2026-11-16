@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PBZ_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not exist "%PBZ_PYTHON%" (
  echo Python runtime not found. Please open 67-三Boss工作台v2交付说明.md.
  pause
  exit /b 1
)
"%PBZ_PYTHON%" "%~dp0tools\boss_workbench_v2_window.py"
if errorlevel 1 pause
