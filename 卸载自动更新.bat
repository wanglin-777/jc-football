@echo off
chcp 65001 >nul
schtasks /Delete /F /TN "JCFootballAutoRefresh"
echo 已卸载自动更新计划任务。
pause
