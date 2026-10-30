"""Persona-independent presentation regressions; no QQ sends."""
import re
import unittest
from unittest.mock import patch
from test_jingjing_repairs import plugin, response, prepare, FakeEvent, Plain, Image, NATIVE_REGEX
import main


class PresentationTests(unittest.TestCase):
    def test_real_feedback_pauses(self):
        for text in ['喊这么多遍，我又不会跑掉，说吧', '才一晚上没见，就又想了呀',
                     '吃了，白饭两碗，差点都被你抢走', '困就早点躺下，别又刷手机刷到半夜']:
            formatted = main._jj_chat_paragraphs(text)
            self.assertEqual(len(formatted.split('\n\n')), 2, text)
            self.assertEqual(formatted.replace('\n\n', ''), text)
            self.assertEqual(main._jj_chat_paragraphs(formatted), formatted)

    def test_short_clause_and_quote_not_forced_apart(self):
        for text in ['吃了，白饭两碗', '行吧', '他说“困就早点躺下，别又刷手机刷到半夜”']:
            self.assertEqual(main._jj_chat_paragraphs(text), text)

    def test_emoji_weight_and_probability(self):
        samples = [main._jj_optional_chat_emoji('好呀', '', i / 1000) for i in range(1000)]
        self.assertEqual(sum(s != '好呀' for s in samples), 350)
        self.assertEqual(sum(s.endswith(('🐳', '🐋')) for s in samples), 300)

    def test_emoji_context_and_existing_emoji(self):
        for text, incoming in [('好呀😏', ''), ('好呀', '不要emoji'), ('好呀', '我很难过'),
                               ('执行命令：docker restart', ''), ('收到', ''), ('```好呀```', '')]:
            self.assertEqual(main._jj_optional_chat_emoji(text, incoming, 0), text)

    def test_final_pipeline_without_persona_or_response_hook_keeps_image(self):
        p = plugin()
        e, _ = response(p, '困就早点躺下，别又刷手机刷到半夜[[JJ_STICKER:happy]]')
        prepare(p, e)
        text = ''.join(c.text for c in e.result.chain if isinstance(c, Plain))
        self.assertEqual(len(re.findall(NATIVE_REGEX, text)), 2)
        self.assertTrue(any(isinstance(c, Image) for c in e.result.chain))
        self.assertFalse(any(s.endswith(('，', '。')) for s in text.split('\n\n')))

    def test_final_emoji_only_once_and_can_be_disabled(self):
        p = plugin(); p.jj_stickers_enabled = False
        p.jj_semantic_emoji_enabled = True
        e, _ = response(p, '好呀', FakeEvent(text='聊天'))
        with patch.object(main.random, 'random', return_value=0):
            prepare(p, e); prepare(p, e)
        self.assertEqual(''.join(c.text for c in e.result.chain if isinstance(c, Plain)), '好呀🐳')
        p.jj_semantic_emoji_enabled = False
        e, _ = response(p, '好呀', FakeEvent(text='聊天'))
        with patch.object(main.random, 'random', return_value=0):
            prepare(p, e)
        self.assertEqual(''.join(c.text for c in e.result.chain if isinstance(c, Plain)), '好呀')
