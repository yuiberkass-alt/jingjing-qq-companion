#!/usr/bin/env python3
"""memctl - JingJing layered memory admin CLI (stdlib only, JSON output).

Scopes:
  core    shared persona memory, applies to every group/platform ('*')
  group   public memory of one group
  member  memory about one member inside one group

Every mutating command writes a row to memory_revisions so a wrong edit can be
traced and reverted by hand. All reads/writes are plain SQLite; the bot's
recall path is separate (memory_reader.py) and stays fail-closed.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path("/home/ubuntu/jingjing/data/plugin_data/jingjing_memory/memory.sqlite3")
SCHEMA = Path(__file__).with_name("schema_v2.sql")
SCOPES = {"core", "group", "member"}
STATUSES = {"candidate", "active", "archived", "deleted"}
CORE_CATEGORIES = {"identity", "style", "boundary", "preference", "shared_episode"}
MEMBER_CATEGORIES = {"interest", "preferred_name", "interaction_boundary", "shared_episode", "preference"}
GROUP_CATEGORIES = {"group_lore", "group_rule", "shared_episode", "preference"}


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def connect(db: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(db), timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def rows(con, sql, args=()):
    return [dict(r) for r in con.execute(sql, args)]


def revision(con, memory_id, action, before, after):
    con.execute(
        "INSERT INTO memory_revisions(memory_id, action, actor, before_json, after_json, recorded_at)"
        " VALUES(?,?,?,?,?,?)",
        (memory_id, action, "owner", json.dumps(before, ensure_ascii=False),
         json.dumps(after, ensure_ascii=False), now()),
    )


def validate(scope, category, group_id, user_id):
    if scope not in SCOPES:
        raise SystemExit(f"scope must be one of {sorted(SCOPES)}")
    if scope == "core":
        if group_id or user_id:
            raise SystemExit("core memory must not carry group_id/user_id")
        if category not in CORE_CATEGORIES:
            raise SystemExit(f"core category must be one of {sorted(CORE_CATEGORIES)}")
    elif scope == "group":
        if not group_id or user_id:
            raise SystemExit("group memory needs group_id and no user_id")
        if category not in GROUP_CATEGORIES:
            raise SystemExit(f"group category must be one of {sorted(GROUP_CATEGORIES)}")
    else:
        if not group_id or not user_id:
            raise SystemExit("member memory needs group_id and user_id")
        if category not in MEMBER_CATEGORIES:
            raise SystemExit(f"member category must be one of {sorted(MEMBER_CATEGORIES)}")


def ensure_schema(con):
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    # v2.1: a group must be explicitly approved before it may hold memory.
    cols = {row[1] for row in con.execute("PRAGMA table_info(spaces)")}
    if "approved" not in cols:
        con.execute("ALTER TABLE spaces ADD COLUMN approved INTEGER NOT NULL DEFAULT 1")
    # v2.6: one approval per group instead of one per member.
    if "auto_consent" not in cols:
        con.execute("ALTER TABLE spaces ADD COLUMN auto_consent INTEGER NOT NULL DEFAULT 1")
    # v2.2: a memory thickens as the same fact comes back, and can be replaced.
    memory_cols = {row[1] for row in con.execute("PRAGMA table_info(memories)")}
    if "evidence_count" not in memory_cols:
        con.execute("ALTER TABLE memories ADD COLUMN evidence_count INTEGER NOT NULL DEFAULT 1")
    if "last_seen_at" not in memory_cols:
        con.execute("ALTER TABLE memories ADD COLUMN last_seen_at TEXT NOT NULL DEFAULT ''")
    if "superseded_by" not in memory_cols:
        con.execute("ALTER TABLE memories ADD COLUMN superseded_by INTEGER")
    # v2.5: familiarity growth is capped per day.
    relation_cols = {row[1] for row in con.execute("PRAGMA table_info(relations)")}
    if relation_cols:
        if "last_day" not in relation_cols:
            con.execute("ALTER TABLE relations ADD COLUMN last_day TEXT NOT NULL DEFAULT ''")
        if "day_gain" not in relation_cols:
            con.execute("ALTER TABLE relations ADD COLUMN day_gain INTEGER NOT NULL DEFAULT 0")
    con.commit()


def has_table(con, name):
    return bool(con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone())


def cmd_init(args):
    con = connect(Path(args.db))
    ensure_schema(con)
    con.close()
    print(json.dumps({"ok": True, "db": args.db, "schema": "v2"}))


def cmd_migrate(args):
    con = connect(Path(args.db))
    plan = {
        "from": "v1" if has_table(con, "memories") and "platform_id" not in {r[1] for r in con.execute("PRAGMA table_info(memories)")} else "v2",
        "memories": 0, "spaces": 0, "consents": 0,
    }
    if plan["from"] == "v2":
        ensure_schema(con)
        print(json.dumps({"ok": True, "already": "v2"}))
        return
    old_memories = rows(con, "SELECT * FROM memories")
    old_rules = rows(con, "SELECT * FROM group_rules") if has_table(con, "group_rules") else []
    old_consents = rows(con, "SELECT * FROM member_consent") if has_table(con, "member_consent") else []
    plan.update(memories=len(old_memories), spaces=len(old_rules), consents=len(old_consents))
    if args.dry_run:
        print(json.dumps({"ok": True, "dry_run": plan}, ensure_ascii=False))
        return
    backup = Path(str(args.db) + ".bak-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    backup.write_bytes(Path(args.db).read_bytes())
    con.execute("ALTER TABLE memories RENAME TO v1_memories")
    if old_rules:
        con.execute("ALTER TABLE group_rules RENAME TO v1_group_rules")
    if old_consents:
        con.execute("ALTER TABLE member_consent RENAME TO v1_member_consents")
    if has_table(con, "memory_revisions"):
        con.execute("ALTER TABLE memory_revisions RENAME TO v1_memory_revisions")
    ensure_schema(con)
    stamp = now()
    for rule in old_rules:
        con.execute("INSERT OR REPLACE INTO spaces(platform_id, bot_id, group_id, enabled, note, updated_at)"
                    " VALUES(?,?,?,?,?,?)", ("aiocqhttp", "*", str(rule["group_id"]), int(rule["enabled"]), "migrated from v1", stamp))
    for row in old_consents:
        con.execute("INSERT OR REPLACE INTO consents(platform_id, bot_id, group_id, user_id, consent, updated_at)"
                    " VALUES(?,?,?,?,?,?)", ("aiocqhttp", "*", str(row["group_id"]), str(row["user_id"]), int(row["consent"]), stamp))
    for row in old_memories:
        scope = row["scope"] if row["scope"] in {"group", "member"} else "member"
        cur = con.execute(
            "INSERT OR IGNORE INTO memories(platform_id, bot_id, scope, group_id, user_id, category, content,"
            " confidence, importance, status, source_ref, created_at, updated_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("aiocqhttp", "*", scope, str(row["group_id"] or ""), str(row["user_id"] or ""),
             row["category"] or "preference", row["content"] or "", float(row["confidence"] or 1.0),
             2, "active" if row["status"] == "active" else "archived",
             row["source_ref"] or "v1", row["created_at"] or stamp, stamp),
        )
        if cur.lastrowid:
            revision(con, cur.lastrowid, "create", {}, {"migrated_from": row["id"]})
    con.commit()
    print(json.dumps({"ok": True, "backup": str(backup), "migrated": plan}, ensure_ascii=False))


def cmd_list(args):
    con = connect(Path(args.db))
    where, params = ["1=1"], []
    if args.scope:
        where.append("scope=?"); params.append(args.scope)
    if args.group:
        where.append("(group_id=? OR scope='core')"); params.append(args.group)
    if args.user:
        where.append("user_id=?"); params.append(args.user)
    if args.status:
        where.append("status=?"); params.append(args.status)
    if args.search:
        where.append("content LIKE ?"); params.append(f"%{args.search}%")
    sql = ("SELECT id, scope, platform_id, group_id, user_id, category, content, confidence, importance,"
           " status, evidence_count, last_seen_at, superseded_by, created_at, updated_at"
           " FROM memories WHERE " + " AND ".join(where) +
           " ORDER BY scope='core' DESC, importance DESC, evidence_count DESC, id DESC LIMIT ?")
    params.append(max(1, min(int(args.limit), 500)))
    print(json.dumps({"ok": True, "items": rows(con, sql, params)}, ensure_ascii=False))


def cmd_add(args):
    con = connect(Path(args.db))
    validate(args.scope, args.category, args.group or "", args.user or "")
    stamp = now()
    platform = "*" if args.scope == "core" else (args.platform or "aiocqhttp")
    bot = "*" if args.scope == "core" else (args.bot or "*")
    try:
        cur = con.execute(
            "INSERT INTO memories(platform_id, bot_id, scope, group_id, user_id, category, content, confidence,"
            " importance, status, source_ref, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (platform, bot, args.scope, args.group or "", args.user or "", args.category, args.content,
             float(args.confidence), int(args.importance), args.status, args.source or "manual", stamp, stamp),
        )
    except sqlite3.IntegrityError:
        print(json.dumps({"ok": False, "error": "duplicate memory"}, ensure_ascii=False)); return
    revision(con, cur.lastrowid, "create", {}, {"content": args.content})
    con.commit()
    print(json.dumps({"ok": True, "id": cur.lastrowid}, ensure_ascii=False))


def cmd_edit(args):
    con = connect(Path(args.db))
    row = con.execute("SELECT * FROM memories WHERE id=?", (args.id,)).fetchone()
    if not row:
        raise SystemExit("memory not found")
    before = dict(row)
    fields, params = [], []
    for name in ("content", "category", "importance", "confidence", "status"):
        value = getattr(args, name)
        if value is not None:
            fields.append(f"{name}=?"); params.append(value)
    if not fields:
        raise SystemExit("nothing to change")
    if args.status and args.status not in STATUSES:
        raise SystemExit(f"status must be one of {sorted(STATUSES)}")
    fields.append("updated_at=?"); params.append(now()); params.append(args.id)
    con.execute("UPDATE memories SET " + ", ".join(fields) + " WHERE id=?", params)
    after = dict(con.execute("SELECT * FROM memories WHERE id=?", (args.id,)).fetchone())
    revision(con, args.id, "edit", before, after)
    con.commit()
    print(json.dumps({"ok": True, "memory": after}, ensure_ascii=False))


LABELS = {
    "identity": "身份", "style": "风格", "boundary": "边界", "group_lore": "群梗",
    "group_rule": "群约定", "interest": "兴趣", "preferred_name": "称呼",
    "interaction_boundary": "互动边界", "shared_episode": "共同经历", "preference": "偏好",
}
STOP_TAGS = {
    "我们", "你们", "他们", "这个", "那个", "什么", "怎么", "可以", "就是", "不是",
    "一个", "自己", "现在", "今天", "明天", "时候", "觉得", "喜欢", "还是", "因为",
}


def _tags_of(content: str, limit: int = 3) -> list[str]:
    """Short phrases as tags. Deliberately dumb: no word segmenter, so it
    splits on punctuation and keeps the useful clauses instead of inventing
    keywords from arbitrary character pairs."""
    import re

    text = (content or "").strip()
    pieces = re.split(r"[，。！？；、,.!?;:\s]+", text)
    tags: list[str] = []
    for piece in pieces:
        piece = re.sub(r"^(?:我|你|他|她|它|我们|你们|群里|这个)", "", piece.strip())
        piece = piece.strip("的了啦呀嘛呢")
        if not (2 <= len(piece) <= 12) or piece in STOP_TAGS or piece in tags:
            continue
        tags.append(piece)
        if len(tags) >= limit:
            break
    return tags


def cmd_health(args):
    """Look for memories that are probably wrong, thin or stale. Read only."""
    import re as _re
    from datetime import datetime, timedelta

    con = connect(Path(args.db))
    ensure_schema(con)
    active = rows(con, "SELECT id, scope, group_id, user_id, category, content, confidence,"
                       " evidence_count, COALESCE(NULLIF(last_seen_at,''), created_at) AS seen"
                       " FROM memories WHERE status='active' AND superseded_by IS NULL")
    norm = lambda text: _re.sub(r"[\s，。！？；、,.!?;:~～…\"'“”‘’()（）]+", "", text or "").lower()
    seen: dict[tuple, list[int]] = {}
    for row in active:
        seen.setdefault((row["scope"], row["group_id"], row["user_id"],
                         row["category"], norm(row["content"])), []).append(row["id"])
    duplicates = [ids for ids in seen.values() if len(ids) > 1]
    cutoff = (datetime.now().astimezone() - timedelta(days=max(1, args.stale_days))).isoformat(timespec="seconds")
    stale = [row["id"] for row in active
             if str(row["seen"] or "") < cutoff and int(row["evidence_count"] or 1) <= 1]
    low = [row["id"] for row in active if float(row["confidence"] or 0) < 0.6]
    long_items = [row["id"] for row in active if len(row["content"]) > 40]
    suspicious = [row["id"] for row in active
                  if _re.search(r"(这个?(AI|机器人|模型|助手)|上下文|联网|知识库|部署|沙币|傻逼|废物)", row["content"])]
    print(json.dumps({
        "ok": True,
        "counts": {"active": len(active), "duplicates": len(duplicates), "stale": len(stale),
                   "low_confidence": len(low), "too_long": len(long_items), "suspicious": len(suspicious)},
        "samples": {"duplicates": duplicates[:5], "stale": stale[:5], "low_confidence": low[:5],
                    "too_long": long_items[:5], "suspicious": suspicious[:5]},
    }, ensure_ascii=False))


def cmd_style(args):
    """How each group responds to the bot: counted, not guessed."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from group_style import hint

    con = connect(Path(args.db))
    try:
        records = rows(con, "SELECT group_id, replies, continued, updated_at FROM group_style"
                            " ORDER BY replies DESC LIMIT ?", (int(args.limit),))
    except sqlite3.OperationalError:
        records = []
    for record in records:
        record["hint"] = hint(Path(args.db), record["group_id"])
        record["rate"] = round(record["continued"] / max(1, record["replies"]), 2)
    print(json.dumps({"ok": True, "items": records}, ensure_ascii=False))


