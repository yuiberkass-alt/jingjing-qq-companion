"""r11: continuation without a judge call, visible skips, context-driven stickers.

These cases encode the behaviour that was missing in r10:
* a person the bot just answered is not re-judged before the next turn,
* a cold conversation is rate-limited by a *logged* skip, never a silent drop,
* whether a picture goes out is read from the conversation, not a dice roll.
"""
import unittest
from unittest.mock import AsyncMock, patch

from test_jingjing_repairs import plugin, FakeEvent, Plain
import main


def remember_partner(p, event, *, age=1.0, rounds=0, sender=None):
    key = p._directed_group_key(event)
    who = sender if sender is not None else str(event.get_sender_id())
    stamp = main.monotonic() - age
    p._jj_group_sessions[key] = (stamp, "刚才那句", rounds, who)
    p._jj_last_partner[key] = (stamp, who)
    return key


class ContinuationTests(unittest.IsolatedAsyncioTestCase):
    async def _turn(self, p, event):
        p._get_or_create_conversation = AsyncMock(return_value=object())
        with patch.object(main, "_jj_wait", new=AsyncMock()):
            return [request async for request in p.smart_active_reply(event)]

    async def test_same_sender_continues_without_asking_the_judge(self):
        p = plugin()
        event = FakeEvent(text="那你就陪我聊会儿")
        remember_partner(p, event)
        p._jj_semantic_decide = AsyncMock(return_value="WAIT")
        requests = await self._turn(p, event)
        self.assertEqual(len(requests), 1)
        p._jj_semantic_decide.assert_not_awaited()

    async def test_other_sender_is_still_judged(self):
        p = plugin()
        event = FakeEvent(sender_id="user-b", text="你们在聊啥")
        remember_partner(p, event, sender="user-a")
        p._jj_semantic_decide = AsyncMock(return_value="WAIT")
        await self._turn(p, event)
        self.assertEqual(p._jj_semantic_decide.await_count, 1)

    async def test_stale_partner_is_not_revived(self):
        # r26: outside the continuation window and not addressed by name, the
        # bot no longer judges its way back into the conversation.
        p = plugin()
        p.mention_keywords = ["小昭"]
        event = FakeEvent(text="我回来了")
        remember_partner(p, event, age=p.jj_fast_continuation_window_sec + 5)
        p._jj_semantic_decide = AsyncMock(return_value="WAIT")
        await self._turn(p, event)
        self.assertEqual(p._jj_semantic_decide.await_count, 0)

    async def test_round_cap_never_silences_an_open_conversation(self):
        # r14: the cap used to drop the 7th consecutive reply, which looked
        # exactly like the bot walking away mid-chat.
        p = plugin()
        event = FakeEvent(text="你还要接着说吗")
        remember_partner(p, event, rounds=p.jj_semantic_max_rounds + 4)
        p._jj_semantic_decide = AsyncMock(return_value="WAIT")
        requests = await self._turn(p, event)
        self.assertEqual(len(requests), 1)
        p._jj_semantic_decide.assert_not_awaited()

    async def test_round_cap_still_limits_a_judged_reply(self):
        # A different speaker still goes through the judge, and the cap keeps
        # the bot from interjecting forever in a group it is not part of.
        p = plugin()
        event = FakeEvent(sender_id="user-b", text="你们聊什么呢")
        remember_partner(p, event, rounds=p.jj_semantic_max_rounds, sender="user-a")
        p._jj_semantic_decide = AsyncMock(return_value="REPLY")
        requests = await self._turn(p, event)
        self.assertEqual(requests, [])
        self.assertEqual(p._jj_semantic_decide.await_count, 1)

    async def test_exit_forgets_the_partner(self):
        p = plugin()
        event = FakeEvent(sender_id="user-b", text="换个话题")
        key = remember_partner(p, event, sender="user-a")
        p._jj_semantic_decide = AsyncMock(return_value="EXIT")
        await self._turn(p, event)
        self.assertNotIn(key, p._jj_last_partner)
        self.assertNotIn(key, p._jj_group_sessions)

    async def test_cold_gap_skip_is_logged_not_silent(self):
        # r26: an unaddressed line is skipped before the judge, and the skip is
        # written to the log (it used to vanish silently).
        p = plugin()
        p.mention_keywords = ["小昭"]
        event = FakeEvent(text="随便说一句")
        p._jj_semantic_decide = AsyncMock(return_value="REPLY")
        with patch.object(main.logger, "info") as log:
            requests = await self._turn(p, event)
        self.assertEqual(requests, [])
        p._jj_semantic_decide.assert_not_awaited()
        self.assertTrue(any("reason=not_addressed" in str(call.args[0]) for call in log.call_args_list))


