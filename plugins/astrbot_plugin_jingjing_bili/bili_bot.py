"""Bilibili side of JingJing: her own account talking to the operator by DM.

Two switches, both explicit:
  reply   - answer private messages (always on once the cookie is saved)
  roam    - browse videos, comment, remember, recommend (only while the
            operator has said yes; revoked by saying no)

Nothing here writes to QQ. Memories go to the same database, tagged platform
"bilibili", so they stay separate from the QQ groups.
"""
from __future__ import annotations

import json
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .bili_api import BiliClient, BiliError

COOKIE_FILE = Path("/AstrBot/data/plugin_data/jingjing_bili/cookie.json")
DB = Path("/AstrBot/data/plugin_data/jingjing_memory/memory.sqlite3")

BV_RE = re.compile(r"(BV[0-9A-Za-z]{10})")
SHORT_RE = re.compile(r"https?://b23\.tv/[0-9A-Za-z]+")
# Standing permission ("以后你可以自己逛") and a one-off errand ("现在去逛逛")
# are different things: the first is a switch, the second is a single trip.
YES = re.compile(r"(以后.{0,4}(可以|允许).{0,4}逛|你可以自己去逛|你自己逛吧|自己去逛逛吧)")
NO = re.compile(r"(别逛|不要逛|不许逛|收回|不同意|别再评论|老实待着|先别逛|停止逛)")
NOW = re.compile(r"(现在|这就|帮我|去)(?:去)?(逛逛|看看|找个视频|推荐几个视频)|你去逛逛")
ROAM_LIMIT_PER_DAY = 3
COMMENT_LIMIT_PER_DAY = 2


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_cookie() -> dict | None:
    try:
        data = json.loads(COOKIE_FILE.read_text(encoding="utf-8"))
        if data.get("sessdata"):
            return data
    except Exception:
        pass
    return None


def client_from_cookie() -> BiliClient | None:
    data = load_cookie()
    if not data:
        return None
    return BiliClient(sessdata=data["sessdata"], bili_jct=data.get("bili_jct", ""),
                      buvid3=data.get("buvid3", ""), uid=data.get("uid", ""))


def _settings(db: Path, key: str, value: str | None = None, *, default: str = "") -> str:
    if not db.is_file():
        return default
    con = sqlite3.connect(str(db), timeout=5)
    try:
        if value is None:
            row = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return row[0] if row else default
        con.execute("INSERT INTO settings(key, value, updated_at) VALUES(?,?,?)"
                    " ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                    (key, value, now()))
        con.commit()
        return value
    finally:
        con.close()


def roam_enabled(db: Path = DB) -> bool:
    return _settings(db, "bili_roam", default="0") == "1"


def set_roam(enabled: bool, db: Path = DB) -> None:
    _settings(db, "bili_roam", "1" if enabled else "0")


def maybe_toggle_roam(text: str, db: Path = DB) -> str | None:
    """Returns 'on', 'off', or 'once' when the operator asked for something."""
    if not text:
        return None
    if NO.search(text):
        if roam_enabled(db):
            set_roam(False, db)
        return "off"
    if YES.search(text):
        if not roam_enabled(db):
            set_roam(True, db)
        return "on"
    if NOW.search(text):
        return "once"
    return None


@dataclass
class Message:
    seqno: int
    sender_uid: str
    text: str
    timestamp: int


def extract_text(raw_content: str) -> str:
    """DM content is JSON; keep only what a human typed."""
    try:
        data = json.loads(raw_content)
    except Exception:
        return ""
    if isinstance(data, dict):
        return str(data.get("content") or "").strip()
    return ""


def poll(client: BiliClient, talker_id: str, last_seqno: int) -> list[Message]:
    out: list[Message] = []
    for item in client.messages(talker_id):
        try:
            seqno = int(item.get("msg_key") or item.get("seqno") or 0)
        except Exception:
            seqno = 0
        if seqno <= last_seqno:
            continue
        text = extract_text(item.get("content") or "")
        if not text:
            continue
        out.append(Message(seqno=seqno, sender_uid=str(item.get("sender_uid") or ""),
                           text=text, timestamp=int(item.get("timestamp") or 0)))
    out.sort(key=lambda m: m.seqno)
    return out


def remember(db: Path, *, uid: str, content: str, category: str = "shared_episode") -> None:
    """One durable line about the operator, isolated under the bilibili platform."""
    if not db.is_file() or not content:
        return
    con = sqlite3.connect(str(db), timeout=6)
    try:
        stamp = now()
        exists = con.execute(
            "SELECT id FROM memories WHERE platform_id='bilibili' AND scope='member'"
            " AND user_id=? AND content=? AND status='active'", (uid, content)).fetchone()
        if exists:
            con.execute("UPDATE memories SET evidence_count=evidence_count+1, last_seen_at=?,"
                        " updated_at=? WHERE id=?", (stamp, stamp, exists[0]))
        else:
            con.execute(
                "INSERT INTO memories(platform_id, bot_id, scope, group_id, user_id, category, content,"
                " confidence, importance, status, source_ref, evidence_count, last_seen_at,"
                " created_at, updated_at) VALUES('bilibili','bili','member','',?,?,?,0.8,2,'active',"
                " 'bili:dm',1,?,?,?)", (uid, category, content[:120], stamp, stamp, stamp))
        con.commit()
    finally:
        con.close()

def last_key(db: Path = DB) -> int:
    """Highest DM msg_key already answered; survives restarts."""
    try:
        return int(_settings(db, "bili_last_key", default="0") or 0)
    except Exception:
        return 0


def set_last_key(value: int, db: Path = DB) -> None:
    _settings(db, "bili_last_key", str(int(value)))

def extract_bvid(text: str, client=None) -> str:
    """Pull a video id out of a message, following b23.tv links when needed."""
    if not text:
        return ""
    match = BV_RE.search(text)
    if match:
        return match.group(1)
    short = SHORT_RE.search(text)
    if short and client is not None:
        resolved = client.resolve_short(short.group(0))
        match = BV_RE.search(resolved or "")
        if match:
            return match.group(1)
    return ""


def last_recommended(db: Path = DB) -> set[str]:
    raw = _settings(db, "bili_recommended", default="")
    return {item for item in raw.split(",") if item}


def add_recommended(bvid: str, db: Path = DB) -> None:
    items = list(last_recommended(db))
    items.append(bvid)
    _settings(db, "bili_recommended", ",".join(items[-60:]))


def mark_roam(db: Path = DB) -> None:
    _settings(db, "bili_last_roam", now())


def last_roam(db: Path = DB) -> str:
    return _settings(db, "bili_last_roam", default="")