def cmd_consolidate(args):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from memory_consolidate import consolidate, refine_groups, stale

    result = consolidate(Path(args.db), limit=args.limit)
    result.update(refine_groups(Path(args.db)))
    result["stale"] = len(stale(Path(args.db), days=args.stale_days))
    print(json.dumps(result, ensure_ascii=False))


def cmd_relations(args):
    """How well the bot knows each member of a group (private, counter only)."""
    con = connect(Path(args.db))
    where, params = ["1=1"], []
    if args.group:
        where.append("group_id=?"); params.append(args.group)
    try:
        records = rows(con, "SELECT group_id, user_id, nickname, interactions, familiarity, stage,"
                            " last_interaction_at FROM relations WHERE " + " AND ".join(where) +
                       " ORDER BY familiarity DESC LIMIT ?", params + [int(args.limit)])
    except sqlite3.OperationalError:
        records = []
    print(json.dumps({"ok": True, "items": records}, ensure_ascii=False))


def cmd_graph(args):
    """Nodes and edges for the console's memory map.

    The graph is a view, not new storage: every node points back at a real row,
    so the same scoping and consent rules as recall apply.
    """
    con = connect(Path(args.db))
    where, params = ["status='active'"], []
    if args.group:
        where.append("(group_id=? OR scope='core')"); params.append(args.group)
    if args.user:
        where.append("(user_id=? OR scope='core')"); params.append(args.user)
    if args.scope:
        where.append("scope=?"); params.append(args.scope)
    records = rows(con, "SELECT id, scope, group_id, user_id, category, content, importance,"
                        " evidence_count FROM memories WHERE " + " AND ".join(where) +
                   " ORDER BY scope='core' DESC, importance DESC, id DESC LIMIT ?",
                   params + [max(1, min(int(args.limit), 300))])

    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    edge_seen: set[tuple[str, str, str]] = set()

    def node(node_id, label, kind, weight=1, **extra):
        item = nodes.get(node_id)
        if item:
            item["weight"] += weight
        else:
            nodes[node_id] = {"id": node_id, "label": label, "type": kind, "weight": weight, **extra}
        return node_id

    def edge(source, target, kind):
        key = (source, target, kind)
        if key in edge_seen:
            return
        edge_seen.add(key)
        edges.append({"source": source, "target": target, "type": kind})

    for row in records:
        memory_id = f"mem:{row['id']}"
        node(memory_id, row["content"][:24], "memory",
             weight=int(row["evidence_count"] or 1),
             category=row["category"], scope=row["scope"], full=row["content"])
        category_id = node(f"cat:{row['category']}", LABELS.get(row["category"], row["category"]), "category")
        edge(memory_id, category_id, "category")
        if row["scope"] == "group" and row["group_id"]:
            group_id = node(f"group:{row['group_id']}", "群 " + row["group_id"], "group")
            edge(memory_id, group_id, "group")
        elif row["scope"] == "member" and row["user_id"]:
            member_id = node(f"user:{row['user_id']}", row["user_id"], "member")
            edge(member_id, memory_id, "about")
            if row["group_id"]:
                group_id = node(f"group:{row['group_id']}", "群 " + row["group_id"], "group")
                edge(member_id, group_id, "in")
        else:
            node("core:root", "核心设定", "core")
            edge(memory_id, "core:root", "core")
        for tag in _tags_of(row["content"]):
            if tag == row["content"].strip():
                continue  # the phrase is the whole memory; a tag adds nothing
            tag_id = node(f"tag:{tag}", tag, "tag")
            edge(memory_id, tag_id, "mentions")

    print(json.dumps({
        "ok": True,
        "nodes": list(nodes.values()),
        "edges": edges,
        "counts": {"memories": len(records), "nodes": len(nodes), "edges": len(edges)},
    }, ensure_ascii=False))


