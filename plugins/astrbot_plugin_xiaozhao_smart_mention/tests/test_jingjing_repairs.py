"""Offline regression cases: no provider, network, QQ, or production writes."""
import ast
import asyncio
import json
from pathlib import Path
import re
import types
import unittest
from unittest.mock import AsyncMock, patch

from test_directed_guard import FakeEvent, FakeResult, FakeContext, FakeProvider, build_plugin
import main
from astrbot.api.message_components import Plain, Image, At, Reply
from sticker_selector import StickerSelector


ROOT = Path(__file__).resolve().parents[3]
NATIVE_REGEX = (
    r"\A(?=[\s\S]*(?:`|https?://|(?m:^\s*(?:[-*]\s|\d+[.、]\s|#{1,6}\s))|[A-Za-z]:\\))"
    r"[\s\S]+\Z|.+?(?:\n{2,}|\Z)"
)


def plugin():
    p = build_plugin({
        "jj_semantic_enabled": True, "jj_semantic_group_ids": ["group-a", "group-b"],
        "jj_stickers_enabled": True, "smart_segment_use_model": False,
        "smart_segment_interval_sec": 0,
    })
    p._jj_sticker_path = lambda name: Path("/synthetic/" + name + ".png") if name in {"happy", "rest"} else None
    p.jj_input_quiet_sec = 0
    p.jj_sticker_probability = 1
    p.jj_sticker_cooldown_sec = 10
    # Legacy exact-text cases isolate randomness; r8 tests enable emoji.
    p.jj_semantic_emoji_enabled = False
    p.context = FakeContext(FakeProvider("must not be called"))
    return p


def response(p, text, event=None, allowed=("happy", "rest")):
    event = event or FakeEvent(text="来张表情包")
    event.set_extra("JJ_STICKER_ALLOWED_NAMES_V01", list(allowed))
    resp = types.SimpleNamespace(completion_text=text)
    asyncio.run(p.clean_llm_response_actions(event, resp))
    event.result = FakeResult([Plain(resp.completion_text)])
    return event, resp


def prepare(p, event):
    with patch.object(Image, "fromFileSystem", side_effect=lambda path: Image(path), create=True):
        asyncio.run(p.send_natural_segments(event))


