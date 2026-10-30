"""Turn a stretch of group chat into durable memories, ChatGPT-style.

The cue-based extractor only fires on phrases like "我叫..."; this reads a whole
window of conversation and keeps what a person would actually remember, then
merges with what is already known instead of piling up duplicates.
"""
from __future__ import annotations

import copy
import json
import re

FENCE = re.compile(r"^```(?:json)?|^```$", re.MULTILINE)

SYSTEM = (
    "你是一个记忆整理器。读一段群聊记录，挑出**值得长期记住**的事，像人会记住朋友那样。"
    "值得记的：稳定偏好、称呼、习惯、正在经历的事（工作/学业/生活状态）、明确说过的边界、"
    "和群友之间的共同经历与梗、群里的固定约定。"
    "绝不要记的："
    "1) 任何关于这个 AI/机器人本身的事（模型、上下文、联网、知识库、回复慢、部署），"
    "2) 对人的评价、辱骂、嘲讽（谁傻、谁废物、谁只会吃），"
    "3) 对这个机器人或群友的抱怨、吐槽、情绪宣泄，"
    "4) 一次性的安排、天气、当下情绪、玩笑、转述、猜测，"
    "5) 敏感信息（密码、证件、住址、电话、健康、政治、性、色情）。"
    "只写当事人明确表达的内容，不要脑补。拿不准就不写。"
    '只输出 JSON：{"memories":[{"who":"成员昵称或空","scope":"member|group",'
    '"category":"interest|preferred_name|interaction_boundary|shared_episode|preference|group_lore|group_rule",'
    '"content":"...","replaces":"旧内容片段或空"}]}，没有值得记的就输出 {"memories":[]}。最多 3 条。'
    "如果新内容和已有记忆矛盾（比如以前喜欢猫、现在说更喜欢狗），"
    "在 replaces 里写旧内容的一小段，系统会把旧的那条作废。"
)


def build_prompt(transcript: str, known: list[str]) -> str:
    parts = ["最近的群聊记录：", transcript]
    if known:
        parts.append("已经记住的（不要重复，除非有新增细节）：")
        parts.extend("- " + item for item in known[:12])
    parts.append("请按要求输出 JSON。")
    return "\n".join(parts)


BOT_META = re.compile(
    r"(这个?(AI|机器人|模型|助手)|上下文|联网|知识库|部署|接口|API|token|提示词|"
    r"回复慢|答不上|处理不过来|记忆库|插件)", re.IGNORECASE)
INSULT = re.compile(r"(沙币|傻逼|傻|废物|垃圾|只会吃|去死|脑残|弱智|蠢)")


def acceptable_item(content: str) -> bool:
    """Keep the summary away from meta-talk about the bot and from name-calling."""
    if not content or len(content) > 60:
        return False
    if BOT_META.search(content) or INSULT.search(content):
        return False
    return True


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
    items = data.get("memories")
    if not isinstance(items, list):
        return []
    out: list[dict] = []
    for item in items[:3]:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "").strip()[:80]
        if not acceptable_item(content):
            continue
        out.append({
            "who": str(item.get("who") or "").strip()[:20],
            "scope": "group" if str(item.get("scope")) == "group" else "member",
            "category": str(item.get("category") or "preference"),
            "content": content,
            "replaces": str(item.get("replaces") or "").strip()[:40],
        })
    return out


async def summarize(provider, *, transcript: str, known: list[str], timeout: float = 20.0) -> list[dict]:
    import asyncio

    if provider is None or not transcript.strip():
        return []
    config = getattr(provider, "provider_config", None)
    get_model = getattr(provider, "get_model", None)
    if isinstance(config, dict) and callable(get_model) and "deepseek" in str(get_model()).lower():
        provider = copy.copy(provider)
        provider.provider_config = dict(config)
        extras = config.get("custom_extra_body") or {}
        provider.provider_config["custom_extra_body"] = {**extras, "thinking": {"type": "disabled"}}
    resp = await asyncio.wait_for(
        provider.text_chat(prompt=build_prompt(transcript, known), system_prompt=SYSTEM,
                           contexts=[], request_max_retries=1),
        timeout=timeout,
    )
    return parse(getattr(resp, "completion_text", "") or "")
