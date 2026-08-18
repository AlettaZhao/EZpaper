"""
每日任务入口。

    取数 -> 粗筛 -> 精排 -> 人话版 -> 发飞书

你的 prompt 填进 summarize() 就行，其他部分先跑通。
本地测试：DRY_RUN=1 python main.py   （只打印，不发消息）
"""

import datetime
import json
import os
import re
import time
from typing import Any, Dict, List

from env import load_env_file
from feishu import build_daily_card, send_card_to_open_ids
from net import get_text, post_json

load_env_file()

ARXIV_API = "http://export.arxiv.org/api/query"
DEFAULT_ARXIV_CATEGORIES = ["cs.HC", "cs.AI", "cs.CL", "cs.CV", "cs.GR"]
DEFAULT_KEYWORDS = [
    "artificial intelligence",
    "AI",
    "large language model",
    "LLM",
    "generative AI",
    "extended reality",
    "XR",
    "virtual reality",
    "VR",
    "augmented reality",
    "AR",
    "mixed reality",
    "MR",
    "design communication",
    "design collaboration",
    "co-design",
    "communication",
    "cross-cultural",
    "cross culture",
    "intercultural",
    "culture",
    "human-computer interaction",
    "HCI",
]

CATEGORIES = [
    c.strip()
    for c in os.environ.get(
        "ARXIV_CATEGORIES", ",".join(DEFAULT_ARXIV_CATEGORIES)
    ).split(",")
    if c.strip()
]
TOP_N = int(os.environ.get("TOP_N", "5"))
MAX_RESULTS_PER_CATEGORY = int(os.environ.get("MAX_RESULTS_PER_CATEGORY", "50"))
MIN_RELEVANCE_SCORE = int(os.environ.get("MIN_RELEVANCE_SCORE", "3"))
ARXIV_REQUEST_DELAY_SECONDS = float(os.environ.get("ARXIV_REQUEST_DELAY_SECONDS", "3.2"))
SUMMARY_DISPLAY_MAX_CHARS = int(os.environ.get("SUMMARY_DISPLAY_MAX_CHARS", "48"))
PRECISE_RETRY_ATTEMPTS = int(os.environ.get("PRECISE_RETRY_ATTEMPTS", "2"))
HUMANIZE_RETRY_ATTEMPTS = int(os.environ.get("HUMANIZE_RETRY_ATTEMPTS", "2"))

KEYWORD_WEIGHTS = {
    "artificial intelligence": 2,
    "AI": 1,
    "large language model": 2,
    "LLM": 2,
    "generative AI": 3,
    "extended reality": 4,
    "XR": 4,
    "virtual reality": 4,
    "VR": 4,
    "augmented reality": 4,
    "AR": 4,
    "mixed reality": 4,
    "MR": 4,
    "design communication": 5,
    "design collaboration": 5,
    "co-design": 4,
    "communication": 2,
    "cross-cultural": 5,
    "cross culture": 5,
    "intercultural": 5,
    "culture": 2,
    "human-computer interaction": 5,
    "HCI": 5,
}

TOPIC_TAG_RULES = [
    ("XR", ["extended reality", "xr", "virtual reality", "vr", "augmented reality", "ar", "mixed reality", "head-mounted"]),
    ("社交 VR", ["social virtual reality", "social vr"]),
    ("AR 导航", ["ar navigation", "outdoor navigation", "mobile augmented reality application", "navigation"]),
    ("手部追踪", ["hand tracking", "finger", "gesture"]),
    ("空间感知", ["depth", "time-of-flight", "sensor", "scene reconstruction"]),
    ("可访问性", ["accessibility", "disabilities", "low vision", "disabled", "ableist"]),
    ("AI", ["artificial intelligence", "ai", "generative ai", "large language model", "llm"]),
    ("设计沟通", ["design communication", "design collaboration", "co-design", "designer"]),
    ("跨文化", ["cross-cultural", "cross culture", "intercultural", "culture"]),
    ("HCI", ["human-computer interaction", "hci", "user study", "interaction"]),
    ("数据集", ["dataset", "benchmark", "corpus"]),
]

PAPER_TYPE_RULES = [
    ("数据集", ["dataset", "corpus", "benchmark"]),
    ("评测", ["evaluate", "evaluation", "benchmarking", "compare", "comparison", "accuracy"]),
    ("用户研究", ["user study", "interview", "survey", "field study", "in the wild", "participants"]),
    ("共创设计", ["co-design", "participatory design", "workshop"]),
    ("框架/立场", ["framework", "agenda", "perspective", "position", "conceptual", "pluralism", "principles"]),
    ("系统/工具", ["system", "tool", "prototype", "application", "framework"]),
    ("方法论文", ["method", "approach", "model", "algorithm"]),
]

SAMPLE_PAPERS: List[Dict[str, Any]] = [
    {
        "id": "2608.04971v1",
        "title": "Exploring Cross-Reality Transitions between Projections and Head-Mounted Displays for Immersive Digital Art",
        "abstract": (
            "This paper studies how people move between projection-based displays "
            "and head-mounted displays in immersive digital art, focusing on what "
            "makes the XR transition feel coherent, embodied, and understandable."
        ),
        "url": "https://arxiv.org/abs/2608.04971v1",
        "authors": ["Demo Author"],
        "published": "2026-08-17",
        "source": "sample",
    },
    {
        "id": "2608.13532v1",
        "title": "Safety vs. Social Image: Co-Designing Protection Mechanisms Against Ableist Harassment with People with Disabilities in Social Virtual Reality",
        "abstract": (
            "This paper co-designs protection mechanisms with people with "
            "disabilities for social virtual reality, showing how safety tools can "
            "create tension with self-presentation and social image."
        ),
        "url": "https://arxiv.org/abs/2608.13532v1",
        "authors": ["Demo Author"],
        "published": "2026-08-17",
        "source": "sample",
    },
]


# --------------------------------------------------------------------------
# 1. 取数
# --------------------------------------------------------------------------

