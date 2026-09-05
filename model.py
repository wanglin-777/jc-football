# -*- coding: utf-8 -*-
"""
胜平负概率模型
==============
两类信息源融合:
  1) 泊松比分模型: 由两队近期攻防强度(近期进球/失球, 主客场修正, 近期加权)
     推算 λ主/λ客 -> 枚举比分 -> P(主胜)/P(平)/P(客胜)
  2) 官方赔率隐含概率(去掉庄家水分) -> 市场先验

当历史情报充分(两队近况场次多)时, 加大模型权重;
当缺少历史情报时, 完全退化为官方赔率(诚实标注来源)。
另支持 extra_intel 中的 +/- 修正(手动情报: 伤停/转会/教练/战意/热度等),
以很小幅度微调概率并反映在理由文案中。

纯标准库实现(不依赖 scipy), 便于离线运行。
"""
import math

from config import MAX_PROB_PICK, N_RECENT, RECENT_DECAY

# 近期场次对"可信任度"的权重曲线: 场次越多, 历史模型占比越高
# 说明: 欧洲主流联赛 9 月仅开赛数轮, 近期样本偏小; 官方赔率(市场共识)是更强先验,
#       因此历史模型的权重刻意压低, 只做温和修正, 避免小样本导致的过度自信。
HIST_WEIGHT_MAX = 0.42        # 历史情报充分时的最大模型权重
HIST_GAMES_FULL = 9           # 达到该场次(每队)视为充分
HIST_GAMES_MIN = 3            # 低于该场次基本不用历史模型


def poisson_pmf(k, lam):
    """泊松概率质量函数 P(X=k)"""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * lam ** k / math.factorial(k)


def score_matrix_p(home_lam, away_lam, max_goals=10):
    """独立泊松枚举比分矩阵, 返回 P(主胜/平/客胜)"""
    ph = [[poisson_pmf(i, home_lam) for i in range(max_goals + 1)]]
    pa = [poisson_pmf(j, away_lam) for j in range(max_goals + 1)]
    p_h = p_d = p_a = 0.0
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            p = ph[0][i] * pa[j]
            if i > j:
                p_h += p
            elif i == j:
                p_d += p
            else:
                p_a += p
    # 少量平局补偿(平局在真实足球中略高于独立泊松假设) -> 温和向平局挪一点
    total = p_h + p_d + p_a
    if total <= 0:
        return 0.34, 0.32, 0.34
    p_h, p_d, p_a = p_h / total, p_d / total, p_a / total
    draw_boost = 0.03
    p_h -= draw_boost / 2
    p_a -= draw_boost / 2
    p_d += draw_boost
    return p_h, p_d, p_a


def implied_from_odds(o_h, o_d, o_a):
    """官方赔率 -> 去水分后的市场隐含概率"""
    if not (o_h and o_d and o_a):
        return None
    inv = [1.0 / o_h, 1.0 / o_d, 1.0 / o_a]
    s = sum(inv)
    if s <= 0:
        return None
    return [x / s for x in inv]      # [主胜, 平, 客胜]


def _wavg(games, key, is_home=None):
    """按近期衰减权重求均值。games: [{...}] 已按日期从近到远。"""
    wsum = 0.0
    num = 0.0
    for idx, g in enumerate(games):
        if is_home is not None and g.get("is_home") != is_home:
            continue
        w = RECENT_DECAY ** idx
        v = g.get(key)
        if v is None:
            continue
        wsum += w * v
        num += w
    return (wsum / num) if num > 0 else None


def poisson_lambdas(feat):
    """
    由情报特征求 λ主/λ客。
    用「近 N 场主客分离的攻防率」对全场均值做比例缩放:
      λ主 = 联赛主队场均进球 × 主队进攻系数 × 客队客场防守系数
    系数 = 该队近期(相应主客)场均进球/失球 除以 全场相应基线。
    数据不足时回退到总体/1.0。
    """
    base_h = feat.get("base_home_goals") or 1.55   # 联赛主队场均进球基线
    base_a = feat.get("base_away_goals") or 1.15   # 联赛客队场均进球基线

    # 主队: 进攻(主场进球率) / 防守(主场失球率)
    h_att = feat.get("home_home_gf")              # 主队近N场主场场均进球
    h_att_overall = feat.get("home_gf")
    h_def = feat.get("home_home_ga")              # 主队近N场主场场均失球
    h_def_overall = feat.get("home_ga")
    # 客队
    a_att = feat.get("away_away_gf")
    a_att_overall = feat.get("away_gf")
    a_def = feat.get("away_away_ga")
    a_def_overall = feat.get("away_ga")

    def coef(team_val, overall_val, base):
        """比例系数: 优先主客样本, 样本不足向总体收缩; 收缩后温和放大/缩小"""
        v = team_val or overall_val
        if v is None:
            return 1.0
        raw = v / max(base, 0.1)
        raw = max(0.65, min(1.4, raw))     # 防极端值
        return 1.0 + 0.75 * (raw - 1.0)    # 向 1 收缩 25%, 降低噪声

    home_attack = coef(h_att, h_att_overall, base_h)
    home_defence = coef(h_def, h_def_overall, base_a)
    away_attack = coef(a_att, a_att_overall, base_a)
    away_defence = coef(a_def, a_def_overall, base_h)

    lam_home = base_h * home_attack * away_defence
    lam_away = base_a * away_attack * home_defence

    # 用官方让球盘做轻微校正: 若让球很深说明市场认为主队更强, 微调 λ差
    gl = feat.get("hhad_gl")
    if gl is not None and gl != 0 and abs(gl) <= 2.5:
        # 负=主队让球(市场看主强)
        adj = -gl * 0.10
        lam_home = max(0.1, lam_home + adj)
        lam_away = max(0.1, lam_away - adj)
    # 全局 λ 上限, 防止单一爆冷比分把概率推过头
    lam_home = max(0.25, min(3.8, lam_home))
    lam_away = max(0.25, min(3.8, lam_away))
    return lam_home, lam_away


