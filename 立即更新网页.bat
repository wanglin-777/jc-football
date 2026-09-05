@echo off
chcp 65001 >nul
cd /d %~dp0
echo 正在抓取最新竞彩数据并更新网页...
"d:\python\.venv-1\Scripts\python.exe" refresh_push.py
start https://wanglin-777.github.io/jc-football/
pause
