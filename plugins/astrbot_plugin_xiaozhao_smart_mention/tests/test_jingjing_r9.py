import unittest, types, json
from unittest.mock import AsyncMock, patch
from test_jingjing_repairs import plugin, FakeEvent, Plain, Image
from test_directed_guard import FakeResult
import test_jingjing_r3 as r3
import main

class PresentationTests(unittest.TestCase):
    def test_feedback_condition_is_separate_beat(self):
        text='行啊，那我就一直这样，你也别嫌烦'
        self.assertEqual(main._jj_trim_chat_endings(main._jj_chat_paragraphs(text)),
                         '行啊，那我就一直这样\n\n你也别嫌烦')

    def test_casual_emoji_coverage_without_forcing_every_reply(self):
        for text in ['刚睡醒，正趴着发呆呢', '这张脸凑这么近，是等着我夸你呀', '行啊，那我就一直这样，你也别嫌烦']:
            self.assertTrue(main._jj_optional_chat_emoji(text,'',.1).endswith('🐳'))
            self.assertEqual(main._jj_optional_chat_emoji(text,'',.9),text)
            self.assertEqual(main._jj_optional_chat_emoji(text,'今天很难过',.1),text)

class ConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_text_during_selection_suppresses_old_reply(self):
        p=plugin(); e=FakeEvent(text='第一句话');p._record_input_event(e)
        e.result=FakeResult([Plain('旧回复')])
        async def selecting(*args):
            p._record_input_event(FakeEvent(text='还有补充'))
        p._jj_choose_contextual_sticker=AsyncMock(side_effect=selecting)
        with patch.object(p,'_jj_prepare_sticker') as attach:
            await p.send_natural_segments(e)
        attach.assert_not_called();self.assertIsNone(e.get_result())

    async def test_other_sender_during_selection_does_not_drop_reply(self):
        p=plugin();e=FakeEvent(text='第一句话');p._record_input_event(e)
        e.result=FakeResult([Plain('我的回复')])
        async def selecting(*args):p._record_input_event(FakeEvent(sender_id='other',text='别人路过'))
        p._jj_choose_contextual_sticker=AsyncMock(side_effect=selecting)
        await p.send_natural_segments(e)
        self.assertIsNotNone(e.get_result())

    async def test_consumed_image_cannot_answer_again(self):
        p=plugin(); e=FakeEvent(text='',messages=[Image('/synthetic/a.png')]);seq=p._record_input_event(e)
        p._jj_consumed_image_sequences[e.unified_msg_origin].append(seq)
        await p._jj_attach_supplement_images(e,types.SimpleNamespace(image_urls=[]))
        e.result=FakeResult([Plain('重复解释图片')])
        p._jj_choose_contextual_sticker=AsyncMock()
        await p.send_natural_segments(e)
        self.assertIsNone(e.get_result());p._jj_choose_contextual_sticker.assert_not_awaited()

    async def test_selector_receives_context_and_can_decline_bad_match(self):
        p=r3.FallbackTests().setup_plugin(); e=FakeEvent(text='聊天');p._record_input_event(e)
        e.set_extra(main.EXTRA_JJ_STICKER_STATUS,'no_marker')
        p._call_internal_model=AsyncMock(return_value='{"name":"NONE"}')
        await p._jj_choose_contextual_sticker(e,FakeResult([Plain('今天挺开心')]))
        kwargs=p._call_internal_model.await_args.kwargs
        self.assertIn('speaker_context',json.loads(kwargs['prompt']))
        self.assertIn('图中文字',kwargs['system_prompt'])
        self.assertTrue(e.get_extra('jj_fallback_checked'))
        self.assertIsNone(e.get_extra(main.EXTRA_JJ_STICKER))
