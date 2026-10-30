"""JingJing's Bilibili account: private messages, and (optionally) roaming.

One background loop does two things:
  * answers the operator's DMs, including videos he shares
  * when roaming is allowed, wanders off now and then and shares what it found

Roaming is toggled by the operator's own words ("可以逛了" / "别逛了") and by the
console switch. Commenting is a separate, still-disabled capability.
"""
from __future__ import annotations

import asyncio
import re
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import filter
from astrbot.api.star import Context, Star

from .bili_api import BiliClient
from .bili_bot import (DB, add_recommended, extract_bvid, last_key, last_recommended,
                       last_roam, load_cookie, mark_roam, maybe_toggle_roam, poll,
                       roam_enabled, set_last_key)
from .memory_note import refresh_note

PERSONA_DB = Path("/AstrBot/data/data_v4.db")
PERSONA_ID = "jingjing_v0.4"
EXTRA = (
    "\n\n【当前场景】你在 B 站私信里和对方说话。这里只有你们两个人，"
    "可以稍微放松一点，但仍然是鲸鲸：短句、自然、软。不要提 QQ、群聊或其他人。"
    "不要在回复里展示这些方括号里的说明。"
    "\n【你的能力】你手里有个小工具，可以真的在 B 站搜视频、看视频的标题和简介；"
    "对方让你去逛、或者分享视频给你时，就答应并真的去看。评论需要对方同意，没同意就不要提。"
)


def persona_prompt() -> str:
    try:
        con = sqlite3.connect(f"file:{PERSONA_DB.as_posix()}?mode=ro", uri=True)
        try:
            row = con.execute("SELECT system_prompt FROM personas WHERE persona_id=?",
                              (PERSONA_ID,)).fetchone()
            return (row[0] if row else "") + EXTRA
        finally:
            con.close()
    except Exception:
        return "你是鲸鲸，一个说话很软很短的 AI 朋友。" + EXTRA


