import unittest
from unittest.mock import patch, AsyncMock
from test_jingjing_repairs import plugin, FakeEvent, Plain, Image, response, prepare
from test_directed_guard import build_plugin
import main

class TurnAndStyleTests(unittest.TestCase):
    def test_new_default_has_high_opportunity(self):
        self.assertEqual(build_plugin({}).jj_sticker_probability,.85)

    def test_two_pictures_then_text_then_picture(self):
        p=plugin();p.jj_sticker_cooldown_sec=0
        found=[]
        with patch.object(main.random,'random',return_value=0):
            for _ in range(4):
                e,_=response(p,'好呀[[JJ_STICKER:happy]]',FakeEvent(text='一起聊天'))
                prepare(p,e)
                found.append(any(isinstance(c,Image) for c in e.result.chain))
        self.assertEqual(found,[True,True,False,True])

    def test_explicit_request_can_override_streak(self):
        p=plugin();e=FakeEvent(text='来张表情包')
        p._jj_sticker_streak[p._directed_group_key(e)]=2
        self.assertTrue(p._jj_sticker_opportunity(e))

    def test_supplement_after_text_does_not_start_new_turn(self):
        p=plugin();text=FakeEvent(text='要不要抱抱');p._record_input_event(text)
        image=FakeEvent(text='',messages=[Image('/synthetic/a.png')]);p._record_input_event(image)
        self.assertTrue(p._jj_image_is_emotional_supplement(image))

    def test_supplement_scope_and_time(self):
        p=plugin();p._record_input_event(FakeEvent(sender_id='other',text='别人的话'))
        e=FakeEvent(text='',messages=[Image('/synthetic/a.png')]);p._record_input_event(e)
        self.assertFalse(p._jj_image_is_emotional_supplement(e))
        p._record_input_event(FakeEvent(text='要不要抱抱'))
        e=FakeEvent(text='',messages=[Image('/synthetic/b.png')]);p._record_input_event(e)
        with patch.object(main,'monotonic',return_value=main.monotonic()+31):
            self.assertFalse(p._jj_image_is_emotional_supplement(e))

    def test_explicit_image_question_is_not_silenced(self):
        p=plugin();p._record_input_event(FakeEvent(text='前一句'))
        e=FakeEvent(text='这张图是什么',messages=[Image('/synthetic/a.png')]);p._record_input_event(e)
        self.assertFalse(p._jj_image_is_emotional_supplement(e))

    def test_emoji_not_limited_to_small_word_list(self):
        for text in ['正瘫着啥也没干，就这么耗着','白饭配个菜就挺稳','要啊，不过抱一下就够了']:
            self.assertTrue(main._jj_optional_chat_emoji(text,'',.1).endswith('🐳'))
            self.assertEqual(main._jj_optional_chat_emoji(text,'',.8),text)
            self.assertEqual(main._jj_optional_chat_emoji(text,'不要emoji',.1),text)

class RouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_late_supplement_never_calls_judge(self):
        p=plugin();p._record_input_event(FakeEvent(text='一起吃什么'))
        e=FakeEvent(text='',messages=[Image('/synthetic/a.png')]);p._record_input_event(e)
        p._jj_semantic_decide=AsyncMock(return_value='REPLY')
        with patch.object(main,'_jj_wait',new=AsyncMock()):
            result=[item async for item in p.smart_active_reply(e)]
        self.assertEqual(result,[]);p._jj_semantic_decide.assert_not_awaited()
