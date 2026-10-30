"""Current-intent stickers and actual incoming-image request propagation."""
import asyncio
import types
import unittest
from unittest.mock import AsyncMock, patch
from test_jingjing_repairs import plugin, response, prepare, FakeEvent, Image, Plain, ROOT, StickerSelector
import test_jingjing_r3 as r3
import main


class PictureInputTests(unittest.IsolatedAsyncioTestCase):
    async def test_same_sender_supplement_reaches_request_and_is_consumed(self):
        p=plugin();event=FakeEvent(text='鲸鲸，想你了')
        p._record_input_event(event)
        picture=FakeEvent(text='',messages=[Image('/synthetic/love.png')])
        seq=p._record_input_event(picture)
        req=types.SimpleNamespace(image_urls=[])
        await p._jj_attach_supplement_images(event,req)
        self.assertEqual(req.image_urls,['/synthetic/love.png'])
        self.assertIn(seq,p._jj_consumed_image_sequences[event.unified_msg_origin])

    async def test_existing_image_and_supplement_deduplicated(self):
        p=plugin();event=FakeEvent(text='看看',messages=[Image('/synthetic/a.png')])
        p._record_input_event(event)
        p._record_input_event(FakeEvent(text='',messages=[Image('/synthetic/a.png')]))
        req=types.SimpleNamespace(image_urls=['/synthetic/a.png'])
        await p._jj_attach_supplement_images(event,req)
        self.assertEqual(req.image_urls,['/synthetic/a.png'])

    async def test_other_sender_or_new_text_is_a_barrier(self):
        for follow in [FakeEvent(sender_id='other',text='',messages=[Image('/synthetic/other.png')]),FakeEvent(text='换个话题')]:
            p=plugin();event=FakeEvent(text='想你了');p._record_input_event(event)
            p._record_input_event(follow)
            p._record_input_event(FakeEvent(text='',messages=[Image('/synthetic/later.png')]))
            req=types.SimpleNamespace(image_urls=[])
            await p._jj_attach_supplement_images(event,req)
            self.assertEqual(req.image_urls,[])

    async def test_failed_conversion_not_claimed_as_seen(self):
        p=plugin();event=FakeEvent(text='想你了');p._record_input_event(event)
        bad=Image('/synthetic/missing.png');bad.convert_to_file_path=AsyncMock(side_effect=OSError())
        seq=p._record_input_event(FakeEvent(text='',messages=[bad]))
        req=types.SimpleNamespace(image_urls=[])
        await p._jj_attach_supplement_images(event,req)
        self.assertEqual(req.image_urls,[])
        self.assertNotIn(seq,p._jj_consumed_image_sequences[event.unified_msg_origin])

    async def test_late_picture_in_active_chat_can_get_own_request(self):
        p=plugin();event=FakeEvent(text='',messages=[Image('/synthetic/late.png')])
        p._jj_group_sessions[p._directed_group_key(event)]=(main.monotonic(),'刚才聊的话',0)
        p.jj_semantic_max_delay_sec=0
        p._jj_semantic_decide=AsyncMock(return_value='REPLY')
        p._get_or_create_conversation=AsyncMock(return_value=object())
        with patch.object(main,'_jj_wait',new=AsyncMock()):
            requests=[r async for r in p.smart_active_reply(event)]
        self.assertEqual(len(requests),1)
        self.assertEqual(requests[0].image_urls,['/synthetic/late.png'])
        self.assertNotIn('按上一轮请求',requests[0].prompt)

    async def test_cold_unsolicited_picture_does_not_wake_bot(self):
        p=plugin();event=FakeEvent(text='',messages=[Image('/synthetic/a.png')])
        p._jj_semantic_decide=AsyncMock(return_value='REPLY')
        with patch.object(main,'_jj_wait',new=AsyncMock()):
            requests=[r async for r in p.smart_active_reply(event)]
        self.assertEqual(requests,[])
        self.assertEqual(p._jj_semantic_decide.await_count,0)


class ProactiveStickerTests(unittest.TestCase):
    def plugin(self):return r3.FallbackTests().setup_plugin()

    def test_affection_sends_without_image_command(self):
        p=self.plugin()
        event,_=response(p,'行吧，我也勉强想你一下',FakeEvent(text='鲸鲸，想你了'),allowed=['jj0001'])
        prepare(p,event)
        self.assertTrue(any(isinstance(c,Image) for c in event.result.chain))
        self.assertEqual(event.get_extra(main.EXTRA_JJ_STICKER_STATUS),'attached_not_confirmed')
        selected=p._jj_sticker_selector.recent[p._directed_group_key(event)][-1]
        self.assertEqual(next(a['category'] for a in p._jj_sticker_selector.assets if a['name']==selected),'亲近与安慰')

    def test_laugh_sends_without_image_command(self):
        p=self.plugin();event,_=response(p,'笑得这么神神秘秘的',FakeEvent(text='嘿嘿'),allowed=['jj0001'])
        prepare(p,event)
        self.assertTrue(any(isinstance(c,Image) for c in event.result.chain))

    def test_stale_history_cannot_crowd_out_current_intent(self):
        s=self.plugin()._jj_sticker_selector
        choices=s.context_candidates('想你了','token模型api烧钱，吃饭白饭开心成功哈哈'*20,'g')
        self.assertEqual(choices[0]['category'],'亲近与安慰')

    def test_unknown_model_name_is_replaced_by_independent_safe_choice(self):
        p=self.plugin();event,resp=response(p,'开心分你一半[[JJ_STICKER:invented_happy]]',FakeEvent(text='来张开心的表情包呗'),allowed=['jj0001'])
        self.assertEqual(event.get_extra(main.EXTRA_JJ_STICKER_STATUS),'not_allowed')
        prepare(p,event)
        self.assertTrue(any(isinstance(c,Image) for c in event.result.chain))
        self.assertNotIn('invented_happy',event.get_extra('JJ_STICKER_ALLOWED_NAMES_V01'))
        self.assertNotIn('JJ_STICKER',resp.completion_text)

    def test_rejection_and_serious_scene_keep_text_only(self):
        for text in ['想你了，但不要发表情包','嘿嘿，不过朋友住院了','配置报错了，今天不开心']:
            p=self.plugin();event,_=response(p,'收到',FakeEvent(text=text),allowed=['jj0001'])
            prepare(p,event)
            self.assertFalse(any(isinstance(c,Image) for c in event.result.chain))


if __name__=='__main__':unittest.main()
