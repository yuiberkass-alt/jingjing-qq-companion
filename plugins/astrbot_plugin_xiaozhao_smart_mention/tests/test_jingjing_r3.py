"""Screenshot regressions: output beats, sticker fallback, text + image bursts."""
import asyncio
import unittest
from unittest.mock import AsyncMock, patch
from time import monotonic
from test_jingjing_repairs import plugin, response, prepare, FakeEvent, Plain, Image, StickerSelector, ROOT
import main


class BeatsTests(unittest.TestCase):
    def test_question_then_answer_splits(self):
        text = '心情好就送我白饭？那我可就不客气了，碗已经端好了'
        self.assertEqual(main._jj_chat_paragraphs(text).split('\n\n'), ['心情好就送我白饭？', '那我可就不客气了，碗已经端好了'])

    def test_punchline_after_complete_clause_splits(self):
        self.assertEqual(main._jj_chat_paragraphs('谢谢谢谢，够不够，再不够我可要磕头了😏').split('\n\n'), ['谢谢谢谢，够不够，', '再不够我可要磕头了😏'])

    def test_short_sentence_stays_whole(self):
        text = '谢啦，这下又能多啃几口了😏'
        self.assertEqual(main._jj_chat_paragraphs(text), text)

    def test_quote_emoji_and_technical_protection(self):
        for text in ['她说“心情好就送我白饭？那我就不客气了！”', '好耶👩🏽‍💻，还是挺好玩的', '```python\nprint("真的可以？但是不能拆")\n```']:
            self.assertEqual(main._jj_chat_paragraphs(text), text)

    def test_three_full_beats_and_final_punctuation(self):
        p = plugin()
        p.context.get_config = lambda _: {'platform_settings': {'segmented_reply': {'enable': True}}}
        event, _ = response(p, '今天确实很开心。明天咱们继续加油！后天也别忘了休息')
        prepare(p, event)
        self.assertEqual(event.result.chain[0].text.split('\n\n'), ['今天确实很开心', '明天咱们继续加油', '后天也别忘了休息'])


class InputBurstTests(unittest.IsolatedAsyncioTestCase):
    def setup_plugin(self):
        p = plugin()
        p.jj_rhythm_v032_enabled = True
        p.jj_semantic_min_delay_sec = 1
        p.jj_semantic_max_delay_sec = 2
        p._jj_group_sessions[p._directed_group_key(FakeEvent())] = (monotonic(), '谢啦，这下又能多啃几口了', 0)
        p._jj_semantic_decide = AsyncMock(return_value='REPLY')
        p._build_active_reply_request = AsyncMock(return_value=object())
        return p

    async def collect(self, p, event):
        return [item async for item in p.smart_active_reply(event)]

    async def test_text_then_same_sender_image_preserves_reply_in_gather_wait(self):
        for text in ['', '[图片]']:
            p = self.setup_plugin()
            first = FakeEvent(text='还不快多感谢感谢我')
            image = FakeEvent(text=text, messages=[Image('/synthetic/hamster.png')])
            async def wait(event, seconds, phase):
                if phase == 'semantic_delay':
                    p._record_input_event(image)
            with patch.object(main, '_jj_wait', side_effect=wait):
                result = await self.collect(p, first)
                from types import SimpleNamespace
                await p._jj_attach_supplement_images(first, SimpleNamespace(image_urls=[]))
                image_result = await self.collect(p, image)
            self.assertEqual(len(result), 1)
            self.assertEqual(image_result, [])
            self.assertEqual(p._build_active_reply_request.await_count, 1)
            self.assertTrue(first.get_extra('jj_image_supplement_seen'))

    async def test_image_during_judge_preserves_original_request(self):
        p = self.setup_plugin()
        first = FakeEvent(text='还不快多感谢感谢我')
        async def judge(*args, **kwargs):
            p._record_input_event(FakeEvent(text='', messages=[Image('/synthetic/a.png')]))
            return 'REPLY'
        p._jj_semantic_decide.side_effect = judge
        with patch.object(main, '_jj_wait', new=AsyncMock()):
            self.assertEqual(len(await self.collect(p, first)), 1)

    async def test_new_text_still_supersedes_old_and_latest_waits_gap(self):
        p = self.setup_plugin()
        first, latest = FakeEvent(text='先感谢我'), FakeEvent(text='再夸两句吧')
        async def judge(event, text, **kwargs):
            if event is first:
                p._record_input_event(latest)
            return 'REPLY'
        p._jj_semantic_decide.side_effect = judge
        with patch.object(main, '_jj_wait', new=AsyncMock()) as wait:
            self.assertEqual(await self.collect(p, first), [])
            self.assertEqual(len(await self.collect(p, latest)), 1)
        self.assertIn('judge_gap', [call.args[2] for call in wait.await_args_list])
        self.assertEqual(p._build_active_reply_request.await_count, 1)

    async def test_active_session_not_swallowed_by_legacy_ten_second_cooldown(self):
        p = self.setup_plugin()
        event = FakeEvent(text='还不快多感谢感谢我')
        p._last_active_reply_at[event.unified_msg_origin] = monotonic()
        with patch.object(main, '_jj_wait', new=AsyncMock()):
            self.assertEqual(len(await self.collect(p, event)), 1)

    async def test_unrelated_sender_image_still_supersedes(self):
        p = self.setup_plugin()
        event = FakeEvent(text='还不快多感谢感谢我')
        async def wait(*args):
            p._record_input_event(FakeEvent(sender_id='other', text='', messages=[Image('/synthetic/a.png')]))
        with patch.object(main, '_jj_wait', side_effect=wait):
            self.assertEqual(await self.collect(p, event), [])
        self.assertEqual(p._jj_semantic_decide.await_count, 0)

    async def test_debounce_image_is_supplement_but_text_is_superseding(self):
        for is_image in [True, False]:
            p = self.setup_plugin()
            event = FakeEvent(text='谢谢你')
            p._record_input_event(event)
            follow = FakeEvent(text='' if is_image else '其实还有一件事', messages=[Image('/synthetic/a.png')] if is_image else [])
            async def wait(*args):p._record_input_event(follow)
            with patch.object(main, '_jj_wait', side_effect=wait):
                deferred = await p._defer_reply_if_input_continues(event, require_short=False)
            self.assertEqual(deferred, not is_image)

    async def test_cold_chat_and_round_cap_still_block(self):
        for cold in [True, False]:
            p = self.setup_plugin()
            event = FakeEvent(text='还不快多感谢感谢我')
            key = p._directed_group_key(event)
            if cold:
                p._jj_group_sessions.clear()
                p._jj_group_judge_at[key] = monotonic()
            else:
                p._jj_group_sessions[key] = (monotonic(), '之前的回复', 6)
            with patch.object(main, '_jj_wait', new=AsyncMock()):
                self.assertEqual(await self.collect(p, event), [])
            self.assertEqual(p._build_active_reply_request.await_count, 0)

    async def test_judge_wait_and_exit_still_respected(self):
        for decision in ['WAIT', 'EXIT']:
            p = self.setup_plugin()
            event = FakeEvent(text='换个话题')
            p._jj_semantic_decide.return_value = decision
            with patch.object(main, '_jj_wait', new=AsyncMock()):
                self.assertEqual(await self.collect(p, event), [])
            self.assertEqual(p._build_active_reply_request.await_count, 0)
            if decision == 'EXIT':
                self.assertNotIn(p._directed_group_key(event), p._jj_group_sessions)


