@echo off
chcp 65001 >nul
cd /d %~dp0
"d:\python\.venv-1\Scripts\python.exe" autostart.py uninstall
echo.
pause