class StickerTierTests(unittest.TestCase):
    def test_flat_chat_gets_no_picture_and_emotional_chat_does(self):
        p = plugin()
        self.assertFalse(p._jj_sticker_opportunity(FakeEvent(text="今天几号")))
        self.assertTrue(p._jj_sticker_opportunity(FakeEvent(text="好累😭")))

    def test_two_pictures_in_a_row_then_plain(self):
        p = plugin()
        key = p._directed_group_key(FakeEvent(text="好累😭"))
        p._jj_sticker_streak[key] = 2
        self.assertFalse(p._jj_sticker_opportunity(FakeEvent(text="好累😭")))

    def test_explicit_request_wins(self):
        p = plugin()
        key = p._directed_group_key(FakeEvent(text="来张表情包"))
        p._jj_sticker_streak[key] = 2
        self.assertTrue(p._jj_sticker_opportunity(FakeEvent(text="来张表情包")))


class BeatTests(unittest.TestCase):
    def test_a_26_character_line_stays_whole(self):
        text = "上课确实磨人，撑完这节课就找个地方瘫一会儿，别硬顶着"
        self.assertLess(len(text), 28)
        self.assertEqual(main._jj_chat_paragraphs(text), text)

    def test_a_long_line_gets_one_natural_break(self):
        text = "今天上课的时候老师又拖堂了，我实在撑不住想趴桌上睡一会儿"
        self.assertGreaterEqual(len(text), 28)
        parts = main._jj_chat_paragraphs(text).split("\n\n")
        self.assertEqual(len(parts), 2)
        # The split point is a chat beat, so the comma itself is dropped the
        # same way _jj_trim_chat_endings drops other end punctuation.
        self.assertEqual("".join(parts), text.replace("，", ""))


class HistoryImageTests(unittest.TestCase):
    """r11: past pictures are no longer re-uploaded on every single turn.

    Measured on the production history: 12 base64 images made the request
    2.39 MB and pushed the model from 1.9s to 5.18s. The current turn's
    pictures travel in req.image_urls, not in contexts.
    """

    @staticmethod
    def _request(contexts):
        import types
        return types.SimpleNamespace(contexts=contexts, image_urls=['/synthetic/now.png'])

    def test_base64_history_images_are_removed_and_text_kept(self):
        contexts = [
            {"role": "user", "content": [{"type": "text", "text": "看这个"},
                                          {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,AAA"}}]},
            {"role": "assistant", "content": [{"type": "text", "text": "看到了"}]},
        ]
        req = self._request(contexts)
        self.assertEqual(main._jj_strip_context_images(req), 1)
        self.assertEqual(contexts[0]["content"], [{"type": "text", "text": "看这个"}])
        self.assertEqual(contexts[1]["content"], [{"type": "text", "text": "看到了"}])
        self.assertEqual(req.image_urls, ['/synthetic/now.png'])

    def test_image_only_message_gets_a_text_placeholder(self):
        contexts = [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:,"}}]}]
        self.assertEqual(main._jj_strip_context_images(self._request(contexts)), 1)
        self.assertEqual(contexts[0]["content"], [{"type": "text", "text": "[图片]"}])

    def test_message_objects_are_supported(self):
        import types
        message = types.SimpleNamespace(content=[{"type": "image_url", "image_url": {"url": "data:,"}},
                                                 {"type": "text", "text": "嗯"}])
        req = self._request([message])
        self.assertEqual(main._jj_strip_context_images(req), 1)
        self.assertEqual(message.content, [{"type": "text", "text": "嗯"}])

    def test_no_images_means_no_change(self):
        contexts = [{"role": "user", "content": "普通文字"}]
        self.assertEqual(main._jj_strip_context_images(self._request(contexts)), 0)
        self.assertEqual(contexts[0]["content"], "普通文字")

    def test_disabled_by_config_leaves_history_alone(self):
        from test_directed_guard import build_plugin
        p = build_plugin({"jj_strip_history_images": False})
        self.assertFalse(p.jj_strip_history_images)
        self.assertTrue(build_plugin({}).jj_strip_history_images)


class ConfigTests(unittest.TestCase):
    def test_quiet_window_no_longer_overrides_the_configured_delay(self):
        # Not in _conf_schema.json nor in the live config, so the code default
        # is what runs. It used to be 3.0s and silently overrode the
        # configured 1.0-2.0s semantic delay on every single reply.
        from test_directed_guard import build_plugin
        p = build_plugin({})
        self.assertEqual(p.jj_input_quiet_sec, 1.2)
        self.assertTrue(p.jj_fast_continuation_enabled)

    def test_comfort_rule_is_in_the_reminder(self):
        p = plugin()
        reminder = p._natural_chat_style_reminder("active_reply")
        self.assertIn("先接住情绪", reminder)
        self.assertIn("不要给作息建议", reminder)