class NaturalBoundaryTests(unittest.TestCase):
    def test_eight_and_ten_characters_stay_one(self):
        for text in ["今天一起出去玩吧", "今天不错，出去走走吧"]:
            self.assertLessEqual(len(text), 10)
            self.assertEqual(main._natural_local_segments(text, 3), [text])

    def test_twelve_characters_with_pause_split(self):
        text = "今天还不错，咱们出去走走"
        self.assertEqual(len(text), 12)
        self.assertEqual(main._natural_local_segments(text, 3), ["今天还不错，", "咱们出去走走"])

    def test_medium_sentence_and_emoji_are_preserved(self):
        for text in ["今天真的挺开心，咱们一起出去走走吧", "今天真的挺开心。明天也要继续加油！👩🏽‍💻"]:
            parts = main._natural_local_segments(text, 3)
            self.assertTrue(2 <= len(parts) <= 3)
            self.assertEqual("".join(parts), text)
            self.assertTrue(all(parts))

    def test_no_arbitrary_word_cut(self):
        text = "今天确实是一个适合一起出去散步的好日子"
        self.assertEqual(main._natural_local_segments(text, 3), [text])

    def test_leading_punctuation_is_never_lost(self):
        text = "！！今天真的开心。明天也要继续加油吧！"
        self.assertEqual("".join(main._natural_local_segments(text, 3)), text)

    def test_quotes_and_emoji_are_not_orphaned(self):
        for text in ['她说：“今天开心，明天也开心。”那就一起加油吧！', '今天开心。👩🏽‍💻明天也一起加油吧！', '她说“天气真好，一起走走”，那就出门吧']:
            parts = main._natural_local_segments(text, 3)
            self.assertEqual("".join(parts), text)
            self.assertFalse(any(p.startswith(("”", "，", "🏽", "\u200d")) for p in parts))

    def test_technical_content_is_unchanged(self):
        for text in ['```python\nprint("a,b")\n\nprint("c")\n```', '参考 https://example.test/a,b，然后执行命令。', '配置检查：\n1. enable=True\n2. timeout=10']:
            self.assertEqual(main._natural_local_segments(text, 3), [text])

    def test_explicit_paragraph_cap_preserves_text(self):
        text = "第一段。\n\n第二段。\n\n第三段。\n\n第四段。"
        parts = main._natural_local_segments(text, 3)
        self.assertEqual(len(parts), 3)
        self.assertEqual("".join(parts), text.replace("\n\n", ""))

    def test_short_reply_no_longer_splits_at_comma(self):
        p = plugin()
        event = FakeEvent(text="今天如何")
        event.result = FakeResult([Plain("今天还不错，咱们出去走走")])
        prepare(p, event)
        self.assertEqual(event.sent_messages, [])
        self.assertEqual(event.result.chain[0].text, "今天还不错，咱们出去走走")
        self.assertEqual(p.context.provider.calls, [])

    def test_native_enabled_prevents_plugin_direct_send(self):
        p = plugin()
        p.context.get_config = lambda origin: {"platform_settings": {"segmented_reply": {"enable": True}}}
        event, _ = response(p, "今天还不错，咱们出去走走")
        prepare(p, event)
        self.assertEqual(event.sent_messages, [])
        self.assertIsNotNone(event.result)

    def test_jingjing_never_calls_segmentation_model_even_if_config_enabled(self):
        p = plugin()
        p.smart_segment_use_model = True
        text = "没有标点但也不应额外花钱请求模型" * 12
        self.assertEqual(asyncio.run(p._build_natural_segments(FakeEvent(), text)), [text])
        self.assertEqual(p.context.provider.calls, [])