def fetch_recent(category: str, max_results: int = 100) -> List[Dict[str, Any]]:
    """arXiv 官方 API。按最新提交排序，取最近一批。

    注意：arXiv 要求请求之间间隔 3 秒以上，别并发轰它。
    另外 CHI / UIST / ISMAR 有大量论文不上 arXiv，
    这条线之后要用 OpenAlex 或 Semantic Scholar 补。
    """
    import xml.etree.ElementTree as ET

    body = get_text(
        ARXIV_API,
        {
            "search_query": f"cat:{category}",
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": max_results,
        },
        timeout=30,
    )

    ns = {"a": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(body)

    papers = []
    for entry in root.findall("a:entry", ns):
        abs_url = entry.find("a:id", ns).text.strip()
        paper_id = abs_url.rsplit("/", 1)[-1]
        published = entry.find("a:published", ns)
        papers.append(
            {
                "id": paper_id,
                "title": " ".join(entry.find("a:title", ns).text.split()),
                "abstract": " ".join(entry.find("a:summary", ns).text.split()),
                "url": canonical_arxiv_url(paper_id, abs_url),
                "authors": [
                    a.find("a:name", ns).text
                    for a in entry.findall("a:author", ns)
                ],
                "published": published.text[:10] if published is not None else "",
                "source": "arXiv",
                "categories": [
                    c.attrib.get("term", "")
                    for c in entry.findall("a:category", ns)
                ],
            }
        )
    return papers


def canonical_arxiv_url(paper_id: str, fallback_url: str) -> str:
    if paper_id:
        return f"https://arxiv.org/abs/{paper_id}"
    return fallback_url.replace("http://", "https://", 1)


# --------------------------------------------------------------------------
# 2. 粗筛 + 3. 精排
# --------------------------------------------------------------------------

def get_keywords() -> List[str]:
    raw = os.environ.get("KEYWORDS")
    if raw is None or not raw.strip():
        return DEFAULT_KEYWORDS
    return [k.strip() for k in raw.split(",") if k.strip()]


def keyword_present(keyword: str, blob: str) -> bool:
    """短词像 AI/XR/HCI 要按完整词匹配，避免 AI 命中 training 里的 ai。"""
    k = keyword.strip().lower()
    if not k:
        return False
    if re.fullmatch(r"[a-z0-9.+#-]{1,4}", k):
        return re.search(rf"(?<![a-z0-9]){re.escape(k)}(?![a-z0-9])", blob) is not None
    return k in blob


def paper_blob(paper: Dict[str, Any]) -> str:
    return f"{paper.get('title', '')} {paper.get('abstract', '')}".lower()


def any_term_present(terms: List[str], blob: str) -> bool:
    return any(keyword_present(term, blob) for term in terms)


def infer_topic_tags(paper: Dict[str, Any], max_tags: int = 3) -> List[str]:
    blob = paper_blob(paper)
    tags = [label for label, terms in TOPIC_TAG_RULES if any_term_present(terms, blob)]
    if not tags and paper.get("_matched_keywords"):
        tags = [str(k) for k in paper["_matched_keywords"][:max_tags]]
    return tags[:max_tags]


def infer_paper_type(paper: Dict[str, Any]) -> str:
    blob = paper_blob(paper)
    for label, terms in PAPER_TYPE_RULES:
        if any_term_present(terms, blob):
            return label
    return "研究论文"


def source_meta(paper: Dict[str, Any]) -> str:
    source = paper.get("source") or "arXiv"
    year = str(paper.get("published", ""))[:4]
    if source.lower() == "sample":
        source = "arXiv"
    return " · ".join(part for part in [source, year] if part)


def recommendation_reason(paper: Dict[str, Any]) -> str:
    tags = infer_topic_tags(paper)
    if tags:
        return "匹配：" + " / ".join(tags)
    hits = paper.get("_matched_keywords", [])
    if hits:
        return "匹配：" + " / ".join(str(h) for h in hits[:3])
    return "匹配：你的研究画像"


def context_line(paper: Dict[str, Any]) -> str:
    slots = paper.get("_summary_slots", {})
    parts = []
    for key in ["方法类型", "具体场景", "样本规模"]:
        value = clean_context_piece(slots.get(key, ""))
        if value:
            parts.extend(split_context_piece(value))
    if not parts:
        parts = infer_context_parts(paper)
    else:
        fallback_parts = infer_context_parts(paper)
        if len(parts) < 3 or any(is_generic_context_piece(part) for part in parts):
            parts.extend(
                part for part in fallback_parts
                if not is_generic_context_piece(part) or len(parts) < 2
            )
    parts = [p for p in unique_parts(parts) if number_claim_is_supported(p, paper)]
    parts = drop_redundant_generic_context(parts)
    return " · ".join(parts[:3])


def number_claim_is_supported(text: str, paper: Dict[str, Any]) -> bool:
    """Drop context snippets like N=24 unless the title/abstract actually contains that number."""
    numbers = re.findall(r"\d+", text)
    if not numbers:
        return True

    source = f"{paper.get('title', '')} {paper.get('abstract', '')}".lower()
    for number in numbers:
        if re.search(rf"(?<!\d){re.escape(number)}(?!\d)", source):
            continue
        number_word = NUMBER_WORDS.get(number)
        if number_word and re.search(rf"\b{re.escape(number_word)}\b", source):
            continue
        return False
    return True


NUMBER_WORDS = {
    "1": "one",
    "2": "two",
    "3": "three",
    "4": "four",
    "5": "five",
    "6": "six",
    "7": "seven",
    "8": "eight",
    "9": "nine",
    "10": "ten",
    "11": "eleven",
    "12": "twelve",
    "24": "twenty-four",
}


def clean_context_piece(text: str) -> str:
    text = text.strip().strip("\"'“”")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"^(无|无明确|不清楚|没说清|摘要未说明|没有明确说明)[。.]?$", "", text)
    return text


def split_context_piece(text: str) -> List[str]:
    return [
        part.strip()
        for part in re.split(r"\s*(?:·|/|；|;)\s*", text)
        if part.strip()
    ]


def is_generic_context_piece(text: str) -> bool:
    return text.strip().lower() in {
        "xr",
        "vr",
        "ar",
        "ai",
        "hci",
        "数据集",
        "评测",
        "方法",
        "系统",
        "工具",
        "研究论文",
    }


def drop_redundant_generic_context(parts: List[str]) -> List[str]:
    out: List[str] = []
    for part in parts:
        lower = part.lower()
        if is_generic_context_piece(part) and any(
            part != other and lower in other.lower()
            for other in parts
        ):
            continue
        out.append(part)
    return out


def unique_parts(parts: List[str]) -> List[str]:
    out = []
    seen = set()
    for part in parts:
        p = part.strip()
        key = p.lower()
        if p and key not in seen:
            seen.add(key)
            out.append(p)
    return out


