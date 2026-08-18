import json
import os
import sys
import time
import xml.etree.ElementTree as ET
from copy import deepcopy
from typing import Any, Dict, List

import main

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


GOLDEN_NEGATIVE_PATH = os.path.join(os.path.dirname(__file__), "golden_negative_cases.json")


OLD_SUMMARY_PROMPT = """你是给 HCI / XR / AI Design 研究者做每日论文速递的编辑。

任务：不要自由写一句话。先按槽位提取信息，只输出 JSON：
{"做了什么": "", "发现了什么": "", "方法类型": "", "具体场景": "", "样本规模": "", "依据句": ""}

槽位要求：
- "做了什么"：论文实际做法，必须来自标题或摘要
- "发现了什么"：优先写最有价值的结论、张力、限制或判断；如果摘要真的没有结论，就留空
- "方法类型"：只写实验、访谈、问卷、共创工作坊、系统、数据集、评测、综述等；摘要没说就留空
- "具体场景"：只写能决定适用边界的场景、人群或任务，如残障玩家、社交 VR、AR 导航、手部追踪；不要写作者机构和理论框架
- "样本规模"：只写摘要明确给出的数字，如 12 人、200 次试验；摘要没说就留空，不能猜
- "依据句"：摘要里支持上面判断的原句或短语，不能编。宁可短，不要编数字

写作标准：
- 目标是最后能拼成一句通俗中文，像给同门扫一眼
- 优先回答“所以呢”，但摘要没有明确发现时就在 "发现了什么" 写「摘要没有给出明确结论」
- 优先把发现写成这几类之一：打破预期（本以为 A，其实 B）、意外代价（做到了 A，但代价是 B）、失效条件（A 在 B 情况下不成立）、反直觉排序（真正起作用的不是 A 而是 B）、适用边界（A 只在 B 场景下有用）
- 如果发现只是多个因素并列，只保留最出人意料或最影响设计判断的一项
- 如果没有发现，就把做法写得具体：方法 + 对象/场景 + 任务
- 如果是数据集、工具或系统论文，不要硬找反常识发现；重点写规模、包含什么、能拿来做什么
- 不要以「这篇」「本文」「该研究」「本论文」开头
- 不要编造摘要里没有的信息；不确定就让 "发现了什么" 为空
- 只输出 JSON，不要解释，不要 markdown
"""


ATTITUDE_PROBES: List[Dict[str, Any]] = [
    {
        "id": "probe-ableist-avatar",
        "title": "Safety vs. Social Image: Co-Designing Protection Mechanisms Against Ableist Harassment with People with Disabilities in Social Virtual Reality",
        "abstract": (
            "We co-designed social VR safety tools with 11 people with disabilities. "
            "Participants preferred avatars and profile cues that made disability identity visible for self-expression, "
            "but these cues also made them recognizable targets for ableist harassment. "
            "Our findings show a tension between protection, disclosure, and social image."
        ),
        "authors": ["Probe Author"],
        "published": "2026-08-17",
        "source": "prompt-probe",
    },
    {
        "id": "probe-ai-privacy",
        "title": "Personalization or Privacy: How Designers Use Sensitive Context in Generative AI Tools",
        "abstract": (
            "In interviews with 18 designers, we found that richer personal context made generative AI suggestions more relevant, "
            "but it also increased privacy concerns and led participants to avoid sensitive prompts. "
            "The study highlights a trade-off between personalization quality and disclosure risk."
        ),
        "authors": ["Probe Author"],
        "published": "2026-08-17",
        "source": "prompt-probe",
    },
    {
        "id": "probe-ar-low-vision",
        "title": "In-the-Wild AR Navigation for People with Low Vision",
        "abstract": (
            "Twelve low-vision users used an AR navigation prototype outdoors for seven days. "
            "While users appreciated persistent visual cues, glare, shadows, and nonstandard road markings caused missed cues, "
            "forcing participants to slow down or switch back to audio guidance."
        ),
        "authors": ["Probe Author"],
        "published": "2026-08-17",
        "source": "prompt-probe",
    },
    {
        "id": "probe-design-ai-convergence",
        "title": "Generative AI in Early Design Collaboration",
        "abstract": (
            "Across six design teams, LLM-generated alternatives helped teams move faster in brainstorming, "
            "but repeated exposure to similar suggestions converged the teams on familiar concepts and reduced discussion of edge cases. "
            "The results reveal a cost of speed in collaborative ideation."
        ),
        "authors": ["Probe Author"],
        "published": "2026-08-17",
        "source": "prompt-probe",
    },
    {
        "id": "probe-cross-cultural-moodboards",
        "title": "Cross-Cultural Design Communication with Shared Moodboards",
        "abstract": (
            "We studied remote design teams using shared moodboards for cross-cultural communication. "
            "Moodboards reduced ambiguity during early discussion, but culturally specific references were misread and created false agreement, "
            "causing teams to discover disagreement only after prototyping."
        ),
        "authors": ["Probe Author"],
        "published": "2026-08-17",
        "source": "prompt-probe",
    },
]

