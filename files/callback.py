"""
阶段二才需要：接收卡片按钮的回传交互。

跑起来：uvicorn callback:app --host 0.0.0.0 --port 8000
然后把公网地址填到开发者后台的「卡片请求网址」和「事件订阅请求地址」。
本地调试用 ngrok / cpolar 开个隧道就行。
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, Request

from env import load_env_file

load_env_file()

app = FastAPI()

VERIFICATION_TOKEN = os.environ.get("FEISHU_VERIFICATION_TOKEN", "")
DATA_DIR = Path(os.environ.get("EZPAPER_DATA_DIR", Path(__file__).resolve().parent / "data"))


@app.post("/feishu/callback")
async def callback(request: Request) -> Dict[str, Any]:
    body = await request.json()

    # 1) 后台填 URL 时飞书会先来验一次，原样把 challenge 回去
    if body.get("type") == "url_verification":
        return {"challenge": body["challenge"]}

    # 2) 校验来源
    token = body.get("token") or body.get("header", {}).get("token")
    if VERIFICATION_TOKEN and token != VERIFICATION_TOKEN:
        return {"code": -1, "msg": "invalid token"}

    # 3) 取按钮 value。新旧两种回调结构都兜一下，
    #    你在开发者后台实际配好之后可以只留用到的那种。
    action = body.get("action") or body.get("event", {}).get("action", {})
    value = action.get("value", {})
    if isinstance(value, str):
        value = json.loads(value)

    open_id = (
        body.get("open_id")
        or body.get("event", {}).get("operator", {}).get("open_id")
        or ""
    )

    handle_action(open_id, value.get("action"), value.get("paper_id"))

    # 4) 返回一张卡片就会原地替换掉原消息，做即时反馈
    return {
        "toast": {"type": "success", "content": "记下了"},
    }


def handle_action(open_id: str, action: str, paper_id: str) -> None:
    """先把信号写到本地 jsonl，之后再换成数据库或 Zotero API。"""
    print(f"[signal] user={mask_identifier(open_id)} action={action} paper={paper_id}")
    log_feedback(open_id, action, paper_id)

    if action == "detail":
        # TODO: 发送详细版 + 原文链接
        pass
    elif action == "zotero":
        # TODO: 调 Zotero Web API 写入用户的库
        # POST https://api.zotero.org/users/{userID}/items
        # header: Zotero-API-Key
        pass
    elif action == "skip":
        # TODO: 负样本，回去更新画像
        pass


def mask_identifier(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return f"{value[:3]}***{value[-3:]}"


def log_feedback(open_id: str, action: str, paper_id: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "open_id": open_id,
        "action": action,
        "paper_id": paper_id,
    }
    with (DATA_DIR / "feedback.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