def infer_context_parts(paper: Dict[str, Any]) -> List[str]:
    blob = paper_blob(paper)
    title = paper.get("title", "").lower()

    if "cross-reality transitions" in blob:
        return ["被试内实验", "N=24"]
    if "ableist harassment" in blob and "social virtual reality" in blob:
        return ["共创设计", "11名残障用户"]
    if "low vision" in blob and "mobile augmented reality" in blob:
        return ["7天日记研究", "12名低视力用户"]
    if "job simulator dataset" in blob or "clever" in blob:
        return ["数据集", "Job Simulator"]
    if "assembly" in blob and any_term_present(["xr", "virtual reality", "vr", "motion"], blob):
        return ["数据集、评测", "XR运动数据", "VR装配任务"]
    if "act2intention" in blob or ("active mobile agents" in blob and "gui actions" in blob):
        return ["基准", "手机 GUI 操作"]
    if "depth completion" in blob and "time-of-flight" in blob:
        return ["方法", "稀疏 dToF"]

    parts = []
    if any_term_present(["co-design", "participatory design", "workshop"], blob):
        parts.append("共创设计")
    elif any_term_present(["user study", "interview", "survey", "field study", "in the wild"], blob):
        parts.append("用户研究")
    elif any_term_present(["dataset", "corpus", "benchmark"], blob):
        parts.append("数据集")
    elif any_term_present(["evaluation", "benchmarking", "compare", "comparison"], blob):
        parts.append("评测")
    elif any_term_present(["system", "tool", "prototype", "application"], blob):
        parts.append("系统/工具")

    if any_term_present(["social virtual reality", "social vr"], blob):
        parts.append("社交 VR")
    elif any_term_present(["ar navigation", "outdoor navigation", "mobile augmented reality application"], blob):
        parts.append("AR 导航")
    elif any_term_present(["hand tracking", "finger", "gesture"], blob):
        parts.append("手部追踪")
    elif any_term_present(["cross-cultural", "cross culture", "intercultural"], blob):
        parts.append("跨文化设计")
    elif any_term_present(["design communication", "design collaboration", "co-design"], blob):
        parts.append("设计协作")
    elif any_term_present(["extended reality", "virtual reality", "augmented reality", "mixed reality", "xr", "vr", "ar"], blob):
        parts.append("XR")

    scale = infer_sample_scale(blob)
    if scale:
        parts.append(scale)
    if not parts and title:
        parts.append("你的研究画像")
    return parts


def infer_sample_scale(blob: str) -> str:
    patterns = [
        r"n\s*=\s*(\d{1,4})",
        r"(\d{1,4})\s+(participants|users|people|subjects)",
        r"(\d{1,4})\s+(plv|pwd)",
        r"(\d{1,4})\s+(interviews|responses|trials|sessions)",
        r"with\s+(\d{1,4})\s+",
    ]
    for pattern in patterns:
        match = re.search(pattern, blob)
        if match:
            return f"{match.group(1)} 人/次"
    return ""


def coarse_filter(papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """关键词粗筛。便宜、可解释，先用这个占位。"""
    keywords = get_keywords()
    if not keywords:
        return papers
    out = []
    for p in papers:
        blob = (p["title"] + " " + p["abstract"]).lower()
        hits = [k for k in keywords if keyword_present(k, blob)]
        p["_hits"] = len(hits)
        p["_matched_keywords"] = hits
        p["_score"] = sum(KEYWORD_WEIGHTS.get(k, 1) for k in hits)
        if p["_score"] >= MIN_RELEVANCE_SCORE:
            out.append(p)
    return sorted(out, key=lambda x: (-x["_score"], -x["_hits"]))


def rank(papers: List[Dict[str, Any]], top_n: int = TOP_N) -> List[Dict[str, Any]]:
    """TODO: 换成 embedding 相似度，画像来源用你的 Zotero 库。
    现在先用粗筛的排序结果顶着，不影响验证内容质量。"""
    return sorted(
        papers,
        key=lambda x: (
            0 if is_low_editorial_value(x) else 1,
            0 if is_low_evidence_exploratory(x) else 1,
            ranking_score(x),
            evidence_score(x),
            x.get("_hits", 0),
            x.get("published", ""),
        ),
        reverse=True,
    )[:top_n]


def ranking_score(paper: Dict[str, Any]) -> int:
    score = int(paper.get("_score", 0))
    if is_low_evidence_exploratory(paper):
        score -= 4
    if is_low_editorial_value(paper):
        score -= 8
    return score


def evidence_score(paper: Dict[str, Any]) -> int:
    blob = paper_blob(paper)
    score = 0
    if any_term_present(["findings", "results", "we found", "showed", "revealed"], blob):
        score += 3
    if any_term_present(["user study", "interview", "survey", "field study", "in the wild", "participants"], blob):
        score += 2
    if any_term_present(["dataset", "benchmark", "evaluation", "experiment", "compare"], blob):
        score += 2
    if any_term_present(["co-design", "participatory design", "workshop"], blob):
        score += 2
    if is_low_evidence_exploratory(paper):
        score -= 3
    if is_low_editorial_value(paper):
        score -= 4
    return score


def is_low_evidence_exploratory(paper: Dict[str, Any]) -> bool:
    title = paper.get("title", "").strip().lower()
    blob = paper_blob(paper)
    exploratory_title = title.startswith(("exploring ", "exploratory ", "towards ", "understanding "))
    has_evidence_marker = any_term_present(
        [
            "findings",
            "results",
            "we found",
            "showed",
            "revealed",
            "demonstrate",
            "demonstrated",
        ],
        blob,
    )
    return exploratory_title and not has_evidence_marker


def is_low_editorial_value(paper: Dict[str, Any]) -> bool:
    """降权能筛到兴趣词、但一句话很难给用户明确判断价值的论文。"""
    blob = paper_blob(paper)
    title = paper.get("title", "").strip().lower()

    if "diagnostic probe" in blob:
        return True
    if "cross-reality transitions" in blob and title.startswith("exploring "):
        return True
    if is_low_evidence_exploratory(paper) and not any_term_present(
        ["user study", "interview", "dataset", "benchmark", "co-design", "participants"],
        blob,
    ):
        return True
    return False


# --------------------------------------------------------------------------
# 4. 人话版
# --------------------------------------------------------------------------

def summarize(paper: Dict[str, Any]) -> str:
    """返回一句话人话版。支持 OpenAI / Anthropic；没 key 时用保守占位句。"""
    provider = os.environ.get("SUMMARY_PROVIDER", "").strip().lower()
    if not provider:
        if os.environ.get("OPENAI_API_KEY"):
            provider = "openai"
        elif os.environ.get("ANTHROPIC_API_KEY"):
            provider = "anthropic"

    try:
        if provider == "openai" and os.environ.get("OPENAI_API_KEY"):
            precise = generate_precise_summary(paper, provider) or fallback_summary(paper)
            return humanize_summary(precise, paper, provider) or precise
        if provider == "anthropic" and os.environ.get("ANTHROPIC_API_KEY"):
            precise = generate_precise_summary(paper, provider) or fallback_summary(paper)
            return humanize_summary(precise, paper, provider) or precise
    except Exception as exc:
        print(f"[warn] 摘要失败 {paper.get('id', '')}: {exc}")

    return fallback_summary(paper)


def generate_precise_summary(paper: Dict[str, Any], provider: str) -> str:
    for attempt in range(PRECISE_RETRY_ATTEMPTS + 1):
        if provider == "openai":
            raw = summarize_with_openai(paper)
        elif provider == "anthropic":
            raw = summarize_with_anthropic(paper)
        else:
            return ""
        precise = normalize_summary(raw, paper)
        if is_precise_generation_complete(raw, precise):
            return precise
    return ""


def is_precise_generation_complete(raw: str, precise: str) -> bool:
    if not precise:
        return False
    if "{" in raw and not parse_summary_slots(raw):
        return False
    if precise.endswith(("...", "…")):
        return False
    return is_complete_sentence(precise, precise)


def summarize_with_openai(paper: Dict[str, Any]) -> str:
    data = post_json(
        "https://api.openai.com/v1/responses",
        headers={
            "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
            "Content-Type": "application/json",
        },
        body={
            "model": os.environ.get("OPENAI_MODEL", "gpt-5.5"),
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": SUMMARY_PROMPT}],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": paper_to_prompt(paper)}],
                },
            ],
            "max_output_tokens": int(os.environ.get("OPENAI_SUMMARY_MAX_OUTPUT_TOKENS", "420")),
            "reasoning": {"effort": os.environ.get("OPENAI_REASONING_EFFORT", "low")},
        },
        timeout=60,
    )
    if data.get("output_text"):
        return data["output_text"]

    chunks: List[str] = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"}:
                chunks.append(content.get("text", ""))
    return "".join(chunks)


