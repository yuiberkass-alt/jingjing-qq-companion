#!/usr/bin/env python3
"""JingJing desktop console - local UI over the existing SSH connection.

Design notes:
  * binds 127.0.0.1 only, no external port, no stored credentials
  * every action is one ssh call running memrpc.py with a base64 JSON payload,
    so Chinese text and quoting never break
  * the window is Edge/Chrome in --app mode, started with the random port
"""
from __future__ import annotations

import base64
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
UI = ROOT / "ui"
LOG = ROOT / "console.log"
SSH_CONFIG = os.environ.get("JJ_SSH_CONFIG", "D:/Jingjing/ssh/config")
SSH_HOST = os.environ.get("JJ_SSH_HOST", "oJingJing")


def log(message: str) -> None:
    """The window has no console, so failures must land in a file."""
    try:
        with LOG.open("a", encoding="utf-8") as handle:
            handle.write(time.strftime("%Y-%m-%d %H:%M:%S ") + message + "\n")
    except Exception:
        pass
REMOTE_RPC = "python3 /home/ubuntu/jingjing/memory/memrpc.py"
MAIN_PLUGIN = "/home/ubuntu/jingjing/data/plugins/astrbot_plugin_xiaozhao_smart_mention/main.py"
TIMEOUT = 45
# Browsers throttle timers in background tabs to about once a minute, so a
# 30s watchdog killed the server while the window was simply minimised.
IDLE_EXIT_SEC = float(os.environ.get("JJ_IDLE_EXIT", "180"))
LAST_SEEN = {"at": 0.0}


def _hidden() -> dict:
    """Keep ssh/scp from flashing a console window on every call.

    pythonw has no console, so Windows allocates one for each child process.
    """
    if os.name != "nt":
        return {}
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    return {"creationflags": 0x08000000, "startupinfo": startup}  # CREATE_NO_WINDOW


def _ssh(args: list[str], *, stdin: bytes | None = None, timeout: int = TIMEOUT) -> subprocess.CompletedProcess:
    cmd = ["ssh", "-F", SSH_CONFIG, "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", SSH_HOST, *args]
    return subprocess.run(cmd, input=stdin, capture_output=True, timeout=timeout, **_hidden())


def _text(blob: bytes) -> str:
    """Windows ssh writes localized errors in the OEM codepage, not UTF-8."""
    for enc in ("utf-8", "gbk", "cp936"):
        try:
            return blob.decode(enc)
        except Exception:
            continue
    return blob.decode("utf-8", "replace")


def run_script(script: str, timeout: int = TIMEOUT) -> subprocess.CompletedProcess:
    """Run a bash script on the server via stdin.

    Passing the script as ssh arguments breaks on quoting (ssh joins argv with
    spaces), so the script always travels on stdin.
    """
    return _ssh(["bash", "-s"], stdin=script.encode("utf-8"), timeout=timeout)


