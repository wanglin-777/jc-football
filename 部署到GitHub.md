# 🚀 部署到 GitHub Pages（每 4 小时自动更新 · 公开网址随时可看）

把 `jc_football` 整个文件夹作为一个 GitHub 仓库推上去即可。
之后 **GitHub Actions 每 4 小时**自动抓取竞彩官方数据 → 生成静态网页 → 部署到 GitHub Pages。
你、以及任何人在**任何网络环境**打开网址即可查看，**不需要开你的电脑**。

---

## 一、先做一次的准备

### 1) 新建一个 GitHub 仓库
1. 浏览器登录 GitHub → 右上角 `+` → **New repository**
2. Repository name 填：`jc-football`（可自定，记下即可）
3. Visibility：**Public**（免费 Pages 需要；也可以 Private，站点仍公开）
4. 其它（README/.gitignore/license）**全部不勾选**，保持空仓库
5. 点 **Create repository**

### 2) 把代码推上去（二选一）

**方式 A：用 GitHub 网页直接上传（最简单，无需装任何东西）**
> ⚠️ 但 `.github\workflows\` 是隐藏文件夹，网页拖拽上传可能带不进去，
> 所以**推荐方式 B 或 C**。

**方式 B：用 Git 命令上传（推荐，一次搞定，含隐藏文件夹）**
在本机打开终端，逐条粘贴执行（把 `你的用户名` 换成你的）：
```bash
cd /d d:\python\jc_football
git init
git add .
git commit -m "竞彩两串一预测 v1"
git branch -M main
git remote add origin https://github.com/你的用户名/jc-football.git
git push -u origin main
```
推送时若弹出 GitHub 登录窗口，用浏览器完成授权即可。

**方式 C：让我帮你执行**
如果你装了 GitHub CLI 并登录（或愿意用 git 命令行），
告诉我你已经建好仓库的**用户名/仓库名**，我可以直接在这里帮你推。

### 3) 开启 GitHub Pages（用 Actions 部署）
1. 进入仓库 → **Settings** → 左侧 **Pages**
2. **Build and deployment** → **Source** 选 **GitHub Actions**
3. 完成（不需要填自定义域名）

### 4) 首次生成
推送代码后会自动触发一次工作流；也可手动触发：
仓库 → **Actions** → 左侧 **定时更新竞彩预测** → 右侧 **Run workflow** → 绿色按钮。
等 1~2 分钟，Actions 显示绿色 ✔ 即成功。

---

## 二、你的网站地址

```
https://你的用户名.github.io/jc-football/
```
浏览器收藏这个网址，之后**任何时间、任何网络**打开即可。

> 找不到内容时：确认 Settings→Pages 的 Source 是 **GitHub Actions**，
> 且 Actions 里最近一次是绿色成功。

---

## 三、更新频率（每 4 小时自动）

- GitHub Actions 的定时任务（`cron: '17 */4 * * *'`）每天 0/4/8/12/16/20 点后约几分钟运行
- 免费版 GitHub 高峰时定时任务**可能延迟几十分钟到 1 小时**，属正常现象
- 页面顶部会显示**本次数据更新时间**，可据此判断是否最新
- 想立刻更新：仓库 → Actions → Run workflow（手动跑一次即可）

---

## 四、遇到问题排查

| 现象 | 处理 |
|------|------|
| 网页打开但数据是旧的 | Actions→ 手动 Run workflow 一次；看是否绿色成功 |
| Actions 失败 | 点进红色任务看日志；多为**云端访问体彩官网被限流**。已做兜底：失败时**保留上次成功的数据**不覆盖，网站仍可用 |
| 手机打不开 | 确认网址拼写；GitHub Pages 是公开网站，无需任何额外操作 |
| 想改更新间隔 | 编辑 `.github/workflows/update.yml` 里的 `cron`，比如每 1 小时：`cron: '17 * * * *'` |

---

## 五、本机预览（可选）

不改代码也能在本地看静态页效果：双击 **`生成网站.bat`**（会联网抓最新数据并打开网页预览）。

> 说明：网页内容 = 竞彩官方赔率 + 泊松模型预测（详见 README）。
> 伤病/转会/战意等人工情报字段在云端任务里默认不填；若想启用，把填写好的
> `data/extra_intel.json` 一起提交进仓库即可（记得去掉 .gitignore 中对它的忽略，该文件默认未忽略）。
