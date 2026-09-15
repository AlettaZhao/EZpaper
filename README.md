# EZpaper

> 每天自动从 arXiv 挑出与你研究方向最相关的论文，用一句中文讲清楚“它到底做了什么”，再把精选结果推送到飞书。

EZpaper 面向不想每天手动刷 arXiv 的研究者。它会完成 **抓取 → 去重 → 相关性筛选 → LLM 一句话总结 → 飞书卡片推送**，默认每天只留下 3–5 篇真正值得打开的论文。

<!--
真实飞书卡片截图到位后，将图片保存为 docs/images/feishu-card.png，并取消下面一行的注释。
![EZpaper 飞书卡片效果](docs/images/feishu-card.png)
-->

## 它能做什么

- 按研究方向配置 arXiv 领域和关键词；
- 用核心相关性门槛过滤“只是沾了 AI 关键词”的弱相关论文；
- 自动识别同一论文的不同 arXiv 版本，避免重复推送；
- 调用 OpenAI 或 Anthropic，把摘要改写成一句易读的中文；
- 支持飞书群机器人 webhook 和自建应用单聊，两种渠道可任选或同时使用；
- 使用 GitHub Actions 定时运行，不需要自己的服务器或常开电脑；
- arXiv 偶发超时时自动重试，单个分类失败不会拖垮整份日报。

## 四步开始

### 1. Fork 仓库

点击页面右上角 **Fork**，把 EZpaper 复制到自己的 GitHub 账号。

### 2. 填写飞书凭证和模型密钥

进入 fork 后的仓库：

`Settings → Secrets and variables → Actions → New repository secret`

最快的配置是“飞书群机器人 + OpenAI”，只需添加两个 Secret：

| Secret | 填写内容 |
| --- | --- |
| `FEISHU_WEBHOOKS` | 飞书群自定义机器人的 webhook；多个地址用英文逗号分隔 |
| `OPENAI_API_KEY` | OpenAI API key |

如果想让机器人私聊发送，再添加：

| Secret | 填写内容 |
| --- | --- |
| `FEISHU_APP_ID` | 飞书自建应用 App ID |
| `FEISHU_APP_SECRET` | 飞书自建应用 App Secret |
| `FEISHU_OPEN_IDS` | 接收人的飞书 `open_id`；多个用英文逗号分隔 |

群机器人开启签名校验时，还要添加 `FEISHU_WEBHOOK_SECRET`。模型也可以换成 Anthropic：只添加 `ANTHROPIC_API_KEY` 时程序会自动选择 Anthropic；如果同时配置了两种模型密钥，可在 workflow 的 `env` 中添加 `SUMMARY_PROVIDER: anthropic` 明确指定。

> 不要把真实 key、webhook 或 `.env` 提交到仓库。GitHub Actions 只从 repository secrets 读取这些值。

### 3. 修改研究方向、推送数量和时间

编辑 [`.github/workflows/daily.yml`](.github/workflows/daily.yml) 中 `python main.py` 步骤的环境变量：

```yaml
ARXIV_CATEGORIES: "cs.HC,cs.AI,cs.LG,stat.ML,cs.CL,cs.CV,cs.GR,cs.RO"
KEYWORDS: "human-AI interaction,AI design,XR,virtual reality,user study"
MIN_RELEVANCE_SCORE: "4"
TOP_N: "5"
```

- `ARXIV_CATEGORIES`：要抓取的 arXiv 分类；
- `KEYWORDS`：你的领域、方法、对象和任务关键词；
- `MIN_RELEVANCE_SCORE`：越高越严格，推荐从 `4` 开始；
- `TOP_N`：每天最多推送多少篇。

默认每天北京时间 09:00 运行：

```yaml
on:
  schedule:
    - cron: "0 9 * * *"
      timezone: "Asia/Shanghai"
```

这里使用 IANA 时区名称；想改时间只需要修改 `cron` 和 `timezone`。可参考 [GitHub Actions 工作流语法](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onschedule)。

### 4. 启用 GitHub Actions

fork 出来的仓库默认不会自动运行工作流：

1. 打开仓库的 **Actions** 页面；
2. 确认启用工作流；
3. 选择左侧 **daily-papers**；
4. 点击 **Run workflow** 做第一次测试。

GitHub 官方说明见 [Workflows in forked repositories](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflows-in-forked-repositories)。第一次成功后，日报会按设定时间自动发送。

## 配置说明

### 推送渠道

