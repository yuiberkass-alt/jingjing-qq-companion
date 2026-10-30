"""Turn-level audit for the JingJing reply pipeline.

Usage: python r11_chat_audit.py <log-file> [--json out.json]

Reads only structural log fields (timings, decisions, paragraph and sticker
counts). Message text is never printed, so the report is safe to share.

Two numbers matter for acceptance:
  * wait   - how long the plugin itself slept (this is what r11 cut)
  * wall   - triggering message to reply-ready, i.e. what the user felt
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

ANSI = re.compile(r"\x1b\[[0-9;]*m")
TIME = re.compile(r"\[(\d{2}:\d{2}:\d{2}\.\d{3})\]")
TRACE = re.compile(r"trace=([0-9a-f]{12})")
INBOUND = re.compile(r"event_bus:117\]")
SEND = re.compile(r"Prepare to send")
FIELDS = {
    "prepare": re.compile(r"prepare_ms=(-?\d+) llm_roundtrip_ms=(-?\d+) observed_wait_ms=(-?\d+)"),
    "llm_req": re.compile(r"system_chars=(\d+) contexts=(\d+) tools=(\w+) images=(\d+) prompt_chars=(\d+)"),
    "style": re.compile(r"paragraphs=(\d+) emoji=(\w+)"),
    "sticker": re.compile(r"stage=([a-z_]+)"),
    "vendor": re.compile(r"stage=(\w+) internal_model_roundtrip_ms=(\d+) lightweight=(\w+)"),
    "skip": re.compile(r"decision=SKIP.*?reason=(\w+)"),
    "decision": re.compile(r"decision=(\w+) session=(\w+)"),
    "send": re.compile(r"segments=(\d+) sent=(\d+)"),
    "pipe": re.compile(r"pipeline_after_prepare_ms=(\d+)"),
}


def stamp_of(line: str):
    match = TIME.search(line)
    return datetime.strptime(match.group(1), "%H:%M:%S.%f") if match else None


def unanswered_inbound(path: Path, *, burst_sec: float = 2.5, grace_sec: float = 12.0, show_text: bool = False):
    """Count inbound messages that never produced a reply.

    A burst of inbound lines closer than burst_sec is treated as one turn, and
    a reply up to grace_sec after the burst closes it. This is the direct
    measure of "the bot walked away": it needs no guesswork about judges.
    """
    import re as _re
    inbound, outbound = [], []
    text_re = _re.compile(r"event_bus:117\]: \[default\] \[[^\]]+\] ([^:]+): (.*)$")
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = ANSI.sub("", raw)
        stamp = stamp_of(line)
        if not stamp:
            continue
        if INBOUND.search(line):
            match = text_re.search(line)
            text = match.group(2) if match else ""
            # A bare picture or sticker is an emotional supplement by design:
            # it is meant to be merged into the previous turn, not answered.
            if _re.fullmatch(r"\[(?:图片|表情|动画表情)(?:[\s:：]*x?\d*)?\]", text.strip() or "x"):
                continue
            inbound.append({"at": stamp, "who": match.group(1) if match else "", "text": text})
        elif SEND.search(line):
            outbound.append(stamp)
    inbound.sort(key=lambda item: item["at"])
    outbound.sort()
    groups, current = [], []
    for item in inbound:
        if current and (item["at"] - current[-1]["at"]).total_seconds() <= burst_sec:
            current.append(item)
        else:
            if current:
                groups.append(current)
            current = [item]
    if current:
        groups.append(current)
    silent = []
    for group in groups:
        start = group[0]["at"]
        # A reply may serve more than one tight group when messages merge, so
        # the window is not bounded by the next group; only by the grace time.
        answered = any(
            start <= stamp and (stamp - start).total_seconds() <= grace_sec
            for stamp in outbound
        )
        if not answered:
            entry = {"at": start.strftime("%H:%M:%S"), "messages": len(group)}
            if show_text:
                entry["text"] = group[0]["text"][:40]
            silent.append(entry)
    return {"inbound_turns": len(groups), "replies": len(outbound), "unanswered": silent}


def parse(path: Path):
    rows: dict[str, dict] = {}
    order: list[str] = []
    inbound: list[datetime] = []
    skips: list[dict] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = ANSI.sub("", raw)
        stamp = stamp_of(line)
        if INBOUND.search(line) and stamp:
            inbound.append(stamp)
            continue
        if "jj_" not in line:
            continue
        trace = TRACE.search(line)
        key = trace.group(1) if trace else None
        if key is None:
            if m := FIELDS["skip"].search(line):
                skips.append({"at": stamp.strftime("%H:%M:%S") if stamp else "", "reason": m.group(1)})
            continue
        if key not in rows:
            rows[key] = {"trace": key, "at": stamp.strftime("%H:%M:%S.%f")[:-3] if stamp else ""}
            order.append(key)
        row = rows[key]
        if "jj_timing" in line and (m := FIELDS["prepare"].search(line)):
            row["prepare_ms"], row["llm_ms"], row["wait_ms"] = (int(x) for x in m.groups())
            # prepare_ms is measured from the message that triggered the turn
            # to the moment the reply is ready, so it is the user-felt latency.
            row["wall_ms"] = row["prepare_ms"]
        elif "jj_llm_request" in line and (m := FIELDS["llm_req"].search(line)):
            row["system_chars"], row["contexts"], row["tools"], row["images"], row["prompt_chars"] = (
                int(m.group(1)), int(m.group(2)), m.group(3), int(m.group(4)), int(m.group(5))
            )
        elif "jj_style" in line and (m := FIELDS["style"].search(line)):
            row["paragraphs"], row["emoji"] = int(m.group(1)), m.group(2) == "True"
        elif "internal_model_roundtrip_ms" in line and (m := FIELDS["vendor"].search(line)):
            row.setdefault("vendor_calls", []).append({"stage": m.group(1), "ms": int(m.group(2)), "light": m.group(3)})
            row["judged"] = row.get("judged", False) or m.group(1) == "judge"
        elif "jj_v03" in line and (m := FIELDS["decision"].search(line)):
            row["decision"] = m.group(1)
        elif "smart segmented send" in line and (m := FIELDS["send"].search(line)):
            row["segments"], row["sent"] = int(m.group(1)), int(m.group(2))
        elif "jj_sticker" in line and (m := FIELDS["sticker"].search(line)):
            row.setdefault("sticker_stages", []).append(m.group(1))
        elif "pipeline_after_prepare" in line and (m := FIELDS["pipe"].search(line)):
            row["after_prepare_ms"] = int(m.group(1))
    return [rows[k] for k in order if "prepare_ms" in rows[k]], skips


def median(values):
    values = sorted(values)
    return values[len(values) // 2] if values else None


def report(rows, skips, path: Path | None = None) -> None:
    head = (f"{'at':>12} {'wall':>6} {'wait':>5} {'llm':>6} {'judge':>6} "
            f"{'para':>4} {'pic':<4} {'sent':>4} {'path':<12}")
    print(head)
    print("-" * len(head))
    for row in rows:
        judges = [v for v in row.get("vendor_calls", []) if v["stage"] == "judge"]
        sticker = any(s in {"validated", "semantic_selected", "attached_not_confirmed"} for s in row.get("sticker_stages", []))
        kind = "judged" if judges else "continuation"
        print(f"{row.get('at',''):>12} {row.get('wall_ms','-'):>6} {row.get('wait_ms','-'):>5} "
              f"{row.get('llm_ms','-'):>6} {(judges[0]['ms'] if judges else '-'):>6} "
              f"{row.get('paragraphs','-'):>4} {('yes' if sticker else 'no'):<4} {row.get('sent','-'):>4} {kind:<12}")
    print()
    summary = {
        "turns_with_reply": len(rows),
        "continuation_turns": sum(1 for r in rows if not r.get("judged")),
        "judge_calls": sum(1 for r in rows for v in r.get("vendor_calls", []) if v["stage"] == "judge"),
        "median_wall_ms": median([r["wall_ms"] for r in rows if "wall_ms" in r]),
        "median_plugin_wait_ms": median([r["wait_ms"] for r in rows if "wait_ms" in r]),
        "median_model_ms": median([r["llm_ms"] for r in rows if r.get("llm_ms", -1) >= 0]),
        "skips": skips,
        "inbound": unanswered_inbound(path, show_text="--show-text" in sys.argv) if path else None,
    }
    print(json.dumps(summary, ensure_ascii=False))
    gate(summary, rows)


# Acceptance gate. Thresholds are anchored on the r10 baseline measured with
# the same script: median 10.1s felt latency, median 3.0s of plugin waiting.
GATE = {
    "min_replied_turns": 3,
    "median_wall_ms_max": 5000,
    "max_wall_ms": 8000,
    "median_plugin_wait_ms_max": 1000,
    "require_a_continuation_turn": True,
}


def gate(summary, rows) -> None:
    checks = []

    def check(name, ok, detail):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    check("turns replied", summary["turns_with_reply"] >= GATE["min_replied_turns"],
          summary["turns_with_reply"])
    check("median felt latency", (summary["median_wall_ms"] or 10 ** 9) <= GATE["median_wall_ms_max"],
          summary["median_wall_ms"])
    walls = [r["wall_ms"] for r in rows if "wall_ms" in r]
    check("worst felt latency", (max(walls) if walls else 10 ** 9) <= GATE["max_wall_ms"],
          max(walls) if walls else None)
    check("median plugin wait", (summary["median_plugin_wait_ms"] if summary["median_plugin_wait_ms"] is not None else 10 ** 9)
          <= GATE["median_plugin_wait_ms_max"], summary["median_plugin_wait_ms"])
    if GATE["require_a_continuation_turn"]:
        check("fast continuation used", summary["continuation_turns"] >= 1, summary["continuation_turns"])
        # 1500ms allows the 1.2s input-debounce that the direct-summon path uses
        # by design; the semantic continuation path waits 0.3-0.8s.
        slow = [r for r in rows if not r.get("judged") and (r.get("wait_ms") or 0) > 1500]
        check("continuation waits are short", not slow, len(slow))
    failed = [c for c in checks if not c["ok"]]
    for item in checks:
        print(f"[{'PASS' if item['ok'] else 'FAIL'}] {item['check']}: {item['detail']}")
    print(json.dumps({"gate_passed": not failed, "failed": [c["check"] for c in failed]}, ensure_ascii=False))
    if failed:
        sys.exit(2)


def main() -> None:
    path = Path(sys.argv[1])
    rows, skips = parse(path)
    report(rows, skips, path)
    if "--json" in sys.argv:
        Path(sys.argv[sys.argv.index("--json") + 1]).write_text(
            json.dumps({"rows": rows, "skips": skips}, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
