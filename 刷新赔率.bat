@echo off
chcp 65001 >nul
cd /d %~dp0
echo 正在联网刷新竞彩官方赔率数据...
"d:\python\.venv-1\Scripts\python.exe" -c "from sporttery import fetch_today; r=fetch_today(force=True); print('已更新: ', r['date'], ' 在售 ', len(r['matches']), ' 场')"
pause
