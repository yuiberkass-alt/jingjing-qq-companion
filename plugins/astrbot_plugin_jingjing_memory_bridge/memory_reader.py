"""Read-only, fail-closed access to JingJing's layered memory (schema v2).

Scopes:
  core    shared persona memory, applies in every group
  group   public memory of one group
  member  memory about one member inside one group

Rules kept from v0.1:
  * every lookup is read-only, no writes, no model calls
  * group/member recall needs an enabled space AND that member's consent
  * unknown identity, unknown platform or unknown group -> no recall at all
  * data is untrusted: callers render it as data, never as instructions
"""
from __future__ import annotations

import math
import re
import sqlite3
from datetime import datetime
from pathlib import Path

DEFAULT_DB = Path("/AstrBot/data/plugin_data/jingjing_memory/memory.sqlite3")
CATEGORIES = {
    "core": {"identity", "style", "boundary", "preference", "shared_episode"},
    "group": {"self_note", "group_lore", "group_rule", "shared_episode", "preference"},
    "member": {"note", "interest", "preferred_name", "interaction_boundary", "shared_episode", "preference"},
}
MAX_CONTENT = 200


def _clean(text: str) -> str:
    return re.sub(r"[\x00-\x1f\x7f]+", " ", text or "").strip()


def _platform_match(row_value: str, actual: str) -> bool:
    return row_value in ("*", "", actual)


def eligible(*, enabled: bool, platform: str, group_id: str, user_id: str, bot_id: str,
             allowed_groups: set[str], allowed_bots: set[str]) -> bool:
    """Cheap pre-check before touching the database.

    The group whitelist is no longer the gate: the console registers and
    approves groups in the database, so approval takes effect without editing
    plugin config. The bot identity is still checked here, and read_memories
    requires an approved, enabled space.
    """
    return bool(enabled and platform == "aiocqhttp" and group_id and user_id and bot_id
                and bot_id in allowed_bots)


# Small synonym table: people do not repeat the exact word a memory used.
SYNONYMS = {
    "番": "动画 动漫 番剧", "动画": "番 动漫 番剧", "动漫": "番 动画 番剧",
    "游戏": "手游 端游 打游戏", "手游": "游戏 抽卡", "原神": "抽卡 米哈游",
    "猫": "猫咪 小猫 喵", "狗": "狗狗 小狗 汪",
    "累": "疲惫 好累 累死", "难过": "伤心 郁闷 不开心",
}


def _expand(text: str) -> str:
    out = [text or ""]
    for key, extra in SYNONYMS.items():
        if key in (text or ""):
            out.append(extra)
    return " ".join(out)


def _bigrams(text: str) -> set[str]:
    compact = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", text or "")
    if len(compact) < 2:
        return {compact} if compact else set()
    return {compact[index:index + 2] for index in range(len(compact) - 1)}


def _tokens(text: str) -> list[str]:
    compact = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", _expand(text or ""))
    if not compact:
        return []
    if len(compact) == 1:
        return [compact]
    return [compact[i:i + 2] for i in range(len(compact) - 1)]


def _bm25(query: str, docs: list[str], k1: float = 1.3, b: float = 0.7) -> list[float]:
    """Rank memories against the query: a small BM25, no model, no network.

    The old score compared raw bigram overlap, which treated a chatty memory as
    more relevant simply because it contained more words.
    """
    terms = _tokens(query)
    if not terms or not docs:
        return [0.0] * len(docs)
    tokenised = [_tokens(doc) for doc in docs]
    lengths = [len(t) or 1 for t in tokenised]
    avg = sum(lengths) / len(lengths)
    df: dict[str, int] = {}
    for tokens in tokenised:
        for term in set(tokens):
            df[term] = df.get(term, 0) + 1
    n = len(docs)
    scores: list[float] = []
    for tokens, length in zip(tokenised, lengths):
        counts: dict[str, int] = {}
        for token in tokens:
            counts[token] = counts.get(token, 0) + 1
        score = 0.0
        for term in set(terms):
            tf = counts.get(term, 0)
            if not tf:
                continue
            idf = math.log(1 + (n - df.get(term, 0) + 0.5) / (df.get(term, 0) + 0.5))
            score += idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * length / avg))
        scores.append(score)
    return scores


