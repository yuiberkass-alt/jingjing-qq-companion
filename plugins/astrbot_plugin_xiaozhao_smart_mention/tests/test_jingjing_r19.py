"""r19: the bot should notice when a topic is over instead of talking on.

Observed in the new group: it answered every follow-up of a long thread and
kept asking follow-up questions, which reads as 话痨.
"""
import unittest
from unittest.mock import AsyncMock, patch

from test_jingjing_repairs import plugin, FakeEvent
import main


def remember(p, event, *, rounds):
    key = p._directed_group_key(event)
    stamp = main.monotonic() - 1
    p._jj_group_sessions[key] = (stamp, "刚才那句", rounds, str(event.get_sender_id()))
    p._jj_last_partner[key] = (stamp, str(event.get_sender_id()))


class TopicCloseTests(unittest.IsolatedAsyncioTestCase):
    async def _turn(self, p, event):
        p._get_or_create_conversation = AsyncMock(return_value=object())
        p._jj_semantic_decide = AsyncMock(return_value="REPLY")
        with patch.object(main, "_jj_wait", new=AsyncMock()):
            return [r async for r in p.smart_active_reply(event)]

    async def test_short_ack_ends_the_topic(self):
        for text in ("嗯", "哦哦", "行吧", "哈哈", "6", "晚安", "先这样"):
            p = plugin()
            event = FakeEvent(text=text)
            remember(p, event, rounds=2)
            self.assertEqual(await self._turn(p, event), [], text)

    async def test_normal_line_still_gets_a_reply(self):
        p = plugin()
        event = FakeEvent(text="那你明天吃什么")
        remember(p, event, rounds=1)  # early turns are unaffected
        self.assertEqual(len(await self._turn(p, event)), 1)

    async def test_long_streak_needs_more_than_a_statement(self):
        p = plugin()
        short_statement = FakeEvent(text="今天真热啊")
        remember(p, short_statement, rounds=7)
        self.assertEqual(await self._turn(p, short_statement), [])

        p2 = plugin()
        question = FakeEvent(text="那你说明天要不要带伞呢")
        remember(p2, question, rounds=7)
        self.assertEqual(len(await self._turn(p2, question)), 1)

    def test_call_by_name_reopens_the_topic(self):
        # A name call never reaches this path (smart_mention owns it), but the
        # closing rule must still treat it as an opening, not an ending.
        p = plugin()
        p.mention_keywords = ["小昭"]
        event = FakeEvent(text="小昭")
        self.assertFalse(p._jj_should_close_topic(event, "小昭", 9))
        self.assertTrue(p._jj_should_close_topic(event, "嗯", 9))

    async def test_long_thread_gets_a_short_reply_hint(self):
        p = plugin()
        event = FakeEvent(text="那你继续说啊")
        remember(p, event, rounds=3)
        await self._turn(p, event)
        self.assertTrue(event.get_extra("jj_short_reply"))

    def test_closing_detector(self):
        self.assertTrue(main._jj_is_closing_message("嗯嗯"))
        self.assertTrue(main._jj_is_closing_message("……"))
        self.assertFalse(main._jj_is_closing_message("那你说说看"))
