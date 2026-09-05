# -*- coding: utf-8 -*-
"""
自动抓数据 + 推送到 GitHub (refresh_push.py)
=============================================
背景: 竞彩官网只允许中国大陆网络访问, GitHub 云端抓不到,
      所以由"你自己的电脑"每 4 小时执行一次本脚本:
      1) 联网抓取竞彩官方最新场次/赔率 -> 更新 data/today_matches.*
      2) 有变化就 commit 并 push 到 GitHub
      3) GitHub Pages/Actions 会把最新数据部署成公开网页(随时可看)

用系统"任务计划程序"每 4 小时静默运行本脚本(pythonw, 无窗口)。
日志: data/refresh.log
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
LOG = os.path.join(DATA, "refresh.log")
GIT_AUTHOR = ("wanglin-777", "wanglin-777@users.noreply.github.com")


def _log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line)


def _git(*args):
    return subprocess.run(["git", "-C", BASE, *args],
                          capture_output=True, text=True, encoding="utf-8")


def main():
    # 1) 联网抓最新数据(失败也不中断, 由上层重试)
    try:
        from sporttery import fetch_today
        res = fetch_today(force=True)
        _log(f"抓取成功: 日期 {res['date']}, 在售 {len(res['matches'])} 场")
    except Exception as e:
        _log(f"⚠ 抓取失败: {e}")

    # 2) 提交并推送变化(没有变化就跳过, 不产生噪音提交)
    st = _git("status", "--porcelain")
    if st.returncode != 0:
        _log(f"⚠ git status 失败: {st.stderr.strip()}")
        return 1
    if not st.stdout.strip():
        _log("无数据变化, 跳过推送。")
        return 0

    _git("add", "-A")
    msg = f"auto: 定时刷新竞彩数据 {time.strftime('%Y-%m-%d %H:%M')}"
    _git("-c", f"user.name={GIT_AUTHOR[0]}", "-c", f"user.email={GIT_AUTHOR[1]}",
         "commit", "-m", msg)
    push = _git("push", "origin", "main")
    if push.returncode == 0:
        _log(f"✅ 已推送数据更新 (commit: {msg})")
        return 0
    _log(f"⚠ 推送失败: {push.stderr.strip()}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