def history_weight(feat):
    """根据两队有效近期场次数给出 [0..1] 历史模型权重"""
    n = min(feat.get("home_games", 0), feat.get("away_games", 0))
    if n <= 0:
        return 0.0
    w = (n - HIST_GAMES_MIN) / (HIST_GAMES_FULL - HIST_GAMES_MIN)
    return max(0.0, min(1.0, w)) * HIST_WEIGHT_MAX


def _rank_num(s):
    """把 "[英超7]" / "[7]" / "英超7" 解析成排名数字 7; 解析不了返回 None"""
    import re as _re
    if not s:
        return None
    m = _re.search(r"(\d+)", str(s))
    return int(m.group(1)) if m else None


def upset_analysis(feat, probs):
    """
    爆冷分析: 对已算好的胜平负概率 probs=[P主胜,P平,P客胜] 判断:
      - 大热方(主胜/客胜里盘口隐含概率高者; 无明显大热时提示)
      - 大热不胜概率(防冷=平+负), 直接输(被爆冷)概率
      - 与盘口隐含对比的"爆冷风险"等级 + 大概原因(状态/主客/交锋/体能/排名/情报等)
    返回 dict, 字段见代码。
    """
    labels = ["主胜", "平", "客胜"]
    sides = ["home", "away"]
    mkt = implied_from_odds(feat.get("had_h"), feat.get("had_d"), feat.get("had_a"))
    m = mkt if mkt else probs
    # 大热 = 主胜/客胜 中市场概率更高的一方(平局不算热门方向)
    fav = 0 if m[0] >= m[2] else 2
    other = 2 if fav == 0 else 0
    fav_odds = [feat.get("had_h"), feat.get("had_d"), feat.get("had_a")][fav]
    hot = bool(fav_odds and fav_odds <= 2.20)   # 赔率≤2.2 才算"大热"(优势较明显)

    p_nowin = 1.0 - probs[fav]            # 大热不胜(平或输)
    p_draw = probs[1]
    p_uw = probs[other]                   # 直接输(被爆冷胜)
    m_nowin = 1.0 - m[fav] if mkt else p_nowin
    edge = p_nowin - m_nowin              # 模型比盘口更担心爆冷的幅度

    # 风险分级(以大热不胜概率为尺, 高≈接近半数翻车可能, 中≈需要留神)
    if not hot:
        risk = "低"
    elif p_nowin >= 0.46:
        risk = "高"
    elif p_nowin >= 0.34:
        risk = "中"
    else:
        risk = "低"
    if hot and edge >= 0.05 and risk != "高":
        risk = {"低": "中", "中": "高"}.get(risk, risk)

    fav_team = feat.get("home") if fav == 0 else feat.get("away")
    opp_team = feat.get("away") if fav == 0 else feat.get("home")

    # ---------- 收集爆冷的大概原因 ----------
    reasons = []
    def gv(key):
        return feat.get(key)

    if not hot:
        reasons.append(f"无明显大热(大热方赔率{fav_odds}较高), 双方接近, 爆冷概念弱")
    else:
        if edge >= 0.05:
            reasons.append(f"模型判断比盘口更担心翻车({p_nowin:.0%} vs 盘口{m_nowin:.0%})")
        # 大热方自己的状态/属性
        fw = gv("home_win_w") if fav == 0 else gv("away_win_w")
        fga = gv("home_ga") if fav == 0 else gv("away_ga")
        frest = gv("home_rest") if fav == 0 else gv("away_rest")
        frk = _rank_num(gv("home_rank")) if fav == 0 else _rank_num(gv("away_rank"))
        ow = gv("away_win_w") if fav == 0 else gv("home_win_w")
        ogf = gv("away_gf") if fav == 0 else gv("home_gf")
        ork = _rank_num(gv("away_rank")) if fav == 0 else _rank_num(gv("home_rank"))
        if fw is not None and fw < 0.40:
            reasons.append(f"{fav_team}近期胜率仅{fw:.0%}, 状态不稳")
        if ow is not None and ow >= 0.50:
            reasons.append(f"对手{opp_team}近期状态好(胜率{ow:.0%})")
        if fga is not None and fga >= 1.50:
            reasons.append(f"{fav_team}近期防守一般(场均失{fga:.1f})")
        if ogf is not None and ogf >= 1.60:
            reasons.append(f"{opp_team}攻击不错(场均进{ogf:.1f})")
        if frk is not None and ork is not None and abs(frk - ork) <= 3:
            reasons.append(f"双方排名接近(差≤3), 实力差距不大")
        if frest is not None and frest <= 3:
            reasons.append(f"{fav_team}仅休息{frest}天(赛程紧)")
        # 交锋(记录为"主队角度")
        import re as _re
        hm = _re.search(r"(\d+)胜(\d+)平(\d+)负", feat.get("h2h_summary") or "")
        if hm:
            w, d, l = int(hm.group(1)), int(hm.group(2)), int(hm.group(3))
            tot = w + d + l
            if tot >= 2:
                fav_ok = (w >= l) if fav == 0 else (l >= w)
                if not fav_ok:
                    reasons.append(f"近{tot}次交锋{fav_team}不占优({w}胜{d}平{l}负, 主队视角)")
        if feat.get("data_quality") in ("odds_only", "partial") and risk != "低":
            reasons.append("两队历史情报不足(仅盘口/部分), 结果不确定性高")
    if feat.get("intel_note"):
        reasons.append(f"人工情报提示: {feat['intel_note']}")
    if hot and not reasons:
        if risk in ("中", "高"):
            reasons.append(f"大热方赔率仅@{fav_odds}, 优势不悬殊, 翻车属正常波动")
        else:
            reasons.append("无明显爆冷信号(大热状态/盘口正常)")

    return {
        "fav": labels[fav], "fav_team": fav_team, "fav_odds": fav_odds,
        "hot": hot,
        "no_win_p": round(p_nowin, 4),      # 防冷: 大热不胜
        "draw_p": round(p_draw, 4),         # 其中: 平
        "upset_win_p": round(p_uw, 4),      # 直接输(被爆冷胜)
        "mkt_no_win_p": round(m_nowin, 4),
        "edge": round(edge, 4),
        "risk": risk,
        "reasons": reasons,
    }