def cmd_delete(args):
    """Soft delete: the row stops being recalled but stays auditable."""
    con = connect(Path(args.db))
    row = con.execute("SELECT * FROM memories WHERE id=?", (args.id,)).fetchone()
    if not row:
        raise SystemExit("memory not found")
    before = dict(row)
    con.execute("UPDATE memories SET status='deleted', updated_at=? WHERE id=?",
                (now(), args.id))
    con.execute(
        "INSERT INTO memory_revisions(memory_id, action, actor, before_json, after_json, recorded_at)"
        " VALUES(?,?,?,?,?,?)",
        (args.id, "delete", "owner", json.dumps(before, ensure_ascii=False),
         json.dumps({"reason": args.reason or ""}, ensure_ascii=False), now()),
    )
    con.commit()
    print(json.dumps({"ok": True, "id": args.id, "status": "deleted"}, ensure_ascii=False))


def cmd_promote(args):
    con = connect(Path(args.db))
    row = con.execute("SELECT * FROM memories WHERE id=?", (args.id,)).fetchone()
    if not row:
        raise SystemExit("memory not found")
    if row["scope"] == "core":
        raise SystemExit("already core")
    if row["status"] != "active":
        raise SystemExit("only active memories can be promoted")
    cur = con.execute("INSERT INTO promotions(source_memory_id, note, created_at) VALUES(?,?,?)",
                      (args.id, args.note or "", now()))
    con.commit()
    print(json.dumps({"ok": True, "promotion": cur.lastrowid, "source": dict(row)}, ensure_ascii=False))