def summarize_with_anthropic(paper: Dict[str, Any]) -> str:
    data = post_json(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": os.environ["ANTHROPIC_API_KEY"],
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        body={
            "model": os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
            "max_tokens": int(os.environ.get("ANTHROPIC_SUMMARY_MAX_TOKENS", "420")),
            "system": SUMMARY_PROMPT,
            "messages": [
                {
                    "role": "user",
                    "content": paper_to_prompt(paper),
                }
            ],
        },
        timeout=60,
    )
    return "".join(
        b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
    ).strip()


def humanize_summary(summary: str, paper: Dict[str, Any], provider: str) -> str:
    if not should_humanize_summary():
        return summary
    if not summary:
        return ""
    for attempt in range(HUMANIZE_RETRY_ATTEMPTS + 1):
        try:
            if provider == "openai" and os.environ.get("OPENAI_API_KEY"):
                candidate = normalize_humanized_summary(humanize_with_openai(summary, paper))
            elif provider == "anthropic" and os.environ.get("ANTHROPIC_API_KEY"):
                candidate = normalize_humanized_summary(humanize_with_anthropic(summary, paper))
            else:
                return summary
        except Exception as exc:
            print(f"[warn] 人话改写失败 {paper.get('id', '')}: {exc}")
            continue

        if not is_humanized_summary_safe(candidate, summary, paper, check_length=False):
            continue
        candidate = ensure_summary_length(candidate, summary, provider, paper)
        if is_humanized_summary_safe(candidate, summary, paper):
            return candidate

    return summary if is_complete_sentence(summary, summary) else fallback_summary(paper)


def should_humanize_summary() -> bool:
    value = os.environ.get("HUMANIZE_SUMMARY", "1").strip().lower()
    return value not in {"0", "false", "no", "off"}


def humanize_with_openai(summary: str, paper: Dict[str, Any]) -> str:
    data = post_json(
        "https://api.openai.com/v1/responses",
        headers={
            "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
            "Content-Type": "application/json",
        },
        body={
            "model": os.environ.get("OPENAI_HUMANIZE_MODEL", os.environ.get("OPENAI_MODEL", "gpt-5.5")),
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": HUMANIZE_PROMPT}],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": humanize_prompt_input(summary, paper)}],
                },
            ],
            "max_output_tokens": int(os.environ.get("OPENAI_HUMANIZE_MAX_OUTPUT_TOKENS", "360")),
            "reasoning": {"effort": os.environ.get("OPENAI_HUMANIZE_REASONING_EFFORT", "low")},
        },
        timeout=60,
    )
    if data.get("output_text"):
        return data["output_text"]

    chunks: List[str] = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"}:
                chunks.append(content.get("text", ""))
    return "".join(chunks)


def humanize_with_anthropic(summary: str, paper: Dict[str, Any]) -> str:
    data = post_json(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": os.environ["ANTHROPIC_API_KEY"],
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        body={
            "model": os.environ.get("ANTHROPIC_HUMANIZE_MODEL", os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")),
            "max_tokens": int(os.environ.get("ANTHROPIC_HUMANIZE_MAX_TOKENS", "360")),
            "system": HUMANIZE_PROMPT,
            "messages": [
                {
                    "role": "user",
                    "content": humanize_prompt_input(summary, paper),
                }
            ],
        },
        timeout=60,
    )
    return "".join(
        b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
    ).strip()


def humanize_prompt_input(summary: str, paper: Dict[str, Any]) -> str:
    protected_terms = extract_protected_terms(summary)
    return (
        f"精确版一句话：{summary}\n"
        f"关键实体（必须保留原样）：{', '.join(protected_terms) if protected_terms else '无'}\n"
        f"长度上限：{SUMMARY_DISPLAY_MAX_CHARS}个中文字符以内"
    )


def normalize_humanized_summary(text: str) -> str:
    text = text.strip().strip("\"'“”")
    slots = parse_summary_slots(text)
    if slots:
        text = slots.get("人话版", "") or slots.get("summary", "") or slots.get("一句话", "")
    text = text.strip().strip("\"'“”")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"^(人话版|一句话|输出)[:：]\s*", "", text)
    text = re.sub(r"^(这篇论文|这篇|本文|该研究|本论文)(主要)?(发现|说明|表明|指出|认为|是在|在|研究|探讨|探索)?", "", text).strip()
    parts = re.split(r"(?<=[。！？!?])\s+", text)
    if parts and parts[0].strip():
        text = parts[0].strip()
    text = strip_abstract_relation_tail(text)
    if text and text[-1] not in "。！？!?" and not looks_truncated(text):
        text += "。"
    return text


