"""Ask the chat model whether one message holds a memory worth keeping.

Conservative on purpose: the model may return nothing, the caller still runs
consent/space checks, sensitive内容 is filtered again in memory_writer, and
core memory is never written here (only the owner promotes to core).
"""
from __future__ import annotations

import copy
import json
import re

CUES = re.compile(
    r"(我叫|我是|叫我|别叫|不要叫|喜欢|讨厌|最爱|不吃|不能吃|过敏|习惯|"
    r"记住|以后|我家|我养|我在.{0,6}(上班|上学|工作|读书)|我住)"
)
FENCE = re.compile(r"^```(?:json)?|^```$", re.MULTILINE)

SYSTEM = (
    "你是记忆整理助手。判断这句话里有没有**长期有用、且以后还会用到**的信息。"
    "只提取这几类：称呼偏好、稳定兴趣、明确的互动边界、共同经历、群约定。"
    "日常情绪、一次性的安排、玩笑、吐槽、天气、吃了什么、临时心情都不要记。"
    "涉及密码、证件、住址、电话、健康、政治、色情等敏感内容一律不记。"
    "不要编造，不要推断，只写对方明说的事实。"
    '只输出 JSON：{"candidates":[{"scope":"member","category":"preference","content":"..."}]}，'
    "没有就输出 {\"candidates\":[]}。最多 2 条，每条不超过 40 个字，"
    "用第三人称陈述，例如「喜欢猫，家里养了两只」。"
)


def should_extract(text: str) -> bool:
    return bool(text) and len(text) <= 200 and bool(CUES.search(text))


def build_prompt(text: str, speaker: str) -> str:
    return f"发言人：{speaker}\n这句话：{text}\n请判断是否需要记住，并按格式输出 JSON。"


def parse(raw: str) -> list[dict]:
    if not raw:
        return []
    cleaned = FENCE.sub("", raw).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        return []
    try:
        data = json.loads(cleaned[start:end + 1])
    except Exception:
        return []
    items = data.get("candidates")
    if not isinstance(items, list):
        return []
    out: list[dict] = []
    for item in items[:2]:
        if not isinstance(item, dict):
            continue
        scope = "group" if str(item.get("scope")) == "group" else "member"
        out.append({
            "scope": scope,
            "category": str(item.get("category") or "preference"),
            "content": str(item.get("content") or "").strip()[:80],
        })
    return out


async def extract(provider, *, text: str, speaker: str, timeout: float = 12.0) -> list[dict]:
    import asyncio

    if provider is None:
        return []
    config = getattr(provider, "provider_config", None)
    get_model = getattr(provider, "get_model", None)
    if isinstance(config, dict) and callable(get_model) and "deepseek" in str(get_model()).lower():
        provider = copy.copy(provider)
        provider.provider_config = dict(config)
        extras = config.get("custom_extra_body") or {}
        provider.provider_config["custom_extra_body"] = {**extras, "thinking": {"type": "disabled"}}
    resp = await asyncio.wait_for(
        provider.text_chat(prompt=build_prompt(text, speaker), system_prompt=SYSTEM,
                           contexts=[], request_max_retries=1),
        timeout=timeout,
    )
    return parse(getattr(resp, "completion_text", "") or "")
