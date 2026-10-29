"""Non-video content agents used by the unified FrameForge workflow.

The social agents intentionally follow the original post_generate_final
contract: they ask the selected LLM for a JSON object containing the actual
post text and a separate hashtag list. The parser is kept explicit because
local Ollama models can sometimes return incomplete structured-output
objects when a strict Pydantic schema is used directly.
"""

import json
import re
from typing import Any, List

from agents.llm_provider import get_llm


def _llm(state):
    return get_llm(
        provider=state.get("provider", "local"),
        api_key=state.get("api_key", ""),
        model=state.get("model", ""),
        base_url=state.get("base_url", ""),
    )


def _content(response: Any) -> str:
    value = getattr(response, "content", response)
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("text"):
                parts.append(str(item["text"]))
        return "\n".join(parts)
    return str(value)


def _parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Recover the first JSON object if the model added a short preface.
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
    return {"post": "", "posts": [], "hashtags": [], "_raw": text}


def _clean_hashtags(values: Any) -> List[str]:
    if not isinstance(values, list):
        values = [values] if isinstance(values, str) else []
    result = []
    for value in values:
        value = str(value).strip()
        if not value:
            continue
        if not value.startswith("#"):
            value = "#" + value
        value = re.sub(r"\s+", "", value)
        if value not in result:
            result.append(value)
    return result[:5]


def _extract_post(data: dict) -> str:
    for key in ("post", "content", "text", "body", "message"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _extract_posts(data: dict) -> List[str]:
    value = data.get("posts")
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    post = _extract_post(data)
    return [post] if post else []


def _social_json_call(state, platform: str, research: dict) -> dict:
    if platform == "LinkedIn":
        output_schema = '{"platform":"LinkedIn","post":"...","hashtags":["#...","#..."]}'
        instructions = """
Create ONE complete, publication-ready LinkedIn post.
The post field MUST contain the full body of the LinkedIn post, not just a
headline, title, summary, or hashtags. Use 2-5 short paragraphs when useful.
Include a clear opening, the main information supported by the research, and
a natural closing. Do not put hashtags inside the post field.
Return 3-5 relevant hashtags separately in the hashtags array.
"""
    else:
        output_schema = '{"platform":"X","posts":["..."],"hashtags":["#...","#..."]}'
        instructions = """
Create complete publication-ready content for X.
For a simple topic, return exactly one post in the posts array. If the source
requires multiple connected messages, return a short thread (2-4 posts).
Each posts item MUST contain actual post text, not just a headline or
hashtags. Do not put hashtags inside the posts items.
Return 2-4 relevant hashtags separately in the hashtags array.
"""

    prompt = f"""
You are the {platform} Content Agent in an institutional content
transformation platform.

Use ONLY the supplied research brief. Never invent facts, names, dates,
statistics, achievements, events, or claims. Do not disclose operational,
classified, or sensitive information. Do not create political persuasion or
sensational language.

{instructions}

Formatting requirements:
- Target language: {state.get('language', 'English')}
- Target audience: {state.get('audience', 'General Audience')}
- Tone: {state.get('tone', 'informative')}
- Detail level: {state.get('detail_level', 'standard')}
- Hashtags must be separate from the post text.
- Return JSON ONLY. No Markdown fences. No explanation before or after JSON.

Required JSON shape:
{output_schema}

RESEARCH BRIEF:
{json.dumps(research, ensure_ascii=False, indent=2)}
"""

    response = _llm(state).invoke(prompt)
    data = _parse_json(_content(response))

    # One corrective pass if the model returned only hashtags or otherwise
    # omitted the actual post body. This is especially useful with local LLMs.
    if platform == "LinkedIn":
        if not _extract_post(data):
            retry = f"""
Your previous response did not contain a usable LinkedIn post body.
Rewrite it now. The JSON field 'post' MUST contain 2-5 complete paragraphs
of actual publication text. The hashtags array is separate.
Return ONLY valid JSON in exactly this shape:
{output_schema}

Research:
{json.dumps(research, ensure_ascii=False, indent=2)}
"""
            response = _llm(state).invoke(retry)
            data = _parse_json(_content(response))
        return {
            "post": _extract_post(data),
            "hashtags": _clean_hashtags(data.get("hashtags", [])),
        }

    posts = _extract_posts(data)
    if not posts:
        retry = f"""
Your previous response did not contain a usable X post.
Return actual post text in the 'posts' array. Do not return only hashtags.
Return ONLY valid JSON in exactly this shape:
{output_schema}

Research:
{json.dumps(research, ensure_ascii=False, indent=2)}
"""
        response = _llm(state).invoke(retry)
        data = _parse_json(_content(response))
        posts = _extract_posts(data)

    return {
        "posts": posts[:4],
        "hashtags": _clean_hashtags(data.get("hashtags", [])),
    }


def research_agent(state):
    topic = state["topic"]
    prompt = f"""
You are the Research and Planning Agent for an official institutional
content transformation platform.

Convert ONLY the operator-supplied source into a factual brief.
Rules:
- Use only information supplied by the operator.
- Never invent names, dates, statistics, achievements, events or claims.
- Do not create operational, classified or sensitive information.
- Separate uncertain claims instead of presenting them as facts.
- Do not claim external verification was performed.

Return JSON ONLY with this shape:
{{"summary":"...","facts":[],"uncertain_claims":[],"sensitive_items":[],"writing_guidance":[]}}

SOURCE:
{topic}
TARGET LANGUAGE: {state.get('language', 'English')}
TARGET AUDIENCE: {state.get('audience', 'General Audience')}
DETAIL LEVEL: {state.get('detail_level', 'standard')}
"""
    data = _parse_json(_content(_llm(state).invoke(prompt)))
    return {
        "summary": str(data.get("summary", "")).strip(),
        "facts": data.get("facts", []) if isinstance(data.get("facts", []), list) else [],
        "uncertain_claims": data.get("uncertain_claims", []) if isinstance(data.get("uncertain_claims", []), list) else [],
        "sensitive_items": data.get("sensitive_items", []) if isinstance(data.get("sensitive_items", []), list) else [],
        "writing_guidance": data.get("writing_guidance", []) if isinstance(data.get("writing_guidance", []), list) else [],
    }


def linkedin_agent(state, research: dict):
    return _social_json_call(state, "LinkedIn", research)


def x_agent(state, research: dict):
    return _social_json_call(state, "X", research)


def generate_social_outputs(state, selected_outputs):
    """Generate selected social deliverables from one shared research brief."""
    selected = {item.lower() for item in selected_outputs}
    if not ({"linkedin", "x"} & selected):
        return {}

    research = research_agent(state)
    result = {"research": research}

    if "linkedin" in selected:
        result["linkedin"] = linkedin_agent(state, research)
    if "x" in selected:
        result["x_post"] = x_agent(state, research)

    return result