def cmd_decide(args):
    con = connect(Path(args.db))
    promo = con.execute("SELECT * FROM promotions WHERE id=?", (args.promotion,)).fetchone()
    if not promo:
        raise SystemExit("promotion not found")
    if promo["status"] != "pending":
        raise SystemExit("promotion already decided")
    created = None
    if args.approve:
        source = con.execute("SELECT * FROM memories WHERE id=?", (promo["source_memory_id"],)).fetchone()
        if not source:
            raise SystemExit("source memory missing")
        category = source["category"] if source["category"] in CORE_CATEGORIES else "shared_episode"
        try:
            cur = con.execute(
                "INSERT INTO memories(platform_id, bot_id, scope, group_id, user_id, category, content, confidence,"
                " importance, status, source_ref, origin_memory_id, created_at, updated_at)"
                " VALUES('*','*','core','','',?,?,?,?,'active',?,?,?,?)",
                (category, source["content"], float(source["confidence"]), int(source["importance"]),
                 f"promoted:{source['id']}", source["id"], now(), now()),
            )
            created = cur.lastrowid
            revision(con, created, "create", {}, {"promoted_from": source["id"]})
        except sqlite3.IntegrityError:
            created = con.execute("SELECT id FROM memories WHERE scope='core' AND content=?",
                                  (source["content"],)).fetchone()[0]
    con.execute("UPDATE promotions SET status=?, decided_at=?, created_memory_id=? WHERE id=?",
                ("approved" if args.approve else "rejected", now(), created, args.promotion))
    con.commit()
    print(json.dumps({"ok": True, "promotion": args.promotion, "created_memory_id": created}, ensure_ascii=False))


