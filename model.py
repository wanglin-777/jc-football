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
    }
