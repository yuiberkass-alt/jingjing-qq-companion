"""Merge duplicates and retire memories that a newer one replaced.

Runs after a summarisation pass and from the console. It never deletes: a
merged-away row keeps its history and is only marked as superseded.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path


def _norm(text: str) -> str:
    return re.sub(r"[\s，。！？；、,.!?;:~～…\"'“”‘’()（）]+", "", text or "").lower()


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def consolidate(db_path: Path, *, limit: int = 500) -> dict:
    if not db_path.is_file():
        return {"ok": False, "reason": "no database"}
    con = sqlite3.connect(str(db_path), timeout=8)
    con.row_factory = sqlite3.Row
    merged = 0
    archived = 0
    try:
        rows = con.execute(
            "SELECT id, platform_id, bot_id, scope, group_id, user_id, category, content,"
            " importance, confidence, evidence_count, created_at FROM memories"
            " WHERE status='active' AND superseded_by IS NULL ORDER BY id LIMIT ?", (limit,)
        ).fetchall()
        buckets: dict[tuple, list[sqlite3.Row]] = {}
        for row in rows:
            key = (row["platform_id"], row["bot_id"], row["scope"], row["group_id"],
                   row["user_id"], row["category"], _norm(row["content"]))
            buckets.setdefault(key, []).append(row)
        stamp = _now()
        for key, group in buckets.items():
            if len(group) < 2:
                continue
            keep = max(group, key=lambda r: (int(r["evidence_count"] or 1), -int(r["id"])))
            total = sum(int(r["evidence_count"] or 1) for r in group)
            con.execute(
                "UPDATE memories SET evidence_count=?, importance=?, last_seen_at=?, updated_at=?"
                " WHERE id=?",
                (total, max(int(r["importance"] or 1) for r in group), stamp, stamp, keep["id"]),
            )
            for row in group:
                if row["id"] == keep["id"]:
                    continue
                con.execute("UPDATE memories SET superseded_by=?, status='archived', updated_at=?"
                            " WHERE id=?", (keep["id"], stamp, row["id"]))
                con.execute(
                    "INSERT INTO memory_revisions(memory_id, action, actor, before_json, after_json, recorded_at)"
                    " VALUES(?,?,?,?,?,?)",
                    (row["id"], "merge", "consolidate", json.dumps({"content": row["content"]}, ensure_ascii=False),
                     json.dumps({"superseded_by": keep["id"]}, ensure_ascii=False), stamp),
                )
                merged += 1
        con.commit()
    finally:
        con.close()
    return {"ok": True, "merged": merged, "archived": archived}


def stale(db_path: Path, *, days: int = 120) -> list[dict]:
    """Old memories that were never reinforced. Reported, never auto-removed."""
    if not db_path.is_file():
        return []
    cutoff = (datetime.now().astimezone() - timedelta(days=days)).isoformat(timespec="seconds")
    con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=4)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT id, scope, group_id, user_id, category, content, last_seen_at FROM memories"
            " WHERE status='active' AND COALESCE(NULLIF(last_seen_at,''), created_at) < ?"
            " AND evidence_count <= 1 ORDER BY id", (cutoff,)
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        con.close()

TAG_SPLIT = re.compile(r"[，。！？；、,.!?;:\s]+")


def _tags(content: str) -> list[str]:
    pieces = [p.strip("的了啦呀嘛呢") for p in TAG_SPLIT.split(content or "") if len(p.strip()) >= 2]
    return pieces


def refine_groups(db_path: Path, *, minimum: int = 12, top: int = 3) -> dict:
    """One evolving line per group: what this group mostly talks about.

    Only rewritten when the top tags actually change, so it does not churn.
    """
    if not db_path.is_file():
        return {"ok": False}
    con = sqlite3.connect(str(db_path), timeout=8)
    con.row_factory = sqlite3.Row
    updated = 0
    try:
        groups = [row[0] for row in con.execute(
            "SELECT group_id FROM memories WHERE scope IN ('group','member') AND status='active'"
            " AND superseded_by IS NULL GROUP BY group_id HAVING COUNT(*) >= ?", (minimum,))]
        for group_id in groups:
            rows = con.execute(
                "SELECT content FROM memories WHERE group_id=? AND status='active'"
                " AND superseded_by IS NULL ORDER BY evidence_count DESC, id DESC LIMIT 60",
                (group_id,)).fetchall()
            phrases: set[str] = set()
            for row in rows:
                phrases.update(_tags(row["content"]))
            # A topic counts when the phrase shows up in several memories, even
            # if each sentence words it differently.
            counts: dict[str, int] = {}
            for phrase in phrases:
                hits = sum(1 for row in rows if phrase in row["content"])
                if hits >= 2:
                    counts[phrase] = hits
            ranked = sorted(counts.items(), key=lambda kv: (-kv[1], -len(kv[0]), kv[0]))
            best: list[str] = []
            for phrase, _ in ranked:
                if any(phrase in other or other in phrase for other in best):
                    continue  # one topic, one label
                best.append(phrase)
                if len(best) >= top:
                    break
            if not best:
                continue
            line = "群里常聊：" + "、".join(best)
            current = con.execute(
                "SELECT id, content FROM memories WHERE group_id=? AND source_ref='refined:auto'"
                " AND status='active' LIMIT 1", (group_id,)).fetchone()
            stamp = _now()
            if current is None:
                con.execute(
                    "INSERT INTO memories(platform_id, bot_id, scope, group_id, user_id, category, content,"
                    " confidence, importance, status, source_ref, evidence_count, last_seen_at,"
                    " created_at, updated_at) VALUES('*','*','group',?,'','group_lore',?,0.6,1,'active',"
                    " 'refined:auto',1,?,?,?)", (group_id, line, stamp, stamp, stamp))
                updated += 1
            elif current["content"] != line:
                con.execute("UPDATE memories SET content=?, updated_at=? WHERE id=?",
                            (line, stamp, current["id"]))
                con.execute(
                    "INSERT INTO memory_revisions(memory_id, action, actor, before_json, after_json, recorded_at)"
                    " VALUES(?,?,?,?,?,?)",
                    (current["id"], "refine", "consolidate", json.dumps({"content": current["content"]}, ensure_ascii=False),
                     json.dumps({"content": line}, ensure_ascii=False), stamp))
                updated += 1
            # L3: her own note about how to behave in this group, rebuilt from
            # measured behaviour plus the topics above.
            self_note = _self_note(group_id, con, best)
            if self_note:
                updated += _upsert_note(con, group_id, self_note)
        con.commit()
    finally:
        con.close()
    return {"ok": True, "refined": updated}


def forget(db_path: Path, *, days: int = 120, limit: int = 5) -> int:
    """Retire low-value memories that were never reinforced.

    Soft only: rows are archived, never deleted, so a wrong call is reversible
    from the console.
    """
    if not db_path.is_file():
        return 0
    cutoff = (datetime.now().astimezone() - timedelta(days=days)).isoformat(timespec="seconds")
    con = sqlite3.connect(str(db_path), timeout=8)
    con.row_factory = sqlite3.Row
    archived = 0
    try:
        rows = con.execute(
            "SELECT id, content FROM memories WHERE status='active' AND superseded_by IS NULL"
            " AND COALESCE(NULLIF(last_seen_at,''), created_at) < ? AND evidence_count <= 1"
            " AND category NOT IN ('self_note','note') ORDER BY id LIMIT ?", (cutoff, limit)).fetchall()
        stamp = _now()
        for row in rows:
            con.execute("UPDATE memories SET status='archived', updated_at=? WHERE id=?",
                        (stamp, row["id"]))
            con.execute(
                "INSERT INTO memory_revisions(memory_id, action, actor, before_json, after_json, recorded_at)"
                " VALUES(?,?,?,?,?,?)",
                (row["id"], "forget", "consolidate", json.dumps({"content": row["content"]}, ensure_ascii=False),
                 json.dumps({"reason": "stale"}, ensure_ascii=False), stamp))
            archived += 1
        con.commit()
    finally:
        con.close()
    return archived


def _style_hint(group_id: str, con) -> str:
    try:
        row = con.execute("SELECT replies, continued FROM group_style WHERE group_id=?",
                          (group_id,)).fetchone()
    except Exception:
        return ""
    if not row or int(row["replies"] or 0) < 10:
        return ""
    rate = int(row["continued"] or 0) / max(1, int(row["replies"]))
    if rate < 0.35:
        return "回了话常没人接，句子要更短，少追问"
    if rate > 0.65:
        return "大家愿意接着聊，可以多接一句"
    return ""


def _self_note(group_id: str, con, topics: list[str]) -> str:
    """One line of lived experience, not a summary of facts."""
    parts = []
    hint = _style_hint(group_id, con)
    if hint:
        parts.append(hint)
    if topics:
        parts.append("这里常聊 " + "、".join(topics[:2]))
    if not parts:
        return ""
    return "，".join(parts)


def _upsert_note(con, group_id: str, text: str) -> int:
    row = con.execute(
        "SELECT id, content FROM memories WHERE group_id=? AND category='self_note'"
        " AND status='active' LIMIT 1", (group_id,)).fetchone()
    stamp = _now()
    if row is None:
        con.execute(
            "INSERT INTO memories(platform_id, bot_id, scope, group_id, user_id, category, content,"
            " confidence, importance, status, source_ref, evidence_count, last_seen_at,"
            " created_at, updated_at) VALUES('*','*','group',?,'','self_note',?,0.7,2,'active',"
            " 'self:auto',1,?,?,?)", (group_id, text, stamp, stamp, stamp))
        return 1
    if row["content"] == text:
        return 0
    con.execute("UPDATE memories SET content=?, updated_at=?, last_seen_at=? WHERE id=?",
                (text, stamp, stamp, row["id"]))
    return 1