def cmd_promotions(args):
    con = connect(Path(args.db))
    sql = ("SELECT p.*, m.content, m.scope, m.group_id, m.user_id, m.category FROM promotions p"
           " JOIN memories m ON m.id=p.source_memory_id")
    params = []
    if args.status:
        sql += " WHERE p.status=?"; params.append(args.status)
    print(json.dumps({"ok": True, "items": rows(con, sql + " ORDER BY p.id DESC LIMIT 200", params)}, ensure_ascii=False))


def cmd_spaces(args):
    con = connect(Path(args.db))
    print(json.dumps({"ok": True,
                      "spaces": rows(con, "SELECT * FROM spaces ORDER BY group_id"),
                      "consents": rows(con, "SELECT * FROM consents ORDER BY group_id, user_id")}, ensure_ascii=False))


def cmd_register(args):
    """Register a group number as pending; it cannot recall memory yet."""
    con = connect(Path(args.db))
    ensure_schema(con)
    con.execute(
        "INSERT INTO spaces(platform_id, bot_id, group_id, enabled, note, updated_at, approved)"
        " VALUES(?,?,?,0,?,?,0)"
        " ON CONFLICT(platform_id, bot_id, group_id) DO UPDATE SET note=excluded.note, updated_at=excluded.updated_at",
        (args.platform or "aiocqhttp", args.bot or "*", args.group, args.note or "待审核", now()),
    )
    con.commit()
    print(json.dumps({"ok": True, "group": args.group, "state": "pending"}, ensure_ascii=False))