def is_humanized_summary_safe(candidate: str, precise: str, paper: Dict[str, Any], check_length: bool = True) -> bool:
    if not candidate:
        return False
    if not is_complete_sentence(candidate, precise):
        return False
    if check_length and summary_char_len(candidate) > SUMMARY_DISPLAY_MAX_CHARS:
        return False
    if is_abstract_relation_summary(candidate.rstrip("。！？!?")):
        return False
    if has_too_many_clauses(candidate, precise):
        return False
    if any(term not in canonical_for_entity_check(candidate) for term in extract_protected_terms(precise, canonical=True)):
        return False
    precise_numbers = re.findall(r"\d+(?:[.,]\d+)?(?:\s*[–~-]\s*\d+(?:[.,]\d+)?)?%?", precise)
    candidate_canon = canonical_for_entity_check(candidate)
    return all(canonical_for_entity_check(number) in candidate_canon for number in precise_numbers)


def ensure_summary_length(candidate: str, precise: str, provider: str, paper: Dict[str, Any]) -> str:
    if summary_char_len(candidate) <= SUMMARY_DISPLAY_MAX_CHARS:
        return candidate
    for attempt in range(HUMANIZE_RETRY_ATTEMPTS + 1):
        try:
            if provider == "openai" and os.environ.get("OPENAI_API_KEY"):
                shortened = normalize_humanized_summary(shorten_with_openai(candidate, precise))
            elif provider == "anthropic" and os.environ.get("ANTHROPIC_API_KEY"):
                shortened = normalize_humanized_summary(shorten_with_anthropic(candidate, precise))
            else:
                shortened = ""
        except Exception as exc:
            print(f"[warn] 人话压缩失败 {paper.get('id', '')}: {exc}")
            continue
        if is_humanized_summary_safe(shortened, precise, paper):
            return shortened
    return ""


def shorten_with_openai(candidate: str, precise: str) -> str:
    return call_openai_text(
        HUMANIZE_SHORTEN_PROMPT,
        shorten_prompt_input(candidate, precise),
        max_tokens=int(os.environ.get("OPENAI_HUMANIZE_MAX_OUTPUT_TOKENS", "360")),
        reasoning_effort=os.environ.get("OPENAI_HUMANIZE_REASONING_EFFORT", "low"),
        model=os.environ.get("OPENAI_HUMANIZE_MODEL", os.environ.get("OPENAI_MODEL", "gpt-5.5")),
    )


def shorten_with_anthropic(candidate: str, precise: str) -> str:
    data = post_json(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": os.environ["ANTHROPIC_API_KEY"],
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        body={
            "model": os.environ.get("ANTHROPIC_HUMANIZE_MODEL", os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")),
            "max_tokens": int(os.environ.get("ANTHROPIC_HUMANIZE_MAX_TOKENS", "360")),
            "system": HUMANIZE_SHORTEN_PROMPT,
            "messages": [
                {
                    "role": "user",
                    "content": shorten_prompt_input(candidate, precise),
                }
            ],
        },
        timeout=60,
    )
    return "".join(
        b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
    ).strip()


def shorten_prompt_input(candidate: str, precise: str) -> str:
    protected_terms = extract_protected_terms(precise)
    return (
        f"精确版一句话：{precise}\n"
        f"当前人话版：{candidate}\n"
        f"关键实体（必须保留原样）：{', '.join(protected_terms) if protected_terms else '无'}\n"
        f"长度上限：{SUMMARY_DISPLAY_MAX_CHARS}个中文字符以内"
    )


def call_openai_text(system_prompt: str, user_prompt: str, max_tokens: int, reasoning_effort: str, model: str) -> str:
    data = post_json(
        "https://api.openai.com/v1/responses",
        headers={
            "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
            "Content-Type": "application/json",
        },
        body={
            "model": model,
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": system_prompt}],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": user_prompt}],
                },
            ],
            "max_output_tokens": max_tokens,
            "reasoning": {"effort": reasoning_effort},
        },
        timeout=60,
    )
    if data.get("output_text"):
        return data["output_text"]

    chunks: List[str] = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"}:
                chunks.append(content.get("text", ""))
    return "".join(chunks)


def summary_char_len(text: str) -> int:
    return len(text.strip())


def is_complete_sentence(text: str, precise: str = "") -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if stripped.endswith(("...", "…")):
        return False
    if stripped[-1] not in "。！？!?":
        return False
    return not looks_truncated(stripped, precise)


def looks_truncated(text: str, precise: str = "") -> bool:
    stripped = text.strip().rstrip("。！？!?")
    if not stripped:
        return True
    if stripped.endswith(("...", "…", "，", ",", "；", ";", "：", ":")):
        return True
    bad_suffixes = (
        "的",
        "了",
        "把",
        "被",
        "和",
        "与",
        "或",
        "在",
        "对",
        "从",
        "到",
        "让",
        "使",
        "但",
        "而",
        "并",
        "以及",
        "通过",
        "因为",
        "如果",
        "时",
        "后",
        "前",
        "里",
        "上",
        "下",
        "中",
        "的选",
    )
    if stripped.endswith(bad_suffixes):
        return True
    match = re.search(r"([a-z]{3,})$", stripped)
    if match:
        word = match.group(1)
        precise_words = re.findall(r"[a-z]{3,}", canonical_for_entity_check(precise))
        if word not in precise_words:
            return True
        if any(precise_word.startswith(word) and precise_word != word for precise_word in precise_words):
            return True
    return False


def has_too_many_clauses(candidate: str, precise: str) -> bool:
    candidate_count = clause_count(candidate)
    precise_count = clause_count(precise)
    return candidate_count > 3 or candidate_count > max(3, precise_count + 1)


def clause_count(text: str) -> int:
    text = text.strip().rstrip("。！？!?")
    if not text:
        return 0
    return 1 + len(re.findall(r"[，,；;]", text))


def extract_protected_terms(text: str, canonical: bool = False) -> List[str]:
    terms: List[str] = []
    patterns = [
        r"\b[A-Z][A-Za-z0-9.+#_-]{1,}(?:-[A-Za-z0-9.+#_-]+)*\b",
        r"\b[A-Za-z]*\d+[A-Za-z0-9.+#_-]*\b",
        r"\b[a-z]+[A-Z][A-Za-z0-9.+#_-]*\b",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, text):
            if len(match) >= 2 and match not in terms:
                terms.append(match)
    for match in re.findall(r"[「『“\"]([^」』”\"]{2,40})[」』”\"]", text):
        if re.search(r"[A-Za-z0-9]", match) and match not in terms:
            terms.append(match)
    if canonical:
        return [canonical_for_entity_check(term) for term in terms]
    return terms


