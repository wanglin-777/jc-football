@echo off
chcp 65001 >nul
cd /d %~dp0
echo 正在抓取最新竞彩数据并更新网页(只更新, 不打开网页)...
"d:\python\.venv-1\Scripts\python.exe" refresh_push.py
echo.
echo 更新完成。查看网页: https://wanglin-777.github.io/jc-football/
pause