def _freshness(seen: str, half_life_days: float = 30.0) -> float:
    """Small bonus for recent memories, capped so it never dominates matching."""
    try:
        then = datetime.fromisoformat(str(seen))
        days = max(0.0, (datetime.now().astimezone() - then).total_seconds() / 86400)
        return 0.25 * (0.5 ** (days / half_life_days))
    except Exception:
        return 0.0


def read_memories(db_path: Path, *, platform: str, group_id: str, user_id: str, bot_id: str,
                  limit_core: int = 2, limit_group: int = 1, limit_member: int = 3,
                  query: str = "") -> list[dict]:
    if not (platform and group_id and user_id and bot_id) or not db_path.is_file():
        return []
    con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=1)
    try:
        con.execute("PRAGMA query_only=ON")
        columns = {row[1] for row in con.execute("PRAGMA table_info(spaces)")}
        approved_filter = " AND approved=1" if "approved" in columns else ""
        space = con.execute(
            "SELECT enabled FROM spaces WHERE group_id=? AND (platform_id=? OR platform_id='*')"
            " AND (bot_id=? OR bot_id='*')" + approved_filter +
            " ORDER BY platform_id='*' LIMIT 1",
            (group_id, platform, bot_id),
        ).fetchone()
        if not space or space[0] != 1:
            return []
        consent = con.execute(
            "SELECT consent FROM consents WHERE group_id=? AND user_id=?"
            " AND (platform_id=? OR platform_id='*') AND (bot_id=? OR bot_id='*')"
            " ORDER BY platform_id='*' LIMIT 1",
            (group_id, user_id, platform, bot_id),
        ).fetchone()
        if consent is not None:
            member_ok = bool(consent[0] == 1)
        else:
            # No explicit choice from this person: the group's default decides,
            # the same rule the writer uses, so recall never contradicts capture.
            space_columns = {row[1] for row in con.execute("PRAGMA table_info(spaces)")}
            auto = 0
            if "auto_consent" in space_columns:
                auto_row = con.execute(
                    "SELECT auto_consent FROM spaces WHERE group_id=?"
                    " AND (platform_id=? OR platform_id='*') AND (bot_id=? OR bot_id='*') LIMIT 1",
                    (group_id, platform, bot_id),
                ).fetchone()
                auto = int(auto_row[0] or 0) if auto_row else 0
            member_ok = auto == 1
        memory_columns = {row[1] for row in con.execute("PRAGMA table_info(memories)")}
        live = " AND superseded_by IS NULL" if "superseded_by" in memory_columns else ""
        order = "importance DESC, evidence_count DESC, id DESC" if "evidence_count" in memory_columns else "importance DESC, id DESC"
        items: list[dict] = []
        for scope, limit, extra, args in (
            ("core", limit_core, "", ()),
            ("group", limit_group, "", ()),
            ("member", limit_member, " AND user_id=?", (user_id,)),
        ):
            if limit <= 0:
                continue
            if scope == "member" and not member_ok:
                continue
            rows = con.execute(
                "SELECT category, content, COALESCE(NULLIF(last_seen_at,''), created_at) AS seen"
                " FROM memories WHERE scope=? AND status='active'"
                " AND (platform_id=? OR platform_id='*') AND (bot_id=? OR bot_id='*')"
                + (" AND group_id=?" if scope == "group" else "")
                + extra + live +
                " ORDER BY " + order + " LIMIT ?",
                ((scope, platform, bot_id) + ((group_id,) if scope == "group" else ()) + args + (limit * 4,)),
            ).fetchall()
            cleaned = []
            for index, (category, content, seen) in enumerate(rows):
                if category not in CATEGORIES[scope] or not isinstance(content, str):
                    continue
                safe = _clean(content)
                if not (0 < len(safe) <= MAX_CONTENT):
                    continue
                cleaned.append((index, category, safe, seen))
            scores = _bm25(query, [item[2] for item in cleaned])
            scored = [
                (scores[position] + _freshness(seen), -index, category, safe)
                for position, (index, category, safe, seen) in enumerate(cleaned)
            ]
            scored.sort(reverse=True)
            for _, _, category, safe in scored[:limit]:
                items.append({"scope": scope, "category": category, "content": safe})
        return items
    finally:
        con.close()
