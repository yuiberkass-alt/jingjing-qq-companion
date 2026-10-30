"""r13: picture eligibility must read the recent inputs, and the tone rules.

Observed 13:00-13:01 on the live group: five replies, zero pictures, while the
user sent two photos and an emoji. The gate only looked at the current line, so
a picture that arrived as its own message - or as a supplement merged into the
request - was invisible to it.
"""
import unittest
from unittest.mock import AsyncMock

from test_jingjing_repairs import plugin, FakeEvent, FakeResult, Image, Plain, response
import main


class EligibilityContextTests(unittest.TestCase):
    def test_recent_picture_makes_the_turn_eligible(self):
        p = plugin()
        self.assertTrue(p._jj_sticker_eligible_by_content(
            "大肥鱼", "喊一声就够啦，你还真喊上瘾了",
            "華kas: 大肥鱼 [图片 x1]\n華kas: 大肥鱼大肥鱼"))

    def test_recent_emoji_makes_the_turn_eligible(self):
        p = plugin()
        self.assertTrue(p._jj_sticker_eligible_by_content(
            "大白饭吗", "对啊，大白饭", "華kas: [表情:13]"))

    def test_flat_history_stays_ineligible(self):
        p = plugin()
        self.assertFalse(p._jj_sticker_eligible_by_content(
            "今天几号", "周四", "華kas: 今天几号"))

    def test_playful_endings_cover_ba_and_a(self):
        p = plugin()
        self.assertTrue(p._jj_sticker_eligible_by_content("几点", "随便找家近的吃一口吧"))
        self.assertTrue(p._jj_sticker_eligible_by_content("几点", "还早着呢"))


class StickerAfterPictureTests(unittest.TestCase):
    def test_picture_supplement_makes_the_selector_run(self):
        from pathlib import Path
        p = plugin()
        p._jj_sticker_path = lambda name: Path("/synthetic/" + str(name) + ".png")
        picture = FakeEvent(text="", messages=[Image("/synthetic/cat.png")])
        p._record_input_event(picture)
        event, _ = response(p, "喊一声就够啦，你还真喊上瘾了", FakeEvent(text="大肥鱼"))
        event.set_extra(main.EXTRA_JJ_STICKER_STATUS, "no_marker")
        p._call_internal_model = AsyncMock(
            return_value='{"name":"' + p._jj_sticker_selector.assets[0]["name"] + '"}'
        )
        import asyncio
        asyncio.run(p._jj_choose_contextual_sticker(event, event.result))
        self.assertTrue(event.get_extra(main.EXTRA_JJ_STICKER))
        self.assertEqual(p._call_internal_model.await_count, 1)


class ToneRuleTests(unittest.TestCase):
    def test_no_dismissive_openers(self):
        reminder = plugin()._natural_chat_style_reminder("mention")
        self.assertIn("又有啥事", reminder)
        self.assertIn("不要把对方的靠近当成打扰", reminder)

    def test_no_unsolicited_advice(self):
        reminder = plugin()._natural_chat_style_reminder("mention")
        self.assertIn("不要下指令", reminder)
