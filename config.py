# -*- coding: utf-8 -*-
"""
足彩竞彩预测 - 全局配置
========================
集中管理路径、官方接口、联赛历史数据源注册表与推荐参数。
"""
import os

# ---------- 目录 ----------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
INTEL_FILE = os.path.join(DATA_DIR, "extra_intel.json")   # 手动补充情报(伤病/转会/教练等)

for _d in (DATA_DIR, CACHE_DIR):
    os.makedirs(_d, exist_ok=True)

# ---------- 竞彩官方数据接口(实测可用, 返回当天可售真实数据) ----------
SPORTTERY_BASE = "https://webapi.sporttery.cn/gateway/jc/football"
SPORTTERY_MATCH_URL = (
    SPORTTERY_BASE
    + "/getMatchCalculatorV1.qry?poolCode=hhad,had&channel=c"
)
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.sporttery.cn/",
    "Connection": "close",
}

# ---------- 联赛历史赛果注册表 ----------
# sporttery 的联赛编码 -> (fixturedownload 当前赛季 feed slug, 联赛中文名)
# slug 探测结论(2026-09-05):
#   已确认可用: EPL/CHA/BUN/ERE
#   其余联赛若在 fixturedownload 上 slug 正确, 填入后即可自动获得该联赛全部历史赛果
#   slug 规则形如 <league>-2026(以开赛年份结尾); 若找不到对应联赛可删掉该行, 系统会自动降级为"仅赔率预测"
LEAGUE_FEED = {
    "EPL": ("epl-2026", "英超"),
    "CHA": ("championship-2026", "英冠"),
    "BUN": ("bundesliga-2026", "德甲"),
    "ERE": ("eredivisie-2026", "荷甲"),
    "ISA": ("serie-a-2026", "意甲"),
    "FR1": ("ligue-1-2026", "法甲"),
    "LLA": ("la-liga-2026", "西甲"),
    "POR": ("primeira-liga-2026", "葡超"),
    "FR2": ("ligue-2-2026", "法乙"),
    "USA": ("mls-2026", "美职"),
    # fixturedownload 暂缺的联赛(探测不到slug): 挪超/巴甲/日职/韩职/瑞超/沙职等
    # 若日后有可用源, 按 "联赛码": (slug, 中文名) 追加即可。
}
# sporttery 联赛 abb 名 -> league_code(有些接口只给 abb 中文名, 这里统一口径)
LEAGUE_ABB_TO_CODE = {
    "英超": "EPL", "英冠": "CHA", "德甲": "BUN", "荷甲": "ERE",
    "西甲": "LLA", "意甲": "ISA", "法甲": "FR1",
    "葡超": "POR", "挪超": "NOR", "沙职": "SAP", "巴甲": "BRA",
    "日职": "JPN", "韩职": "KOR", "瑞超": "SWE", "苏超": "SCO",
    "比甲": "BEL", "土超": "TUR", "美职": "USA", "奥超": "AUT",
    "瑞超": "SWI", "德乙": "BU2", "英甲": "LE1", "法乙": "FR2",
}

# ---------- 推荐/模型参数 ----------
N_RECENT = 10          # 每队取最近 N 场做状态分析(用户要求约10场)
RECENT_DECAY = 0.88    # 越近权重越高: weight = decay ** 场次间隔
N_RECOMMEND = 5        # 串关推荐组数(用户要5组)
COMBO_MIN_ODDS = 2.0   # 串后最低赔率(用户要求 >= 2)
COMBO_LEGS = 2         # 只串两关
MIN_PROB_PICK = 0.50   # 单场入选推荐的最低模型胜率(可调; 过高会导致可选场太少)
MAX_PROB_PICK = 0.92   # 过高的模型胜率视为异常, 防止把"必死盘"当稳胆