def rpc(argv: list[str], *, db: str | None = None) -> dict:
    payload = {"argv": argv}
    if db:
        payload["db"] = db
    blob = base64.b64encode(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    done = _ssh([REMOTE_RPC], stdin=blob)
    text = _text(done.stdout).strip()
    if not text:
        raise RuntimeError((_text(done.stderr).strip() or "empty response")[:300])
    return json.loads(text.splitlines()[-1])


PERSONACTL = "/AstrBot/data/plugin_data/jingjing_memory/personactl.py"


def persona_rpc(payload: dict) -> dict:
    blob = base64.b64encode(json.dumps(payload, ensure_ascii=False).encode("utf-8")).decode("ascii")
    done = _ssh(["sudo", "-n", "docker", "exec", "-i", "astrbot", "python", "-B", PERSONACTL, "--b64", blob])
    text = _text(done.stdout).strip()
    if not text:
        raise RuntimeError(_text(done.stderr).strip()[:300] or "empty response")
    return json.loads(text.splitlines()[-1])


def status() -> dict:
    script = (
        "sudo -n docker ps --format '{{.Names}}|{{.Status}}'; echo '===';"
        "sha256sum " + MAIN_PLUGIN + " | cut -c1-16; echo '===';"
        "sudo -n docker logs --since 6h astrbot 2>&1 | grep -c 'Prepare to send' || true"
    )
    done = run_script(script)
    if done.returncode != 0:
        raise RuntimeError(_text(done.stderr).strip()[:300] or "ssh failed")
    parts = _text(done.stdout).split("===")
    containers = [line for line in (parts[0].splitlines() if parts else []) if line.strip()]
    sha = (parts[1].strip() if len(parts) > 1 else "")
    replies = parts[2].strip() if len(parts) > 2 else "0"
    try:
        memory = rpc(["stats"])
    except Exception as exc:
        memory = {"ok": False, "error": str(exc)[:200]}
    return {"containers": containers, "main_sha": sha,
            "replies_6h": int(replies or 0), "memory": memory}


class Handler(BaseHTTPRequestHandler):
    server_version = "JingJingConsole/1.0"

    def log_message(self, fmt, *args):
        return

    def _json(self, payload: dict, code: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path: Path) -> None:
        data = path.read_bytes()
        ctype = {".html": "text/html; charset=utf-8", ".js": "application/javascript; charset=utf-8",
                 ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml"}.get(path.suffix, "text/plain")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _ops(self, name: str, body: dict | None = None) -> None:
        try:
            log("op " + name)
            if name == "backup":
                return self._json(_ops_backup())
            if name == "restart":
                return self._json(_ops_restart())
            if name == "recent":
                return self._json(_ops_recent())
            if name == "tunnel":
                return self._json(_ops_tunnel())
            if name == "report":
                hours = (body or {}).get("hours") or 24
                return self._json(_ops_report(int(hours)))
        except subprocess.TimeoutExpired:
            return self._json({"ok": False, "error": "ssh timeout"}, 504)
        except Exception as exc:
            return self._json({"ok": False, "error": str(exc)[:300]}, 500)
        self.send_error(404)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            return self._file(UI / "index.html")
        if parsed.path == "/api/ping":
            LAST_SEEN["at"] = time.time()
            return self._json({"ok": True})
        if parsed.path == "/api/chat":
            try:
                return self._json(_chat_config())
            except Exception as exc:
                return self._json({"ok": False, "error": str(exc)[:200]}, 500)
        if parsed.path == "/api/bili":
            try:
                return self._json(_bili_status())
            except Exception as exc:
                return self._json({"ok": False, "error": str(exc)[:200]}, 500)
        if parsed.path == "/api/account":
            try:
                return self._json(_ops_account())
            except Exception as exc:
                return self._json({"ok": False, "error": str(exc)[:300]}, 500)
        if parsed.path == "/api/ops/recent":
            try:
                return self._json(_ops_recent())
            except Exception as exc:
                return self._json({"ok": False, "error": str(exc)[:300]}, 500)
        if parsed.path == "/api/status":
            try:
                return self._json({"ok": True, **status()})
            except Exception as exc:
                return self._json({"ok": False, "error": str(exc)[:300]}, 500)
        candidate = (UI / parsed.path.lstrip("/")).resolve()
        if UI in candidate.parents and candidate.is_file():
            return self._file(candidate)
        self.send_error(404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            return self._json({"ok": False, "error": "bad json"}, 400)
        if parsed.path == "/api/chat":
            try:
                flag = body.get("active_reply")
                return self._json(_chat_config(set_active=bool(flag) if flag is not None else None))
            except Exception as exc:
                return self._json({"ok": False, "error": str(exc)[:200]}, 500)
        if parsed.path == "/api/bili":
            try:
                if "roam" in body:
                    return self._json(_bili_roam(bool(body.get("roam"))))
                return self._json(_bili_save(body))
            except Exception as exc:
                return self._json({"ok": False, "error": str(exc)[:200]}, 500)
        if parsed.path == "/api/rpc":
            try:
                return self._json(rpc(body.get("argv") or []))
            except subprocess.TimeoutExpired:
                log("rpc timeout")
                return self._json({"ok": False, "error": "ssh timeout"}, 504)
            except Exception as exc:
                log("rpc error: " + str(exc)[:200])
                return self._json({"ok": False, "error": str(exc)[:300]}, 500)
        if parsed.path == "/api/persona":
            try:
                return self._json(persona_rpc(body))
            except subprocess.TimeoutExpired:
                return self._json({"ok": False, "error": "ssh timeout"}, 504)
            except Exception as exc:
                log("persona error: " + str(exc)[:200])
                return self._json({"ok": False, "error": str(exc)[:300]}, 500)
        if parsed.path == "/api/account":
            try:
                return self._json(_ops_account())
            except Exception as exc:
                return self._json({"ok": False, "error": str(exc)[:300]}, 500)
        if parsed.path.startswith("/api/ops/"):
            return self._ops(parsed.path.rsplit("/", 1)[-1], body)
        if parsed.path == "/api/quit":
            for proc in TUNNELS.values():
                try:
                    proc.terminate()
                except Exception:
                    pass
            self._json({"ok": True})
            threading.Timer(0.3, lambda: os._exit(0)).start()
            return
        self.send_error(404)


OPS_BACKUP_DIR = Path("D:/Jingjing/backups/memory")


def _ops_backup() -> dict:
    OPS_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    remote = f"/home/ubuntu/jingjing/backups/memory-{stamp}.sqlite3"
    script = (
        "mkdir -p /home/ubuntu/jingjing/backups && "
        "python3 - <<'PY'\n"
        "import sqlite3\n"
        "src = sqlite3.connect('file:/home/ubuntu/jingjing/data/plugin_data/jingjing_memory/memory.sqlite3?mode=ro', uri=True)\n"
        f"dst = sqlite3.connect('{remote}')\n"
        "src.backup(dst)\n"
        "dst.close(); src.close()\n"
        "PY\n"
        f"sha256sum {remote}"
    )
    done = run_script(script, timeout=90)
    if done.returncode != 0:
        return {"ok": False, "error": done.stderr.decode("utf-8", "replace")[:300]}
    digest = done.stdout.decode("utf-8", "replace").split()[0]
    local = OPS_BACKUP_DIR / f"memory-{stamp}.sqlite3"
    copy = subprocess.run(["scp", "-F", SSH_CONFIG, "-o", "BatchMode=yes",
                           f"{SSH_HOST}:{remote}", str(local)], capture_output=True, timeout=120,
                          **_hidden())
    if copy.returncode != 0:
        return {"ok": False, "error": copy.stderr.decode("utf-8", "replace")[:300]}
    return {"ok": True, "remote": remote, "local": str(local), "sha256": digest,
            "bytes": local.stat().st_size}


def _ops_restart() -> dict:
    script = ("sudo -n docker restart -t 30 astrbot >/dev/null 2>&1; "
              "sudo -n docker inspect astrbot --format '{{.State.StartedAt}}'")
    done = run_script(script, timeout=120)
    if done.returncode != 0:
        return {"ok": False, "error": done.stderr.decode("utf-8", "replace")[:300]}
    return {"ok": True, "started_at": done.stdout.decode("utf-8", "replace").strip()}


ANSI = __import__("re").compile(r"\x1b\[[0-9;]*m")


TUNNELS: dict[str, subprocess.Popen] = {}


def _ops_account() -> dict:
    script = """python - <<'PY'
import json, pathlib
qq = ""
try:
    cfg = json.load(open("/AstrBot/data/config/astrbot_plugin_jingjing_memory_bridge_config.json", encoding="utf-8-sig"))
    ids = cfg.get("bot_qq_ids") or []
    qq = str(ids[0]) if ids else ""
except Exception:
    pass
conns = 0
for name in ("/proc/net/tcp", "/proc/net/tcp6"):
    path = pathlib.Path(name)
    if not path.is_file():
        continue
    for line in path.read_text().splitlines()[1:]:
        fields = line.split()
        try:
            if fields[3] == "01" and int(fields[2].split(":")[1], 16) == 6199:
                conns += 1
        except Exception:
            pass
print(json.dumps({"qq": qq, "adapter_connections": conns}))
PY
"""
    done = _ssh(["sudo", "-n", "docker", "exec", "-i", "astrbot", "sh", "-s"], stdin=script.encode())
    info = {"qq": ""}
    try:
        info.update(json.loads(_text(done.stdout).strip().splitlines()[-1]))
    except Exception:
        pass
    # The adapter socket is not reliably visible from /proc inside the
    # container (IPv6/bridge), so report the last connect/disconnect line AstrBot
    # itself logged. It is a record, not a live probe, and is labelled as such.
    logline = run_script(
        "sudo -n docker logs --since 48h astrbot 2>&1 | "
        "grep -aE '适配器已连接|适配器已断开|适配器连接断开' | tail -1")
    raw_log = ANSI.sub("", _text(logline.stdout)).strip()
    info["adapter_last"] = raw_log[-120:] if raw_log else ""
    info["adapter_connected"] = "已连接" in raw_log
    webui = run_script("sudo -n docker exec napcat sh -c 'cat /app/napcat/config/webui.json' 2>/dev/null || echo '{}'")
    token, port = "", 6099
    try:
        cfg = json.loads(_text(webui.stdout).strip() or "{}")
        token = str(cfg.get("token") or "")
        port = int(cfg.get("port") or 6099)
    except Exception:
        pass
    containers = run_script("sudo -n docker ps --format '{{.Names}}|{{.Status}}'")
    status = {}
    for line in _text(containers.stdout).splitlines():
        if "|" in line:
            name, state = line.split("|", 1)
            status[name.strip()] = state.strip()
    return {"ok": True, **info, "webui_port": port, "webui_token": token,
            "napcat": status.get("napcat", ""), "astrbot": status.get("astrbot", ""),
            "wechat": "未接入", "bilibili": "未接入"}


CHAT_CONFIG = "/home/ubuntu/jingjing/data/config/astrbot_plugin_xiaozhao_smart_mention_config.json"


def _chat_config(read_only: bool = True, set_active: bool | None = None) -> dict:
    """Read or flip the chat plugin switch (auto replies on/off)."""
    script = (
        "import json, shutil, datetime, pathlib\n"
        f"p = pathlib.Path('{CHAT_CONFIG}')\n"
        "data = json.loads(p.read_text(encoding='utf-8-sig'))\n"
        "before = data.get('active_reply_enabled')\n"
        f"target = {repr(set_active)}\n"
        "changed = False\n"
        "if target is not None and target != before:\n"
        "    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')\n"
        "    shutil.copyfile(p, pathlib.Path('/home/ubuntu/jingjing/plugin-backups') / ('config-' + stamp + '.json'))\n"
        "    data['active_reply_enabled'] = target\n"
        "    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8-sig')\n"
        "    changed = True\n"
        "print(json.dumps({'ok': True, 'active_reply': data.get('active_reply_enabled'),"
        " 'changed': changed, 'before': before}))\n"
    )
    done = _ssh(["sudo", "-n", "python3", "-"], stdin=script.encode(), timeout=60)
    raw = _text(done.stdout).strip()
    try:
        return json.loads(raw.splitlines()[-1])
    except Exception:
        return {"ok": False, "error": (raw or _text(done.stderr))[:200]}


BILI_DIR = "/home/ubuntu/jingjing/data/plugin_data/jingjing_bili"


def _bili_status() -> dict:
    # The cookie file is 0600 root-owned, so the check has to run as root too.
    done = run_script("sudo -n python3 /home/ubuntu/jingjing/tools/bili_status.py", timeout=60)
    raw = _text(done.stdout).strip()
    try:
        return json.loads(raw.splitlines()[-1])
    except Exception:
        return {"ok": False, "error": (raw or _text(done.stderr))[:200]}


def _bili_save(payload: dict) -> dict:
    record = {
        "sessdata": str(payload.get("sessdata") or "").strip(),
        "bili_jct": str(payload.get("bili_jct") or "").strip(),
        "buvid3": str(payload.get("buvid3") or "").strip(),
        "owner_uid": str(payload.get("owner_uid") or "").strip(),
    }
    if not record["sessdata"]:
        return {"ok": False, "error": "SESSDATA 不能为空"}
    blob = base64.b64encode(json.dumps(record, ensure_ascii=False).encode()).decode()
    # Piped over stdin: the cookie never appears on a command line or in a log.
    script = (
        "import base64, json, os, pathlib\n"
        "payload = json.loads(base64.b64decode('" + blob + "').decode())\n"
        "path = pathlib.Path('" + BILI_DIR + "/cookie.json')\n"
        "path.parent.mkdir(parents=True, exist_ok=True)\n"
        "path.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')\n"
        "os.chmod(path, 0o600)\n"
        "print('saved')\n"
    )
    done = _ssh(["sudo", "-n", "python3", "-"], stdin=script.encode(), timeout=60)
    if done.returncode != 0:
        return {"ok": False, "error": _text(done.stderr)[:200]}
    return _bili_status()


def _bili_roam(enabled: bool) -> dict:
    value = "1" if enabled else "0"
    script = (
        "import datetime, sqlite3\n"
        "db = '/home/ubuntu/jingjing/data/plugin_data/jingjing_memory/memory.sqlite3'\n"
        "con = sqlite3.connect(db)\n"
        "stamp = datetime.datetime.now().astimezone().isoformat(timespec='seconds')\n"
        "con.execute(\"INSERT INTO settings(key, value, updated_at) VALUES('bili_roam', ?, ?)\"\n"
        "            \" ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at\",\n"
        "            ('" + value + "', stamp))\n"
        "con.commit()\n"
        "print('ok')\n"
    )
    done = _ssh(["sudo", "-n", "python3", "-"], stdin=script.encode(), timeout=60)
    if done.returncode != 0:
        return {"ok": False, "error": _text(done.stderr)[:200]}
    return _bili_status()


def _ops_report(hours: int = 24) -> dict:
    """Behaviour summary for the last N hours, computed from the log."""
    hours = max(1, min(int(hours), 168))
    done = run_script(
        f"sudo -n docker logs --since {hours}h astrbot 2>&1 | python3 /home/ubuntu/jingjing/tools/chat_report.py",
        timeout=120)
    raw = _text(done.stdout).strip()
    line = raw.splitlines()[-1] if raw else ""
    try:
        report = json.loads(line)
    except Exception:
        return {"ok": False, "error": (line or _text(done.stderr))[:300]}
    report["hours"] = hours
    return report


def _ops_tunnel() -> dict:
    """Forward the NapCat WebUI to a random local port and open it."""
    port = free_port()
    proc = subprocess.Popen(
        ["ssh", "-F", SSH_CONFIG, "-o", "BatchMode=yes", "-o", "ExitOnForwardFailure=yes",
         "-N", "-L", f"127.0.0.1:{port}:127.0.0.1:6099", SSH_HOST],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        **_hidden(),
    )
    TUNNELS[str(port)] = proc
    time.sleep(0.8)
    if proc.poll() is not None:
        return {"ok": False, "error": "端口转发没起来，检查 ssh 是否可用"}
    url = f"http://127.0.0.1:{port}/"
    threading.Timer(0.4, lambda: open_window(url)).start()
    return {"ok": True, "url": url, "port": port}


def _ops_recent() -> dict:
    script = ("sudo -n docker logs --since 6h astrbot 2>&1 | "
              "grep 'Prepare to send' | tail -20 | sed -E 's/^.*Prepare to send - //'")
    done = run_script(script, timeout=60)
    raw = ANSI.sub("", done.stdout.decode("utf-8", "replace"))
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    return {"ok": True, "items": lines}


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


BROWSERS = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
)


def open_window(url: str) -> None:
    for exe in BROWSERS:
        if not os.path.isfile(exe):
            continue
        try:
            subprocess.Popen([exe, "--app=" + url, "--window-size=1180,820"],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, close_fds=True)
            return
        except Exception:
            continue
    webbrowser.open(url)


def main() -> None:
    log("console starting; ssh host=" + SSH_HOST)
    port = free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = "http://127.0.0.1:" + str(port) + "/"
    threading.Thread(target=server.serve_forever, daemon=True).start()

    def watchdog():
        # The page pings while its window is open. If the window is closed
        # without pressing 退出, stop instead of leaving an orphan process.
        while True:
            time.sleep(3)
            seen = LAST_SEEN["at"]
            if seen and time.time() - seen > IDLE_EXIT_SEC:
                log("idle exit after window closed")
                os._exit(0)

    threading.Thread(target=watchdog, daemon=True).start()
    if not os.environ.get("JJ_NO_WINDOW"):
        threading.Timer(0.6, lambda: open_window(url)).start()
    print("JingJing console: " + url, flush=True)
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    except Exception:
        import traceback
        log("fatal: " + traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