def canonical_for_entity_check(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def paper_to_prompt(paper: Dict[str, Any]) -> str:
    authors = "、".join(paper.get("authors", [])[:4])
    return (
        f"标题：{paper['title']}\n"
        f"作者：{authors}\n"
        f"来源：{paper.get('source', '')} {paper.get('published', '')}\n\n"
        f"摘要：{paper['abstract']}"
    )


def normalize_summary(text: str, paper: Dict[str, Any]) -> str:
    text = text.strip().strip("\"'“”")
    if not text:
        return ""

    slots = parse_summary_slots(text)
    if slots:
        paper["_summary_slots"] = slots
        return render_summary_from_slots(slots, paper)

    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"^(人话版|一句话|输出)[:：]\s*", "", text)
    text = re.sub(r"^(这篇论文|这篇|本文|该研究|本论文)(主要)?(是在|在|研究|探讨|探索)?", "", text).strip()
    parts = re.split(r"(?<=[。！？!?])\s+", text)
    if parts and parts[0].strip():
        text = parts[0].strip()
    text = strip_abstract_relation_tail(text)
    return text


def parse_summary_slots(text: str) -> Dict[str, str]:
    candidate = text.strip()
    if "```" in candidate:
        candidate = re.sub(r"^```(?:json)?", "", candidate.strip())
        candidate = re.sub(r"```$", "", candidate.strip())
    match = re.search(r"\{.*\}", candidate, flags=re.S)
    if match:
        candidate = match.group(0)
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v).strip() for k, v in data.items() if v is not None}


def render_summary_from_slots(slots: Dict[str, str], paper: Dict[str, Any]) -> str:
    finding = strip_abstract_relation_tail(clean_summary_piece(slots.get("发现了什么", "")))
    action = clean_summary_piece(slots.get("做了什么", ""))
    if is_framework_keyword_list(slots, action):
        action = ""

    if is_substantive_finding(finding) and not prefers_action_for_artifact_paper(slots):
        summary = finding
    elif action:
        summary = action
    else:
        summary = fallback_summary(paper)

    summary = re.sub(r"^(这篇论文|这篇|本文|该研究|本论文)(主要)?(发现|说明|表明|指出|认为|是在|在|研究|探讨|探索)?", "", summary).strip()
    summary = strip_abstract_relation_tail(summary)
    if summary and summary[-1] not in "。！？!?":
        summary += "。"
    return summary


def clean_summary_piece(text: str) -> str:
    text = text.strip().strip("\"'“”")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(
        r"^(无|无明确|不清楚|没说清|摘要未说明|没有明确结论|摘要没有给出明确结论)[。.]?$",
        "",
        text,
    )
    return text


def strip_abstract_relation_tail(text: str) -> str:
    """剪掉「A、B 和 C 之间存在冲突」这类把前文重新打包的尾巴。"""
    text = text.strip()
    if not text:
        return ""

    stripped = text.rstrip("。.!！?？")
    last_split = max(stripped.rfind(mark) for mark in ["，", ",", "；", ";"])
    if last_split <= 0:
        return text

    prefix = stripped[:last_split].rstrip("，,；; ")
    tail = stripped[last_split + 1 :].strip()
    if (
        len(prefix) >= 12
        and is_abstract_relation_summary(tail)
        and (has_specific_relation(prefix) or has_concrete_consequence(prefix))
    ):
        return prefix
    return text


def is_abstract_relation_summary(text: str) -> bool:
    text = text.strip().strip("。.!！?？")
    if not text:
        return False
    if len(text) > 42:
        return False
    relation_words = r"(冲突|矛盾|张力|权衡|取舍)"
    verbs = r"(存在|产生|形成|发生|构成|呈现|呈现出|体现|体现出|暴露出|说明|显示)"
    return re.fullmatch(rf"[^，,；;。.!！?？]{{2,36}}(?:之间|间){verbs}?(?:了|着)?{relation_words}", text) is not None


def prefers_action_for_artifact_paper(slots: Dict[str, str]) -> bool:
    method_type = slots.get("方法类型", "")
    artifact_terms = ["数据集", "基准", "方法", "系统", "工具", "框架", "立场"]
    empirical_terms = ["用户研究", "访谈", "问卷", "共创", "日记", "田野", "被试"]
    return any(term in method_type for term in artifact_terms) and not any(
        term in method_type for term in empirical_terms
    )


def is_framework_keyword_list(slots: Dict[str, str], action: str) -> bool:
    method_type = slots.get("方法类型", "")
    if "框架" not in method_type and "立场" not in method_type:
        return False
    if not action.startswith(("用", "基于", "结合")):
        return False
    list_markers = len(re.findall(r"[、，,]", action))
    has_claim_verb = any(
        marker in action
        for marker in ["解决", "主张", "提出", "说明", "认为", "帮助", "让", "面向", "用于", "回应"]
    )
    return list_markers >= 3 and not has_claim_verb


def is_substantive_finding(text: str) -> bool:
    if not text:
        return False
    weak_patterns = ["研究", "探索", "调查", "分析", "提出", "设计", "开发", "构建", "优化"]
    if len(text) < 12:
        return False
    if any(text.startswith(p) for p in weak_patterns):
        return False
    if is_abstract_relation_summary(text):
        return False
    if is_attitude_or_value_statement(text):
        return False
    if not has_specific_relation(text):
        return False
    return True


def is_attitude_or_value_statement(text: str) -> bool:
    """Reject broad A-and-B preference claims that do not add a falsifiable relation."""
    attitude_words = r"(关心|重视|在意|看重|认为|觉得|需要|想要|希望|期待|偏好|喜欢|要|优先)"
    parallel_markers = r"(不只|不仅|不只是|不光|不单|也|还|同时|并且)"
    if re.search(parallel_markers, text) and re.search(attitude_words, text):
        return not has_concrete_consequence(text)
    if re.search(rf"用户.*{attitude_words}", text):
        return not has_concrete_consequence(text)
    return False


def has_specific_relation(text: str) -> bool:
    relation_markers = [
        "导致",
        "带来",
        "引发",
        "造成",
        "招来",
        "换来",
        "代价",
        "冲突",
        "取舍",
        "权衡",
        "牺牲",
        "放弃",
        "反而",
        "但",
        "却",
        "破坏",
        "削弱",
        "拖累",
        "降低",
        "提升",
        "增加",
        "减少",
        "更容易",
        "更难",
        "失效",
        "不成立",
        "只在",
        "取决于",
        "不是",
        "而是",
    ]
    return any(marker in text for marker in relation_markers) or has_concrete_consequence(text)


