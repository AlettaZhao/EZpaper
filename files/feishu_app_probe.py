"""
飞书自建应用联调脚本。

依次执行：
1. 用 FEISHU_APP_ID / FEISHU_APP_SECRET 换 tenant_access_token
2. 用手机号查 open_id
3. 给该 open_id 发送交互式卡片消息

注意：脚本会按你的要求打印每一步的完整返回值，tenant_access_token 会出现在终端输出里。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict

from env import load_env_file


FEISHU_HOST = "https://open.feishu.cn"



def main() -> None:
    global FEISHU_HOST
    configure_stdio()
    load_env_file()
    FEISHU_HOST = os.environ.get("FEISHU_HOST", FEISHU_HOST).rstrip("/")
    args = parse_args()

    app_id = require_env("FEISHU_APP_ID")
    app_secret = require_env("FEISHU_APP_SECRET")
    mobile = args.mobile or os.environ.get("FEISHU_MOBILE")
    if not mobile:
        raise SystemExit("缺少手机号：请设置 FEISHU_MOBILE，或运行时加 --mobile 13812345678")

    token_data = get_tenant_access_token(app_id, app_secret)
    tenant_access_token = token_data["tenant_access_token"]

    user_data = get_open_id_by_mobile(tenant_access_token, mobile, args.include_resigned)
    open_id = extract_open_id(user_data, mobile)
    print(f"\n解析到 open_id: {open_id}")

    message_data = send_interactive_card(
        tenant_access_token=tenant_access_token,
        open_id=open_id,
        title=args.card_title,
        text=args.card_text,
    )
    print(f"\n发送完成，message_id: {message_data.get('data', {}).get('message_id')}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="联调飞书自建应用：token -> open_id -> 交互式卡片")
    parser.add_argument("--mobile", help="你的飞书手机号；也可用 FEISHU_MOBILE 环境变量")
    parser.add_argument(
        "--include-resigned",
        action="store_true",
        default=env_bool("FEISHU_INCLUDE_RESIGNED"),
        help="查 open_id 时是否包含离职用户；也可设置 FEISHU_INCLUDE_RESIGNED=1",
    )
    parser.add_argument("--card-title", default="EZpaper 自建应用联调")
    parser.add_argument(
        "--card-text",
        default="如果你看到这张卡片，说明 tenant_access_token、open_id 查询和机器人单聊发送都已经跑通。",
    )
    return parser.parse_args()


def get_tenant_access_token(app_id: str, app_secret: str) -> Dict[str, Any]:
    return post_feishu_json(
        step="1. 获取 tenant_access_token",
        url=f"{FEISHU_HOST}/open-apis/auth/v3/tenant_access_token/internal",
        json_body={
            "app_id": app_id,
            "app_secret": app_secret,
        },
    )


def get_open_id_by_mobile(
    tenant_access_token: str,
    mobile: str,
    include_resigned: bool,
) -> Dict[str, Any]:
    return post_feishu_json(
        step="2. 手机号查询 open_id",
        url=f"{FEISHU_HOST}/open-apis/contact/v3/users/batch_get_id",
        params={"user_id_type": "open_id"},
        headers=auth_headers(tenant_access_token),
        json_body={
            "mobiles": [mobile],
            "include_resigned": include_resigned,
        },
    )


def send_interactive_card(
    tenant_access_token: str,
    open_id: str,
    title: str,
    text: str,
) -> Dict[str, Any]:
    card = build_probe_card(title=title, text=text)
    return post_feishu_json(
        step="3. 发送交互式卡片消息",
        url=f"{FEISHU_HOST}/open-apis/im/v1/messages",
        params={"receive_id_type": "open_id"},
        headers=auth_headers(tenant_access_token),
        json_body={
            "receive_id": open_id,
            "msg_type": "interactive",
            "content": json.dumps(card, ensure_ascii=False),
        },
    )


def build_probe_card(title: str, text: str) -> Dict[str, Any]:
    sent_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "blue",
            "title": {"tag": "plain_text", "content": title},
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**联调消息**\n{text}",
                },
            },
            {
                "tag": "note",
                "elements": [
                    {
                        "tag": "plain_text",
                        "content": f"Sent by local Python requests script at {sent_at}",
                    }
                ],
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "收到"},
                        "type": "primary",
                        "value": {
                            "action": "ezpaper_probe_ack",
                            "source": "feishu_app_probe.py",
                        },
                    }
                ],
            },
        ],
    }


def post_feishu_json(
    step: str,
    url: str,
    json_body: Dict[str, Any],
    headers: Dict[str, str] | None = None,
    params: Dict[str, str] | None = None,
) -> Dict[str, Any]:
    requests = import_requests()
    request_headers = {
        "Content-Type": "application/json; charset=utf-8",
        **(headers or {}),
    }
    response = requests.post(
        url,
        params=params,
        headers=request_headers,
        data=json.dumps(json_body, ensure_ascii=False).encode("utf-8"),
        timeout=20,
    )
    parsed = parse_response_body(response)
    print_response(step, response, parsed)

    if not response.ok:
        raise SystemExit(f"{step} HTTP 请求失败：{response.status_code}")
    if not isinstance(parsed, dict):
        raise SystemExit(f"{step} 返回值不是 JSON 对象")
    if parsed.get("code") != 0:
        raise SystemExit(f"{step} 飞书返回 code={parsed.get('code')}，msg={parsed.get('msg')}")
    return parsed


def parse_response_body(response: requests.Response) -> Any:
    if not response.text:
        return {}
    try:
        return response.json()
    except ValueError:
        return response.text


def print_response(step: str, response: requests.Response, body: Any) -> None:
    print(f"\n========== {step} ==========")
    print(f"HTTP: {response.status_code} {response.reason}")
    log_id = response.headers.get("X-Tt-Logid") or response.headers.get("x-tt-logid")
    if log_id:
        print(f"X-Tt-Logid: {log_id}")
    print("Response:")
    if isinstance(body, (dict, list)):
        print(json.dumps(body, ensure_ascii=False, indent=2))
    else:
        print(body)


def extract_open_id(user_data: Dict[str, Any], mobile: str) -> str:
    user_list = user_data.get("data", {}).get("user_list", [])
    if not user_list:
        raise SystemExit(
            "手机号没有查到用户。请检查手机号是否属于应用可见范围；非中国大陆手机号需要带 +国家/地区代码。"
        )

    matched_user = next((item for item in user_list if item.get("mobile") == mobile), user_list[0])
    open_id = matched_user.get("user_id")
    if not open_id:
        raise SystemExit(f"返回里没有 user_id/open_id 字段：{matched_user}")
    return open_id


def auth_headers(tenant_access_token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {tenant_access_token}"}


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"缺少环境变量：{name}")
    return value


def env_bool(name: str) -> bool:
    value = os.environ.get(name, "")
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def import_requests() -> Any:
    try:
        import requests
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "缺少 Python 依赖 requests。请先运行：pip install -r files/requirements.txt"
        ) from exc
    return requests


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


if __name__ == "__main__":
    main()
