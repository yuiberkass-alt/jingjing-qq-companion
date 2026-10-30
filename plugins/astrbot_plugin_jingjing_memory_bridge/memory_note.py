"""One short, editable text note per person, like ChatGPT's memory entries.

Instead of piling up raw lines ("在吗", "对的对的"), the note is rewritten each
time: the model reads the previous note plus the newest exchange and produces a
compact description that stays under a couple of sentences.
"""
from __future__ import annotations

import copy
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

NOTE_CATEGORY = "note"
MAX_CHARS = 220
FENCE = re.compile(r"^```(?:json)?|^```$", re.MULTILINE)

SYSTEM = (
    "你在维护一条关于某个人的记忆笔记。读旧笔记和最近的对话，重写这条笔记。"
    "只保留长期有用的事实：称呼、稳定偏好、在意的事、明确的边界、共同经历。"
    "不要写对话原话，不要写一次性的安排，不要写情绪化的瞬间，不要写关于机器人自己的事。"
    "用第三人称陈述，一行一句，最多三句，总长不超过 120 字。"
    "如果新对话没有提供新信息，就原样返回旧笔记。"
    '只输出 JSON：{"note":"..."}'
)


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_note(db: Path, *, platform: str, group_id: str, user_id: str) -> str:
    if not db.is_file():
        return ""
    try:
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=2)
    except Exception:
        return ""
    try:
        row = con.execute(
            "SELECT content FROM memories WHERE platform_id=? AND group_id=? AND user_id=?"
            " AND category=? AND status='active' LIMIT 1",
            (platform, group_id, user_id, NOTE_CATEGORY)).fetchone()
        return row[0] if row else ""
    except Exception:
        return ""
    finally:
        con.close()


def write_note(db: Path, *, platform: str, bot_id: str, group_id: str, user_id: str, text: str) -> bool:
    text = (text or "").strip()[:MAX_CHARS]
    if not text or not db.is_file():
        return False
    con = sqlite3.connect(str(db), timeout=6)
    try:
        stamp = _now()
        row = con.execute(
            "SELECT id FROM memories WHERE platform_id=? AND group_id=? AND user_id=?"
            " AND category=? LIMIT 1",
            (platform, group_id, user_id, NOTE_CATEGORY)).fetchone()
        if row:
            con.execute("UPDATE memories SET content=?, status='active', updated_at=?, last_seen_at=?"
                        " WHERE id=?", (text, stamp, stamp, row[0]))
        else:
            con.execute(
                "INSERT INTO memories(platform_id, bot_id, scope, group_id, user_id, category, content,"
                " confidence, importance, status, source_ref, evidence_count, last_seen_at,"
                " created_at, updated_at) VALUES(?,?,'member',?,?,?,?,0.9,3,'active','note:auto',1,?,?,?)",
                (platform, bot_id, group_id, user_id, NOTE_CATEGORY, text, stamp, stamp, stamp))
        con.commit()
        return True
    finally:
        con.close()


def parse(raw: str) -> str:
    if not raw:
        return ""
    cleaned = FENCE.sub("", raw).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(cleaned[start:end + 1])
            return str(data.get("note") or "").strip()[:MAX_CHARS]
        except Exception:
            pass
    return cleaned.splitlines()[0][:MAX_CHARS] if cleaned else ""


async def refresh_note(provider, *, db: Path, platform: str, bot_id: str, group_id: str,
                       user_id: str, transcript: str, timeout: float = 30.0) -> str:
    import asyncio

    if provider is None or not transcript.strip():
        return ""
    old = read_note(db, platform=platform, group_id=group_id, user_id=user_id)
    config = getattr(provider, "provider_config", None)
    get_model = getattr(provider, "get_model", None)
    if isinstance(config, dict) and callable(get_model) and "deepseek" in str(get_model()).lower():
        provider = copy.copy(provider)
        provider.provider_config = dict(config)
        extras = config.get("custom_extra_body") or {}
        provider.provider_config["custom_extra_body"] = {**extras, "thinking": {"type": "disabled"}}
    prompt = "旧笔记：\n" + (old or "（空）") + "\n\n最近对话：\n" + transcript[-1200:]
    resp = await asyncio.wait_for(
        provider.text_chat(prompt=prompt, system_prompt=SYSTEM, contexts=[], request_max_retries=1),
        timeout=timeout)
    note = parse(getattr(resp, "completion_text", "") or "")
    if note and note != old:
        write_note(db, platform=platform, bot_id=bot_id, group_id=group_id, user_id=user_id, text=note)
        return note
    return old