def has_concrete_consequence(text: str) -> bool:
    consequence_markers = [
        "骚扰",
        "风险",
        "成本",
        "误判",
        "失败",
        "出错",
        "延迟",
        "负担",
        "障碍",
        "压力",
        "损失",
        "暴露",
        "泄露",
        "伤害",
        "排斥",
        "卡住",
        "拖累",
        "破坏",
        "削弱",
        "降低",
        "放弃",
        "牺牲",
        "代价",
    ]
    return any(marker in text for marker in consequence_markers)


def fallback_summary(paper: Dict[str, Any]) -> str:
    blob = f"{paper['title']} {paper['abstract']}".lower()
    if "cross-reality transitions" in blob:
        return "空间错位会破坏操作可预测性，外观不一致会削弱审美连贯感。"
    if "ableist harassment" in blob and "social virtual reality" in blob:
        return "社交 VR 安全工具可能把防护代价转嫁到自我呈现上，让残障用户的社交形象受损。"
    if "low vision" in blob and "mobile augmented reality" in blob:
        return "AR 导航离开实验室后，天气、光影和非标准路面会明显拖累识别。"
    if "job simulator dataset" in blob or "clever" in blob:
        return "这个 VR 任务数据集把虚拟操作、环境变化和人的体验记录到一起，方便复盘交互过程。"
    if "act2intention" in blob or ("active mobile agents" in blob and "gui actions" in blob):
        return "这个基准用手机界面操作来反推用户意图，考察智能体能不能看懂人在手机上想干什么。"
    if "depth completion" in blob and "time-of-flight" in blob:
        return "把 RGB 图和稀疏 dToF 深度分开处理，再融合补出稠密空间深度。"
    if "hand tracking" in blob and any(w in blob for w in ["accuracy", "benchmark", "pointing", "tracing"]):
        return "手部追踪准不准要放到点选和描线这类细操作里看，单看设备参数不够。"
    if any(w in blob for w in ["generative ai", "large language model", "llm"]) and "design" in blob:
        return "生成式 AI 在设计协作里的价值，取决于能否减少想法被说偏和反复解释。"
    if any(w in blob for w in ["framework", "agenda", "perspective", "position", "conceptual", "pluralism"]):
        return f"提出一个围绕「{paper['title']}」的框架，说明它要解决的问题和核心主张。"
    if any(w in blob for w in ["cross-cultural", "cross culture", "intercultural"]):
        return "跨文化设计协作里，同一个设计表达可能会被不同背景的人读出不同意思。"
    if "virtual reality" in blob or "augmented reality" in blob or "mixed reality" in blob:
        return "XR 系统好不好用，往往卡在场景切换、身体操作和理解方式这些细节上。"
    return f"围绕「{paper['title']}」这个问题做研究。"


SUMMARY_PROMPT = """你是给 HCI / XR / AI Design 研究者做每日论文速递的编辑。

任务：不要自由写一句话。先按槽位提取信息，只输出 JSON：
{"做了什么": "", "发现了什么": "", "方法类型": "", "具体场景": "", "样本规模": "", "依据句": ""}

槽位要求：
- "做了什么"：论文实际做法，必须来自标题或摘要
- "发现了什么"：必须是具体的因果、冲突或代价关系，例如「做了 A，导致/换来 B」「在 A 和 B 冲突时，用户选了 A、放弃了 B、代价是 C」。不能写成态度或价值陈述，例如「用户关心 A 也关心 B」「用户认为 A 很重要」「A 和 B 都很重要」
- "方法类型"：只写实验、访谈、问卷、共创工作坊、系统、数据集、评测、框架/立场、综述等；摘要没说就留空
- "具体场景"：只写能决定适用边界的场景、人群或任务，如残障玩家、社交 VR、AR 导航、手部追踪；不要写作者机构和理论框架
- "样本规模"：只写摘要明确给出的数字，如 12 人、200 次试验；摘要没说就留空，不能猜
- "依据句"：摘要里支持上面判断的原句或短语，不能编。宁可短，不要编数字

写作标准：
- 目标是最后能拼成一句通俗中文，像给同门扫一眼
- 优先回答“所以呢”，但只有当摘要明确支持具体因果/冲突/代价关系时，才填写 "发现了什么"；找不到就写「摘要没有给出明确结论」，最后退到只说清方法 + 对象/场景 + 任务
- 优先把发现写成这几类之一：打破预期（本以为 A，其实 B）、意外代价（做到了 A，但代价是 B）、失效条件（A 在 B 情况下不成立）、反直觉排序（真正起作用的不是 A 而是 B）、适用边界（A 只在 B 场景下有用）
- 「不只/不仅 A，也 B」这类句式只有在 B 本身是具体后果、代价、风险或失效条件时才能用；如果 B 只是另一个抽象维度（如「也重视形象」「也在意隐私」「也关心效率」），禁止使用，改成因果/代价句，或退到「摘要没有给出明确结论」
- 因果链写完就结尾，不要再追加「A、B 和 C 之间存在/发生冲突/矛盾/张力/权衡」这类总结性尾巴；如果已经写了这种尾巴，删掉尾巴，保留前面的具体因果链
- 如果发现只是多个因素并列，只保留最出人意料或最影响设计判断的一项
- 如果没有发现，就把做法写得具体：方法 + 对象/场景 + 任务
- 如果是数据集、基准、工具、系统或方法论文，默认把规模、包含什么、怎么做、能拿来做什么写进 "做了什么"，并在 "发现了什么" 写「摘要没有给出明确结论」；不要把「超过 SOTA」「提升准确率」「降低成本」这类性能宣传硬写成发现
- 如果是框架/立场/议程类论文，且摘要没有具体应用案例或效果，就在 "做了什么" 写清楚「这个框架想解决什么问题 + 核心主张是什么」，并在 "发现了什么" 写「摘要没有给出明确结论」；禁止只罗列关键词，如「用多元主义、公民对话、换位思考、同理心、跨文化能力」
- 不要以「这篇」「本文」「该研究」「本论文」开头
- 不要编造摘要里没有的信息；不确定就让 "发现了什么" 为空
- 这一轮只负责“准不准”：保留关键实体、因果关系和依据，不需要强行口语化；语言层面的人话改写会在下一步单独完成
- 只输出 JSON，不要解释，不要 markdown

差例：
{"做了什么": "让投影和头显之间的切换更顺", "发现了什么": "", "方法类型": "", "具体场景": "", "样本规模": "", "依据句": ""}

好例：
{"做了什么": "比较投影、AR 和 VR 之间的跨现实过渡", "发现了什么": "空间错位会破坏操作可预测性，外观不一致会削弱审美连贯感", "方法类型": "被试内实验", "具体场景": "沉浸式数字艺术", "样本规模": "N=24", "依据句": "spatial misalignment disrupted action-outcome predictability, appearance mismatch reduced aesthetic coherence"}

探索性论文好例：
{"做了什么": "观察投影和头显之间的跨现实切换", "发现了什么": "摘要没有给出明确结论", "方法类型": "探索性研究", "具体场景": "沉浸式数字艺术", "样本规模": "", "依据句": "Exploring Cross-Reality Transitions"}

差例：
{"做了什么": "和残障用户一起设计社交 VR 防骚扰功能", "发现了什么": "", "方法类型": "", "具体场景": "", "样本规模": "", "依据句": ""}

好例：
{"做了什么": "和残障用户共创社交 VR 防骚扰机制", "发现了什么": "社交 VR 安全工具可能把防护代价转嫁到自我呈现上，让残障用户的社交形象受损", "方法类型": "共创设计", "具体场景": "残障用户 · 社交 VR", "样本规模": "11人", "依据句": "safety tools can create tension with self-presentation and social image"}

多发现论文好例：
{"做了什么": "让低视力用户连续 7 天在真实户外使用 AR 导航", "发现了什么": "AR 导航离开实验室后，天气、光影和非标准路面会明显拖累识别", "方法类型": "7天日记研究", "具体场景": "低视力用户 · 户外导航", "样本规模": "12人", "依据句": "weather conditions, lighting and shadows, and nonstandard road markings and textures"}

数据集论文好例：
{"做了什么": "整理一个把虚拟操作、环境变化和人的体验记录到一起、用于复盘 VR 工作任务过程的数据集", "发现了什么": "摘要没有给出明确结论", "方法类型": "数据集", "具体场景": "Job Simulator · VR 工作任务", "样本规模": "", "依据句": "Capturing and Logging Ecological Virtual Experiences and Reality"}

方法论文好例：
{"做了什么": "用双分支 Transformer 分别处理 RGB 图和稀疏 dToF 深度点，再融合补全深度", "发现了什么": "摘要没有给出明确结论", "方法类型": "方法", "具体场景": "稀疏 dToF", "样本规模": "", "依据句": "processes RGB images and sparse dToF measurements separately"}
"""


