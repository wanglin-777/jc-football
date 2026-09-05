# -*- coding: utf-8 -*-
"""
开机自启 安装/卸载 (autostart.py)
=================================
安装后, 每次 Windows 登录会自动静默启动"竞彩串关预测"网页服务,
你在浏览器随时打开 http://localhost:8501 即可(同一 WiFi 手机也能访问)。

用法:
    python autostart.py install     # 安装开机自启 + 启动服务 + 桌面快捷方式
    python autostart.py uninstall   # 卸载开机自启(不影响当前运行)
"""
import os
import shutil
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
VENV_PY = r"d:\python\.venv-1\Scripts\python.exe"   # 与实际 .bat 保持一致
VENV_PYW = r"d:\python\.venv-1\Scripts\pythonw.exe"
SERVE = os.path.join(BASE, "serve.py")


def _startup_dir():
    appdata = os.environ.get("APPDATA", "")
    return os.path.join(appdata, "Microsoft", "Windows", "Start Menu",
                        "Programs", "Startup")


def _desktop_dir():
    # 优先真实桌面; 取不到就退回用户目录
    for key in ("USERPROFILE", "HOMEDRIVE"):
        pass
    return os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")


VBS_NAME = "竞彩串关预测_自启.vbs"
URL_NAME = "竞彩串关预测.url"


def _vbs_content():
    return ('Set ws = CreateObject("Wscript.Shell")\r\n'
            f'ws.Run """{VENV_PYW}"" ""{SERVE}""", 0, False\r\n')


def _url_content():
    return ("[InternetShortcut]\r\n"
            "URL=http://localhost:8501\r\n"
            "IconIndex=0\r\n")


def install():
    # 1) 写入开机自启 vbs
    startup = _startup_dir()
    os.makedirs(startup, exist_ok=True)
    vbs_path = os.path.join(startup, VBS_NAME)
    with open(vbs_path, "w", encoding="utf-8") as f:
        f.write(_vbs_content())
    # 2) 桌面快捷方式(网页)
    desktop = _desktop_dir()
    try:
        os.makedirs(desktop, exist_ok=True)
        with open(os.path.join(desktop, URL_NAME), "w", encoding="utf-8") as f:
            f.write(_url_content())
    except Exception:
        pass
    print("✅ 已安装开机自启(下次登录自动运行)。")
    print(f"   自启文件: {vbs_path}")

    # 3) 立即启动服务(若已在运行会跳过)
    try:
        subprocess.run([sys.executable, SERVE, "--open"],
                       check=False, creationflags=0x08000000 if os.name == "nt" else 0)
    except Exception:
        pass
    print("🌐 现在就可以打开: http://localhost:8501  (或在桌面双击『竞彩串关预测』)")


def uninstall():
    startup = _startup_dir()
    vbs = os.path.join(startup, VBS_NAME)
    removed = False
    try:
        if os.path.exists(vbs):
            os.remove(vbs)
            removed = True
    except Exception:
        pass
    url = os.path.join(_desktop_dir(), URL_NAME)
    try:
        if os.path.exists(url):
            os.remove(url)
    except Exception:
        pass
    if removed:
        print("✅ 已卸载开机自启(下次登录将不再自动运行)。")
        print("   当前正在运行的服务不受影响; 如需彻底停止请运行: serve.py stop")
    else:
        print("未找到已安装的自启项(可能之前未安装)。")


if __name__ == "__main__":
    cmd = (sys.argv[1] if len(sys.argv) > 1 else "install").lower()
    if cmd == "uninstall":
        uninstall()
    else:
        install()
