@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "PBZ_WORKFLOW_PY=C:\Users\xuesong\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not exist "%PBZ_WORKFLOW_PY%" (
  echo 本机 Python 运行时不存在；未启动游戏，也没有自动安装软件。
  pause
  exit /b 1
)
"%PBZ_WORKFLOW_PY%" -X utf8 tools\run_boss_offline_milestone.py
if errorlevel 1 (
  echo 离线检查未通过，请保留本窗口的具体错误。
) else (
  echo 多 Boss 离线里程碑已完成。候选和待验批次位于 research\boss-adaptation。
)
pause
