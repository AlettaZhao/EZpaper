import json
from typing import Any, Dict, Optional
from urllib import error, parse, request


def get_text(
    url: str,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = 30,
) -> str:
    full_url = build_url(url, params)
    req = request.Request(full_url, headers={"User-Agent": "EZpaper/0.1"})
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode(resp.headers.get_content_charset() or "utf-8")
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body[:500]}") from exc


def post_json(
    url: str,
    body: Dict[str, Any],
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = 30,
) -> Dict[str, Any]:
    full_url = build_url(url, params)
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)

    req = request.Request(
        full_url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers=req_headers,
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode(resp.headers.get_content_charset() or "utf-8")
    except error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        try:
            parsed: Any = json.loads(text)
        except json.JSONDecodeError:
            parsed = text[:500]
        raise RuntimeError({"status": exc.code, "body": parsed}) from exc

    if not text:
        return {}
    return json.loads(text)


def build_url(url: str, params: Optional[Dict[str, Any]]) -> str:
    if not params:
        return url
    query = parse.urlencode(params)
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{query}"
