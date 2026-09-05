# -*- coding: utf-8 -*-
"""
竞彩足球·串关预测网页版 (Streamlit)
===================================
功能:
  - 概览: 当天在售场次 / 可预测场次 / 情报覆盖情况
  - 🎯 串关推荐: 五大「两串一」(串后赔率>=2.0, 按联合胜率排序)
  - 📊 全场预测: 每场胜平负概率 + 推荐选项 + 数据来源标注
  - 🔎 情报明细: 每场两队近况/交锋/让球盘/排名/手动情报(伤病转会等)
  - ⚠️ 数据来源与免责说明

运行:
    streamlit run app.py        (或双击 启动网页版.bat)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st  # noqa: E402

import model   # noqa: E402
import parlay  # noqa: E402
import scout   # noqa: E402
from sporttery import fetch_today  # noqa: E402

st.set_page_config(page_title="竞彩串关预测", page_icon="⚽", layout="wide",
                   initial_sidebar_state="expanded")

# ---------------- 数据加载(磁盘缓存, 离线可用) ----------------
def _refresh_state():
    return st.session_state.get("force_update", False)


@st.cache_data(show_spinner=False)
def load_today(force=False):
    return fetch_today(force=force)


@st.cache_data(show_spinner="正在合成两队情报并预测...")
def compute(fetch_force, with_intel):
    today = load_today(fetch_force)
    ms = today["matches"]
    feats = scout.build_features(ms)
    pred_map, ordered, preds = {}, [], []
    for f in feats:
        if f["had_h"] and f["had_d"] and f["had_a"]:
            pred_map[f["num_str"]] = model.predict(f)
    ordered = [f for f in feats if f["num_str"] in pred_map]
    preds = [pred_map[f["num_str"]] for f in ordered]
    rec = parlay.recommend(ordered, preds)
    return today, feats, pred_map, ordered, preds, rec


# ---------------- 工具函数 ----------------
def top_rows(ordered, pred_map):
    """按模型胜率降序排列"""
    return sorted(ordered, key=lambda f: pred_map[f["num_str"]]["pick_p"], reverse=True)


# ---------------- 侧边栏 ----------------
with st.sidebar:
    st.title("⚽ 竞彩串关预测")
    st.caption("基于中国体彩·竞彩足球官方数据")
    fetch_force = st.button("↻ 强制联网更新赔率", width="stretch")
    if fetch_force:
        st.session_state["force_update"] = True
        st.cache_data.clear()
        st.rerun()
    st.divider()
    st.markdown("**免责声明**")
    st.caption("本页为统计模型对历史数据与官方赔率的分析, 足球比赛存在偶然性, "
               "预测仅供参考, 不构成投注建议。请理性购彩、量力而行。")

today, feats, pred_map, ordered, preds, rec = compute(_refresh_state(), True)

# ---------------- 概览指标 ----------------
c1, c2, c3, c4 = st.columns(4)
full = sum(1 for f in feats if f.get("data_quality") == "full")
partial = sum(1 for f in feats if f.get("data_quality") == "partial")
c1.metric("在售场次", len(feats))
c2.metric("可预测(开胜平负)", len(ordered))
c3.metric("完整情报场次", full)
c4.metric("部分情报场次", partial)
st.caption(f"销售日期 {today['date']} · 模型来源: 泊松强度 + 官方赔率融合"
           f" · 未标注完整情报的场次将自动降级为『仅赔率预测』")

tab1, tab2, tab3, tab4 = st.tabs(["🎯 串关推荐", "📊 全场预测", "🔎 情报明细", "ℹ️ 说明"])

# ================= 串关推荐 =================
with tab1:
    st.subheader("五大「两串一」推荐")
    st.caption("规则: 只串两关 · 串后赔率 ≥ 2.0 · 按两场联合胜率(p₁×p₂)从高到低")
    if not rec["combos"]:
        st.warning("暂无满足条件的组合(可选场次不足/赔率不足 2)。可尝试降低稳胆门槛或补充队名数据。")
    for i, cb in enumerate(rec["combos"], 1):
        with st.container(border=True):
            cols = st.columns([1, 2, 1])
            cols[0].markdown(f"### TOP {i}")
            cols[1].markdown(f"**联合胜率 {cb['joint']:.1%}**")
            cols[2].markdown(f"**串后赔率 {cb['odds']:.2f}**")
            st.progress(min(cb["joint"], 1.0))
            for l in cb["legs"]:
                st.markdown(
                    f"**{l['num']} [{l['league']}] {l['home']} vs {l['away']}**  "
                    f"推荐【{l['pick']}】 胜率 **{l['prob']:.0%}** · 单关赔率 {l['odds']:.2f}"
                )
                with st.expander(f"查看 {l['home']} vs {l['away']} 情报", expanded=False):
                    st.markdown(f"- {l['home_summary']}")
                    st.markdown(f"- {l['away_summary']}")

# ================= 全场预测 =================
with tab2:
    st.subheader("全部场次胜平负预测")
    rows = []
    for f in top_rows(ordered, pred_map):
        pr = pred_map[f["num_str"]]
        rows.append({
            "场次": f["num_str"], "联赛": f["league_abb"],
            "对阵": f"{f['home']} vs {f['away']}",
            "推荐": pr["pick"], "概率": f"{pr['pick_p']:.0%}",
            "赔率": pr.get("pick_odds"), "数据": f.get("data_quality"),
        })
    st.dataframe(rows, width="stretch", hide_index=True)

    st.divider()
    st.markdown("**逐场深看**: 选择一场查看 胜/平/负 三向概率")
    sel = st.selectbox("选择场次", [f"{f['num_str']} {f['home']} vs {f['away']}"
                                    for f in ordered], label_visibility="collapsed")
    idx = next(i for i, f in enumerate(ordered)
               if f"{f['num_str']} {f['home']} vs {f['away']}" == sel)
    f, pr = ordered[idx], pred_map[ordered[idx]["num_str"]]
    c = st.columns(3)
    labels = [("主胜", pr["home"], "🥇"), ("平局", pr["draw"], "🤝"), ("客胜", pr["away"], "🥈")]
    for col, (lab, p, emo) in zip(c, labels):
        col.metric(f"{emo} {lab}", f"{p:.1%}")
    st.markdown(f"**推荐**: {pr['pick']} (胜率 {pr['pick_p']:.1%}) · 来源: {pr['source']}")
    st.markdown(f"- 主队: {f.get('home_summary')}")
    st.markdown(f"- 客队: {f.get('away_summary')}")
    st.markdown(f"- 交锋: {f.get('h2h_summary') or '近10场内无直接交锋记录'}")
    if f.get("intel_note"):
        st.info(f"🧠 手动情报: {f['intel_note']}")

# ================= 情报明细 =================
with tab3:
    st.subheader("每场两队情报明细")
    rows2 = []
    for f in feats:
        rows2.append({
            "场次": f["num_str"], "联赛": f["league_abb"], "对阵": f"{f['home']} vs {f['away']}",
            "主队排名": f.get("home_rank", "").strip("[]"),
            "客队排名": f.get("away_rank", "").strip("[]"),
            "让球盘": (f"{f['hhad_gl']:g}" if f.get("hhad_gl") is not None else "-"),
            "数据": f.get("data_quality"),
            "主队近况": f.get("home_summary", ""), "客队近况": f.get("away_summary", ""),
        })
    st.dataframe(rows2, width="stretch", hide_index=True, height=420)

# ================= 说明 =================
with tab4:
    st.subheader("数据来源与如何补充情报")
    st.markdown("""
