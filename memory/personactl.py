#!/usr/bin/env python3
"""personactl - read and edit AstrBot personas with file-based version history.

Runs inside the astrbot container (it needs write access to data_v4.db).
Every save first writes the previous text to
  /AstrBot/data/plugin_data/jingjing_memory/persona_versions/<persona_id>/<ts>.txt
so a bad edit can be restored without touching the database directly.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DB = Path("/AstrBot/data/data_v4.db")
VERSIONS = Path("/AstrBot/data/plugin_data/jingjing_memory/persona_versions")


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def connect():
    con = sqlite3.connect(f"file:{DB}?mode=rw", uri=True, timeout=10)
    con.row_factory = sqlite3.Row
    return con


def version_dir(persona_id: str) -> Path:
    safe = "".join(c for c in persona_id if c.isalnum() or c in "._-") or "unknown"
    path = VERSIONS / safe
    path.mkdir(parents=True, exist_ok=True)
    return path


def snapshot(persona_id: str, content: str, tag: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    path = version_dir(persona_id) / f"{stamp}-{tag}.txt"
    path.write_text(content, encoding="utf-8")
    return str(path)


def op_list() -> dict:
    con = connect()
    rows = [dict(r) for r in con.execute(
        "SELECT id, persona_id, length(system_prompt) AS chars, updated_at FROM personas ORDER BY id")]
    con.close()
    for row in rows:
        folder = VERSIONS / row["persona_id"]
        row["versions"] = len(list(folder.glob("*.txt"))) if folder.is_dir() else 0
    return {"ok": True, "items": rows}


def op_get(persona_id: str) -> dict:
    con = connect()
    row = con.execute("SELECT persona_id, system_prompt, updated_at FROM personas WHERE persona_id=?",
                      (persona_id,)).fetchone()
    con.close()
    if not row:
        return {"ok": False, "error": "persona not found"}
    folder = version_dir(persona_id)
    versions = sorted((p.name for p in folder.glob("*.txt")), reverse=True)[:20]
    return {"ok": True, "persona_id": row["persona_id"], "content": row["system_prompt"],
            "updated_at": row["updated_at"], "versions": versions}


def op_save(persona_id: str, content: str, note: str) -> dict:
    if not content.strip():
        return {"ok": False, "error": "empty persona"}
    con = connect()
    row = con.execute("SELECT system_prompt FROM personas WHERE persona_id=?", (persona_id,)).fetchone()
    if not row:
        con.close()
        return {"ok": False, "error": "persona not found"}
    backup = snapshot(persona_id, row["system_prompt"], "before")
    con.execute("UPDATE personas SET system_prompt=?, updated_at=? WHERE persona_id=?",
                (content, now(), persona_id))
    con.commit()
    con.close()
    snapshot(persona_id, content, "saved")
    return {"ok": True, "persona_id": persona_id, "chars": len(content), "backup": backup,
            "note": note, "restart_required": True}


def op_preview(persona_id: str, content: str, message: str) -> dict:
    """One dry-run reply with this prompt, without saving or restarting."""
    import time
    import urllib.request

    if not content.strip() or not message.strip():
        return {"ok": False, "error": "需要人格内容和一句话"}
    cfg = json.loads(Path("/AstrBot/data/cmd_config.json").read_text(encoding="utf-8-sig"))
    sources = [s for s in cfg.get("provider_sources", []) if s.get("provider") == "deepseek"]
    providers = [p for p in cfg.get("provider", []) if p.get("enable", True)]
    if not sources or not providers:
        return {"ok": False, "error": "没有可用的 deepseek provider"}
    src = sources[0]
    key = src["key"][0] if isinstance(src.get("key"), list) else src.get("key")
    base = str(src.get("api_base") or "").rstrip("/")
    model = providers[0].get("model") or "deepseek-chat"
    body = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": content},
                     {"role": "user", "content": message}],
    }).encode()
    req = urllib.request.Request(base + "/chat/completions", data=body,
                                 headers={"Authorization": "Bearer " + str(key),
                                          "Content-Type": "application/json"})
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.load(resp)
    except Exception as exc:
        return {"ok": False, "error": "调用失败：" + str(exc)[:160]}
    reply = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    return {"ok": True, "reply": reply.strip(), "sec": round(time.time() - started, 2)}


def op_versions(persona_id: str) -> dict:
    folder = version_dir(persona_id)
    items = []
    for path in sorted(folder.glob("*.txt"), reverse=True)[:50]:
        text = path.read_text(encoding="utf-8", errors="replace")
        items.append({"file": path.name, "chars": len(text), "head": text[:80]})
    return {"ok": True, "items": items}


def op_restore(persona_id: str, version: str) -> dict:
    path = version_dir(persona_id) / version
    if not path.is_file():
        return {"ok": False, "error": "version not found"}
    return op_save(persona_id, path.read_text(encoding="utf-8"), "restore:" + version)


def _payload() -> dict:
    """Accept the JSON as argv[1], as base64 in argv[2], or on stdin.

    ssh joins its arguments into one shell string, so piping stdin through
    docker exec is fragile; an argument survives intact.
    """
    import base64
    if len(sys.argv) > 1 and sys.argv[1]:
        raw = sys.argv[1]
        if sys.argv[1] == "--b64" and len(sys.argv) > 2:
            return json.loads(base64.b64decode(sys.argv[2]).decode("utf-8"))
        return json.loads(raw)
    return json.loads(sys.stdin.read() or "{}")


def main() -> None:
    payload = _payload()
    op = payload.get("op")
    pid = str(payload.get("persona_id") or "")
    try:
        if op == "list":
            out = op_list()
        elif op == "get":
            out = op_get(pid)
        elif op == "save":
            out = op_save(pid, str(payload.get("content") or ""), str(payload.get("note") or ""))
        elif op == "preview":
            out = op_preview(pid, str(payload.get("content") or ""), str(payload.get("message") or ""))
        elif op == "versions":
            out = op_versions(pid)
        elif op == "restore":
            out = op_restore(pid, str(payload.get("version") or ""))
        else:
            out = {"ok": False, "error": "unknown op"}
    except Exception as exc:
        out = {"ok": False, "error": type(exc).__name__ + ": " + str(exc)[:200]}
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
