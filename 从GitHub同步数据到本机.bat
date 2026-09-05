@echo off
chcp 65001 >nul
cd /d %~dp0
echo 正在从 GitHub 同步数据到本机(以 GitHub 为准)...
git fetch origin
git reset --hard origin/main
echo.
echo 完成! 本机数据已与 GitHub 一致:
echo   data\today_matches.*    当天快照
echo   data\history\           每日预测账本
echo   data\history_csv\       可直接打开的 CSV
echo   data\cache\             各联赛整季赛果(备份)
echo   docs\                   网页
echo.
echo 注意: 本机私有文件(deepseek_key.txt / ai_cache.json)不会被改动。
pause
