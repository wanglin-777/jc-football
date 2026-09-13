# -*- coding: utf-8 -*-
"""
自动联网情报 (web_intel)
========================
目的: 自动搜集每场比赛的"近期状态 / 伤停 / 动机(战意)"信息,
      供「做胆核验」和「串关规避」使用, 替代原来只能手动录入的 extra_intel.json。

流程(全部在你本机进行, 云端 GitHub 不参与):
  1) 用「头条搜索」按 "联赛 主队 客队 伤停 首发 前瞻" 检索, 抽取含关键词的正文片段;
  2) 片段交给 DeepSeek 归纳成一句话情报 + 风险档 + 微调值(adj, ±1 以内);
  3) 结果按天缓存到 data/web_intel.json, 同一天重复重建网页不再重复请求。

诚实标注: 搜索来源为公开网页摘要, 可能存在过期/无关内容;
         情报只作"核验与提示"用途, 结论仍以赔率+模型为主。
"""
import json
import os
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request

import deepseek_client

# 中文 Windows 控制台是 GBK, 直接 print emoji 会崩; 统一改 UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(BASE, "data", "web_intel.json")
SOURCE_NAME = "头条搜索(自动)"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

# 关键词权重: 越靠前越优先保留
KW_STRONG = ["伤停", "伤病", "停赛", "缺阵", "受伤", "复出", "阵容", "首发", "大名单", "轮换"]
KW_MID = ["状态", "近况", "战意", "动机", "保级", "夺冠", "目标", "压力", "体能", "欧冠", "轮休"]
KW_ALL = KW_STRONG + KW_MID

# 明显无关/垃圾片段的关键词(纯赌博站、广告)
BAD = ["博彩", "彩票代购", "开户", "返水", "免费心水", "内幕", "加微信", "包赢"]


# ---------------------------------------------------------------- 抓取
def _http(url, timeout=12):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        raw = r.read()
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except Exception:
            pass
    return raw.decode("utf-8", "replace")


