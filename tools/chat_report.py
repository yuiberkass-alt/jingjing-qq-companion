#!/usr/bin/env python3
"""Summarise the bot's own behaviour from AstrBot logs (read only).

    sudo docker logs --since 24h astrbot 2>&1 | python3 chat_report.py

Prints one JSON object: decisions, reasons, latency percentiles and how many
memories were written. No message text is ever printed.
"""
from __future__ import annotations

import json
import re
import statistics
import sys

ANSI = re.compile(r"\x1b\[[0-9;]*m")
TS = re.compile(r"\[(\d{2}:\d{2}:\d{2})\.\d+\]")
DECISION = re.compile(r"jj_v03: group=(\S+) decision=(\w+)(?: session=\S+)?(?: reason=(\w+))?")
TIMING = re.compile(r"jj_timing trace=\S+ prepare_ms=(\d+) llm_roundtrip_ms=(\d+) observed_wait_ms=(\d+)")
INBOUND = re.compile(r"event_bus:117")
REPLY = re.compile(r"Prepare to send - ")
SUMMARY = re.compile(r"summarised (\d+) memory item")
EXTRACT = re.compile(r"auto remembered (\d+) item")
BLOCK = re.compile(r"reason=topic_block")


def _secs(hhmmss: str) -> float:
    h, m, s = (int(part) for part in hhmmss.split(":"))
    return h * 3600 + m * 60 + s


def main() -> None:
    text = ANSI.sub("", sys.stdin.read())
    lines = text.splitlines()
    decisions: dict[str, int] = {}
    reasons: dict[str, int] = {}
    groups: dict[str, int] = {}
    prep, wait, model = [], [], []
    inbound = replies = summaries = extracts = blocked = 0
    events: list[tuple[float, str, str]] = []
    for line in lines:
        stamp = TS.search(line)
        if INBOUND.search(line):
            inbound += 1
            if stamp:
                body = line.split("aiocqhttp)] ")[-1] if "aiocqhttp)] " in line else line
                events.append((_secs(stamp.group(1)), "in", body))
        if stamp and REPLY.search(line) and events:
            events.append((_secs(stamp.group(1)), "out", ""))
        if REPLY.search(line):
            replies += 1
        if BLOCK.search(line):
            blocked += 1
        match = DECISION.search(line)
        if match:
            group, decision, reason = match.groups()
            decisions[decision] = decisions.get(decision, 0) + 1
            groups[group] = groups.get(group, 0) + 1
            if reason:
                reasons[reason] = reasons.get(reason, 0) + 1
        match = TIMING.search(line)
        if match:
            prep.append(int(match.group(1)))
            model.append(int(match.group(2)))
            wait.append(int(match.group(3)))
        match = SUMMARY.search(line)
        if match:
            summaries += int(match.group(1))
        match = EXTRACT.search(line)
        if match:
            extracts += int(match.group(1))

    def stats(values: list[int]) -> dict:
        if not values:
            return {}
        values = sorted(values)
        return {
            "count": len(values),
            "median": int(statistics.median(values)),
            "p90": values[int(len(values) * 0.9) - 1] if len(values) > 1 else values[0],
            "max": values[-1],
        }

    addressed = missed = 0
    for position, (when, kind, body) in enumerate(events):
        if kind != "in":
            continue
        if not re.search(r"(鲸鲸|大肥鱼|<BOT_QQ>)", body):
            continue
        addressed += 1
        answered = any(kind2 == "out" and 0 <= when2 - when <= 30
                       for when2, kind2, _ in events[position + 1:])
        if not answered:
            missed += 1

    print(json.dumps({
        "ok": True,
        "lines": len(lines),
        "inbound": inbound,
        "replies": replies,
        "decisions": decisions,
        "reasons": reasons,
        "groups": groups,
        "latency": {"prepare_ms": stats(prep), "model_ms": stats(model), "wait_ms": stats(wait)},
        "memories": {"from_summary": summaries, "from_extract": extracts},
        "topic_blocked": blocked,
        "addressed": addressed,
        "missed": missed,
        "miss_rate": round(missed / addressed, 3) if addressed else 0.0,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()

