# -*- coding: utf-8 -*-
"""
网页常驻服务 (serve.py)
=======================
让竞彩串关预测网页"常驻后台、随时可打开":
    - 无控制台窗口静默运行(pythonw 启动)
    - 端口冲突自动跳过(不会重复启动)
    - 日志写 data/server.log, 进程号写 data/server.pid

用法:
    python serve.py            # 启动(若已在运行则跳过)
    python serve.py --open     # 启动并自动打开浏览器
    python serve.py stop       # 停止服务
    python serve.py status     # 查看状态
"""
import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser

BASE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(BASE, "app.py")
DATA = os.path.join(BASE, "data")
LOG = os.path.join(DATA, "server.log")
PID = os.path.join(DATA, "server.pid")
PORT = 8501
HOST = "0.0.0.0"
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _port_open(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        s.connect(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def _write_pid(pid):
    os.makedirs(DATA, exist_ok=True)
    with open(PID, "w") as f:
        f.write(str(pid))


def _read_pid():
    try:
        with open(PID) as f:
            return int(f.read().strip())
    except Exception:
        return None


def _open_browser():
    time.sleep(3)
    try:
        webbrowser.open(f"http://localhost:{PORT}")
    except Exception:
        pass


def start(open_browser=False):
    if _port_open(PORT):
        print(f"网页已在运行: http://localhost:{PORT}  (无需重复启动)")
        if open_browser:
            webbrowser.open(f"http://localhost:{PORT}")
        return True
    os.makedirs(DATA, exist_ok=True)
    flog = open(LOG, "a", encoding="utf-8")
    flog.write("\n===== 启动服务 %s =====\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
    flog.flush()
    cmd = [sys.executable, "-m", "streamlit", "run", APP,
           "--server.address", HOST, "--server.port", str(PORT),
           "--server.headless", "true",
           "--browser.gatherUsageStats", "false"]
    try:
        p = subprocess.Popen(cmd, stdout=flog, stderr=flog,
                             creationflags=CREATE_NO_WINDOW)
    except Exception as e:
        flog.write("启动失败: %r\n" % e)
        flog.close()
        print("启动失败:", e)
        return False
    _write_pid(p.pid)
    print(f"网页服务已启动: http://localhost:{PORT}  (局域网: http://<本机IP>:{PORT})")
    if open_browser:
        threading.Thread(target=_open_browser, daemon=True).start()
    return True


def stop():
    pid = _read_pid()
    removed = False
    if pid:
        try:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                           capture_output=True)
            removed = True
        except Exception:
            pass
    # 兜底: 若端口仍占用说明进程号对不上, 不再强杀以免误伤其它程序
    if os.path.exists(PID):
        try:
            os.remove(PID)
        except Exception:
            pass
    if removed:
        print("已停止网页服务。")
    else:
        print("未发现运行中的服务(可能已停止, 或由其它方式启动)。")
    return removed


def status():
    pid = _read_pid()
    open_ = _port_open(PORT)
    if open_:
        print(f"运行中: http://localhost:{PORT}  (pid={pid})")
    else:
        print("未运行。(可运行 serve.py 或双击 启动网页版.bat)")


if __name__ == "__main__":
    arg = (sys.argv[1] if len(sys.argv) > 1 else "").lower()
    if arg == "stop":
        stop()
    elif arg == "status":
        status()
    elif arg == "--open":
        start(open_browser=True)
    else:
        start(open_browser=False)
