"""User screenshot regressions, exercised through final send preparation."""
import asyncio
import unittest
from collections import defaultdict, deque
from unittest.mock import patch

import test_jingjing_repairs as fixtures
from test_jingjing_repairs import main, plugin, response, prepare, FakeEvent, FakeResult, Plain, Image, At, StickerSelector


class StyleR2Tests(unittest.TestCase):
    def test_screenshot_short_clauses_stay_together(self):
        for text in ['别乱rua，鳞片都要被你摸掉了', '因为一rua我就痒，急了还会咬你一口，掂量着来', '行行行，你rua吧，别太狠就行']:
            p = plugin()
            event, _ = response(p, text)
            prepare(p, event)
            self.assertEqual(event.sent_messages, [])
            self.assertEqual(event.result.chain[0].text, text)

    def test_one_two_three_beats_follow_model_content(self):
        for count in [1, 2, 3]:
            p = plugin()
            p.context.get_config = lambda _: {'platform_settings': {'segmented_reply': {'enable': True}}}
            parts = ['行吧', '手劲轻点', '我今天已经够困了'][:count]
            event, _ = response(p, '\n\n'.join(parts))
            prepare(p, event)
            self.assertEqual(event.result.chain[0].text.split('\n\n'), parts)
            self.assertFalse(p.context.provider.calls)

    def test_all_prose_end_punctuation_removed_internal_preserved(self):
        text = '行行行，\n\n可以摸，轻点呀？！……'
        self.assertEqual(main._jj_trim_chat_endings(text), '行行行\n\n可以摸，轻点呀')

    def test_emoji_and_quoted_punctuation_preserved(self):
        for text, expected in [('轻点😏！', '轻点😏'), ('好耶👩🏽‍💻', '好耶👩🏽‍💻'), ('她说“别乱摸！”', '她说“别乱摸！”'), ('😏', '😏'), ('？', '？')]:
            self.assertEqual(main._jj_trim_chat_endings(text), expected)

    def test_technical_content_untouched(self):
        for text in ['```python\nprint("x!")\n\nprint("y?")\n```', '参考 https://example.test/a,b?q=x!', '配置检查：\n1. enable=True\n2. timeout=10']:
            self.assertEqual(main._jj_trim_chat_endings(text), text)
            self.assertEqual(main._jj_chat_paragraphs(text), text)

    def test_final_guard_text_also_has_no_end_period(self):
        p = plugin()
        event, _ = response(p, '发了呀。', FakeEvent(text='表情包呢'))
        prepare(p, event)
        self.assertFalse(event.result.chain[0].text.endswith('。'))
        self.assertNotIn('发了呀', event.result.chain[0].text)

    def test_headers_and_image_survive_cleanup(self):
        p = plugin()
        event, _ = response(p, '轻点呀😏！\n[[JJ_STICKER:happy]]')
        header = At('123')
        event.result.chain.insert(0, header)
        prepare(p, event)
        self.assertIs(event.result.chain[0], header)
        self.assertEqual(next(c.text for c in event.result.chain if isinstance(c, Plain)), '轻点呀😏')
        self.assertEqual(sum(isinstance(c, Image) for c in event.result.chain), 1)

    def test_non_model_messages_unchanged(self):
        p = plugin()
        event = FakeEvent()
        event.result = FakeResult([Plain('操作完成。')], model_result=False)
        prepare(p, event)
        self.assertEqual(event.result.chain[0].text, '操作完成。')

    def test_three_paragraph_cap_does_not_drop_words(self):
        text = '第一段\n\n第二段\n\n第三段\n\n第四段'
        result = main._jj_chat_paragraphs(text)
        self.assertEqual(len(result.split('\n\n')), 3)
        self.assertEqual(result.replace('\n\n', ''), text.replace('\n\n', ''))

    def test_rua_candidates_without_previous_chat(self):
        s = StickerSelector.__new__(StickerSelector)
        s.assets = [{'name': 'close', 'category': '亲近与安慰'}]
        s.recent = defaultdict(lambda: deque(maxlen=20))
        import random
        s.random = random.Random(0)
        self.assertEqual([a['name'] for a in s.candidates('就rua', 'g')], ['close'])

    def test_style_instruction_calls_for_context_not_count_rotation(self):
        reminder = plugin()._natural_chat_style_reminder('active_reply')
        for phrase in ['一句够了就停', '不要固定两句', '不要轮流凑一二三句', '每段末尾不带']:
            self.assertIn(phrase, reminder)


if __name__ == '__main__':
    unittest.main()
