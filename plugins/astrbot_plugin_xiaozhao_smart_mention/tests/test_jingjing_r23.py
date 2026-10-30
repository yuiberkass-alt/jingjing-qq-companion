"""r23: stay out of fights, but never stay silent at someone in crisis."""
import unittest
from unittest.mock import AsyncMock, patch

from test_jingjing_repairs import plugin, FakeEvent
import main


class TopicTests(unittest.TestCase):
    def test_risk_topics_detected(self):
        for text in ("你站谁", "这个政治问题怎么看", "他们信什么宗教", "发点色情图"):
            self.assertIsNotNone(main._jj_risk_topic(text), text)
        for text in ("今天吃什么", "鲸鲸好可爱", "帮我看看这个报错"):
            self.assertIsNone(main._jj_risk_topic(text), text)

    def test_care_detected(self):
        self.assertTrue(main._jj_care_needed("我不想活了"))
        self.assertFalse(main._jj_care_needed("今天上班好累"))


class TopicBlockTests(unittest.IsolatedAsyncioTestCase):
    async def _turn(self, p, event):
        p._get_or_create_conversation = AsyncMock(return_value=object())
        p._jj_semantic_decide = AsyncMock(return_value="REPLY")
        with patch.object(main, "_jj_wait", new=AsyncMock()):
            return [r async for r in p.smart_active_reply(event)]

    async def test_politics_is_not_joined(self):
        p = plugin()
        p.jj_semantic_group_ids = ["group-a"]
        event = FakeEvent(text="你们觉得这个政治事件谁对")
        self.assertEqual(await self._turn(p, event), [])
        p._jj_semantic_decide.assert_not_awaited()

    async def test_crisis_still_gets_a_reply(self):
        p = plugin()
        p.jj_semantic_group_ids = ["group-a"]
        event = FakeEvent(text="我真的不想活了")
        self.assertEqual(len(await self._turn(p, event)), 1)
