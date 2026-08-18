# EZpaper · Aletta 的每日论文人话版

目标：每天早上在飞书里给自己推 3-5 篇和 `AI / XR / Design Communication / Cross-culture / HCI` 相关的论文。每篇论文先给一句人话，比如：

> 这篇论文是在比较不同 VR/AR 设备追手指准不准，尤其看点选和描线这类细操作。

现在先做单用户 MVP：arXiv 取数，关键词粗筛，模型生成一句话，飞书群机器人推送。

## 你先做这三步

1. 进入代码目录

```powershell
cd EZpaper\files
```

2. 复制环境变量模板

```powershell
Copy-Item .env.example .env
```

3. 打开 `.env`，填这几个值

```text
FEISHU_WEBHOOK=你的飞书群机器人 webhook
FEISHU_WEBHOOK_SECRET=你的飞书群机器人签名 secret
OPENAI_API_KEY=你的 OpenAI API key
```

如果先不用 OpenAI，也可以改成 Anthropic：

```text
SUMMARY_PROVIDER=anthropic
ANTHROPIC_API_KEY=你的 Anthropic API key
```

## 本地先看卡片长什么样

不联网、不发飞书，只用样例论文打印卡片 JSON：

```powershell
$env:USE_SAMPLE_PAPERS="1"
$env:DRY_RUN="1"
python main.py
```

如果你的 Windows 终端没有 `python`，用 Codex 内置 Python 或先安装 Python 3.11。

阶段一不需要安装第三方依赖；`requirements.txt` 里的依赖只给后面的飞书回调服务用。

## 真正抓 arXiv，但先不发飞书

```powershell
$env:DRY_RUN="1"
python main.py
```

这一步会访问 arXiv 和模型 API，只在终端打印卡片。

## 发到飞书

确认卡片没问题后，清掉 `DRY_RUN` 再跑：

```powershell
Remove-Item Env:\DRY_RUN
python main.py
```

## 上 GitHub 定时

workflow 已经放在项目根目录的 `.github/workflows/daily.yml`。推到 GitHub 后，在仓库的 `Settings → Secrets and variables → Actions` 里加：

```text
FEISHU_WEBHOOK
FEISHU_WEBHOOK_SECRET
OPENAI_API_KEY
```

之后它会在工作日北京时间 08:30 自动跑，也可以在 Actions 页面手动点 `Run workflow`。

## 当前兴趣画像

默认 arXiv 分类：

```text
cs.HC, cs.AI, cs.CL, cs.CV, cs.GR
```

默认关键词：

```text
artificial intelligence, AI, large language model, LLM, generative AI,
extended reality, XR, virtual reality, VR, augmented reality, AR,
mixed reality, MR, design communication, design collaboration, co-design,
communication, cross-cultural, cross culture, intercultural, culture,
human-computer interaction, HCI
```

你可以直接在 `.env` 里改 `KEYWORDS`、`TOP_N` 和 `MIN_RELEVANCE_SCORE`。`MIN_RELEVANCE_SCORE` 越高，推送越少但更贴近；越低，探索性更强。

## 后面再长出来的功能

- 用 OpenAlex / Semantic Scholar 补 CHI、UIST、ISMAR、CSCW、VRST 等来源。
- 把 `rank()` 从关键词计数换成 embedding 相似度。
- 用 Zotero 库和你的点击反馈更新兴趣画像。
- 换成飞书自建应用，支持真正的按钮回调和点对点推送。