| 目标 | 必填配置 | 适合场景 |
| --- | --- | --- |
| 飞书群 | `FEISHU_WEBHOOKS` | 配置最快，多人共同接收 |
| 飞书私聊 | `FEISHU_APP_ID`、`FEISHU_APP_SECRET`、`FEISHU_OPEN_IDS` | 个人订阅或定向发送 |
| 两者同时 | 两组配置都填 | 同一份日报同时发到群和私聊 |

### 筛选参数

| 参数 | 默认值 | 说明 |
| --- | ---: | --- |
| `ARXIV_CATEGORIES` | `cs.HC,cs.AI,...` | arXiv 分类，英文逗号分隔 |
| `KEYWORDS` | 见 workflow | 研究兴趣关键词，英文逗号分隔 |
| `TOP_N` | `5` | 每次最多推送篇数 |
| `MIN_RELEVANCE_SCORE` | `4` | 相关性最低分数 |
| `REQUIRE_CORE_RELEVANCE` | `1` | 是否强制至少命中一个核心研究方向 |
| `MAX_PAPER_AGE_DAYS` | `14` | 只保留最近多少天的论文 |
| `ALLOW_REPEAT_PAPERS` | `0` | 临时设为 `1` 可忽略历史记录重新测试 |

### 摘要参数

| 参数 | 默认值 | 说明 |
| --- | ---: | --- |
| `SUMMARY_PROVIDER` | 自动选择 | `openai` 或 `anthropic`；未设置时按可用密钥选择 |
| `OPENAI_MODEL` | `gpt-5.5` | OpenAI 摘要模型 |
| `OPENAI_REASONING_EFFORT` | `low` | 推理强度 |

项目通过 OpenAI Responses API 调用 `gpt-5.5`；该模型支持 `low` reasoning effort，详见 [OpenAI 官方模型文档](https://developers.openai.com/api/docs/models/gpt-5.5)。如果账号无权使用该模型，可把 workflow 中的 `OPENAI_MODEL` 换成账号可用的文本模型。

### 网络容错参数

| 参数 | 默认值 | 说明 |
| --- | ---: | --- |
| `ARXIV_REQUEST_TIMEOUT_SECONDS` | `45` | 单次 arXiv 请求超时 |
| `ARXIV_RETRY_ATTEMPTS` | `3` | 每个分类最多尝试次数 |
| `ARXIV_RETRY_BACKOFF_SECONDS` | `5` | 重试退避的基础秒数 |

## 本地运行

需要 Python 3.11+。

```bash
git clone https://github.com/AlettaZhao/EZpaper.git
cd EZpaper/files
cp .env.example .env
```

Windows PowerShell 可将最后一行换成：

```powershell
Copy-Item .env.example .env
```

填写 `.env` 后先检查配置：

```bash
python check_config.py
```

只预览、不发送：

```bash
DRY_RUN=1 python main.py
```

PowerShell：

```powershell
$env:DRY_RUN="1"
python main.py
```

更完整的本地调试和飞书自建应用说明见 [`files/README.md`](files/README.md)。

## 如何避免重复推送

发送成功的 arXiv ID 会记录在 `files/data/sent_papers.json`。本地运行时该目录被 Git 忽略；GitHub Actions 使用 cache 跨天保存记录，不会每天向仓库提交数据。

## 安全说明

- `.env`、运行数据、Python 缓存和本地样例目录均不会进入 Git；
- workflow 只使用 GitHub repository secrets，不会把真实凭证写入代码；
- 来自 fork 的 Pull Request 默认无法读取仓库 secrets；
- 不要在 Issue、日志截图或报错信息中粘贴 API key、webhook、手机号或 `open_id`；
- 如果凭证曾意外提交，请先在服务端撤销并重新生成，再清理 Git 历史。

## 项目结构

```text
.github/workflows/daily.yml  定时任务和默认研究配置
files/main.py                抓取、筛选、总结主流程
files/feishu.py              飞书群机器人和私聊发送
files/check_config.py        配置完整性检查
files/.env.example           本地配置模板
files/test_*.py              自动化测试
```

## 加群交流

不想自己部署，或者希望交流论文筛选与提示词配置，可以扫码加入交流群。

<!--
加群二维码到位后，将图片保存为 docs/images/community-qr.png，并取消下面一行的注释。
![EZpaper 交流群二维码](docs/images/community-qr.png)
-->

## 测试

```bash
python -m py_compile files/main.py files/feishu.py files/check_config.py
python -m unittest discover -s files -p "test_*.py"
```

当前测试覆盖论文去重、历史过滤、核心相关性、缩写误判、双渠道发送，以及 arXiv 超时重试和分类级容错。
