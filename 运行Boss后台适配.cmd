@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "PBZ_BACKGROUND_PY=C:\Users\xuesong\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not exist "%PBZ_BACKGROUND_PY%" (
  echo 本机 Python 运行时不存在，未执行后台适配。
  pause
  exit /b 1
)
"%PBZ_BACKGROUND_PY%" -B -X utf8 tools\run_boss_background_milestone.py
set "PBZ_BACKGROUND_RESULT=%errorlevel%"
if "%PBZ_BACKGROUND_RESULT%"=="0" (
  echo 后台盘点、候选生成和离线回归完成。报告路径见上方。
  echo 此入口不启动游戏、不装配运行中的角色。实机效果仍按集中验收记录。
) else (
  echo 后台检查未通过，请保留上方错误和报告。
)
pause
exit /b %PBZ_BACKGROUND_RESULT%
