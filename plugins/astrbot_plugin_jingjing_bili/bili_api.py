"""Minimal Bilibili client: private messages, video info, comments.

Everything authenticates with the operator's own cookie (SESSDATA / bili_jct /
buvid3). The cookie value is never logged, and responses come back as plain
dicts so callers can check code == 0.
"""
from __future__ import annotations

import hashlib
import json
import time
import urllib.parse
import urllib.request
import uuid

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
REFERER = "https://www.bilibili.com/"
MIXIN = [46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
         33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40, 61,
         26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36,
         20, 34, 44, 52]


class BiliError(Exception):
    pass


class BiliClient:
    def __init__(self, *, sessdata: str, bili_jct: str = "", buvid3: str = "", uid: str = ""):
        self.sessdata = sessdata.strip()
        self.bili_jct = bili_jct.strip()
        self.buvid3 = buvid3.strip() or (str(uuid.uuid4()).upper() + "infoc")
        self.uid = str(uid).strip()
        self._wbi_key = ""
        self._wbi_at = 0.0

    def _cookie(self) -> str:
        parts = ["SESSDATA=" + self.sessdata, "buvid3=" + self.buvid3]
        if self.bili_jct:
            parts.append("bili_jct=" + self.bili_jct)
        return "; ".join(parts)

    def _open(self, url: str, data: bytes | None = None, timeout: float = 15.0) -> dict:
        headers = {
            "User-Agent": UA,
            "Referer": REFERER,
            "Cookie": self._cookie(),
            "Accept": "application/json, text/plain, */*",
        }
        if data is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        request = urllib.request.Request(url, data=data, headers=headers)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", "replace")
        try:
            return json.loads(raw)
        except Exception as exc:
            raise BiliError("bad json: " + raw[:120]) from exc

    def _sign(self, params: dict) -> str:
        if not self._wbi_key or time.time() - self._wbi_at > 3600:
            nav = self._open("https://api.bilibili.com/x/web-interface/nav")
            images = nav.get("data", {}).get("wbi_img", {})
            img = images.get("img_url", "").rsplit("/", 1)[-1].split(".")[0]
            sub = images.get("sub_url", "").rsplit("/", 1)[-1].split(".")[0]
            self._wbi_key = "".join((img + sub)[i] for i in MIXIN)[:32]
            self._wbi_at = time.time()
        signed = dict(params, wts=int(time.time()))
        query = urllib.parse.urlencode(sorted(signed.items()))
        signed["w_rid"] = hashlib.md5((query + self._wbi_key).encode()).hexdigest()
        return urllib.parse.urlencode(sorted(signed.items()))

    @staticmethod
    def _ok(payload: dict) -> dict:
        if payload.get("code") != 0:
            raise BiliError(str(payload.get("code")) + ": " +
                            str(payload.get("message") or payload.get("msg")))
        return payload.get("data") or {}

    def whoami(self) -> dict:
        data = self._open("https://api.bilibili.com/x/web-interface/nav")
        if data.get("code") != 0 or not data.get("data", {}).get("isLogin"):
            raise BiliError("账号未登录或 cookie 失效")
        info = data["data"]
        if info.get("mid"):
            self.uid = str(info["mid"])
        return {"uid": self.uid, "name": info.get("uname", ""), "vip": info.get("vipStatus", 0)}

    def sessions(self) -> list[dict]:
        query = urllib.parse.urlencode({"session_type": 1, "group_id": 0, "end_ts": 0})
        data = self._open("https://api.vc.bilibili.com/session_svr/v1/session_svr/get_sessions?" + query)
        return ((data.get("data") or {}).get("session_list") or [])

    def messages(self, talker_id: str, end_seqno: int = 0) -> list[dict]:
        query = urllib.parse.urlencode({
            "talker_id": talker_id, "session_type": 1, "size": 20,
            "end_seqno": end_seqno, "build": 0, "mobi_app": "web",
        })
        data = self._open("https://api.vc.bilibili.com/svr_sync/v1/svr_sync/fetch_session_msgs?" + query)
        payload = data.get("data") or {}
        return list(reversed(payload.get("messages") or []))

    def send_dm(self, receiver_uid: str, text: str) -> dict:
        if not self.bili_jct:
            raise BiliError("缺少 bili_jct，无法发送")
        if not self.uid:
            # sender_uid must be the account's own uid or Bilibili answers -400.
            try:
                self.whoami()
            except Exception:
                pass
        if not self.uid:
            raise BiliError("无法确定发送者 uid")
        body = {
            "msg[sender_uid]": self.uid or "0",
            "msg[receiver_id]": str(receiver_uid),
            "msg[receiver_type]": "1",
            "msg[msg_type]": "1",
            "msg[msg_status]": "0",
            "msg[dev_id]": "AUTO",
            "msg[timestamp]": str(int(time.time())),
            "msg[content]": json.dumps({"content": text}, ensure_ascii=False),
            "csrf": self.bili_jct,
            "csrf_token": self.bili_jct,
        }
        data = urllib.parse.urlencode(body).encode()
        return self._ok(self._open("https://api.vc.bilibili.com/web_im/v1/web_im/send_msg", data=data))

    def video_info(self, bvid: str) -> dict:
        data = self._ok(self._open("https://api.bilibili.com/x/web-interface/view?bvid=" + bvid))
        return {
            "bvid": data.get("bvid"),
            "aid": data.get("aid"),
            "title": data.get("title", ""),
            "desc": (data.get("desc") or "")[:400],
            "owner": (data.get("owner") or {}).get("name", ""),
            "views": (data.get("stat") or {}).get("view", 0),
            "duration": data.get("duration", 0),
        }

    def search(self, keyword: str, limit: int = 5) -> list[dict]:
        query = self._sign({"search_type": "video", "keyword": keyword, "page": 1})
        data = self._open("https://api.bilibili.com/x/web-interface/wbi/search/type?" + query)
        items = ((data.get("data") or {}).get("result") or [])
        out = []
        for item in items[:limit]:
            title = (item.get("title") or "")
            title = title.replace("<em class=\"keyword\">", "").replace("</em>", "")
            out.append({
                "bvid": item.get("bvid", ""),
                "title": title,
                "author": item.get("author", ""),
                "play": item.get("play", 0),
            })
        return out

    def add_comment(self, oid: int, message: str, root: int | None = None, parent: int | None = None) -> dict:
        if not self.bili_jct:
            raise BiliError("缺少 bili_jct，无法评论")
        body = {"oid": str(oid), "type": "1", "message": message,
                "csrf": self.bili_jct, "plat": "1"}
        if root:
            body["root"] = str(root)
            body["parent"] = str(parent or root)
        data = urllib.parse.urlencode(body).encode()
        return self._ok(self._open("https://api.bilibili.com/x/v2/reply/add", data=data))

    def emotes(self) -> list[str]:
        """Emoji codes usable in a DM, e.g. '[doge_金箍]'."""
        data = self._open("https://api.bilibili.com/x/emote/user/panel/web?business=im")
        out: list[str] = []
        for package in ((data.get("data") or {}).get("packages") or []):
            for emote in (package.get("emote") or []):
                text = emote.get("text") or ""
                if text.startswith("[") and text.endswith("]"):
                    out.append(text)
        return out

    def resolve_short(self, url: str) -> str:
        """Follow a b23.tv short link to the full video URL."""
        try:
            request = urllib.request.Request(url, headers={"User-Agent": UA, "Cookie": self._cookie()})
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.geturl()
        except Exception:
            return ""

    def comments(self, oid: int, limit: int = 10) -> list[dict]:
        query = urllib.parse.urlencode({"type": 1, "oid": oid, "sort": 0, "ps": limit, "pn": 1})
        data = self._ok(self._open("https://api.bilibili.com/x/v2/reply?" + query))
        out = []
        for reply in (data.get("replies") or [])[:limit]:
            out.append({
                "rpid": reply.get("rpid"),
                "user": (reply.get("member") or {}).get("uname", ""),
                "uid": (reply.get("mid") or 0),
                "message": (reply.get("content") or {}).get("message", ""),
                "like": reply.get("like", 0),
            })
        return out