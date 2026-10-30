import json, sqlite3, sys
sys.path.insert(0, "/home/ubuntu/jingjing/data/plugins/astrbot_plugin_jingjing_bili")
from pathlib import Path
from bili_api import BiliClient, BiliError

COOKIE = Path("/home/ubuntu/jingjing/data/plugin_data/jingjing_bili/cookie.json")
DB = Path("/home/ubuntu/jingjing/data/plugin_data/jingjing_memory/memory.sqlite3")
out = {"ok": True, "configured": False, "roam": False}
try:
    data = json.loads(COOKIE.read_text(encoding="utf-8"))
except Exception:
    data = None
if data and data.get("sessdata"):
    out["configured"] = True
    out["owner_uid"] = str(data.get("owner_uid") or "")
    try:
        client = BiliClient(sessdata=data["sessdata"], bili_jct=data.get("bili_jct", ""),
                            buvid3=data.get("buvid3", ""), uid=data.get("uid", ""))
        info = client.whoami()
        out.update(login=True, name=info.get("name"), uid=info.get("uid"))
    except Exception as exc:
        out.update(login=False, error=str(exc)[:160])
else:
    out.update(login=False)
try:
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    row = con.execute("SELECT value FROM settings WHERE key='bili_roam'").fetchone()
    out["roam"] = bool(row and row[0] == "1")
    con.close()
except Exception:
    pass
print(json.dumps(out, ensure_ascii=False))