class StickerPipelineTests(unittest.TestCase):
    def test_valid_marker_attaches_once_and_preserves_text(self):
        p = plugin()
        event, _ = response(p, "今天开心。明天继续加油！\n[[JJ_STICKER:happy]]")
        prepare(p, event)
        prepare(p, event)
        self.assertEqual(sum(isinstance(c, Image) for c in event.result.chain), 1)
        self.assertEqual(event.sent_messages, [])
        self.assertEqual(p.context.provider.calls, [])
        self.assertEqual(event.get_extra(main.EXTRA_JJ_STICKER_STATUS), "attached_not_confirmed")

    def test_invalid_duplicate_and_unterminated_markers_do_not_leak(self):
        for suffix in ["[[JJ_STICKER:../secret]]", "[[JJ_STICKER:BAD]]", "[[JJ_STICKER:happy]] [[JJ_STICKER:rest]]", "[[JJ_STICKER:happy", "[[JJ_STICKER:happy]]然后继续说"]:
            p = plugin()
            event, resp = response(p, "好呀。" + suffix)
            self.assertIsNone(event.get_extra(main.EXTRA_JJ_STICKER))
            self.assertNotIn("JJ_STICKER", resp.completion_text)
            self.assertEqual(event.get_extra(main.EXTRA_JJ_STICKER_STATUS), "invalid_marker")

    def test_whitelist_required_even_without_selector(self):
        p = plugin()
        p._jj_sticker_selector = None
        event, _ = response(p, "好呀[[JJ_STICKER:happy]]", allowed=())
        prepare(p, event)
        self.assertFalse(any(isinstance(c, Image) for c in event.result.chain))
        self.assertEqual(event.get_extra(main.EXTRA_JJ_STICKER_STATUS), "not_allowed")

    def test_final_path_rechecked(self):
        p = plugin()
        event, _ = response(p, "好呀[[JJ_STICKER:happy]]")
        p._jj_sticker_path = lambda name: None
        prepare(p, event)
        self.assertEqual(event.get_extra(main.EXTRA_JJ_STICKER_STATUS), "file_unavailable_final")

    def test_cooldown_boundary_and_group_isolation(self):
        p = plugin()
        for now, group, expected in [(100, "group-a", True), (109.999, "group-a", False), (110, "group-a", True), (110, "group-b", True)]:
            event, _ = response(p, "好呀[[JJ_STICKER:happy]]", FakeEvent(group_id=group))
            with patch.object(main, "monotonic", return_value=now):
                prepare(p, event)
            self.assertEqual(any(isinstance(c, Image) for c in event.result.chain), expected)

    def test_mixed_headers_preserved(self):
        p = plugin()
        event, _ = response(p, "好呀[[JJ_STICKER:happy]]")
        headers = [At("synthetic-user"), Reply("synthetic-bot")]
        event.result.chain = headers + event.result.chain
        prepare(p, event)
        self.assertEqual(event.result.chain[:2], headers)
        self.assertIsInstance(event.result.chain[-1], Image)

    def test_existing_image_does_not_gain_second_image(self):
        p = plugin()
        event, _ = response(p, "好呀[[JJ_STICKER:happy]]")
        event.result.chain.append(Image("/synthetic/existing.png"))
        prepare(p, event)
        self.assertEqual(sum(isinstance(c, Image) for c in event.result.chain), 1)

    def test_image_construction_failure_does_not_consume_cooldown(self):
        p = plugin()
        event, _ = response(p, "发了呀[[JJ_STICKER:happy]]")
        with patch.object(Image, "fromFileSystem", side_effect=OSError("synthetic"), create=True):
            asyncio.run(p.send_natural_segments(event))
        self.assertEqual(p._jj_group_sticker_at, {})
        self.assertNotIn("发了", event.result.chain[0].text)

    def test_claim_guard_covers_observed_failures(self):
        for text in ["发了呀，你屏幕是不是卡了", "催什么，这不就来了", "行吧，再甩一张，这回看清楚点", "图片已经发给你了"]:
            guarded = main._jj_guard_image_claim(text, has_image=False, image_context=True)
            self.assertIn("这轮先回文字。", guarded)
            self.assertNotIn("发了呀", guarded)

    def test_claim_guard_preserves_unrelated_negated_and_quoted_text(self):
        for text in ["我还没有发图片。", "你发了图片吗？", '他说“我发了图片”。', "出发了，今晚早点回来。", "！！今天真开心。", '他说“好呀，发了呀，快看看”。']:
            self.assertEqual(main._jj_guard_image_claim(text, has_image=False, image_context=True), text)

    def test_followup_context_records_guarded_final_text(self):
        p = plugin()
        event, _ = response(p, "发了呀[[JJ_STICKER:happy]]")
        with patch.object(p, "_record_followup_response") as record:
            prepare(p, event)
        self.assertEqual(record.call_args.args[1], "配这张")

    def test_attached_image_does_not_claim_delivery(self):
        self.assertEqual(main._jj_guard_image_claim("发了呀", has_image=True, image_context=True), "配这张。")

    def test_stale_choice_cleared_on_new_response(self):
        p = plugin()
        event, _ = response(p, "好呀[[JJ_STICKER:happy]]")
        response(p, "这次回文字", event)
        self.assertIsNone(event.get_extra(main.EXTRA_JJ_STICKER))

    def test_logs_contain_neither_chat_nor_member_ids(self):
        p = plugin()
        event, _ = response(p, "合成私密文本[[JJ_STICKER:happy]]")
        with patch.object(main.logger, "info") as log:
            prepare(p, event)
        logged = repr(log.call_args_list)
        self.assertNotIn("合成私密文本", logged)
        self.assertNotIn("user-a", logged)
        self.assertNotIn("group-a", logged)


