"""Per-group social calibration, with the core persona left untouched.

Only counts what actually happened: how often the group carried on after a
reply. No model judgement, no inference about mood or people.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

MIN_SAMPLES = 10


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _connect(db_path: Path, *, readonly: bool = False) -> sqlite3.Connection:
    if readonly:
        con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=2)
        con.execute("PRAGMA query_only=ON")
    else:
        con = sqlite3.connect(str(db_path), timeout=6)
    con.row_factory = sqlite3.Row
    return con


def note_reply(db_path: Path, group_id: str) -> None:
    if not db_path.is_file() or not group_id:
        return
    con = _connect(db_path)
    try:
        con.execute(
            "INSERT INTO group_style(group_id, replies, continued, updated_at) VALUES(?,1,0,?)"
            " ON CONFLICT(group_id) DO UPDATE SET replies=replies+1, updated_at=excluded.updated_at",
            (group_id, _now()))
        con.commit()
    finally:
        con.close()


def reset(db_path: Path, group_id: str) -> None:
    """Start the count over, e.g. after fixing how it was measured."""
    if not db_path.is_file() or not group_id:
        return
    con = _connect(db_path)
    try:
        con.execute("DELETE FROM group_style WHERE group_id=?", (group_id,))
        con.commit()
    finally:
        con.close()


def note_continuation(db_path: Path, group_id: str) -> None:
    if not db_path.is_file() or not group_id:
        return
    con = _connect(db_path)
    try:
        con.execute(
            "UPDATE group_style SET continued=continued+1, updated_at=? WHERE group_id=?",
            (_now(), group_id))
        con.commit()
    finally:
        con.close()


def stats(db_path: Path, group_id: str) -> dict | None:
    if not db_path.is_file() or not group_id:
        return None
    try:
        con = _connect(db_path, readonly=True)
    except Exception:
        return None
    try:
        row = con.execute("SELECT replies, continued FROM group_style WHERE group_id=?",
                          (group_id,)).fetchone()
        return dict(row) if row else None
    except Exception:
        return None
    finally:
        con.close()


def hint(db_path: Path, group_id: str) -> str | None:
    """One line of calibration for this group, or None while the sample is thin."""
    row = stats(db_path, group_id)
    if not row or int(row["replies"] or 0) < MIN_SAMPLES:
        return None
    replies = int(row["replies"])
    rate = int(row["continued"] or 0) / max(1, replies)
    if rate < 0.35:
        return "这个群接完话常常就散了：回复再短一点，别追问，别硬找话题。"
    if rate > 0.65:
        return "这个群愿意接着聊：可以放松一点，多接一句也没关系。"
    return "这个群节奏正常：一句话接住就行，不用刻意拉长。"
