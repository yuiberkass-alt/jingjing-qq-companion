"""Relationship and mood state for one group member.

Deliberately small and private:
  * familiarity is a counter of interactions, not a score shown to anyone
  * the mood is short-lived (minutes) and only shapes the current turn
  * nothing here is ever recalled by the memory reader; it is not a memory
"""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

STAGES = ((0, "new"), (10, "familiar"), (40, "close"), (120, "old"))
DAILY_GAIN_CAP = 10
STAGE_LABEL = {"new": "刚认识", "familiar": "逐渐熟悉", "close": "熟人", "old": "默契老熟人"}
MOOD_TTL = 900  # default seconds a mood stays relevant
# A mood machine, not a single slot: some states outrank others and fade at
# different speeds.
MOOD_PRIORITY = {"comfort": 5, "tsundere": 4, "shy": 3, "proud": 3, "serious": 2, "happy": 2, "calm": 0}
MOOD_TTL_BY_MOOD = {"comfort": 1800, "serious": 900, "tsundere": 600, "shy": 600, "proud": 600, "happy": 420}
MOODS = {
    "comfort": "对方情绪不好，先安慰",
    "proud": "被夸了，可以小得意",
    "shy": "被夸或亲近，有点害羞",
    "tsundere": "被调侃，可以轻轻回嘴",
    "serious": "在问正经问题，认真回答",
    "happy": "气氛轻松，可以更活泼",
    "calm": "",
}
MOOD_RULES = (
    ("comfort", re.compile(r"(难过|难受|好累|累了|想哭|哭了|烦死|不开心|压力|崩溃|失眠|委屈)")),
    ("proud", re.compile(r"(好厉害|太强了|牛啊|真棒|好棒|你真行|厉害)")),
    ("tsundere", re.compile(r"(大肥鱼|胖鱼|笨蛋|二货|傻|蠢|呆)")),
    ("shy", re.compile(r"(可爱|喜欢你|爱你|亲亲|抱抱|贴贴|想你了)")),
    ("serious", re.compile(r"(为什么|怎么|原理|报错|代码|配置|怎么弄|是什么|区别)")),
    ("happy", re.compile(r"(哈哈哈|笑死|好耶|太开心|嘿嘿)")),
)


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def classify_mood(text: str) -> str:
    for mood, pattern in MOOD_RULES:
        if pattern.search(text or ""):
            return mood
    return "calm"


def stage_of(familiarity: int) -> str:
    stage = "new"
    for threshold, name in STAGES:
        if familiarity >= threshold:
            stage = name
    return stage


def _connect(db_path: Path, *, readonly: bool = False) -> sqlite3.Connection:
    if readonly:
        con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=2)
        con.execute("PRAGMA query_only=ON")
    else:
        con = sqlite3.connect(str(db_path), timeout=6)
    con.row_factory = sqlite3.Row
    return con


def bump(db_path: Path, *, platform: str, bot_id: str, group_id: str, user_id: str,
         nickname: str = "") -> dict | None:
    """Record one more interaction; returns the row after the update."""
    if not db_path.is_file() or not (group_id and user_id):
        return None
    con = _connect(db_path)
    try:
        row = con.execute(
            "SELECT interactions, familiarity, stage FROM relations"
            " WHERE platform_id=? AND bot_id=? AND group_id=? AND user_id=?",
            (platform, bot_id, group_id, user_id),
        ).fetchone()
        interactions = int(row["interactions"] or 0) + 1 if row else 1
        # A single loud evening must not turn a stranger into an old friend:
        # familiarity only grows while it is earned, at most 10 a day.
        today = datetime.now().astimezone().date().isoformat()
        gained = 0 if (not row or row["last_day"] != today) else int(row["day_gain"] or 0)
        gain = 1 if gained < DAILY_GAIN_CAP else 0
        familiarity = min(400, int(row["familiarity"] or 0) + gain) if row else gain
        stage = stage_of(familiarity)
        stamp = now()
        con.execute(
            "INSERT INTO relations(platform_id, bot_id, group_id, user_id, nickname, interactions,"
            " familiarity, stage, last_interaction_at, updated_at, last_day, day_gain)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(platform_id, bot_id, group_id, user_id) DO UPDATE SET"
            " nickname=excluded.nickname, interactions=excluded.interactions,"
            " familiarity=excluded.familiarity, stage=excluded.stage,"
            " last_interaction_at=excluded.last_interaction_at, updated_at=excluded.updated_at,"
            " last_day=excluded.last_day, day_gain=excluded.day_gain",
            (platform, bot_id, group_id, user_id, nickname[:40], interactions,
             familiarity, stage, stamp, stamp, today, gained + gain),
        )
        con.commit()
        return {"interactions": interactions, "familiarity": familiarity, "stage": stage}
    finally:
        con.close()


def get(db_path: Path, *, platform: str, bot_id: str, group_id: str, user_id: str) -> dict | None:
    if not db_path.is_file():
        return None
    try:
        con = _connect(db_path, readonly=True)
    except Exception:
        return None
    try:
        row = con.execute(
            "SELECT interactions, familiarity, stage, nickname FROM relations"
            " WHERE platform_id=? AND bot_id=? AND group_id=? AND user_id=?",
            (platform, bot_id, group_id, user_id),
        ).fetchone()
        return dict(row) if row else None
    except Exception:
        return None
    finally:
        con.close()


def set_mood(db_path: Path, *, group_id: str, mood: str, reason: str = "") -> None:
    """Only a mood at least as strong as the current one takes over."""
    if not db_path.is_file() or not group_id:
        return
    current = get_mood(db_path, group_id=group_id)
    if current and MOOD_PRIORITY.get(current, 0) > MOOD_PRIORITY.get(mood, 0):
        # A stronger state holds the floor only briefly; two minutes later the
        # conversation has moved on and a new mood may take over.
        try:
            con = _connect(db_path, readonly=True)
            try:
                row = con.execute("SELECT updated_at FROM moods WHERE group_id=?",
                                  (group_id,)).fetchone()
                age = (datetime.now().astimezone() - datetime.fromisoformat(row[0])).total_seconds()
            finally:
                con.close()
        except Exception:
            age = 0
        if age < 120:
            return
    con = _connect(db_path)
    try:
        stamp = now()
        con.execute(
            "INSERT INTO moods(group_id, mood, reason, updated_at) VALUES(?,?,?,?)"
            " ON CONFLICT(group_id) DO UPDATE SET mood=excluded.mood,"
            " reason=excluded.reason, updated_at=excluded.updated_at",
            (group_id, mood, reason[:60], stamp),
        )
        con.commit()
    finally:
        con.close()


def get_mood(db_path: Path, *, group_id: str, ttl: int = MOOD_TTL) -> str | None:
    if not db_path.is_file():
        return None
    try:
        con = _connect(db_path, readonly=True)
    except Exception:
        return None
    try:
        row = con.execute("SELECT mood, updated_at FROM moods WHERE group_id=?", (group_id,)).fetchone()
        if not row or not row["mood"]:
            return None
        window = MOOD_TTL_BY_MOOD.get(row["mood"], ttl)
        updated = datetime.fromisoformat(row["updated_at"])
        if datetime.now().astimezone() - updated > timedelta(seconds=window):
            return None
        return row["mood"]
    except Exception:
        return None
    finally:
        con.close()
