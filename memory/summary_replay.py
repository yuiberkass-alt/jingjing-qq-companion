#!/usr/bin/env python3
"""Replay a chat transcript through the memory summariser, offline.

Usage:
    python summary_replay.py transcript.txt [--known "已记住的一句" ...]

Prints what the summariser would keep today, so prompts and filters can be
tuned without waiting for the group to talk. It never writes to the database.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import memory_summarize as ms


def call_model(prompt: str, system: str, timeout: float = 60.0) -> str:
    import urllib.request

    config = json.loads(pathlib.Path("/AstrBot/data/cmd_config.json").read_text(encoding="utf-8-sig"))
    sources = [s for s in config.get("provider_sources", []) if s.get("provider") == "deepseek"]
    if not sources:
        raise SystemExit("no deepseek provider configured")
    source = sources[0]
    key = source["key"][0] if isinstance(source.get("key"), list) else source.get("key")
    base = str(source.get("api_base") or "").rstrip("/")
    model = [p for p in config.get("provider", []) if p.get("enable", True)][0].get("model") or "deepseek-chat"
    body = json.dumps({"model": model, "temperature": 0.2, "messages": [
        {"role": "system", "content": system}, {"role": "user", "content": prompt}]}).encode()
    request = urllib.request.Request(base + "/chat/completions", data=body,
                                     headers={"Authorization": "Bearer " + str(key),
                                              "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.load(response)
    return data["choices"][0]["message"]["content"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("transcript")
    parser.add_argument("--known", action="append", default=[])
    parser.add_argument("--last", type=int, default=40)
    args = parser.parse_args()
    lines = [line.strip() for line in pathlib.Path(args.transcript).read_text(
        encoding="utf-8", errors="replace").splitlines() if line.strip()]
    if not lines:
        raise SystemExit("empty transcript")
    raw = call_model(ms.build_prompt("\n".join(lines[-args.last:]), args.known), ms.SYSTEM)
    print("--- raw ---")
    print(raw.strip()[:800])
    print("--- kept ---")
    kept = ms.parse(raw)
    for item in kept:
        print(json.dumps(item, ensure_ascii=False))
    print(f"count: {len(kept)}")


if __name__ == "__main__":
    main()
