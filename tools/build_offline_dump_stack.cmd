@echo off
rem Purpose: build only the offline dump reader; never start or attach to PBZ.
call "C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 exit /b 1
cd /d "%~dp0..\runtime\dump-analysis"
cl /nologo /EHsc /W4 /std:c++17 /utf-8 /MT /O2 "%~dp0offline_dump_stack.cpp" /Fe:offline_dump_stack.exe /Fo:offline_dump_stack.obj /link dbghelp.lib
exit /b %errorlevel%
