"""r14: emoji rate follows the mood, and the prompt asks for the feeling first."""
import unittest

from test_jingjing_repairs import plugin
import main


class EmojiRateTests(unittest.TestCase):
    TEXT = "就这么耗着呗"

    def test_warm_turn_gets_a_much_higher_rate(self):
        # Same draw, different mood: 0.5 is above the neutral rate but below
        # the warm one, so the mood is what decides.
        self.assertEqual(main._jj_optional_chat_emoji(self.TEXT, "", 0.5), self.TEXT)
        self.assertTrue(main._jj_optional_chat_emoji(self.TEXT, "", 0.5, rate=0.9).endswith("🐳")
                        or main._jj_optional_chat_emoji(self.TEXT, "", 0.5, rate=0.9).endswith("🐋")
                        or main._jj_optional_chat_emoji(self.TEXT, "", 0.5, rate=0.9).endswith("😌"))

    def test_serious_topic_never_decorated(self):
        self.assertEqual(main._jj_optional_chat_emoji("别慌，我在", "我住院了", 0.01, rate=0.9), "别慌，我在")

    def test_existing_emoji_is_not_doubled(self):
        self.assertEqual(main._jj_optional_chat_emoji("好耶😌", "", 0.01, rate=0.9), "好耶😌")


class EmotionRuleTests(unittest.TestCase):
    def test_emotion_first_rule_present(self):
        reminder = plugin()._natural_chat_style_reminder("mention")
        self.assertIn("先看这句背后的情绪", reminder)
        self.assertIn("别一本正经地讲事实", reminder)