def predict(feat):
    """
    输入特征 dict(见 scout.build_feature), 输出:
      {"home": P主胜, "draw": P平, "away": P客胜,
       "pick": "主胜/平/客胜", "pick_p": float, "pick_odds": float,
       "source": "模型+赔率"|"仅赔率", "note": 一句话理由}
    """
    probs = None
    source = "仅赔率"
    hw = history_weight(feat)
    if hw > 0:
        lh, la = poisson_lambdas(feat)
        mp = score_matrix_p(lh, la)
        ip = implied_from_odds(feat.get("had_h"), feat.get("had_d"), feat.get("had_a"))
        if ip:
            probs = [hw * mp[i] + (1 - hw) * ip[i] for i in range(3)]
            source = "模型+赔率"
        else:
            probs = list(mp)
            source = "模型(无赔率)"
    else:
        ip = implied_from_odds(feat.get("had_h"), feat.get("had_d"), feat.get("had_a"))
        if ip:
            probs = list(ip)
        else:
            # 实在什么都没有: 中性先验
            probs = [0.34, 0.32, 0.34]

    # 手动情报微调: +-0.02 量级
    adj = feat.get("intel_adj", 0.0)   # >0 利好主队, <0 利好客队
    if adj:
        s = min(0.06, abs(adj) * 0.02)
        if adj > 0:
            probs[0] += s; probs[1] -= s * 0.4; probs[2] -= s * 0.6
        else:
            probs[2] += s; probs[1] -= s * 0.4; probs[0] -= s * 0.6
    total = sum(probs)
    probs = [max(0.001, p) / total for p in probs]

    labels = ["主胜", "平", "客胜"]
    idx = max(range(3), key=lambda i: probs[i])
    pick = labels[idx]
    pick_p = probs[idx]
    pick_odds = [feat.get("had_h"), feat.get("had_d"), feat.get("had_a")][idx]
    return {
        "home": round(probs[0], 4), "draw": round(probs[1], 4), "away": round(probs[2], 4),
        "pick": pick, "pick_p": round(pick_p, 4), "pick_odds": pick_odds,
        "source": source,
        "upset": upset_analysis(feat, probs),
    }
