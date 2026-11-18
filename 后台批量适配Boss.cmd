@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "PBZ_BACKEND_PY=C:\Users\xuesong\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not exist "%PBZ_BACKEND_PY%" exit /b 1
"%PBZ_BACKEND_PY%" -B -X utf8 tools\run_boss_background_milestone.py
if errorlevel 1 exit /b 1
echo 后台盘点、技能候选、完整查询队列与离线回归已完成。实机缺口保留在报告中。
pause