def _plain(html):
    t = re.sub(r"<script.*?</script>|<style.*?</style>|<!--.*?-->", " ",
               html, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = (t.replace("&nbsp;", " ").replace("&amp;", "&")
          .replace("&quot;", '"').replace("&gt;", ">").replace("&lt;", "<"))
    t = re.sub(r"&#x?[0-9a-fA-F]+;", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _windows(text, names, span=130, limit=10):
    """抽含"队名 + 情报关键词"的正文窗口, 去重并按关键词价值排序"""
    out = []
    for m in re.finditer("|".join(KW_ALL), text):
        seg = text[max(0, m.start() - span):m.start() + span].strip()
        if len(seg) < 40:
            continue
        if not any(n and n in seg for n in names):
            continue
        if any(b in seg for b in BAD):
            continue
        if "头条搜索 搜索 综合" in seg or "大家都在搜" in seg:
            continue
        if any(seg[:30] in o or o[:30] in seg for o in out):
            continue
        out.append(seg)

    def score(s):
        v = 0
        for i, k in enumerate(KW_STRONG):
            if k in s:
                v += 100 - i
        for i, k in enumerate(KW_MID):
            if k in s:
                v += 40 - i
        return v

    out.sort(key=score, reverse=True)
    return out[:limit]


def search_snippets(league, home, away, budget_s=None):
    """返回该场的候选情报片段(已过滤/去重), 失败返回 []"""
    names = [home, away, home[:2], away[:2]]
    out = []
    queries = [f"{league} {home} {away} 伤停 首发 前瞻",
               f"{home} {away} 战意 动机 状态 近况"]
    for q in queries:
        if budget_s is not None and budget_s <= 0:
            break
        t0 = time.time()
        try:
            html = _http("https://so.toutiao.com/search?keyword="
                         + urllib.parse.quote(q))
            out += _windows(_plain(html), names)
        except Exception:
            pass
        if budget_s is not None:
            budget_s -= (time.time() - t0)
        if len(out) >= 8:          # 够了就不再补第二条query
            break
        time.sleep(1.0)
    # 全局再去重
    uniq = []
    for s in out:
        if not any(s[:30] in o or o[:30] in s for o in uniq):
            uniq.append(s)
    return uniq[:8]


# ---------------------------------------------------------------- 缓存
def _load_cache():
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save_cache(d):
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


def get(day, num_str):
    """取某天某场的自动情报(dict|None)"""
    return (_load_cache().get(str(day)) or {}).get(num_str)


def get_any(num_str):
    """按场次号跨天查找(比赛日期可能与销售日不同, 如次日凌晨场)"""
    d = _load_cache()
    for k in sorted(d.keys(), reverse=True):
        it = (d.get(k) or {}).get(num_str)
        if it:
            return it
    return None


# ---------------------------------------------------------------- AI 归纳
SYS = ("你是严谨的中文足球赛前情报整理助手。只能依据我给出的搜索摘要归纳, "
       "不得编造球员名或事实; 信息不足时必须直说。只输出 JSON, 不要解释。")

PROMPT_TPL = """下面是今天 {n} 场竞彩比赛, 每场给了若干条"公开网页搜索摘要"(可能有噪音或过期内容)。

请逐场归纳赛前情报, 输出严格 JSON:
{{"items":[{{"num":"场次号","level":"充分|一般|不足",
  "state":"近期状态一句(空则空串)","absence":"伤停/停赛情况一句(无明确信息则空串)",
  "motive":"动机/战意一句(无则空串)","risk":"低|中|高",
  "adj":0,"note":"≤40字给用户的结论(如'主队两连败且中场双伤停, 谨慎')"}}]}}

要求:
- level=充分: 摘要里明确写到了该场状态与伤停; 一般: 只有状态或只有交锋/排名; 不足: 摘要与该场无关或没有可用信息。
- risk 指"对本场热门方而言的冷门风险", 依据摘要中的伤停/轮换/动机信息, 无信息给低。
- adj 为对主队的微调, 只能是 -1, -0.5, 0, 0.5, 1 之一(利好主队为正); level=不足 时 adj 必须为 0。
- 绝对不要输出球员名以外编造的内容, 摘要没提的就留空。

比赛与摘要:
{body}
"""


def _ai_summarize(rows, chunk=8):
    """rows: [{num, league, home, away, snips:[...]}] -> {num: item}"""
    got = {}
    for i in range(0, len(rows), chunk):
        part = rows[i:i + chunk]
        body = []
        for r in part:
            body.append(f"[{r['num']}] {r['league']} {r['home']} vs {r['away']}")
            for s in r["snips"]:
                body.append("  - " + s[:260])
        prompt = PROMPT_TPL.format(n=len(part), body="\n".join(body))
        txt = deepseek_client.chat(prompt, system=SYS, max_tokens=2000, timeout=150)
        if not txt:
            continue
        m = re.search(r"\{.*\}", txt, re.S)
        if not m:
            continue
        try:
            data = json.loads(m.group(0))
        except Exception:
            continue
        for it in data.get("items", []):
            num = str(it.get("num", "")).strip()
            if not num:
                continue
            try:
                adj = float(it.get("adj", 0) or 0)
            except (TypeError, ValueError):
                adj = 0.0
            lv = str(it.get("level", "")).strip()
            it["adj"] = 0.0 if lv == "不足" else max(-1.0, min(1.0, adj))
            it["risk"] = it.get("risk") if it.get("risk") in ("低", "中", "高") else "低"
            it["num"] = num
            got[num] = it
    return got


def _note_text(it):
    """把 AI 归纳拼成一句话, 供页面/核验使用"""
    bits = [x for x in (it.get("state"), it.get("absence"), it.get("motive"))
            if x and str(x).strip()]
    head = "/".join(str(b).strip() for b in bits)
    tail = str(it.get("note") or "").strip()
    txt = " · ".join(x for x in (head, tail) if x)
    if not txt:
        txt = "自动检索未获得有效情报"
    return txt[:160]


# ---------------------------------------------------------------- 主入口
def ensure(matches, day=None, force=False, budget_s=150, verbose=True):
    """
    为当天比赛补齐自动情报(带缓存)。matches: 官方场次 list(含 num_str/league_abb/home/away)。
    返回 {num_str: item}
    """
    day = str(day or (matches[0].get("date") if matches else ""))[:10] or None
    if not day:
        return {}
    cache = _load_cache()
    day_map = cache.get(day) or {}
    todo = []
    for m in matches:
        num = m.get("num_str")
        if not num:
            continue
        if num in day_map and not force:
            continue
        todo.append(m)
    if not todo:
        return day_map
    if not deepseek_client.available():
        if verbose:
            print("⚠ 未配置 DeepSeek Key, 跳过情报归纳(只做检索不落库)")
        return day_map

    t0 = time.time()
    rows = []
    for m in todo:
        if time.time() - t0 > budget_s:
            break
        snips = search_snippets(m.get("league_abb") or "", m.get("home") or "",
                                m.get("away") or "")
        if not snips:
            continue
        rows.append({"num": m["num_str"], "league": m.get("league_abb") or "",
                     "home": m.get("home") or "", "away": m.get("away") or "",
                     "snips": snips})
    if verbose:
        print(f"🌐 联网情报: 检索 {len(todo)} 场, 命中 {len(rows)} 场")

    got = _ai_summarize(rows) if rows else {}
    for r in rows:
        it = got.get(r["num"])
        if not it:
            continue
        it["src"] = SOURCE_NAME
        it["note_full"] = _note_text(it)
        it["snips"] = r["snips"][:3]
        day_map[r["num"]] = it
    cache[day] = day_map
    keep = sorted(cache.keys())[-7:]           # 只留最近 7 天, 控制体积
    cache = {k: cache[k] for k in keep}
    _save_cache(cache)
    if verbose:
        print(f"🌐 联网情报完成: 本轮新增 {len([r for r in rows if r['num'] in day_map])} 场")
    return day_map


if __name__ == "__main__":
    import sys
    sys.path.insert(0, BASE)
    from source import fetch_today
    t = fetch_today(force=False)
    ms = t.get("matches", [])[:6]
    print(json.dumps(ensure(ms, day=t.get("date"), force=True, budget_s=90),
                     ensure_ascii=False, indent=1)[:2000])
