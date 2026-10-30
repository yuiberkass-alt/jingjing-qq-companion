#!/usr/bin/env python3
"""memrpc - run one memctl command from a base64 JSON payload on stdin.

Keeps the desktop client free of shell quoting problems: the client sends
{"argv": ["list", "--scope", "core"]} and gets memctl's JSON on stdout.
"""
import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import memctl  # noqa: E402

DB = "/home/ubuntu/jingjing/data/plugin_data/jingjing_memory/memory.sqlite3"


def main() -> None:
    raw = sys.stdin.read().strip() or "e30="
    payload = json.loads(base64.b64decode(raw).decode("utf-8"))
    argv = ["--db", payload.get("db") or DB] + [str(x) for x in payload.get("argv", [])]
    try:
        memctl.main(argv)
    except SystemExit as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        sys.exit(0)


if __name__ == "__main__":
    main()
