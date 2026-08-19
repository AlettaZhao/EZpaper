# EZpaper

EZpaper is a daily paper digest bot for HCI / XR / AI Design research. It fetches recent arXiv papers, filters them against a focused research profile, asks an LLM to rewrite each paper into one readable Chinese sentence, and sends the result to Feishu.

The product goal is simple: every morning, get a small, low-noise list of papers that are actually worth opening.

## What It Does

- Fetches recent papers from configurable arXiv categories.
- Filters out weak matches with a stricter core relevance gate.
- Avoids repeat pushes by recording sent arXiv ids.
- Generates one human-readable Chinese sentence per paper.
- Sends the same digest through either or both Feishu channels:
  - Feishu self-built app direct message via `FEISHU_OPEN_IDS`.
  - Feishu group bot webhook via `FEISHU_WEBHOOKS`.
- Shows a dry-run selection report so you can see why papers were selected or skipped.

## Quick Start

```powershell
cd files
Copy-Item .env.example .env
```

Fill in `.env`, then preview without sending:

```powershell
$env:DRY_RUN="1"
python main.py
```

Send for real:

```powershell
Remove-Item Env:\DRY_RUN
python main.py
```

The detailed user manual lives in [files/README.md](files/README.md).

## Repository Layout

```text
files/main.py              Main fetch -> filter -> summarize -> send pipeline
files/feishu.py            Feishu app and webhook delivery
files/check_config.py      Configuration sanity check
files/.env.example         Local configuration template
files/test_selection.py    Filtering and sent-history tests
files/test_feishu.py       Feishu card and dual-channel tests
.github/workflows/daily.yml GitHub Actions daily push
```

Runtime state such as `files/data/sent_papers.json` is intentionally ignored by Git. In GitHub Actions, that file is preserved with Actions cache so daily runs can avoid repeated papers without adding automated commits.

## Verification

```powershell
python -m py_compile files/main.py files/feishu.py files/check_config.py
python -m unittest discover -s files -p "test_*.py"
```
