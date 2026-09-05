@echo off
chcp 65001 >nul
cd /d %~dp0
"d:\python\.venv-1\Scripts\python.exe" build_site.py --open
echo.
pause