def cmd_approve(args):
    con = connect(Path(args.db))
    ensure_schema(con)
    if args.reject:
        con.execute("UPDATE spaces SET approved=0, enabled=0, note=?, updated_at=? WHERE group_id=?",
                    ("已驳回", now(), args.group))
    else:
        con.execute("UPDATE spaces SET approved=1, enabled=1, note=?, updated_at=? WHERE group_id=?",
                    ("已开通", now(), args.group))
    con.commit()
    row = con.execute("SELECT group_id, enabled, approved, note FROM spaces WHERE group_id=?",
                      (args.group,)).fetchone()
    print(json.dumps({"ok": bool(row), "space": dict(row) if row else None}, ensure_ascii=False))


def cmd_set_space(args):
    con = connect(Path(args.db))
    ensure_schema(con)
    platform = args.platform or "aiocqhttp"
    bot = args.bot or "*"
    enabled = 1 if args.enabled == "1" else 0
    con.execute(
        "INSERT INTO spaces(platform_id, bot_id, group_id, enabled, updated_at) VALUES(?,?,?,?,?)"
        " ON CONFLICT(platform_id, bot_id, group_id) DO UPDATE SET"
        " enabled=excluded.enabled, updated_at=excluded.updated_at",
        (platform, bot, args.group, enabled, now()))
    if getattr(args, "auto_consent", None) is not None:
        con.execute(
            "UPDATE spaces SET auto_consent=? WHERE group_id=? AND platform_id=? AND bot_id=?",
            (1 if args.auto_consent == "1" else 0, args.group, platform, bot))
    con.commit()
    row = con.execute("SELECT enabled, approved, auto_consent FROM spaces WHERE group_id=?",
                      (args.group,)).fetchone()
    print(json.dumps({"ok": True, "space": dict(row) if row else {}}, ensure_ascii=False))


