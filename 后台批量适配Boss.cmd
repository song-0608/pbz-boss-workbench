@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "PBZ_BACKEND_PY=C:\Users\xuesong\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not exist "%PBZ_BACKEND_PY%" exit /b 1
"%PBZ_BACKEND_PY%" -B -X utf8 tools\boss_offline_inventory.py
if errorlevel 1 exit /b 1
"%PBZ_BACKEND_PY%" -B -X utf8 tools\prepare_full_boss_catalog.py
if errorlevel 1 exit /b 1
echo 后台盘点与候选查询批次已生成。需要研究版验收的项目已单独列出。
pause
