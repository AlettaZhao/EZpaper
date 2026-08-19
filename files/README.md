# EZpaper · Aletta 的每日论文人话版

目标：每天早上在飞书里推 3-5 篇和 `HCI / Human-AI / AI Design / XR` 相关的新论文。每篇只保留一句真正能看懂的话，再附上简短场景标签、匹配理由、摘要页和 PDF 按钮。

当前数据源是 arXiv。程序会先抓最新论文，再做同篇去重、已推送历史去重、核心相关性过滤，最后把入选论文交给模型生成一句话。

## 两个发送口

EZpaper 支持两条 Feishu 发送通道，可以只开一个，也可以两个都开：

```text
FEISHU_OPEN_IDS=ou_xxx,ou_yyy
FEISHU_WEBHOOKS=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
```

`FEISHU_OPEN_IDS` 是飞书自建应用单聊。它需要同时配置：

```text
FEISHU_APP_ID=cli_xxxxxxxx
FEISHU_APP_SECRET=xxxxxxxx
```

`FEISHU_WEBHOOKS` 是飞书群机器人 webhook。它不需要 app token；如果群机器人开启了签名校验，再配置：

```text
FEISHU_WEBHOOK_SECRET=xxxxxxxx
```

如果两个发送口都配置了，同一张每日论文卡片会同时发到单聊和群里。程序会逐个发送，任何一个目标失败都会在日志里显示；只有所有目标都成功后，才会把论文写入“已推送历史”，避免失败时误标成已读。

## 快速开始

进入代码目录：

```powershell
cd EZpaper\files
```

复制配置模板：

```powershell
Copy-Item .env.example .env
```

至少填这些值：

```text
OPENAI_API_KEY=你的 OpenAI API key

# 发送口二选一，或者两个都填
FEISHU_OPEN_IDS=你的飞书 open_id，多个用英文逗号分隔
FEISHU_WEBHOOKS=飞书群机器人 webhook，多个用英文逗号分隔
```

如果使用 `FEISHU_OPEN_IDS`，还要填 `FEISHU_APP_ID` 和 `FEISHU_APP_SECRET`。如果先不用 OpenAI，也可以换 Anthropic：

```text
SUMMARY_PROVIDER=anthropic
ANTHROPIC_API_KEY=你的 Anthropic API key
```

## 运行前检查

```powershell
python check_config.py
```

这个命令会检查是否至少有一个完整发送通道，以及是否配置了 OpenAI 或 Anthropic key。

## 本地预览

只看样例卡片，不抓 arXiv、不发飞书：

```powershell
$env:USE_SAMPLE_PAPERS="1"
$env:DRY_RUN="1"
python main.py
```

注意：如果 `.env` 里已经配置了模型 key，样例模式仍会调用模型生成一句话；想完全不调模型，可以临时清掉当前终端里的 key。

真正抓 arXiv，但先不发飞书：

```powershell
$env:DRY_RUN="1"
python main.py
```

dry run 会先打印选择报告，例如抓了多少篇、同篇去重多少篇、历史跳过多少篇、核心相关不足挡掉多少篇，然后打印即将发送的卡片 JSON。

## 正式发送

确认 dry run 没问题后，清掉 `DRY_RUN`：

```powershell
Remove-Item Env:\DRY_RUN
python main.py
```

发送成功后，程序会把本次论文记录到：

```text
files/data/sent_papers.json
```

这个文件默认不提交到 Git。它用于避免跨天重复推送同一篇 arXiv 论文；`2608.12345v1` 和 `2608.12345v2` 会被视为同一篇。

## GitHub 定时

workflow 在项目根目录：

```text
.github/workflows/daily.yml
```

默认每天北京时间 09:00 运行，也可以在 GitHub Actions 页面手动点 `Run workflow`。在仓库的 `Settings -> Secrets and variables -> Actions` 里加：

```text
FEISHU_APP_ID
FEISHU_APP_SECRET
FEISHU_OPEN_IDS
FEISHU_WEBHOOKS
FEISHU_WEBHOOK_SECRET
OPENAI_API_KEY
ANTHROPIC_API_KEY
```

只用群机器人时，`FEISHU_APP_ID` / `FEISHU_APP_SECRET` / `FEISHU_OPEN_IDS` 可以不填。只用自建应用单聊时，`FEISHU_WEBHOOKS` / `FEISHU_WEBHOOK_SECRET` 可以不填。

GitHub Actions 会用 cache 保存 `files/data/sent_papers.json`，所以自动任务可以跨天记住已推送论文，同时不会每天产生一个历史文件 commit。

## 筛选逻辑

默认 arXiv 分类：

```text
cs.HC, cs.AI, cs.LG, stat.ML, cs.CL, cs.CV, cs.GR, cs.RO
```

筛选参数：

```text
TOP_N=5
MIN_RELEVANCE_SCORE=4
REQUIRE_CORE_RELEVANCE=1
MAX_PAPER_AGE_DAYS=14
SENT_HISTORY_RETENTION_DAYS=365
ALLOW_REPEAT_PAPERS=0
```

`MIN_RELEVANCE_SCORE` 越高，推送越少但更贴近。`REQUIRE_CORE_RELEVANCE=1` 会要求论文至少命中 HCI、Human-AI、设计/共创、XR/空间交互、可访问性、HRI 等核心方向，避免只因为泛 AI、ML、dataset、evaluation 词多就入选。

`MAX_PAPER_AGE_DAYS` 控制新鲜度窗口。`ALLOW_REPEAT_PAPERS=1` 可以临时允许已推送论文再次出现，适合你想复查筛选效果的时候。

## 输出体验

飞书卡片每篇论文包含：

- 一句话版：最核心的人话总结。
- 场景标签：例如 `用户研究 · XR`。
- 推荐理由：例如 `核心匹配：HCI/用户研究 / XR/空间交互`。
- 两个按钮：`摘要页` 和 `PDF`。

这套呈现的原则是：主信息只放一句话，决策辅助信息放小字，打开论文的动作放按钮。

## 测试

```powershell
python -m py_compile main.py feishu.py check_config.py
python -m unittest discover -s . -p "test_*.py"
```

测试覆盖了：

- 同一篇 arXiv 论文的 `v1/v2` 去重。
- 已推送历史跳过。
- 泛 ML 论文不会只靠关键词入选。
- 医学 `MR` 和 autoregressive `AR` 不会被误判成 XR。
- Feishu app 单聊和群 webhook 可以同时发送。
- 飞书卡片包含摘要页和 PDF 按钮。

## 常见问题

没有命中新论文：

```text
今天没有命中的新论文
```

通常说明最近候选都已经推过，或者筛选太严格。可以临时设置 `ALLOW_REPEAT_PAPERS=1` 看看原始候选，也可以降低 `MIN_RELEVANCE_SCORE`。

想只发群里：

```text
FEISHU_WEBHOOKS=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
```

想只发单聊：

```text
FEISHU_OPEN_IDS=ou_xxx
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
```

想完全预览、不发消息：

```powershell
$env:DRY_RUN="1"
python main.py
```

## 后续方向

- 用 OpenAlex / Semantic Scholar 补 CHI、UIST、ISMAR、CSCW、VRST 等来源。
- 把排序从关键词计分升级成 embedding 相似度。
- 用 Zotero 库和你的点击反馈更新兴趣画像。
- 给飞书卡片加“喜欢 / 不相关 / 稍后读”反馈按钮。
