"""r24: replies must be speech, not narration, and not a bare filler."""
import unittest

import test_jingjing_repairs  # noqa: F401  (installs the astrbot stubs)
import main


class MetaStripTests(unittest.TestCase):
    def test_drops_narration_lines(self):
        text = "用户“ruarua你的大尾巴”在发摸摸\n我需要自然回一句话😋"
        self.assertEqual(main._strip_meta_narration(text), text)

    def test_keeps_real_reply(self):
        self.assertEqual(main._strip_meta_narration("欸嘿，摸摸头"), "欸嘿，摸摸头")

    def test_mixed(self):
        text = "我需要自然回一句话\n抱抱你呀"
        self.assertEqual(main._strip_meta_narration(text), "抱抱你呀")

    def test_never_returns_empty(self):
        text = "我需要自然回一句话"
        self.assertEqual(main._strip_meta_narration(text), text)