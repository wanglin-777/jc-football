@echo off
chcp 65001 >nul
cd /d %~dp0
echo 正在注册"每4小时自动更新"计划任务...
schtasks /Create /F /TN "JCFootballAutoRefresh" /SC HOURLY /MO 4 /ST 09:02 /TR "\"d:\python\.venv-1\Scripts\pythonw.exe\" \"%~dp0refresh_push.py\""
echo.
echo 已安装: 每 4 小时自动抓取竞彩最新数据并推送(需电脑开机)。
echo 现在立即执行一次...
start "" "d:\python\.venv-1\Scripts\python.exe" "%~dp0refresh_push.py"
echo 完成! 查看日志: data\refresh.log
pause