DATASET_ARXIV_IDS = [
    "2608.13715",
    "2605.21796",
    "2406.19353",
    "2603.06648",
    "2411.05184",
]

METHOD_SYSTEM_ARXIV_IDS = [
    "2608.04737",
    "2503.01257",
    "1902.05356",
    "1903.06397",
    "2208.10771",
]


def call_openai_with_prompt(prompt: str, paper: Dict[str, Any]) -> Dict[str, Any]:
    original_prompt = main.SUMMARY_PROMPT
    try:
        main.SUMMARY_PROMPT = prompt
        raw = main.summarize_with_openai(paper)
    finally:
        main.SUMMARY_PROMPT = original_prompt

    slots = main.parse_summary_slots(raw)
    rendered_paper = deepcopy(paper)
    summary = main.normalize_summary(raw, rendered_paper)
    clean_finding = ""
    clean_action = ""
    branch = "raw"
    if slots:
        clean_finding = main.strip_abstract_relation_tail(
            main.clean_summary_piece(slots.get("发现了什么", ""))
        )
        clean_action = main.clean_summary_piece(slots.get("做了什么", ""))
        if main.is_substantive_finding(clean_finding) and not main.prefers_action_for_artifact_paper(slots):
            branch = "finding"
        elif clean_action:
            branch = "action"
        else:
            branch = "fallback"
    return {
        "raw": raw,
        "slots": slots,
        "finding": slots.get("发现了什么", "") if slots else "",
        "clean_finding": clean_finding,
        "action": clean_action,
        "branch": branch,
        "summary": summary,
    }