def cmd_set_consent(args):
    con = connect(Path(args.db))
    con.execute("INSERT INTO consents(platform_id, bot_id, group_id, user_id, consent, updated_at) VALUES(?,?,?,?,?,?)"
                " ON CONFLICT(platform_id, bot_id, group_id, user_id) DO UPDATE SET consent=excluded.consent, updated_at=excluded.updated_at",
                (args.platform or "aiocqhttp", args.bot or "*", args.group, args.user, 1 if args.consent == "1" else 0, now()))
    con.commit()
    print(json.dumps({"ok": True}))


def cmd_settings(args):
    con = connect(Path(args.db))
    ensure_schema(con)
    print(json.dumps({"ok": True, "items": rows(con, "SELECT * FROM settings ORDER BY key")}, ensure_ascii=False))


def cmd_set_setting(args):
    con = connect(Path(args.db))
    ensure_schema(con)
    if args.value is None:
        con.execute("DELETE FROM settings WHERE key=?", (args.key,))
    else:
        con.execute("INSERT INTO settings(key, value, updated_at) VALUES(?,?,?)"
                    " ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                    (args.key, str(args.value), now()))
    con.commit()
    print(json.dumps({"ok": True, "key": args.key, "value": args.value}, ensure_ascii=False))


def cmd_stats(args):
    con = connect(Path(args.db))
    out = {"by_scope": rows(con, "SELECT scope, status, COUNT(*) n FROM memories GROUP BY scope, status"),
           "spaces": con.execute("SELECT COUNT(*) FROM spaces").fetchone()[0],
           "consents": con.execute("SELECT COUNT(*) FROM consents").fetchone()[0],
           "pending_promotions": con.execute("SELECT COUNT(*) FROM promotions WHERE status='pending'").fetchone()[0],
           "db_bytes": Path(args.db).stat().st_size}
    print(json.dumps({"ok": True, **out}, ensure_ascii=False))


def build_parser():
    p = argparse.ArgumentParser(prog="memctl")
    p.add_argument("--db", default=str(DEFAULT_DB))
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("init", "spaces", "stats"):
        sub.add_parser(name)
    m = sub.add_parser("migrate"); m.add_argument("--dry-run", action="store_true")
    l = sub.add_parser("list")
    l.add_argument("--scope"); l.add_argument("--group"); l.add_argument("--user")
    l.add_argument("--status"); l.add_argument("--search"); l.add_argument("--limit", default=100)
    a = sub.add_parser("add")
    a.add_argument("--scope", required=True); a.add_argument("--category", required=True)
    a.add_argument("--content", required=True); a.add_argument("--group", default="")
    a.add_argument("--user", default=""); a.add_argument("--confidence", default=1.0)
    a.add_argument("--importance", default=2); a.add_argument("--status", default="active")
    a.add_argument("--platform"); a.add_argument("--bot"); a.add_argument("--source")
    e = sub.add_parser("edit")
    e.add_argument("--id", type=int, required=True)
    for name in ("content", "category", "importance", "confidence", "status"):
        e.add_argument(f"--{name}")
    pr = sub.add_parser("promote"); pr.add_argument("--id", type=int, required=True); pr.add_argument("--note", default="")
    d = sub.add_parser("decide"); d.add_argument("--promotion", type=int, required=True)
    d.add_argument("--approve", action="store_true"); d.add_argument("--reject", action="store_true")
    po = sub.add_parser("promotions"); po.add_argument("--status")
    hl = sub.add_parser("health")
    hl.add_argument("--stale-days", dest="stale_days", type=int, default=120)
    st = sub.add_parser("style")
    st.add_argument("--limit", type=int, default=20)
    cs = sub.add_parser("consolidate")
    cs.add_argument("--limit", type=int, default=500)
    cs.add_argument("--stale-days", dest="stale_days", type=int, default=120)
    rl = sub.add_parser("relations")
    rl.add_argument("--group")
    rl.add_argument("--limit", type=int, default=50)
    gr = sub.add_parser("graph")
    gr.add_argument("--group")
    gr.add_argument("--user")
    gr.add_argument("--scope")
    gr.add_argument("--limit", type=int, default=120)
    de = sub.add_parser("delete")
    de.add_argument("--id", type=int, required=True)
    de.add_argument("--reason")
    sub.add_parser("settings")
    ss = sub.add_parser("set-setting")
    ss.add_argument("--key", required=True)
    ss.add_argument("--value")
    r = sub.add_parser("register"); r.add_argument("--group", required=True)
    r.add_argument("--note", default="待审核"); r.add_argument("--platform"); r.add_argument("--bot")
    ap = sub.add_parser("approve"); ap.add_argument("--group", required=True)
    ap.add_argument("--reject", action="store_true"); ap.add_argument("--platform"); ap.add_argument("--bot")
    s = sub.add_parser("set-space"); s.add_argument("--group", required=True)
    s.add_argument("--auto-consent", dest="auto_consent", choices=["0", "1"])
    s.add_argument("--enabled", choices=["0", "1"], required=True)
    s.add_argument("--platform"); s.add_argument("--bot")
    c = sub.add_parser("set-consent"); c.add_argument("--group", required=True)
    c.add_argument("--user", required=True); c.add_argument("--consent", choices=["0", "1"], required=True)
    c.add_argument("--platform"); c.add_argument("--bot")
    return p


COMMANDS = {
    "init": cmd_init, "migrate": cmd_migrate, "list": cmd_list, "add": cmd_add,
    "edit": cmd_edit, "promote": cmd_promote, "decide": cmd_decide,
    "promotions": cmd_promotions, "spaces": cmd_spaces, "stats": cmd_stats,
    "set-space": cmd_set_space, "set-consent": cmd_set_consent,
    "register": cmd_register, "approve": cmd_approve,
    "settings": cmd_settings, "set-setting": cmd_set_setting,
    "delete": cmd_delete, "graph": cmd_graph, "relations": cmd_relations,
    "consolidate": cmd_consolidate, "style": cmd_style, "health": cmd_health,
}


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command == "decide":
        if args.approve == args.reject:
            raise SystemExit("choose --approve or --reject")
        if not args.approve and not args.reject:
            raise SystemExit("choose --approve or --reject")
    COMMANDS[args.command](args)


if __name__ == "__main__":
    main()
