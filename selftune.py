# -*- coding: utf-8 -*-
"""
模型自调优 (selftune.py)
========================
把"复盘经验"真正反馈到下次预测: 每次刷新得到最新已核验结果后,
自动计算"预测概率 vs 实际命中"的偏差, 形成每选项(主胜/平/客胜)的温和校准量,
可选再由 DeepSeek 复核/微调, 写成 data/model_tune.json。

model.predict() 在给出最终概率前读取该文件并应用(幅度被严格限制, 只做"适当调整"):
  - 某一方向长期被高估(命中率 < 平均预测概率) -> 下次对该方向轻微降权
  - 某一方向长期被低估 -> 轻微加权
  - 每次只挪 1~4 个百分点, 且与上一次平滑, 避免对单日小样本过拟合。
"""
import json
import os
import re

from config import DATA_DIR

TUNE_FILE = os.path.join(DATA_DIR, "model_tune.json")
LABELS = ["主胜", "平", "客胜"]
# 校准幅度上限 & 平滑系数(求稳)
CLAMP = 0.03          # 单方向单次最多挪 3 个百分点
KAPPA = 0.4           # 把观测偏差打 4 折再施加(避免过度反应)
SMOOTH_OLD = 0.5      # 与旧值平滑的比例(旧)
SMOOTH_NEW = 0.5      # (新)
MIN_N_PER = 10        # 某方向至少核验 N 场才调该方向
MIN_N_TOTAL = 12      # 总核验不足则不启用校准(样本太小时宁可不动)
AI_CLAMP = 0.02       # AI 建议的单方向幅度上限(比数据校准更保守)

_LOCK = {}


def load():
    """读取当前调参(无则返回默认空档)"""
    if "t" not in _LOCK:
        try:
            with open(TUNE_FILE, encoding="utf-8") as f:
                t = json.load(f)
            if not isinstance(t, dict):
                t = {}
        except Exception:
            t = {}
        _LOCK["t"] = t
    return _LOCK["t"]


def _clear():
    _LOCK.pop("t", None)


def apply_tune(probs):
    """在给出最终概率前应用校准(返回新的三向概率列表, 已归一化)"""
    try:
        t = load()
        if not t.get("enabled", True) or not t.get("sample"):
            return probs
        cal = t.get("calib_add") or {}
        comp = {lab: i for i, lab in enumerate(LABELS)}
        out = list(probs)
        for lab, i in comp.items():
            d = cal.get(lab, 0.0) or 0.0
            if d:
                out[i] = max(0.001, out[i] + d)
        s = sum(out)
        return [max(0.001, p) / s for p in out]
    except Exception:
        return probs


def _fingerprint(vdata):
    days = set()
    verified = hits = 0
    for d in vdata:
        days.add(d["date"])
        for r in d["rows"]:
            if r.get("hit") is not None:
                verified += 1
                hits += 1 if r["hit"] else 0
    return days, verified, hits


def _compute_calib(vdata):
    """由已核验记录算每方向的 (n, 平均预测概率, 命中率)"""
    agg = {}
    for d in vdata:
        for r in d["rows"]:
            if r.get("hit") is None:
                continue
            pick = r.get("pick")
            if pick not in LABELS:
                continue
            pp = r.get("probs") or []
            idx = LABELS.index(pick)
            a = pp[idx] if len(pp) == 3 else None
            e = agg.setdefault(pick, [0, 0.0, 0])
            e[0] += 1
            if a is not None:
                e[1] += a
            if r["hit"]:
                e[2] += 1
    out = {}
    total_n = 0
    for lab, (n, sa, h) in agg.items():
        total_n += n
        out[lab] = {"n": n, "avg_p": (sa / n) if n else None, "rate": h / n}
    return out, total_n


def _summarize(stats, total):
    lines = [f"已核验 {total} 场。"]
    for lab, s in stats.items():
        if s["avg_p"] is not None:
            lines.append(f"{lab}: 预测均 {s['avg_p']:.0%} / 实际 {s['rate']:.0%} (n={s['n']})")
    return "；".join(lines)