class JingJingBili(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.interval = max(15, int(config.get("poll_interval_sec", 30)))
        # Idle wandering is expensive; make it rare and opt-in only.
        self.roam_every_min = max(120, int(config.get("roam_interval_min", 360)))
        self._roam_once = False
        self._task = None
        self._busy = False
        self._emotes: list[str] = []
        self._lines: list[str] = []
        self._emotes_at = 0.0
        logger.info("[JingJingBili] loaded; cookie=%s roam=%s",
                    "yes" if load_cookie() else "no", roam_enabled(DB))

    @filter.on_astrbot_loaded()
    async def start_loop(self):
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())
            logger.info("[JingJingBili] polling started every %ss", self.interval)

    def _client(self) -> BiliClient | None:
        data = load_cookie()
        if not data or not data.get("sessdata"):
            return None
        return BiliClient(sessdata=data["sessdata"], bili_jct=data.get("bili_jct", ""),
                          buvid3=data.get("buvid3", ""), uid=data.get("uid", ""))

    async def _loop(self) -> None:
        await asyncio.sleep(5)
        while True:
            try:
                await self._tick()
                await self._maybe_roam()
            except Exception as exc:
                logger.warning("[JingJingBili] tick skipped (%s): %s",
                               type(exc).__name__, str(exc)[:160])
            await asyncio.sleep(self.interval)

    def _emote_codes(self, client: BiliClient) -> list[str]:
        if self._emotes and time.time() - self._emotes_at < 6 * 3600:
            return self._emotes
        try:
            codes = client.emotes()
            if codes:
                self._emotes = codes
                self._emotes_at = time.time()
        except Exception:
            pass
        return self._emotes

    def _clean_emoji(self, text: str) -> str:
        """Drop any bracket token that is not a real Bilibili emoji."""
        allowed = set(self._emotes)

        def repl(match):
            token = match.group(0)
            return token if token in allowed else ""

        return re.sub(r"\[[^\[\]]{1,16}\]", repl, text).strip()

    async def _provider(self):
        get_provider = getattr(self.context, "get_using_provider", None)
        if callable(get_provider):
            return get_provider("bili:dm:owner")
        return None

    async def _generate(self, prompt: str) -> str:
        provider = await self._provider()
        if provider is None:
            return ""
        client = self._client()
        codes = self._emote_codes(client) if client else []
        system = persona_prompt()
        if codes:
            system += ("\n想加表情时，只能从这些 B 站表情里挑一个，原样写在句末："
                       + " ".join(codes[:40]) + "。不要用 emoji、不要用别的括号表情。")
        try:
            resp = await asyncio.wait_for(
                provider.text_chat(prompt=prompt, system_prompt=system, contexts=[]),
                timeout=45)
            return (getattr(resp, "completion_text", "") or "").strip()
        except Exception as exc:
            logger.warning("[JingJingBili] reply failed (%s)", type(exc).__name__)
            return ""

    async def _tick(self) -> None:
        data = load_cookie()
        if not data or self._busy:
            return
        owner = str(data.get("owner_uid") or "")
        client = self._client()
        if not owner or client is None:
            return
        self._busy = True
        try:
            seen = last_key(DB)
            for message in poll(client, owner, seen):
                if message.sender_uid and message.sender_uid != owner:
                    continue
                switch = maybe_toggle_roam(message.text, DB)
                video = self._video_of(client, message.text)
                prompt = message.text
                if video:
                    prompt += (
                        f"\n（对方分享了一个 B 站视频，你刚去看了：《{video['title']}》，"
                        f"UP 主：{video['owner']}，简介：{video['desc'][:150]}。"
                        "用一句自然的话回应，说说你的感觉；不要复述简介，不要编造内容。）"
                    )
                if switch == "on":
                    prompt += "\n（对方刚同意了你可以自己去逛 B 站，简短回应一句）"
                elif switch == "off":
                    prompt += "\n（对方刚收回逛 B 站的许可，简短应一声就好）"
                elif switch == "once":
                    self._roam_once = True
                    prompt += "\n（对方让你现在去逛一趟，简短答应一句，看完会告诉他）"
                reply = await self._generate(prompt)
                if not reply:
                    set_last_key(message.seqno, DB)
                    continue
                reply = self._clean_emoji(reply)
                try:
                    client.send_dm(owner, reply[:900])
                except Exception as exc:
                    logger.warning("[JingJingBili] send failed (%s): %s",
                                   type(exc).__name__, str(exc)[:160])
                    continue
                set_last_key(message.seqno, DB)
                self._lines.append(message.text[:120])
                self._lines.append(reply[:120])
                del self._lines[:-24]
                # Rewrite one compact note instead of storing raw lines.
                if len(self._lines) >= 6:
                    try:
                        await refresh_note(await self._provider(), db=DB, platform="bilibili",
                                           bot_id="bili", group_id="", user_id=owner,
                                           transcript="\n".join(self._lines))
                        self._lines.clear()
                    except Exception as exc:
                        logger.warning("[JingJingBili] note skipped (%s)", type(exc).__name__)
                logger.info("[JingJingBili] replied to a DM (%d chars)", len(reply))
        finally:
            self._busy = False

    def _video_of(self, client: BiliClient, text: str) -> dict | None:
        bvid = extract_bvid(text, client)
        if not bvid:
            return None
        try:
            return client.video_info(bvid)
        except Exception:
            return None

    async def _maybe_roam(self) -> None:
        once = self._roam_once
        if not once and not roam_enabled(DB):
            return
        if once:
            self._roam_once = False
        stamp = last_roam(DB)
        if stamp and not once:
            try:
                if datetime.now().astimezone() - datetime.fromisoformat(stamp) < \
                        timedelta(minutes=self.roam_every_min):
                    return
            except Exception:
                pass
        data = load_cookie()
        client = self._client()
        if not data or client is None:
            return
        owner = str(data.get("owner_uid") or "")
        topic = self._roam_topic()
        try:
            found = client.search(topic, 6)
        except Exception as exc:
            logger.warning("[JingJingBili] search failed (%s)", type(exc).__name__)
            return
        seen = last_recommended(DB)
        for item in found:
            bvid = item.get("bvid") or ""
            if not bvid or bvid in seen:
                continue
            try:
                info = client.video_info(bvid)
            except Exception:
                continue
            text = await self._generate(
                f"你在 B 站逛到一个视频，想分享给对方：《{info['title']}》，"
                f"UP 主：{info['owner']}。用一句话说说你为什么想给他看，语气随意一点。"
            )
            if not text:
                text = f"看到一个挺有意思的，《{info['title']}》"
            text = self._clean_emoji(text) + f"\nhttps://www.bilibili.com/video/{info['bvid']}"
            try:
                client.send_dm(owner, text[:900])
            except Exception as exc:
                logger.warning("[JingJingBili] roam send failed (%s): %s",
                               type(exc).__name__, str(exc)[:120])
                return
            add_recommended(bvid, DB)
            mark_roam(DB)
            remember(DB, uid=owner, content=("逛 B 站看到：" + info["title"])[:80])
            logger.info("[JingJingBili] shared a video while roaming")
            return

    def _roam_topic(self) -> str:
        try:
            con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
            try:
                row = con.execute(
                    "SELECT content FROM memories WHERE status='active' AND category='interest'"
                    " ORDER BY evidence_count DESC, id DESC LIMIT 1").fetchone()
                if row and row[0]:
                    return row[0][:20]
            finally:
                con.close()
        except Exception:
            pass
        return "动画 推荐"
