"""
飞书发送层。

现在使用飞书企业自建应用单聊：

  FEISHU_APP_ID / FEISHU_APP_SECRET
      换 tenant_access_token，同一次运行内缓存复用。

  FEISHU_OPEN_IDS
      逗号分隔的 open_id 列表，逐个发送交互式卡片。
"""

import json
import os
import time
from typing import Any, Dict, List, Optional

from env import load_env_file
from net import post_json

load_env_file()

FEISHU_HOST = "https://open.feishu.cn"


# --------------------------------------------------------------------------
# 自建应用
# --------------------------------------------------------------------------

_token_cache: Dict[str, Any] = {"token": None, "expire_at": 0}


def get_tenant_access_token() -> str:
    """token 有效期 2 小时，这里缓存到过期前 5 分钟。"""
    now = time.time()
    if _token_cache["token"] and now < _token_cache["expire_at"]:
        return _token_cache["token"]

    data = post_json(
        f"{FEISHU_HOST}/open-apis/auth/v3/tenant_access_token/internal",
        {
            "app_id": require_env("FEISHU_APP_ID"),
            "app_secret": require_env("FEISHU_APP_SECRET"),
        },
        timeout=10,
    )
    if data.get("code") != 0:
        raise RuntimeError(f"获取 tenant_access_token 失败: {data}")

    _token_cache["token"] = data["tenant_access_token"]
    _token_cache["expire_at"] = now + data.get("expire", 7200) - 300
    return _token_cache["token"]


def send_via_app(card: Dict[str, Any], open_id: str) -> Dict[str, Any]:
    """点对点发给某个用户。"""
    return post_json(
        f"{FEISHU_HOST}/open-apis/im/v1/messages",
        params={"receive_id_type": "open_id"},
        headers={
            "Authorization": f"Bearer {get_tenant_access_token()}",
            "Content-Type": "application/json; charset=utf-8",
        },
        body={
            "receive_id": open_id,
            "msg_type": "interactive",
            # 坑：content 必须是 JSON 字符串，不是对象
            "content": json.dumps(card, ensure_ascii=False),
        },
        timeout=10,
    )


# --------------------------------------------------------------------------
# 统一入口
# --------------------------------------------------------------------------

def send_card_to_open_ids(
    card: Dict[str, Any],
    open_ids: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """逐个 open_id 发送；单个失败不中断其余，返回每个接收人的结果。"""
    targets = open_ids or get_open_ids()
    results: List[Dict[str, Any]] = []

    for open_id in targets:
        try:
            data = send_via_app(card, open_id)
            code = data.get("code", -1)
            msg = data.get("msg", "")
            ok = code == 0
        except Exception as exc:
            data = {}
            code = -1
            msg = str(exc)
            ok = False

        print(f"飞书发送 open_id={open_id} code={code} msg={msg}")
        results.append(
            {
                "open_id": open_id,
                "ok": ok,
                "code": code,
                "msg": msg,
                "data": data,
            }
        )

    return results


def send_card(card: Dict[str, Any], open_id: Optional[str] = None) -> Dict[str, Any]:
    """兼容旧调用：只发给一个 open_id。新代码优先使用 send_card_to_open_ids。"""
    if not open_id:
        raise RuntimeError("缺少 open_id；请设置 FEISHU_OPEN_IDS")
    return send_via_app(card, open_id)


def get_open_ids() -> List[str]:
    raw = os.environ.get("FEISHU_OPEN_IDS") or os.environ.get("OPEN_IDS", "")
    open_ids = [
        item.strip()
        for item in raw.replace("\n", ",").split(",")
        if item.strip()
    ]
    if not open_ids:
        raise RuntimeError("缺少 FEISHU_OPEN_IDS；请填入逗号分隔的飞书 open_id 列表")
    return open_ids


def require_env(key: str) -> str:
    value = os.environ.get(key, "").strip()
    if not value:
        raise RuntimeError(f"缺少环境变量：{key}")
    return value


# --------------------------------------------------------------------------
# 卡片构建
# --------------------------------------------------------------------------

def build_daily_card(
    papers: List[Dict[str, Any]],
    date_str: str,
    interactive: bool = False,
    click_base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    papers: [{"id","plain","title","url"}]
        plain — 你的人话版一句话
        url   — arXiv abs 页或 DOI 链接

    每条论文都加 URL 跳转按钮；这里不使用 callback 类型按钮。
    """
    elements: List[Dict[str, Any]] = []

    for i, p in enumerate(papers):
        content = f"**{i + 1}.** {p['plain']}"
        elements.append(
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": content},
            }
        )

        url = p.get("url", "").strip()
        context = p.get("context_line", "").strip()
        if context:
            elements.append(
                {
                    "tag": "note",
                    "elements": [
                        {"tag": "lark_md", "content": context}
                    ],
                }
            )

        actions = _paper_url_action(url)
        if actions:
            elements.append({"tag": "action", "actions": actions})
        if i < len(papers) - 1:
            elements.append({"tag": "hr"})

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {
                "tag": "plain_text",
                "content": f"今日论文 · {date_str} · {len(papers)} 篇",
            },
            "template": "blue",
        },
        "elements": elements,
    }


def _paper_url_action(url: str) -> List[Dict[str, Any]]:
    if not url:
        return []
    return [
        {
            "tag": "button",
            "text": {"tag": "plain_text", "content": "看原文"},
            "type": "primary",
            "url": url,
        }
    ]
