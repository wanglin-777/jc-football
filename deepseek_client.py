# -*- coding: utf-8 -*-
"""
DeepSeek API 客户端(可选, 用于 AI 复盘分析)
===========================================
Key 只在你的电脑本地使用, 不会上传 GitHub 也不会显示在网页/日志里。

获取 Key: https://platform.deepseek.com → API Keys 创建(充值少量即可)
配置方式(任选其一):
  1. 环境变量 DEEPSEEK_API_KEY
  2. 在 data/deepseek_key.txt 里粘贴(以 # 开头的行为注释, 会自动忽略; 该文件已被 .gitignore 忽略)
"""
import json
import os
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
KEY_FILE = os.path.join(BASE, "data", "deepseek_key.txt")
API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"


def load_key():
    k = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if k:
        return k
    try:
        with open(KEY_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    return line
    except Exception:
        pass
    return ""


def available():
    return bool(load_key())


def chat(user_prompt, system=None, max_tokens=900, timeout=90):
    """调用 DeepSeek 对话接口; 未配置 Key 或调用失败返回 None"""
    key = load_key()
    if not key:
        return None
    if system is None:
        system = ("你是严谨的中文足球数据分析助手。请基于我给出的统计事实客观复盘，"
                  "不要编造数据；指出问题并给可执行的改进建议，语气平和，篇幅精炼(300字内)。")
    payload = {
        "model": MODEL,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user_prompt}],
        "temperature": 0.3,
        "max_tokens": max_tokens,
        "stream": False,
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        API_URL, data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + key})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]
    except Exception:
        return None