**数据来源(均为免费/公开)**
1. **中国体彩·竞彩足球官方接口** — 当天在售场次、胜平负/让球赔率、联赛排名(实时真实)
2. **fixturedownload** — 英超/英冠/德甲/荷甲/意甲/法甲/美职 整季真实赛果(计算近10场状态/交锋)
3. 伤病、转会、教练、战术、战意、热度等**没有免费稳定的自动来源**, 请手动补充 ↓

**如何补充手动情报(伤停/转会/教练/战意/热度)**
在 `data/extra_intel.json` 中按模板填写(每场一条):
```json
{"matches": [
  {"num": "周六004", "home": "纽卡斯尔", "away": "伯恩茅斯",
   "adj": 1,
   "reason": "主队核心前锋复出; 客队主力中卫停赛; 主队争欧战席位战意强"}
]}
```
- `adj`: 整数 -3 ~ +3, 正数表示**利好主队**, 负数利好客队(会小幅修正概率)
- 保存后刷新页面即可生效

**扩展更多联赛/球队**
- 联赛历史源: 编辑 `config.py` 里的 `LEAGUE_FEED`
- 中文→英文队名: 编辑 `team_map.py` 里的 `CH_TO_EN`
- 若某联赛暂无历史源, 该联赛场次会自动标注「仅赔率预测」, 功能不受影响
""")
    st.warning("重要提示: 本工具是统计分析工具, 不是中奖保证。请理性购彩, 未成年人不得购彩。")