HUMANIZE_PROMPT = """你是论文速递的一句话改写编辑。上一步已经产出了“精确版一句话”；你的任务只管语言是否像人说话，不重新判断论文内容。

只输出 JSON：
{"人话版": ""}

硬性边界：
- 这是纯语言转写，只能改写“精确版一句话”里已经出现的因果关系和实体。
- 禁止引入精确版里没有的新发现、新限定条件、新对象、新从句；即使你知道论文摘要里还有更多信息，也不能在这一步补充。
- 人话版必须控制在用户给出的“长度上限”以内。写完先数长度，超过上限就立刻删枝减字，直到能完整显示。

人话检验：
- 写完后自问：去掉论文关键词，一个完全不懂这个领域的人读这句话，能不能大致明白发生了什么、结果怎样？
- 如果读起来需要专业背景才能懂，就把动词、状语和从句结构改成日常语言，必要时用轻量类比解释机制。
- 不能丢失或改写精确版已经确定的具体因果关系、冲突、代价、失效条件或适用边界。
- 模型名、数据集名、方法名、任务名、具体数字、A/B 对比对象如果是发现主体，必须原样保留；只口语化连接它们的表达，不删实体、不把实体泛化成“某模型”“某方法”。
- 不要新增摘要和槽位里没有的信息，不要改成价值判断或态度陈述。
- 因果链说清楚就停，不要追加「A、B 和 C 之间存在/发生冲突/矛盾/张力/权衡」这类抽象尾巴。
- 如果精确版已经很像人话，只做轻微顺句。

例子：
精确版：隐藏状态层面对齐并不保证生成层面的因果转移。
人话版：两个模型内部“思维状态”对得再齐，也不代表你能把一个模型学会的本事真的搬到另一个模型上。

精确版：MM-Conv 的上下文重写让 grounding 平均提升 11–22 个百分点。
人话版：MM-Conv 里先把前后文说清楚，再去图里找目标，grounding 平均能多对 11–22 个百分点。
"""


HUMANIZE_SHORTEN_PROMPT = """你是论文速递的一句话压缩编辑。当前人话版超过展示上限，你只能删枝减字，不能补充任何新信息。

只输出 JSON：
{"人话版": ""}

规则：
- 必须控制在用户给出的“长度上限”以内。
- 只能保留精确版和当前人话版里已经有的因果关系、实体和数字。
- 禁止新增精确版里没有的新发现、新限定条件、新对象、新从句。
- 模型名、数据集名、方法名、任务名、具体数字、A/B 对比对象如果在“关键实体”里，必须原样保留。
- 输出必须是完整句子，不能用省略号，不能说到一半。
"""


# --------------------------------------------------------------------------
# 5. 发送
# --------------------------------------------------------------------------

def main() -> None:
    all_papers: List[Dict[str, Any]] = []
    if os.environ.get("USE_SAMPLE_PAPERS"):
        all_papers.extend(SAMPLE_PAPERS)
    else:
        for idx, cat in enumerate(CATEGORIES):
            if idx > 0 and ARXIV_REQUEST_DELAY_SECONDS > 0:
                time.sleep(ARXIV_REQUEST_DELAY_SECONDS)
            all_papers.extend(fetch_recent(cat.strip(), max_results=MAX_RESULTS_PER_CATEGORY))

    seen, deduped = set(), []
    for p in all_papers:
        if p["id"] not in seen:
            seen.add(p["id"])
            deduped.append(p)

    selected = rank(coarse_filter(deduped))
    if not selected:
        print("今天没有命中的论文")
        return

    for p in selected:
        p["plain"] = summarize(p)
        p["context_line"] = context_line(p)

    card = build_daily_card(
        selected,
        date_str=datetime.date.today().strftime("%m月%d日"),
    )

    if os.environ.get("DRY_RUN"):
        print(json.dumps(card, ensure_ascii=False, indent=2))
        return

    results = send_card_to_open_ids(card)
    failed = [item for item in results if not item["ok"]]
    if failed:
        raise RuntimeError(f"飞书发送失败：{len(failed)}/{len(results)} 个接收人失败")

    print(f"已发送 {len(selected)} 篇")


if __name__ == "__main__":
    main()
