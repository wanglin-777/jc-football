# ⚽ 竞彩足球 · 两串一预测

基于中国体彩·竞彩足球数据的 **胜平负概率分析 + 两串一推荐**。

- 🌐 **公开网页(云端)**：托管在 GitHub Pages，**任何时间、任何网络**都能打开
- 🔁 **每 4 小时自动更新**：由你电脑上的定时任务抓取竞彩最新数据并推送，网页随之刷新
- 📊 每场 **胜/平/负 概率** + **5 组「两串一」**（只串两关 · 串后赔率≥2 · 按联合胜率排序）

> ⚠️ 本工具是对历史数据与赔率的统计分析，仅供研究参考，**不构成投注建议**；
> 足球充满偶然性，请理性购彩、量力而行，未成年人不得购彩。

---

## 🌐 网页地址

**https://wanglin-777.github.io/jc-football/**

打开后：**🎯 串关推荐**（五大两串一）· 全场预测 · 单场稳胆池，数据更新时间与来源显示在顶部。

> ⚠️ 首次使用请在仓库 **Settings → Pages** 设置：Source = **Deploy from a branch**，
> Branch = `main`，folder = `/docs`。详见 `部署到GitHub.md`。

---

## 🔁 为什么需要电脑"定时更新"？

竞彩数据来自**中国体彩官网**，它**封锁境外 IP**（海外返回 HTTP 567），GitHub 的云端机器读不到。
所以采用分工：
- **网页由 GitHub 云端承载** → 随时打开（不受影响）
- **数据由你的电脑每 4 小时抓取并推送** → 电脑开机时自动完成（每次只需几秒）

> 电脑关机时网页仍能打开，只是数据停在最近一次抓取。

---

## � 数据存哪（约定）

**GitHub = 唯一权威数据源；本机只保留“重要”的：程序代码 + DeepSeek Key + 定时任务。**

- 所有比赛数据（当天快照 / 每赛季赛果 / 每日预测账本 / CSV / 网页）都存/推送到 GitHub：
  - `data/today_matches.*` 当天快照 · `data/history/` 每日账本 · `data/history_csv/` 可读表
  - `data/cache/` 整季赛果备份 · `docs/` 网页
- 本机 `data/` 只是 Git 仓库的**本地镜像**，并非重要数据：几 MB、删了也不怕，
  随时用 `从GitHub同步数据到本机.bat` 从 GitHub 拉回（`git reset --hard origin/main`）。
- 真正留本机不传的只有：`data/deepseek_key.txt`（机密）等本地私有文件。

> 结论：本机坏/重装/换机器都不影响——代码与历史都在 GitHub；这台电脑随时可“退居只浏览”。

---

## �📂 项目结构

```
jc_football/
├── docs/                   # 生成的静态网页(GitHub Pages 直接发布此目录)
├── data/
│   ├── today_matches.json/.csv  # 当天在售场次+赔率(自动更新)
│   ├── extra_intel.json         # 手动情报(伤病/转会/教练/战意...) ← 可编辑
│   └── cache/                   # 各联赛整季赛果缓存
├── 部署到GitHub.md         # 部署与自动更新说明(必读)
├── refresh_push.py         # 核心: 抓数据→重建docs→git推送
├── build_site.py           # 抓数据+建模 → 生成 docs/index.html
├── sporttery.py            # 体彩官方接口抓取
├── history.py / team_map.py    # 历史赛果库 / 队名映射
├── scout.py / model.py / parlay.py   # 情报→概率→两串一
├── predict.py              # 命令行报告
├── app.py / serve.py       # 本机网页版(可选, 备用)
├── 安装自动更新.bat 立即更新网页.bat 卸载自动更新.bat   # 电脑端定时/手动更新
├── 启动网页版.bat 停止服务.bat 刷新赔率.bat            # 本机本地查看(可选)
└── requirements.txt
```

---

## 🚀 使用

### 日常（最常用）
- 打开 **https://wanglin-777.github.io/jc-football/**（建议收藏到手机/电脑）
- 电脑开着：每 4 小时自动更新
- 想立刻更新：在 `jc_football` 双击 **`立即更新网页.bat`**

### 一次性设置（按顺序做一遍）
1. GitHub 仓库 **Settings → Pages**：Source = `Deploy from a branch`，Branch=`main`，folder=`/docs`
2. 电脑双击 **`安装自动更新.bat`** 注册每 4 小时任务
3. 双击 **`立即更新网页.bat`** 立即推送最新网页

### 命令行
```bash
d:\python\.venv-1\Scripts\python.exe refresh_push.py     # 抓数据+重建+推送
d:\python\.venv-1\Scripts\python.exe predict.py          # 终端看文字报告
```

---

## 🧠 模型怎么算
- 每队最近约 10 场(近期加权)攻防强度 → **泊松比分** → P(胜/平/负)
- 与**赔率隐含概率**(去水分)融合；缺历史时自动降级「仅赔率预测」并明示
- **两串一**：每场取胜率最高选项入池 → 任意两场组合、串后赔率≥2 → 按 p₁×p₂ 取前 5 组

## 📝 手动情报(伤病/转会/教练/战意)
无免费自动源 → 编辑 `data/extra_intel.json`（`adj` -3~+3，正=利好主队），保存后下次更新生效。