class SelectorAndTimingTests(unittest.TestCase):
    def selector(self):
        s = StickerSelector(Path(__file__).resolve().parents[1] / "sticker_catalog.json")
        s.assets = [{"name": n, "tags": ["开心"], "description": "", "category": ""} for n in ["a", "b", "c"]]
        return s

    def test_fresh_candidates_preferred(self):
        s = self.selector()
        s.recent["g"].extend(["a", "b"])
        self.assertEqual([x["name"] for x in s.candidates("开心", "g")], ["c"])

    def test_exhausted_category_can_recover_without_immediate_repeat(self):
        s = self.selector()
        s.recent["g"].extend(["a", "b", "c"])
        self.assertEqual([x["name"] for x in s.candidates("开心", "g")], ["a", "b"])
        self.assertEqual(len(s.candidates("开心", "another")), 3)
        self.assertEqual(s.candidates("完全无关语境", "g"), [])

    def test_single_asset_does_not_immediately_repeat(self):
        s = self.selector()
        s.assets = s.assets[:1]
        s.recent["g"].append("a")
        self.assertEqual(s.candidates("开心", "g"), [])

    def test_wait_metrics_do_not_change_requested_delay(self):
        event = FakeEvent()
        with patch.object(main.asyncio, "sleep", new_callable=AsyncMock) as sleep, patch.object(main, "monotonic", side_effect=[10, 10.5]):
            asyncio.run(main._jj_wait(event, 0.5, "input_debounce"))
        sleep.assert_awaited_once_with(0.5)
        self.assertEqual(event.get_extra(main.EXTRA_JJ_TIMING)["wait_sec"], 0.5)

    def test_completion_hook_does_not_claim_delivery(self):
        p = plugin()
        event = FakeEvent()
        event.set_extra(main.EXTRA_JJ_TIMING, {"prepared": 10, "segments_sent": 2})
        with patch.object(main.logger, "info") as log, patch.object(main, "monotonic", return_value=10.5):
            asyncio.run(p.log_jingjing_pipeline_finished(event))
        self.assertIn("delivery_confirmed=false", log.call_args.args[0])
        # r11: the hook now also reports what was actually handed to the
        # adapter, so "sent" is distinguishable from "framework sent it".
        self.assertEqual(log.call_args.args[-2], 2)
        self.assertEqual(log.call_args.args[-1], "segmented")


