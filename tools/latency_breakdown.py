import re, statistics, sys, json
ANSI = re.compile(r"\x1b\[[0-9;]*m")
lines = ANSI.sub("", sys.stdin.read()).splitlines()
timer = re.compile(r"jj_timing trace=(\w+) stage=(\w+)(?: internal_model_roundtrip_ms=(\d+))?")
seq = re.compile(r"jj_timing trace=(\w+) prepare_ms=(\d+) llm_roundtrip_ms=(\d+) observed_wait_ms=(\d+)")
stages = {}
prep = []
for line in lines:
    m = seq.search(line)
    if m:
        prep.append((int(m.group(2)), int(m.group(3)), int(m.group(4))))
        continue
    m = timer.search(line)
    if m:
        trace, stage, ms = m.group(1), m.group(2), m.group(3)
        if ms:
            stages.setdefault(stage, []).append(int(ms))
out = {}
for stage, vals in stages.items():
    out[stage] = {"n": len(vals), "median": int(statistics.median(vals)), "p90": sorted(vals)[int(len(vals)*0.9)-1]}
if prep:
    p = [x[0] for x in prep]; l = [x[1] for x in prep]; w = [x[2] for x in prep]
    out["_prepare"] = {"n": len(p), "median": int(statistics.median(p)), "p90": sorted(p)[int(len(p)*0.9)-1]}
    out["_model"] = {"median": int(statistics.median(l))}
    out["_wait"] = {"median": int(statistics.median(w))}
print(json.dumps(out, ensure_ascii=False))