def fetch_arxiv_papers(arxiv_ids: List[str], probe_kind: str) -> List[Dict[str, Any]]:
    body = main.get_text(
        main.ARXIV_API,
        {"id_list": ",".join(arxiv_ids)},
        timeout=30,
    )
    ns = {"a": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(body)
    by_id: Dict[str, Dict[str, Any]] = {}
    for entry in root.findall("a:entry", ns):
        abs_url = entry.find("a:id", ns).text.strip()
        paper_id = abs_url.rsplit("/", 1)[-1]
        published = entry.find("a:published", ns)
        paper = {
            "id": paper_id,
            "title": " ".join(entry.find("a:title", ns).text.split()),
            "abstract": " ".join(entry.find("a:summary", ns).text.split()),
            "url": main.canonical_arxiv_url(paper_id, abs_url),
            "authors": [
                author.find("a:name", ns).text
                for author in entry.findall("a:author", ns)
            ],
            "published": published.text[:10] if published is not None else "",
            "source": "arXiv",
            "probe_kind": probe_kind,
        }
        by_id[paper_id.split("v", 1)[0]] = paper
    return [by_id[arxiv_id] for arxiv_id in arxiv_ids if arxiv_id in by_id]


def branch_for_slots(slots: Dict[str, str]) -> str:
    clean_finding = main.strip_abstract_relation_tail(
        main.clean_summary_piece(slots.get("发现了什么", ""))
    )
    clean_action = main.clean_summary_piece(slots.get("做了什么", ""))
    if main.is_framework_keyword_list(slots, clean_action):
        clean_action = ""
    if main.is_substantive_finding(clean_finding) and not main.prefers_action_for_artifact_paper(slots):
        return "finding"
    if clean_action:
        return "action"
    return "fallback"


def run_ab_eval(papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    results = []
    for idx, paper in enumerate(papers):
        if idx:
            time.sleep(float(os.environ.get("EVAL_REQUEST_DELAY_SECONDS", "0.5")))
        old_result = call_openai_with_prompt(OLD_SUMMARY_PROMPT, paper)
        time.sleep(float(os.environ.get("EVAL_REQUEST_DELAY_SECONDS", "0.5")))
        new_result = call_openai_with_prompt(main.SUMMARY_PROMPT, paper)
        results.append(
            {
                "id": paper["id"],
                "title": paper["title"],
                "old": old_result,
                "new": new_result,
            }
        )
    return results


def run_new_prompt_eval(papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    results = []
    for idx, paper in enumerate(papers):
        if idx:
            time.sleep(float(os.environ.get("EVAL_REQUEST_DELAY_SECONDS", "0.5")))
        result = call_openai_with_prompt(main.SUMMARY_PROMPT, paper)
        results.append(
            {
                "id": paper["id"],
                "title": paper["title"],
                "url": paper.get("url", ""),
                "probe_kind": paper.get("probe_kind", ""),
                "new": result,
            }
        )
    return results


def run_artifact_eval() -> List[Dict[str, Any]]:
    papers = fetch_arxiv_papers(DATASET_ARXIV_IDS, "dataset")
    papers.extend(fetch_arxiv_papers(METHOD_SYSTEM_ARXIV_IDS, "method_system"))
    return run_new_prompt_eval(papers)


def run_golden_negative_eval(path: str = GOLDEN_NEGATIVE_PATH) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        fixture = json.load(fh)

    local_results = []
    for case in fixture.get("local_cases", []):
        paper = case.get("paper") or {"title": case["id"], "abstract": ""}
        slots = case.get("slots", {})
        summary = main.render_summary_from_slots(slots, paper)
        branch = branch_for_slots(slots)
        forbidden = case.get("forbidden_substrings", [])
        passed = branch == case.get("expected_branch")
        if case.get("expected_summary"):
            passed = passed and summary == case["expected_summary"]
        passed = passed and all(item not in summary for item in forbidden)
        local_results.append(
            {
                "id": case["id"],
                "category": case.get("category", ""),
                "branch": branch,
                "summary": summary,
                "expected_branch": case.get("expected_branch"),
                "expected_summary": case.get("expected_summary", ""),
                "passed": passed,
            }
        )

    humanize_results = []
    for case in fixture.get("humanize_cases", []):
        candidate = main.normalize_humanized_summary(case.get("candidate", ""))
        precise = case.get("precise", "")
        safe = main.is_humanized_summary_safe(candidate, precise, {})
        humanize_results.append(
            {
                "id": case["id"],
                "category": case.get("category", ""),
                "candidate": candidate,
                "length": len(candidate),
                "safe": safe,
                "expected_safe": case.get("expected_safe"),
                "passed": safe == case.get("expected_safe"),
            }
        )

    api_cases = fixture.get("api_cases", [])
    api_results = []
    if api_cases:
        ids = [case["arxiv_id"] for case in api_cases]
        papers = {
            paper["id"].split("v", 1)[0]: paper
            for paper in fetch_arxiv_papers(ids, "golden_negative")
        }
        for idx, case in enumerate(api_cases):
            if idx:
                time.sleep(float(os.environ.get("EVAL_REQUEST_DELAY_SECONDS", "0.5")))
            paper = papers.get(case["arxiv_id"])
            if not paper:
                api_results.append(
                    {
                        "id": case["id"],
                        "arxiv_id": case["arxiv_id"],
                        "expected_branch": case.get("expected_branch"),
                        "passed": False,
                        "error": "arXiv paper not found",
                    }
                )
                continue
            paper["probe_kind"] = case.get("category", "")
            result = call_openai_with_prompt(main.SUMMARY_PROMPT, paper)
            api_results.append(
                {
                    "id": case["id"],
                    "arxiv_id": case["arxiv_id"],
                    "title": paper["title"],
                    "branch": result["branch"],
                    "summary": result["summary"],
                    "expected_branch": case.get("expected_branch"),
                    "passed": result["branch"] == case.get("expected_branch"),
                }
            )

    return {
        "fixture": path,
        "local": local_results,
        "humanize": humanize_results,
        "api": api_results,
        "passed": all(item["passed"] for item in local_results + humanize_results + api_results),
    }


def main_eval() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set.")

    mode = sys.argv[1] if len(sys.argv) > 1 else "ab"
    if mode == "ab":
        payload: Any = run_ab_eval(ATTITUDE_PROBES)
    elif mode == "artifacts":
        payload = run_artifact_eval()
    elif mode == "golden":
        path = sys.argv[2] if len(sys.argv) > 2 else GOLDEN_NEGATIVE_PATH
        payload = run_golden_negative_eval(path)
    elif mode == "all":
        payload = {
            "ab": run_ab_eval(ATTITUDE_PROBES),
            "artifacts": run_artifact_eval(),
            "golden": run_golden_negative_eval(),
        }
    else:
        raise ValueError("mode must be one of: ab, artifacts, golden, all")

    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    print()


if __name__ == "__main__":
    main_eval()