def update_from_verify(vdata, ai=None):
    """
    用最新已核验数据刷新 model_tune.json(每个销售日有新结果时更新)。
    ai: 可选函数 ai(prompt)->str, 供 DeepSeek 复核微调(只在新的一天首次出现时调用一次)。
    返回最新 tune(dict), 供页面展示。
    """
    if not vdata:
        return load()
    days, verified, hits = _fingerprint(vdata)
    stats, total = _compute_calib(vdata)
    old = load()

    # 1) 数据驱动校准量
    cand = {}
    for lab in LABELS:
        s = stats.get(lab)
        if not s or s["n"] < MIN_N_PER:
            continue
        over = (s["avg_p"] or 0.0) - s["rate"]   # >0 表示该方向被高估
        add = -over * KAPPA
        cand[lab] = max(-CLAMP, min(CLAMP, add))

    # 2) 与旧值平滑
    cal = {}
    for lab in LABELS:
        c = cand.get(lab, 0.0)
        o = (old.get("calib_add") or {}).get(lab, 0.0) or 0.0
        if old.get("sample"):
            c = o * SMOOTH_OLD + c * SMOOTH_NEW
        if abs(c) < 0.003:      # 小于 0.3% 视为噪音, 归零
            c = 0.0
        cal[lab] = round(max(-CLAMP, min(CLAMP, c)), 4)

    # 样本太少: 不启用自动校准, 保留旧档但标注
    if total < MIN_N_TOTAL:
        if old.get("sample") and old.get("calib_add"):
            return old   # 沿用上一次(有依据)的校准, 不动
        t = dict(old)
        t.update({"sample": 0, "note": "核验样本过少, 暂不自动校准",
                  "based_on": {"days": sorted(days)[-1:]}})
        _write(t)
        return t

    note = _summarize(stats, total)
    ai_used = False
    ai_note = ""
    # 3) DeepSeek 复核: 仅当出现"新的一天"的结果时才调用, 控制成本
    last_day = max(days)
    if ai is not None and last_day > (old.get("last_ai_day") or ""):
        try:
            lines = [note,
                     "请基于以上'预测概率 vs 实际命中'做一次简短复盘, 并输出一行 JSON:",
                     '{"calib_add":{"主胜":x,"平":y,"客胜":z},"note":"一句话"}',
                     "要求: x/y/z 为十进制小数, 表示下一期对这三维整体概率的微调幅度, "
                     f"每项必须在 [-{AI_CLAMP}, {AI_CLAMP}] 内, 无明显依据就填 0; "
                     f"样本约 {total} 场偏小, 不要过度反应; 只需输出 JSON, 不要额外文字。"]
            txt = ai("\n".join(lines))
            if txt:
                m = re.search(r"\{.*\}", txt, re.S)
                if m:
                    obj = json.loads(m.group(0))
                    ac = obj.get("calib_add") or {}
                    for lab, v in ac.items():
                        if lab in cal and isinstance(v, (int, float)):
                            v = max(-AI_CLAMP, min(AI_CLAMP, float(v)))
                            # AI 与数据校准各占一半, 既用 AI 经验又防其乱来
                            cal[lab] = round(0.6 * cal[lab] + 0.4 * v, 4)
                    ai_note = str(obj.get("note", ""))[:200]
                    ai_used = True
        except Exception:
            ai_used = False

    t = {
        "enabled": True,
        "updated": max(days),
        "sample": total,
        "calib_add": cal,
        "based_on": {"days": sorted(days), "verified": verified, "hits": hits},
        "last_ai_day": max(days) if (ai_used or old.get("last_ai_day")) else old.get("last_ai_day", ""),
        "ai_used": ai_used,
        "ai_note": ai_note,
        "note": note,
    }
    _write(t)
    return t


def _write(t):
    try:
        old = load()
        if old.get("calib_add") == t.get("calib_add") and old.get("sample") == t.get("sample"):
            # 内容无实质变化则不落盘, 避免每次刷新产生 git 噪音
            _LOCK["t"] = t
            return
    except Exception:
        pass
    try:
        with open(TUNE_FILE, "w", encoding="utf-8") as f:
            json.dump(t, f, ensure_ascii=False, indent=1)
    except Exception:
        pass
    _clear()


def describe(t):
    """给页面展示的简短描述"""
    if not t or not t.get("sample"):
        return None
    parts = [f"{k}{v:+.1%}" for k, v in (t.get("calib_add") or {}).items() if v]
    s = f"基于 {t.get('sample')} 场已核验自动校准" + (f"({', '.join(parts)})" if parts else "(无显著偏差)")
    if t.get("ai_used"):
        s += " · 含 DeepSeek 复核"
    return s
