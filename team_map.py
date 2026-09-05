# -*- coding: utf-8 -*-
"""
队名映射表
==========
把竞彩官方的中文队名(如"伯恩茅斯")映射到历史赛果数据源 fixturedownload
使用的英文队名(如"Bournemouth"), 以便按队归集近况。
仅覆盖已开通历史数据源的联赛(见 config.LEAGUE_FEED)。
新增球队时, 在此追加一行:  "中文名": "数据源英文名",  即可。
"""
CH_TO_EN = {
    # ---------- 英超 EPL ----------
    "纽卡斯尔": "Newcastle", "伯恩茅斯": "Bournemouth", "诺丁汉": "Nott'm Forest",
    "热刺": "Spurs", "曼城": "Man City", "考文垂": "Coventry", "布伦特": "Brentford",
    "桑德兰": "Sunderland", "富勒姆": "Fulham", "水晶宫": "Crystal Palace",
    "赫尔城": "Hull", "维拉": "Aston Villa", "埃弗顿": "Everton", "曼联": "Man Utd",
    "阿森纳": "Arsenal", "切尔西": "Chelsea", "利物浦": "Liverpool", "布莱顿": "Brighton",
    "利兹": "Leeds", "伊普斯": "Ipswich",
    # ---------- 英冠 CHA ----------
    "林肯城": "Lincoln City", "南安普敦": "Southampton", "伯明翰": "Birmingham City",
    "伍尔弗": "Wolverhampton Wanderers", "伍尔弗汉普顿": "Wolverhampton Wanderers",
    "西汉姆": "West Ham United", "斯托克城": "Stoke City",
    "诺维奇": "Norwich City", "谢菲联": "Sheffield United", "伯恩利": "Burnley",
    # ---------- 德甲 BUN ----------
    "门兴": "Borussia Mönchengladbach", "埃沃斯堡": "SV Elversberg",
    "不来梅": "SV Werder Bremen", "莱红牛": "RB Leipzig", "帕德博恩": "SC Paderborn 07",
    "弗赖堡": "Sport-Club Freiburg", "霍芬海姆": "TSG Hoffenheim",
    "多特蒙德": "Borussia Dortmund", "勒沃库森": "Bayer 04 Leverkusen",
    "柏林联合": "1. FC Union Berlin", "沙尔克04": "FC Schalke 04", "拜仁": "FC Bayern München",
    "汉堡": "Hamburger SV", "美因茨": "1. FSV Mainz 05", "法兰克福": "Eintracht Frankfurt",
    "奥格斯堡": "FC Augsburg", "斯图加特": "VfB Stuttgart", "科隆": "1. FC Köln",
    # ---------- 荷甲 ERE ----------
    "阿贾克斯": "Ajax", "埃因霍温": "PSV", "海伦芬": "sc Heerenveen", "阿尔克马": "AZ",
    "费耶诺德": "Feyenoord", "特温特": "FC Twente", "乌德勒支": "FC Utrecht",
    # ---------- 意甲 ISA ----------
    "佛罗伦萨": "Fiorentina", "都灵": "Torino", "国际米兰": "Internazionale",
    "那不勒斯": "Napoli", "罗马": "Roma", "亚特兰大": "Atalanta",
    "弗洛西诺": "Frosinone", "威尼斯": "Venezia", "帕尔马": "Parma", "蒙扎": "Monza",
    "博洛尼亚": "Bologna", "萨索洛": "Sassuolo", "尤文图斯": "Juventus",
    "AC米兰": "Milan", "卡利亚里": "Cagliari", "莱切": "Lecce", "乌迪内斯": "Udinese",
    "拉齐奥": "Lazio", "科莫": "Como", "热那亚": "Genoa", "恩波利": "", "维罗纳": "",
    # ---------- 法甲 FR1 ----------
    "朗斯": "RC Lens", "洛里昂": "FC Lorient", "勒阿弗尔": "Havre Athletic Club",
    "布雷斯特": "Stade Brestois 29", "特鲁瓦": "Estac Troyes",
    "斯特拉斯": "RC Strasbourg Alsace", "马赛": "Olympique de Marseille",
    "巴黎FC": "Paris FC", "里尔": "LOSC Lille", "摩纳哥": "AS Monaco",
    "巴黎圣曼": "Paris Saint-Germain", "里昂": "Olympique Lyonnais",
    "雷恩": "Stade Rennais FC", "尼斯": "OGC Nice", "图卢兹": "Toulouse FC",
    "圣埃蒂安": "", "南特": "", "兰斯": "",
    # ---------- 美职 USA(如需再加) ----------
}

EN_TO_CH = {v: k for k, v in CH_TO_EN.items() if v}
