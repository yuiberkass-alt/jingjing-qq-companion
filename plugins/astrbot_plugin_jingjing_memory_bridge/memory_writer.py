"""Write and filter memory candidates extracted from chat.

Only group and member scopes are written automatically; core memory is still
promoted by the owner. Every write is checked for consent, deduplicated and
recorded in memory_revisions.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

SENSITIVE = re.compile(
    r"(密码|passwd|password|身份证|银行卡|信用卡|手机号|电话号码|住址|家庭住址|"
    r"定位|坐标|门牌|病历|诊断|住院|手术|自杀|自残|裸|色情|政治|反动)"
)
CONTROL = re.compile(r"[\x00-\x1f\x7f]+")
MEMBER_CATEGORIES = {"interest", "preferred_name", "interaction_boundary", "shared_episode", "preference"}
GROUP_CATEGORIES = {"group_lore", "group_rule", "shared_episode", "preference"}
MAX_CONTENT = 120


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def clean(text: str) -> str:
    return CONTROL.sub(" ", str(text or "")).strip()


def acceptable(scope: str, category: str, content: str) -> bool:
    if scope not in {"group", "member"}:
        return False
    allowed = MEMBER_CATEGORIES if scope == "member" else GROUP_CATEGORIES
    if category not in allowed:
        return False
    if SENSITIVE.search(content):
        return False
    return 0 < len(content) <= MAX_CONTENT


def allowed_space(con: sqlite3.Connection, *, platform: str, group_id: str, bot_id: str) -> bool:
    columns = {row[1] for row in con.execute("PRAGMA table_info(spaces)")}
    extra = " AND approved=1" if "approved" in columns else ""
    row = con.execute(
        "SELECT enabled FROM spaces WHERE group_id=? AND (platform_id=? OR platform_id='*')"
        " AND (bot_id=? OR bot_id='*')" + extra + " LIMIT 1",
        (group_id, platform, bot_id),
    ).fetchone()
    return bool(row and row[0] == 1)


def member_consented(con: sqlite3.Connection, *, group_id: str, user_id: str, platform: str, bot_id: str) -> bool:
    """An explicit choice always wins; otherwise the group's default decides.

    With auto_consent on (the default), approving a group is enough for its
    members: the bot remembers like ChatGPT does and the owner can review or
    delete afterwards. A member can still opt out with an explicit 0.
    """
    row = con.execute(
        "SELECT consent FROM consents WHERE group_id=? AND user_id=?"
        " AND (platform_id=? OR platform_id='*') AND (bot_id=? OR bot_id='*')"
        " ORDER BY platform_id='*' LIMIT 1",
        (group_id, user_id, platform, bot_id),
    ).fetchone()
    if row is not None:
        return bool(row[0] == 1)
    columns = {info[1] for info in con.execute("PRAGMA table_info(spaces)")}
    if "auto_consent" not in columns:
        return False
    space = con.execute(
        "SELECT auto_consent FROM spaces WHERE group_id=?"
        " AND (platform_id=? OR platform_id='*') AND (bot_id=? OR bot_id='*') LIMIT 1",
        (group_id, platform, bot_id),
    ).fetchone()
    return bool(space and int(space[0] or 0) == 1)


def read_setting(db_path: Path, key: str) -> str | None:
    """Read one console setting; returns None when unset or unreadable."""
    if not db_path.is_file():
        return None
    try:
        con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=3)
        try:
            row = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return row[0] if row else None
        finally:
            con.close()
    except Exception:
        return None


def space_ok(db_path: Path, *, platform: str, bot_id: str, group_id: str) -> bool:
    """Cheap pre-check so capture never costs a model call in an unapproved group."""
    if not db_path.is_file():
        return False
    con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=3)
    try:
        return allowed_space(con, platform=platform, group_id=group_id, bot_id=bot_id)
    except Exception:
        return False
    finally:
        con.close()


def write_candidates(
    db_path: Path,
    *,
    platform: str,
    bot_id: str,
    group_id: str,
    user_id: str,
    candidates: list[dict],
    source: str = "auto",
    daily_cap: int = 40,
) -> list[dict]:
    """Insert accepted candidates; returns what was written and what was skipped."""
    written: list[dict] = []
    if not db_path.is_file():
        return written
    con = sqlite3.connect(str(db_path), timeout=8)
    con.row_factory = sqlite3.Row
    try:
        if not allowed_space(con, platform=platform, group_id=group_id, bot_id=bot_id):
            return []
        # Personal memory needs that member's consent; public group lore only
        # needs the group itself to be approved and enabled.
        consented = member_consented(con, group_id=group_id, user_id=user_id,
                                     platform=platform, bot_id=bot_id)
        today = now()[:10]
        used = con.execute(
            "SELECT COUNT(*) FROM memories WHERE scope IN ('group','member') AND source_ref LIKE ?"
            " AND created_at LIKE ?", (source + "%", today + "%"),
        ).fetchone()[0]
        budget = max(0, daily_cap - used)
        for item in candidates[:2]:
            if budget <= 0:
                break
            scope = str(item.get("scope") or "member")
            category = str(item.get("category") or "preference")
            content = clean(item.get("content"))
            if not acceptable(scope, category, content):
                continue
            if scope == "member" and not consented:
                continue
            exists = con.execute(
                "SELECT id, evidence_count FROM memories WHERE group_id=?"
                " AND (user_id=? OR scope='group') AND content=? AND status='active'"
                " AND superseded_by IS NULL",
                (group_id, user_id if scope == "member" else "", content),
            ).fetchone()
            if exists:
                # Same fact again: counts as more evidence instead of a new row.
                stamp = now()
                evidence = int(exists["evidence_count"] or 1) + 1
                con.execute(
                    "UPDATE memories SET evidence_count=?, last_seen_at=?,"
                    " confidence=MIN(1.0, confidence + 0.05),"
                    " importance=MIN(3, MAX(importance, CASE WHEN ? >= 3 THEN 3 WHEN ? >= 2 THEN 2 ELSE 1 END)),"
                    " updated_at=? WHERE id=?",
                    (evidence, stamp, evidence, evidence, stamp, exists["id"]),
                )
                con.execute(
                    "INSERT INTO memory_revisions(memory_id, action, actor, before_json, after_json, recorded_at)"
                    " VALUES(?,?,?,?,?,?)",
                    (exists["id"], "reinforce", source, "{}",
                     json.dumps({"evidence_count": evidence}, ensure_ascii=False), stamp),
                )
                budget -= 1
                continue
            stamp = now()
            cur = con.execute(
                "INSERT INTO memories(platform_id, bot_id, scope, group_id, user_id, category, content,"
                " confidence, importance, status, source_ref, created_at, updated_at)"
                " VALUES(?,?,?,?,?,?,?,?,?, 'active', ?, ?, ?)",
                (platform, bot_id, scope, group_id, user_id if scope == "member" else "",
                 category, content, float(item.get("confidence") or 0.7),
                 2, source + ":auto", stamp, stamp),
            )
            con.execute(
                "INSERT INTO memory_revisions(memory_id, action, actor, before_json, after_json, recorded_at)"
                " VALUES(?,?,?,?,?,?)",
                (cur.lastrowid, "create", source, "{}", '{"auto_extracted": true}', stamp),
            )
            # A contradicted fact is retired, not kept alongside the new one.
            replaces = str(item.get("replaces") or "").strip()
            if replaces:
                old = con.execute(
                    "SELECT id FROM memories WHERE group_id=? AND category=? AND status='active'"
                    " AND superseded_by IS NULL AND content LIKE ? AND id<>? LIMIT 1",
                    (group_id, category, "%" + replaces + "%", cur.lastrowid)).fetchone()
                if old:
                    con.execute("UPDATE memories SET superseded_by=?, status='archived', updated_at=?"
                                " WHERE id=?", (cur.lastrowid, stamp, old[0]))
                    con.execute(
                        "INSERT INTO memory_revisions(memory_id, action, actor, before_json, after_json, recorded_at)"
                        " VALUES(?,?,?,?,?,?)",
                        (old[0], "supersede", source, "{}",
                         json.dumps({"superseded_by": cur.lastrowid}, ensure_ascii=False), stamp))
            written.append({"id": cur.lastrowid, "scope": scope, "category": category, "content": content})
            budget -= 1
        con.commit()
    finally:
        con.close()
    return written
