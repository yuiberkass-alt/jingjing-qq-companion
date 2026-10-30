"""r17: a short line that starts or ends with the nickname is a call.

Observed 13:34: "憨憨大肥鱼" went to the judge model, which answered SKIP, and
the user got no reply after calling the bot by name. A nickname in the middle
of a sentence ("刚才那句小昭接得还挺自然") is still a judge case.
"""
import unittest
from unittest.mock import AsyncMock

from test_jingjing_repairs import plugin, FakeEvent
import main


def _p():
    from test_directed_guard import build_plugin
    return build_plugin({"mention_keywords": ["小昭"]})


class KeywordCallTests(unittest.IsolatedAsyncioTestCase):
    async def test_suffix_nickname_is_a_call(self):
        p = _p()
        decision, reason = await p._decide(FakeEvent(text="憨憨小昭"), "憨憨小昭")
        self.assertEqual((decision, reason), ("REPLY", "keyword_call"))

    async def test_prefix_nickname_question_is_a_call(self):
        p = _p()
        decision, _ = await p._decide(FakeEvent(text="小昭你明天吃什么"), "小昭你明天吃什么")
        self.assertEqual(decision, "REPLY")

    async def test_middle_nickname_still_goes_to_the_judge(self):
        p = _p()
        p._llm_decide = AsyncMock(return_value="SKIP")
        text = "刚才那句小昭接得还挺自然"
        decision, _ = await p._decide(FakeEvent(text=text), text)
        self.assertEqual(decision, "SKIP")
        self.assertEqual(p._llm_decide.await_count, 1)

    async def test_long_line_with_nickname_is_not_a_short_call(self):
        p = _p()
        text = "小昭今天下午老师拖堂拖了四十分钟我整个人都麻了真的想趴桌上睡过去"
        self.assertFalse(p._is_short_keyword_call(text))

    async def test_no_nickname_is_not_a_call(self):
        self.assertFalse(_p()._is_short_keyword_call("今天中午吃什么"))