class FallbackTests(unittest.TestCase):
    def setup_plugin(self):
        p = plugin()
        p._jj_sticker_selector = StickerSelector(ROOT/'workspace/astrbot_plugin_xiaozhao_smart_mention/sticker_catalog.json')
        names = [a['name'] for a in p._jj_sticker_selector.assets]
        p._jj_sticker_path = lambda n: ROOT/(n+'.png') if n in names else None
        # These cases isolate the legacy fallback; r5 covers semantic selection.
        p._call_internal_model = AsyncMock(return_value=None)
        return p

    def run_reply(self, p, incoming, outgoing, now):
        options=p._jj_sticker_selector.candidates(incoming+'\n'+outgoing, 'g', limit=8)
        names=[a['name'] for a in options]
        event,_=response(p,outgoing,FakeEvent(text=incoming),allowed=names)
        with patch.object(main,'monotonic',return_value=now):prepare(p,event)
        return event

    def test_contextual_fallback_proactive_then_repeated_intent_spacing(self):
        p=self.setup_plugin()
        counts=[]
        for i in range(5):
            e=self.run_reply(p,'给你充好token了','谢啦，这下又能多啃几口了😏',100+i*20)
            counts.append(sum(isinstance(c,Image) for c in e.result.chain))
        self.assertEqual(counts,[1,0,1,0,1])
        self.assertEqual(p.context.provider.calls,[])

    def test_explicit_request_does_not_wait_for_cadence(self):
        p=self.setup_plugin()
        e=self.run_reply(p,'发张开心的表情包','好耶',100)
        self.assertEqual(sum(isinstance(c,Image) for c in e.result.chain),1)

    def test_serious_negative_technical_and_unrelated_no_fallback(self):
        for text in ['别发开心表情包','只回文字，今天开心','今天去世的朋友以前很开心','token配置报错了','普通天气情况']:
            p=self.setup_plugin()
            p._jj_sticker_eligible_turns[p._directed_group_key(FakeEvent())]=1
            e=self.run_reply(p,text,'收到',100)
            self.assertFalse(any(isinstance(c,Image) for c in e.result.chain))

    def test_cooldown_and_repeated_preparation_no_double_attachment(self):
        p=self.setup_plugin()
        first=self.run_reply(p,'发张开心的表情包','好耶',100)
        second=self.run_reply(p,'发张开心的表情包','好耶',105)
        with patch.object(main,'monotonic',return_value=120):prepare(p,first)
        self.assertEqual(sum(isinstance(c,Image) for c in first.result.chain),1)
        self.assertFalse(any(isinstance(c,Image) for c in second.result.chain))

    def test_missing_allowlist_and_invalid_marker_never_bypassed(self):
        p=self.setup_plugin()
        for output,allowed in [('好耶',[]),('好耶[[JJ_STICKER:../bad]]',['jj0001'])]:
            e,_=response(p,output,FakeEvent(text='发张开心表情包'),allowed=allowed)
            prepare(p,e)
            self.assertFalse(any(isinstance(c,Image) for c in e.result.chain))


if __name__=='__main__':unittest.main()