class ActualNativeSegmentationTests(unittest.TestCase):
    """Execute the exact segmentation block fetched from the running container.

    This checks compatibility at the native split boundary, not QQ transport.
    """
    @classmethod
    def setUpClass(cls):
        source = (ROOT / "audit/framework-reference/live/result_decorate_stage.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        node = next(n for n in ast.walk(tree) if isinstance(n, ast.If) and isinstance(n.test, ast.BoolOp) and any(isinstance(v, ast.Attribute) and v.attr == "enable_segmented_reply" for v in n.test.values))
        wrapper = ast.parse("def run(self, event, result):\n    pass\n").body[0]
        wrapper.body = [node, ast.Return(ast.Name(id="result", ctx=ast.Load()))]
        module = ast.fix_missing_locations(ast.Module(body=[wrapper], type_ignores=[]))
        namespace = {"re": re, "Plain": Plain, "logger": main.logger}
        exec(compile(module, "live-native-segmentation-block", "exec"), namespace)
        cls.run_native = staticmethod(namespace["run"])

    def config(self):
        return types.SimpleNamespace(enable_segmented_reply=True, only_llm_result=True, words_count_threshold=10000, split_mode="regex", regex=NATIVE_REGEX, content_cleanup_rule="")

    def test_native_uses_paragraphs_and_keeps_image(self):
        p = plugin()
        p.context.get_config = lambda origin: {"platform_settings": {"segmented_reply": {"enable": True}}}
        event, _ = response(p, "今天还不错，\n\n咱们出去走走[[JJ_STICKER:happy]]")
        prepare(p, event)
        result = self.run_native(self.config(), event, event.result)
        self.assertEqual([c.text for c in result.chain if isinstance(c, Plain)], ["今天还不错", "咱们出去走走"])
        self.assertEqual(sum(isinstance(c, Image) for c in result.chain), 1)
        self.assertEqual(event.sent_messages, [])

    def test_native_preserves_code_and_urls(self):
        for text in ['```python\nprint(1)\n\nprint(2)\n```', '看 https://example.test/a,b\n\n然后验证结果。', '# 操作步骤\n\n第一步。\n\n第二步。']:
            result = self.run_native(self.config(), FakeEvent(), FakeResult([Plain(text)]))
            self.assertEqual([c.text for c in result.chain], [text])

    def test_native_old_rule_does_not_respect_new_comma_pause(self):
        config = self.config()
        config.regex = r".*?[。？！~…]+|.+$"
        result = self.run_native(config, FakeEvent(), FakeResult([Plain("今天还不错，\n\n咱们出去走走")]))
        self.assertEqual(len(result.chain), 1)


class ActualNativeSendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = (ROOT / "audit/framework-reference/live/respond_stage.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        node = next(n for n in ast.walk(tree) if isinstance(n, ast.If) and isinstance(n.test, ast.Call) and isinstance(n.test.func, ast.Attribute) and n.test.func.attr == "is_seg_reply_required")
        wrapper = ast.parse("async def run(self, event, result):\n    need_separately = set()\n").body[0]
        wrapper.body += node.body
        module = ast.fix_missing_locations(ast.Module(body=[wrapper], type_ignores=[]))
        namespace = {"asyncio": asyncio, "ComponentType": types.SimpleNamespace(Reply="Reply", At="At"), "MessageChain": lambda c: c, "logger": types.SimpleNamespace(warning=lambda *a, **k: None, error=lambda *a, **k: None)}
        exec(compile(module, "live-native-send-block", "exec"), namespace)
        cls.run_native = staticmethod(namespace["run"])

    def stage(self):
        def extract(chain, types_, modify_raw_chain=True):
            headers = [c for c in chain if c.type in types_]
            chain[:] = [c for c in chain if c.type not in types_]
            return headers
        return types.SimpleNamespace(_extract_comp=extract, _calc_comp_interval=AsyncMock(return_value=0.5))

    def chain(self):
        chain = [At("synthetic"), Plain("今天还不错，"), Plain("咱们出去走走"), Image("/synthetic/happy.png")]
        for c in chain:
            c.type = type(c).__name__
        return chain

    def test_headers_once_text_image_each_once_and_short_waits(self):
        event = FakeEvent()
        result = FakeResult(self.chain())
        with patch.object(asyncio, "sleep", new_callable=AsyncMock) as sleep:
            asyncio.run(self.run_native(self.stage(), event, result))
        self.assertEqual(len(event.sent_messages), 3)
        self.assertIsInstance(event.sent_messages[0].chain[0], At)
        self.assertFalse(any(isinstance(c, At) for message in event.sent_messages[1:] for c in message.chain))
        self.assertIsInstance(event.sent_messages[-1].chain[0], Image)
        self.assertEqual([call.args for call in sleep.await_args_list], [(0.5,), (0.5,), (0.5,)])

    def test_native_failure_is_caught_without_resending_previous_segment(self):
        event = FakeEvent()
        event.fail_send_at = 2
        with patch.object(asyncio, "sleep", new_callable=AsyncMock):
            asyncio.run(self.run_native(self.stage(), event, FakeResult(self.chain())))
        self.assertEqual(len(event.sent_messages), 1)
        self.assertEqual(event.sent_messages[0].chain[-1].text, "今天还不错，")

    def test_image_reservation_is_atomic_between_coroutines(self):
        p = plugin()
        events = [response(p, "好呀[[JJ_STICKER:happy]]")[0] for _ in range(2)]
        async def run():
            await asyncio.gather(*(p.send_natural_segments(e) for e in events))
        with patch.object(Image, "fromFileSystem", side_effect=lambda path: Image(path), create=True), patch.object(main, "monotonic", return_value=100):
            asyncio.run(run())
        self.assertEqual(sum(isinstance(c, Image) for e in events for c in e.result.chain), 1)


if __name__ == "__main__":
    unittest.main()
