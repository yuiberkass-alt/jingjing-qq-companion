import unittest,json
from unittest.mock import AsyncMock,patch
from test_jingjing_repairs import plugin,FakeEvent,Plain,Image
from test_directed_guard import FakeResult
import test_jingjing_r3 as r3
import main
class RhythmTests(unittest.IsolatedAsyncioTestCase):
 async def test_full_sentence_waits_three_seconds(self):
  p=plugin();p.jj_input_quiet_sec=3;p.input_context_debounce_enabled=True;p.input_context_debounce_sec=.5
  e=FakeEvent(text='这是一句话已经说完但还有下一句补充')
  with patch.object(main,'_jj_wait',new=AsyncMock()) as wait:
   self.assertFalse(await p._defer_reply_if_input_continues(e))
  self.assertEqual(wait.await_args.args[1],3)
 async def test_three_lines_only_last_survives(self):
  p=plugin();p.jj_input_quiet_sec=3;p.input_context_debounce_enabled=True;p.input_context_debounce_sec=.5
  events=[FakeEvent(text=t) for t in ['我有件事想说','刚才试了一下','发现这次好多了']]
  p._record_input_event(events[0])
  for i,e in enumerate(events):
   async def add(*args):
    if i<2:p._record_input_event(events[i+1])
   with patch.object(main,'_jj_wait',side_effect=add):
    self.assertEqual(await p._defer_reply_if_input_continues(e),i<2)
 async def test_other_sender_does_not_supersede_directed_burst(self):
  p=plugin();p.jj_input_quiet_sec=3;p.input_context_debounce_enabled=True;p.input_context_debounce_sec=.5
  e=FakeEvent(text='我想问你一件事');p._record_input_event(e)
  async def add(*args):p._record_input_event(FakeEvent(sender_id='other',text='我也路过'))
  with patch.object(main,'_jj_wait',side_effect=add):
   self.assertFalse(await p._defer_reply_if_input_continues(e,require_short=False,same_sender_only=False))
 async def test_inflight_old_text_is_not_sent(self):
  p=plugin();e=FakeEvent(text='第一句话');p._record_input_event(e)
  p._record_input_event(FakeEvent(text='还有补充第二句'));e.result=FakeResult([Plain('只回答第一句')])
  await p.send_natural_segments(e)
  self.assertIsNone(e.get_result());self.assertEqual(e.sent_messages,[])
 async def test_picture_does_not_cancel_text_result(self):
  p=plugin();e=FakeEvent(text='看看');p._record_input_event(e)
  p._record_input_event(FakeEvent(text='',messages=[Image('/synthetic/a.png')]))
  e.result=FakeResult([Plain('看到了')]);await p.send_natural_segments(e)
  self.assertIsNotNone(e.get_result())
 async def test_sticker_gate_reads_context_not_a_dice_roll(self):
  # r11: the fixed random draw was replaced by a reading of the conversation.
  # A flat line gets nothing even when the old dice would have said yes; an
  # emotional line gets a picture even when the old dice would have said no.
  for text,reply,expected in [('今天几号','周四',False),
                              ('好累😭','撑完这节课就瘫一会儿',True)]:
   p=r3.FallbackTests().setup_plugin();p.jj_sticker_cooldown_sec=3
   e=FakeEvent(text=text);e.set_extra(main.EXTRA_JJ_STICKER_STATUS,'no_marker');e.result=FakeResult([Plain(reply)])
   async def choose(event,**kwargs):return json.dumps({'name':json.loads(kwargs['prompt'])['candidates'][0]['name']})
   p._call_internal_model=AsyncMock(side_effect=choose)
   with patch.object(main.random,'random',return_value=0.5):await p._jj_choose_contextual_sticker(e,e.result)
   self.assertEqual(bool(e.get_extra(main.EXTRA_JJ_STICKER)),expected)
   self.assertEqual(p._call_internal_model.await_count,int(expected))
 async def test_quiet_check_not_repeated_after_prejudge_wait(self):
  p=plugin();p.jj_input_quiet_sec=3;e=FakeEvent(text='完整的话')
  e.set_extra(main.EXTRA_INPUT_QUIET_CHECKED,True)
  with patch.object(main,'_jj_wait',new=AsyncMock()) as wait:
   self.assertFalse(await p._defer_reply_if_input_continues(e));wait.assert_not_awaited()
