import asyncio,unittest
from unittest.mock import patch
from test_jingjing_repairs import plugin,FakeEvent,FakeContext,Plain,Image,response,prepare
from test_directed_guard import build_plugin
import main
class ContextTests(unittest.TestCase):
 def test_short_local_summon_does_not_hide_framework_history(self):
  p=plugin();e=FakeEvent(text='鲸鲸');p._record_input_event(e)
  p.context=FakeContext(group_records={e.unified_msg_origin:['Alice: 我饿了','Alice: 喂我吃饭吧'],'another-group':['SECRET_OTHER_GROUP']})
  text=p._recent_group_context(e)
  self.assertIn('我饿了',text);self.assertIn('喂我吃饭吧',text);self.assertIn('鲸鲸',text)
  self.assertNotIn('SECRET_OTHER_GROUP',text)
 def test_current_speaker_focus_excludes_other_future_and_expired(self):
  p=plugin();first=FakeEvent(text='我饿了');p._record_input_event(first)
  p._record_input_event(FakeEvent(sender_id='other',text='别人的需求'))
  e=FakeEvent(text='鲸鲸');p._record_input_event(e)
  p._record_input_event(FakeEvent(text='未来消息'))
  text=p._jj_current_speaker_context(e)
  self.assertIn('我饿了',text);self.assertNotIn('别人的需求',text);self.assertNotIn('未来消息',text)
  with patch.object(main,'monotonic',return_value=main.monotonic()+p.input_context_window_sec+1):
   self.assertEqual(p._jj_current_speaker_context(e),'')
 def test_summon_reminder_includes_request_and_no_repeat_rule(self):
  p=plugin();p.input_context_wait_sec=0
  for text in ['我饿了','喂我吃饭吧']:p._record_input_event(FakeEvent(text=text))
  e=FakeEvent(text='鲸鲸');p._record_input_event(e)
  note=asyncio.run(p._input_context_reminder(e,enabled=True))
  self.assertIn('喂我吃饭吧',note);self.assertIn('不要说对方只叫你',note);self.assertIn('已经回答',note)
 def test_history_deduplicates_exact_local_line(self):
  p=plugin();e=FakeEvent(text='鲸鲸');p._record_input_event(e)
  line=p._recent_input_context(e,8)
  p.context=FakeContext(group_records={e.unified_msg_origin:[line,line]})
  self.assertEqual(p._recent_group_context(e).count(line),1)
 def test_context_gate_is_deterministic(self):
  # r11: same input, same answer; no draw, no hidden probability.
  p=plugin()
  e=FakeEvent(text='聊聊天')
  with patch.object(main.random,'random') as rnd:
   self.assertFalse(p._jj_sticker_opportunity(e))
   self.assertFalse(p._jj_sticker_opportunity(e))
   rnd.assert_not_called()
  self.assertTrue(p._jj_sticker_opportunity(FakeEvent(text='好累😭')))
  self.assertTrue(p._jj_sticker_opportunity(FakeEvent(text='聊聊天'),'笑得这么神神秘秘的呀'))
 def test_valid_model_marker_is_honored_and_emoji_kept(self):
  # r11: a sticker the model itself chose is a contextual judgment, so it is
  # no longer vetoed by the text tier; the two-turn streak still applies.
  p=plugin()
  e,_=response(p,'好呀😏[[JJ_STICKER:happy]]',FakeEvent(text='聊聊天'))
  prepare(p,e)
  self.assertTrue(any(isinstance(x,Image) for x in e.result.chain))
  self.assertIn('😏',''.join(x.text for x in e.result.chain if isinstance(x,Plain)))
 def test_explicit_sticker_request_is_not_randomly_ignored(self):
  p=plugin();p.jj_sticker_probability=0
  self.assertTrue(p._jj_sticker_opportunity(FakeEvent(text='来张开心的表情包')))
