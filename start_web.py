# -*- coding: utf-8 -*-
"""
一键启动网页版
==============
用法(在项目目录):  python start_web.py
会自动:
  1. 启动 Streamlit 服务器(0.0.0.0:8501, 局域网手机也可访问)
  2. 自动打开浏览器
"""
import os
import subprocess
import sys
import threading
import time
import webbrowser

BASE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(BASE, "app.py")
PORT = 8501


def _open_browser():
    time.sleep(4)
    try:
        webbrowser.open(f"http://localhost:{PORT}")
    except Exception:
        pass


def main():
    print("正在启动竞彩串关预测网页 ...")
    threading.Thread(target=_open_browser, daemon=True).start()
    cmd = [sys.executable, "-m", "streamlit", "run", APP,
           "--server.address", "0.0.0.0",
           "--server.port", str(PORT),
           "--server.headless", "true",
           "--browser.gatherUsageStats", "false"]
    subprocess.call(cmd)


if __name__ == "__main__":
    main()
