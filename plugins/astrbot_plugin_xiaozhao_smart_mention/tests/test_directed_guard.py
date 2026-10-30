from __future__ import annotations

import asyncio
import sys
import time
import types
import unittest
from time import monotonic


def _install_astrbot_test_stubs() -> None:
    astrbot = types.ModuleType("astrbot")

    class _Logger:
        def debug(self, *args, **kwargs) -> None:
            pass

        def info(self, *args, **kwargs) -> None:
            pass

        def warning(self, *args, **kwargs) -> None:
            pass

    astrbot.logger = _Logger()
    sys.modules["astrbot"] = astrbot

    api_event = types.ModuleType("astrbot.api.event")

    class AstrMessageEvent:
        pass

    class _Filter:
        class _EventMessageFlag:
            def __init__(self, name: str) -> None:
                self.name = name

            def __or__(self, other):
                return _Filter._EventMessageFlag(f"{self.name}|{getattr(other, 'name', other)}")

        class EventMessageType:
            GROUP_MESSAGE = None
            PRIVATE_MESSAGE = None
            ALL = None

        EventMessageType.GROUP_MESSAGE = _EventMessageFlag("GROUP_MESSAGE")
        EventMessageType.PRIVATE_MESSAGE = _EventMessageFlag("PRIVATE_MESSAGE")
        EventMessageType.ALL = _EventMessageFlag("ALL")

        @staticmethod
        def event_message_type(*args, **kwargs):
            def decorator(func):
                return func

            return decorator

        @staticmethod
        def custom_filter(*args, **kwargs):
            def decorator(func):
                return func

            return decorator

        @staticmethod
        def on_llm_request(*args, **kwargs):
            def decorator(func):
                return func

            return decorator

        @staticmethod
        def on_llm_response(*args, **kwargs):
            def decorator(func):
                return func

            return decorator

        @staticmethod
        def on_decorating_result(*args, **kwargs):
            def decorator(func):
                return func

            return decorator

        after_message_sent = on_decorating_result

    api_event.AstrMessageEvent = AstrMessageEvent
    api_event.filter = _Filter
    sys.modules["astrbot.api.event"] = api_event

    api_message_components = types.ModuleType("astrbot.api.message_components")

    class At:
        def __init__(self, qq=None) -> None:
            self.qq = qq

    class AtAll:
        pass

    class Image:
        def __init__(self, path: str = "", error: Exception | None = None) -> None:
            self.path = path
            self.error = error

        async def convert_to_file_path(self) -> str:
            if self.error is not None:
                raise self.error
            return self.path

    class Plain:
        def __init__(self, text: str) -> None:
            self.text = text

    class Reply:
        def __init__(self, sender_id=None) -> None:
            self.sender_id = sender_id

    api_message_components.At = At
    api_message_components.AtAll = AtAll
    api_message_components.Image = Image
    api_message_components.Plain = Plain
    api_message_components.Reply = Reply
    sys.modules["astrbot.api.message_components"] = api_message_components

    provider_module = types.ModuleType("astrbot.api.provider")
    provider_entities = types.ModuleType("astrbot.core.provider.entities")

    class ProviderRequest:
        def __init__(
            self,
            *,
            prompt=None,
            session_id=None,
            image_urls=None,
            conversation=None,
            system_prompt=None,
            func_tool=None,
        ) -> None:
            self.prompt = prompt
            self.session_id = session_id
            self.image_urls = image_urls
            self.conversation = conversation
            self.system_prompt = system_prompt
            self.func_tool = func_tool

    provider_module.ProviderRequest = ProviderRequest
    provider_entities.ProviderRequest = ProviderRequest
    sys.modules["astrbot.api.provider"] = provider_module
    sys.modules["astrbot.core.provider.entities"] = provider_entities

    api_star = types.ModuleType("astrbot.api.star")

    class Context:
        pass

    class Star:
        def __init__(self, context) -> None:
            self.context = context

    api_star.Context = Context
    api_star.Star = Star
    sys.modules["astrbot.api.star"] = api_star

    core_config = types.ModuleType("astrbot.core.config")

    class AstrBotConfig(dict):
        pass

    core_config.AstrBotConfig = AstrBotConfig
    sys.modules["astrbot.core.config"] = core_config

    message_type = types.ModuleType("astrbot.core.platform.message_type")

    class MessageType:
        GROUP_MESSAGE = "GROUP_MESSAGE"
        FRIEND_MESSAGE = "FRIEND_MESSAGE"

    message_type.MessageType = MessageType
    sys.modules["astrbot.core.platform.message_type"] = message_type

    custom_filter = types.ModuleType("astrbot.core.star.filter.custom_filter")

    class CustomFilter:
        pass

    custom_filter.CustomFilter = CustomFilter
    sys.modules["astrbot.core.star.filter.custom_filter"] = custom_filter

    agent_tool = types.ModuleType("astrbot.core.agent.tool")

    class FunctionTool:
        def __init__(self, *, name, description, parameters) -> None:
            self.name = name
            self.description = description
            self.parameters = parameters

    class ToolSet:
        def __init__(self, tools) -> None:
            self._tools = list(tools)

        def remove_tool(self, name: str) -> None:
            self._tools = [tool for tool in self._tools if tool.name != name]

        def names(self) -> list[str]:
            return [tool.name for tool in self._tools]

    agent_tool.FunctionTool = FunctionTool
    agent_tool.ToolSet = ToolSet
    sys.modules["astrbot.core.agent.tool"] = agent_tool


try:
    from astrbot.core.agent.tool import FunctionTool, ToolSet
    from astrbot.core.provider.entities import ProviderRequest
except ModuleNotFoundError:
    _install_astrbot_test_stubs()
    from astrbot.core.agent.tool import FunctionTool, ToolSet
    from astrbot.core.provider.entities import ProviderRequest

from main import (
    EXTRA_DECISION,
    EXTRA_INPUT_BURST_START_SEQUENCE,
    EXTRA_INPUT_QUIET_CHECKED,
    EXTRA_INPUT_SEQUENCE,
    EXTRA_REASON,
    Main,
    _bot_reply_invites_image,
    _format_exception,
    _format_natural_chat_paragraphs,
    _is_structured_or_technical_reply,
    _natural_local_segments,
    _normalise_model_segments,
    _stop_event_silently,
    _strip_character_action_output,
    _strip_final_reply_text,
)

from astrbot.api.message_components import Image, Plain


class FakeEvent:
    def __init__(
        self,
        *,
        group_id: str = "group-a",
        sender_id: str = "user-a",
        self_id: str = "bot-a",
        text: str = "",
        message_type: str = "GROUP_MESSAGE",
        platform_name: str = "aiocqhttp",
        platform_id: str = "qq_personal_onebot",
        messages: list | None = None,
    ) -> None:
        origin_kind = "FriendMessage" if message_type == "FRIEND_MESSAGE" else "GroupMessage"
        self.unified_msg_origin = f"{platform_id}:{origin_kind}:{group_id}"
        self._group_id = group_id
        self._sender_id = sender_id
        self._self_id = self_id
        self._text = text
        self._message_type = message_type
        self._platform_name = platform_name
        self._platform_id = platform_id
        self._messages = messages or []
        self._extras = {}
        self._force_stopped = False
        self.is_at_or_wake_command = False
        self.is_wake = False
        self.session_id = group_id
        self.stop_event_called = False
        self.result = None
        self.sent_messages = []
        self.fail_send_at: int | None = None

    def get_group_id(self) -> str:
        return self._group_id

    def get_sender_id(self) -> str:
        return self._sender_id

    def get_self_id(self) -> str:
        return self._self_id

    def get_message_str(self) -> str:
        return self._text

    def get_message_type(self) -> str:
        return self._message_type

    def get_messages(self) -> list:
        return self._messages

    def set_extra(self, key: str, value) -> None:
        self._extras[key] = value

    def get_extra(self, key: str, default=None):
        return self._extras.get(key, default)

    def get_sender_name(self) -> str:
        return "sender"

    def get_platform_id(self) -> str:
        return self._platform_id

    def get_platform_name(self) -> str:
        return self._platform_name

    def request_llm(self, **kwargs) -> ProviderRequest:
        return ProviderRequest(**kwargs)

    def get_result(self):
        return self.result

    def clear_result(self) -> None:
        self.result = None

    async def send(self, message) -> None:
        if self.fail_send_at is not None and len(self.sent_messages) + 1 == self.fail_send_at:
            raise RuntimeError("send failed")
        self.sent_messages.append(message)

    def stop_event(self) -> None:
        self.stop_event_called = True
        self.result = "stop_result"


def build_plugin(config=None) -> Main:
    plugin = Main.__new__(Main)
    Main.__init__(plugin, context=None, config=config or {})
    return plugin


async def _collect_async(async_iterable):
    return [item async for item in async_iterable]


async def _return_skip(event, text):
    return "SKIP"


async def _return_reply(event, text):
    return "REPLY"


class FollowupDecisionSpy:
    def __init__(self, decision: str = "REPLY") -> None:
        self.decision = decision
        self.calls = 0

    async def __call__(self, event, text):
        self.calls += 1
        return self.decision


async def _return_conversation(event):
    return object()


class FakeProvider:
    def __init__(self, completion_text: str | list[str], *, delay: float = 0.0) -> None:
        self.completion_text = completion_text
        self.delay = delay
        self.calls = []

    async def text_chat(self, **kwargs):
        call_index = len(self.calls)
        self.calls.append(kwargs)
        if self.delay > 0:
            await asyncio.sleep(self.delay)
        if isinstance(self.completion_text, list):
            index = min(call_index, len(self.completion_text) - 1)
            text = self.completion_text[index]
        else:
            text = self.completion_text
        return types.SimpleNamespace(completion_text=text)


class FakeContext:
    def __init__(self, provider=None, group_records=None) -> None:
        self.provider = provider
        self.group_records = group_records

    def get_using_provider(self, unified_msg_origin):
        return self.provider

    def get_registered_star(self, name):
        if name != "astrbot" or self.group_records is None:
            return None
        group_chat_context = types.SimpleNamespace(raw_records=self.group_records)
        star_cls = types.SimpleNamespace(group_chat_context=group_chat_context)
        return types.SimpleNamespace(star_cls=star_cls)


class FakeResult:
    def __init__(self, chain, *, model_result: bool = True) -> None:
        self.chain = chain
        self._model_result = model_result

    def is_model_result(self) -> bool:
        return self._model_result

    def derive(self, chain):
        return FakeResult(chain, model_result=self._model_result)


class DirectedReplyGuardTest(unittest.TestCase):
    def test_same_group_is_rate_limited(self) -> None:
        plugin = build_plugin(
            {
                "directed_reply_group_cooldown_sec": 8,
                "directed_reply_sender_cooldown_sec": 60,
            },
        )
        event = FakeEvent(group_id="group-a", sender_id="user-a")

        self.assertEqual(plugin._consume_directed_reply_slot(event, now=100), (True, "allowed"))
        allowed, reason = plugin._consume_directed_reply_slot(
            FakeEvent(group_id="group-a", sender_id="user-b"),
            now=105,
        )

        self.assertFalse(allowed)
        self.assertTrue(reason.startswith("group_cooldown:"))

    def test_same_sender_is_rate_limited_after_group_cooldown(self) -> None:
        plugin = build_plugin(
            {
                "directed_reply_group_cooldown_sec": 8,
                "directed_reply_sender_cooldown_sec": 60,
            },
        )
        event = FakeEvent(group_id="group-a", sender_id="user-a")

        self.assertEqual(plugin._consume_directed_reply_slot(event, now=100), (True, "allowed"))
        allowed, reason = plugin._consume_directed_reply_slot(event, now=120)

        self.assertFalse(allowed)
        self.assertTrue(reason.startswith("sender_cooldown:"))

    def test_different_groups_are_isolated(self) -> None:
        plugin = build_plugin(
            {
                "directed_reply_group_cooldown_sec": 8,
                "directed_reply_sender_cooldown_sec": 60,
            },
        )

        self.assertEqual(
            plugin._consume_directed_reply_slot(
                FakeEvent(group_id="group-a", sender_id="user-a"),
                now=100,
            ),
            (True, "allowed"),
        )
        self.assertEqual(
            plugin._consume_directed_reply_slot(
                FakeEvent(group_id="group-b", sender_id="user-a"),
                now=101,
            ),
            (True, "allowed"),
        )

    def test_owner_ids_default_to_empty_for_repository_safety(self) -> None:
        plugin = build_plugin()

        self.assertEqual(plugin.owner_ids, set())

    def test_owner_ids_are_configurable(self) -> None:
        plugin = build_plugin({"owner_ids": ["owner-a"]})

        self.assertTrue(plugin._is_owner_message(FakeEvent(sender_id="owner-a")))
        self.assertFalse(plugin._is_owner_message(FakeEvent(sender_id="user-a")))

    def test_qq_official_owner_id_uses_openid(self) -> None:
        plugin = build_plugin({"owner_ids": ["member-openid-a"]})
        event = FakeEvent(
            platform_name="qq_official",
            platform_id="default_1903757478",
            group_id="group-openid-a",
            sender_id="member-openid-a",
            self_id="qq_official",
        )

        self.assertTrue(plugin._is_owner_message(event))
        self.assertEqual(
            plugin._directed_group_key(event),
            "default_1903757478:bot:default_1903757478:group:group-openid-a",
        )
        self.assertEqual(
            plugin._directed_sender_key(event),
            "default_1903757478:bot:default_1903757478:group:group-openid-a:sender:member-openid-a",
        )

    def test_qq_official_at_marker_is_native_directed_signal(self) -> None:
        from astrbot.api.message_components import At

        plugin = build_plugin()
        event = FakeEvent(
            platform_name="qq_official",
            platform_id="default_1903757478",
            group_id="group-openid-a",
            sender_id="member-openid-a",
            self_id="qq_official",
            messages=[At(qq="qq_official")],
        )

        self.assertTrue(plugin._has_native_directed_signal(event))

    def test_onebot_identity_still_uses_numeric_bot_id(self) -> None:
        plugin = build_plugin()
        event = FakeEvent(
            platform_name="aiocqhttp",
            platform_id="qq_personal_onebot",
            group_id="10001",
            sender_id="3040470862",
            self_id="123456789",
        )

        self.assertEqual(
            plugin._directed_group_key(event),
            "qq_personal_onebot:bot:123456789:group:10001",
        )
        self.assertEqual(
            plugin._directed_sender_key(event),
            "qq_personal_onebot:bot:123456789:group:10001:sender:3040470862",
        )

    def test_active_judge_attempt_is_rate_limited(self) -> None:
        plugin = build_plugin({"active_judge_attempt_cooldown_sec": 45})
        event = FakeEvent(group_id="group-a")

        self.assertEqual(
            plugin._consume_active_judge_attempt_slot(event, now=100),
            (True, "allowed"),
        )
        allowed, reason = plugin._consume_active_judge_attempt_slot(event, now=120)

        self.assertFalse(allowed)
        self.assertTrue(reason.startswith("active_judge_attempt_cooldown:"))

    def test_judge_failure_backoff_suppresses_follow_up_judges(self) -> None:
        plugin = build_plugin({"judge_failure_backoff_sec": 120})
        event = FakeEvent(group_id="group-a")

        plugin._record_judge_failure(event, "active", TimeoutError(), now=100)
        active, reason = plugin._is_judge_backoff_active(event, now=150)

        self.assertTrue(active)
        self.assertEqual(reason, "judge_backoff:70.0s")
        self.assertEqual(plugin._is_judge_backoff_active(event, now=221), (False, "allowed"))

    def test_explicit_keyword_question_replies_during_judge_backoff(self) -> None:
        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "judge_failure_backoff_sec": 120,
            },
        )
        event = FakeEvent(group_id="group-a", sender_id="user-a")

        plugin._record_judge_failure(event, "active", TimeoutError(), now=monotonic())
        decision, reason = asyncio.run(
            plugin._decide(event, "小昭你觉得这个方案稳不稳"),
        )

        self.assertEqual(decision, "REPLY")
        self.assertTrue(reason.startswith("reply_pattern:"))

    def test_ambiguous_keyword_mention_still_respects_judge_backoff(self) -> None:
        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "judge_failure_backoff_sec": 120,
            },
        )
        event = FakeEvent(group_id="group-a", sender_id="user-a")

        plugin._record_judge_failure(event, "active", TimeoutError(), now=monotonic())
        decision, reason = asyncio.run(
            plugin._decide(event, "刚才那句小昭接得还挺自然"),
        )

        self.assertEqual(decision, "SKIP")
        self.assertTrue(reason.startswith("judge_backoff:"))

    def test_direct_summon_replies_without_llm_judge(self) -> None:
        plugin = build_plugin({"mention_keywords": ["小昭"]})
        provider = FakeProvider("SKIP")
        plugin.context = FakeContext(provider)
        event = FakeEvent(group_id="group-a", sender_id="user-a")

        decision, reason = asyncio.run(plugin._decide(event, "小昭"))

        self.assertEqual(decision, "REPLY")
        self.assertEqual(reason, "direct_summon")
        self.assertEqual(provider.calls, [])

    def test_keyword_replies_are_rate_limited_for_non_owners(self) -> None:
        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "directed_reply_group_cooldown_sec": 8,
                "directed_reply_sender_cooldown_sec": 60,
            },
        )

        first = FakeEvent(group_id="group-a", sender_id="user-a", text="小昭你觉得这样行吗")
        asyncio.run(plugin.smart_mention(first))
        self.assertTrue(first.is_at_or_wake_command)
        self.assertTrue(first.is_wake)

        second = FakeEvent(group_id="group-a", sender_id="user-a", text="小昭你觉得这个呢")
        asyncio.run(plugin.smart_mention(second))

        self.assertFalse(second.is_at_or_wake_command)
        self.assertFalse(second.is_wake)
        self.assertEqual(second.get_extra(EXTRA_DECISION), "SKIP")
        self.assertTrue(second.get_extra(EXTRA_REASON).startswith("group_cooldown:"))

    def test_plain_chat_without_active_cue_does_not_consume_active_judge_slot(self) -> None:
        plugin = build_plugin({"mention_keywords": ["小昭"]})
        event = FakeEvent(group_id="group-a", sender_id="user-a", text="今天群里还挺热闹")

        items = list(asyncio.run(_collect_async(plugin.smart_active_reply(event))))

        self.assertEqual(items, [])
        self.assertEqual(plugin._last_active_judge_attempt_at, {})

    def test_plain_question_consumes_active_judge_slot_once(self) -> None:
        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "active_judge_attempt_cooldown_sec": 45,
            },
        )
        plugin._active_decide = _return_skip
        event = FakeEvent(group_id="group-a", sender_id="user-a", text="这个配置怎么改才好？")

        items = list(asyncio.run(_collect_async(plugin.smart_active_reply(event))))

        self.assertEqual(items, [])
        self.assertEqual(len(plugin._last_active_judge_attempt_at), 1)

    def test_technical_noun_statement_does_not_spend_active_judge_call(self) -> None:
        plugin = build_plugin(
            {
                "active_judge_attempt_cooldown_sec": 0,
                "input_context_debounce_enabled": False,
            },
        )
        plugin._get_or_create_conversation = _return_conversation
        active_spy = FollowupDecisionSpy("REPLY")
        plugin._active_decide = active_spy

        event = FakeEvent(text="这个插件最近更新了")
        items = list(asyncio.run(_collect_async(plugin.smart_active_reply(event))))

        self.assertEqual(items, [])
        self.assertEqual(active_spy.calls, 0)

    def test_explicit_technical_question_remains_active_judge_candidate(self) -> None:
        plugin = build_plugin(
            {
                "active_judge_attempt_cooldown_sec": 0,
                "input_context_debounce_enabled": False,
            },
        )
        plugin._get_or_create_conversation = _return_conversation
        active_spy = FollowupDecisionSpy("REPLY")
        plugin._active_decide = active_spy

        event = FakeEvent(text="这个插件应该怎么配置？")
        items = list(asyncio.run(_collect_async(plugin.smart_active_reply(event))))

        self.assertEqual(len(items), 1)
        self.assertEqual(active_spy.calls, 1)

    def test_default_active_cues_only_judge_question_shaped_messages(self) -> None:
        cases = {
            "我装了几个插件": 0,
            "今天没什么问题": 0,
            "不管怎么说先这样吧": 0,
            "这个配置怎么改": 1,
            "应该选什么版本": 1,
            "这个插件应该怎么配置？": 1,
        }

        for text, expected_calls in cases.items():
            with self.subTest(text=text):
                plugin = build_plugin(
                    {
                        "active_judge_attempt_cooldown_sec": 0,
                        "active_reply_cooldown_sec": 0,
                        "input_context_debounce_enabled": False,
                    },
                )
                plugin._get_or_create_conversation = _return_conversation
                active_spy = FollowupDecisionSpy("REPLY")
                plugin._active_decide = active_spy

                list(
                    asyncio.run(
                        _collect_async(plugin.smart_active_reply(FakeEvent(text=text))),
                    ),
                )

                self.assertEqual(active_spy.calls, expected_calls)

    def test_custom_active_cue_patterns_are_not_question_shape_filtered(self) -> None:
        plugin = build_plugin(
            {
                "active_reply_cue_patterns": [r"几个"],
                "active_judge_attempt_cooldown_sec": 0,
                "input_context_debounce_enabled": False,
            },
        )
        active_spy = FollowupDecisionSpy("SKIP")
        plugin._active_decide = active_spy

        list(
            asyncio.run(
                _collect_async(
                    plugin.smart_active_reply(FakeEvent(text="我装了几个插件")),
                ),
            ),
        )

        self.assertEqual(active_spy.calls, 1)

    def test_recent_same_sender_followup_replies_without_keyword(self) -> None:
        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "active_reply_cooldown_sec": 30,
                "followup_reply_window_sec": 180,
            },
        )
        plugin._get_or_create_conversation = _return_conversation

        first = FakeEvent(
            group_id="group-a",
            sender_id="user-a",
            text="那小昭你觉得我是男孩子还是女孩子呢？",
        )
        asyncio.run(plugin.smart_mention(first))

        followup = FakeEvent(
            group_id="group-a",
            sender_id="user-a",
            text="告诉我你觉得我是男孩子还是女孩子就行了没事的就是好奇问问",
        )
        items = list(asyncio.run(_collect_async(plugin.smart_active_reply(followup))))

        self.assertEqual(len(items), 1)
        self.assertEqual(followup.get_extra(EXTRA_DECISION), "REPLY")
        self.assertTrue(followup.get_extra(EXTRA_REASON).startswith("followup_window:"))

    def test_recent_followup_rule_match_does_not_call_model_judge(self) -> None:
        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "active_reply_cooldown_sec": 30,
                "followup_reply_window_sec": 180,
            },
        )
        plugin._get_or_create_conversation = _return_conversation
        followup_spy = FollowupDecisionSpy("SKIP")
        plugin._followup_decide = followup_spy

        first = FakeEvent(group_id="group-a", sender_id="user-a", text="小昭")
        asyncio.run(plugin.smart_mention(first))

        followup = FakeEvent(group_id="group-a", sender_id="user-a", text="继续讲讲这个")
        items = list(asyncio.run(_collect_async(plugin.smart_active_reply(followup))))

        self.assertEqual(len(items), 1)
        self.assertEqual(followup_spy.calls, 0)
        self.assertTrue(followup.get_extra(EXTRA_REASON).startswith("followup_window:"))

    def test_recent_followup_directed_pronoun_replies_without_model_judge(self) -> None:
        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "active_reply_cooldown_sec": 0,
                "followup_reply_window_sec": 180,
                "followup_score_threshold": 60,
            },
        )
        plugin._get_or_create_conversation = _return_conversation
        followup_spy = FollowupDecisionSpy("SKIP")
        plugin._followup_decide = followup_spy

        first = FakeEvent(group_id="665018346", sender_id="3040470862", text="小昭")
        asyncio.run(plugin.smart_mention(first))

        followup = FakeEvent(group_id="665018346", sender_id="3040470862", text="说你呢")
        items = list(asyncio.run(_collect_async(plugin.smart_active_reply(followup))))

        self.assertEqual(len(items), 1)
        self.assertEqual(followup_spy.calls, 0)
        self.assertEqual(followup.get_extra(EXTRA_DECISION), "REPLY")
        self.assertTrue(followup.get_extra(EXTRA_REASON).startswith("followup_window:"))

    def test_recent_followup_low_score_plain_statement_skips_without_model_judge(self) -> None:
        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "followup_reply_window_sec": 180,
            },
        )
        plugin._get_or_create_conversation = _return_conversation
        followup_spy = FollowupDecisionSpy("REPLY")
        plugin._followup_decide = followup_spy

        first = FakeEvent(group_id="group-a", sender_id="user-a", text="小昭")
        asyncio.run(plugin.smart_mention(first))

        followup = FakeEvent(group_id="group-a", sender_id="user-a", text="今天群里人好多")
        items = list(asyncio.run(_collect_async(plugin.smart_active_reply(followup))))

        self.assertEqual(items, [])
        self.assertEqual(followup_spy.calls, 0)
        self.assertIsNone(followup.get_extra(EXTRA_DECISION))

    def test_recent_same_sender_followup_handles_imperative_topic_request(self) -> None:
        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "active_reply_cooldown_sec": 30,
                "followup_reply_window_sec": 180,
            },
        )
        plugin._get_or_create_conversation = _return_conversation

        first = FakeEvent(group_id="665018346", sender_id="3040470862", text="小昭")
        asyncio.run(plugin.smart_mention(first))

        followup = FakeEvent(
            group_id="665018346",
            sender_id="3040470862",
            text="评价一下青梅煮酒论英雄",
        )
        items = list(asyncio.run(_collect_async(plugin.smart_active_reply(followup))))

        self.assertEqual(len(items), 1)
        self.assertEqual(followup.get_extra(EXTRA_DECISION), "REPLY")
        self.assertTrue(followup.get_extra(EXTRA_REASON).startswith("followup_window:"))

    def test_followup_reply_respects_active_reply_cooldown_after_active_reply(self) -> None:
        plugin = build_plugin(
            {
                "mention_keywords": ["灏忔槶"],
                "active_reply_cooldown_sec": 30,
                "followup_reply_window_sec": 180,
            },
        )
        plugin._get_or_create_conversation = _return_conversation
        plugin._recent_followup_reply_reason = lambda event, text, **kwargs: (
            True,
            "followup_window:1.0/180.0s",
        )
        active = FakeEvent(
            group_id="group-a",
            sender_id="user-a",
            text="杩欎釜閰嶇疆鎬庝箞鏀规墠濂斤紵",
        )
        plugin._record_followup_target(active, now=100)
        plugin._last_active_reply_at[active.unified_msg_origin] = monotonic()

        followup = FakeEvent(
            group_id="group-a",
            sender_id="user-a",
            text="鍛婅瘔鎴戠洿鎺ョ瓟妗堝氨琛?",
        )
        items = list(asyncio.run(_collect_async(plugin.smart_active_reply(followup))))

        self.assertEqual(items, [])
        self.assertIsNone(followup.get_extra(EXTRA_DECISION))

    def test_recent_followup_window_does_not_apply_to_other_senders(self) -> None:
        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "followup_reply_window_sec": 180,
            },
        )
        plugin._get_or_create_conversation = _return_conversation

        first = FakeEvent(
            group_id="group-a",
            sender_id="user-a",
            text="那小昭你觉得我是男孩子还是女孩子呢？",
        )
        asyncio.run(plugin.smart_mention(first))

        other_sender = FakeEvent(
            group_id="group-a",
            sender_id="user-b",
            text="告诉我你觉得我是男孩子还是女孩子就行了没事的就是好奇问问",
        )
        items = list(asyncio.run(_collect_async(plugin.smart_active_reply(other_sender))))

        self.assertEqual(items, [])
        self.assertIsNone(other_sender.get_extra(EXTRA_DECISION))

    def test_vague_demonstrative_does_not_spend_model_call(self) -> None:
        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "followup_reply_window_sec": 180,
            },
        )
        plugin._get_or_create_conversation = _return_conversation
        followup_spy = FollowupDecisionSpy("REPLY")
        plugin._followup_decide = followup_spy

        first = FakeEvent(
            group_id="group-a",
            sender_id="user-a",
            text="那小昭你觉得我是男孩子还是女孩子呢？",
        )
        asyncio.run(plugin.smart_mention(first))

        casual = FakeEvent(group_id="group-a", sender_id="user-a", text="那这个")
        items = list(asyncio.run(_collect_async(plugin.smart_active_reply(casual))))

        self.assertEqual(items, [])
        self.assertEqual(followup_spy.calls, 0)
        self.assertIsNone(casual.get_extra(EXTRA_DECISION))

    def test_recent_followup_window_allows_model_semantic_reply_without_cue(self) -> None:
        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "followup_reply_window_sec": 180,
            },
        )
        plugin._get_or_create_conversation = _return_conversation
        plugin._followup_decide = _return_reply

        first = FakeEvent(
            group_id="group-a",
            sender_id="user-a",
            text="小昭先帮我看看这个问题",
        )
        asyncio.run(plugin.smart_mention(first))

        semantic_followup = FakeEvent(
            group_id="group-a",
            sender_id="user-a",
            text="你还能从另一个角度看这件事",
        )
        items = list(asyncio.run(_collect_async(plugin.smart_active_reply(semantic_followup))))

        self.assertEqual(len(items), 1)
        self.assertEqual(semantic_followup.get_extra(EXTRA_DECISION), "REPLY")
        self.assertTrue(
            semantic_followup.get_extra(EXTRA_REASON).startswith("followup_model:")
        )

    def test_recent_followup_window_respects_model_skip_without_cue(self) -> None:
        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "followup_reply_window_sec": 180,
            },
        )
        plugin._get_or_create_conversation = _return_conversation
        plugin._followup_decide = _return_skip

        first = FakeEvent(
            group_id="group-a",
            sender_id="user-a",
            text="那小昭你觉得我是男孩子还是女孩子呢？",
        )
        asyncio.run(plugin.smart_mention(first))

        casual = FakeEvent(group_id="group-a", sender_id="user-a", text="那这个")
        items = list(asyncio.run(_collect_async(plugin.smart_active_reply(casual))))

        self.assertEqual(items, [])
        self.assertIsNone(casual.get_extra(EXTRA_DECISION))

    def test_recent_followup_score_blocks_short_ack_even_when_model_replies(self) -> None:
        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "followup_reply_window_sec": 180,
            },
        )
        plugin._get_or_create_conversation = _return_conversation
        plugin._followup_decide = _return_reply

        first = FakeEvent(
            group_id="group-a",
            sender_id="user-a",
            text="那小昭你觉得我是男孩子还是女孩子呢？",
        )
        asyncio.run(plugin.smart_mention(first))

        ack = FakeEvent(group_id="group-a", sender_id="user-a", text="好的")
        items = list(asyncio.run(_collect_async(plugin.smart_active_reply(ack))))

        self.assertEqual(items, [])
        self.assertIsNone(ack.get_extra(EXTRA_DECISION))

    def test_followup_end_phrases_do_not_trigger_reply(self) -> None:
        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "active_reply_cooldown_sec": 0,
                "input_context_debounce_enabled": False,
            },
        )
        plugin._get_or_create_conversation = _return_conversation
        followup_spy = FollowupDecisionSpy("REPLY")
        plugin._followup_decide = followup_spy
        first = FakeEvent(group_id="group-a", sender_id="user-a", text="小昭")
        asyncio.run(plugin.smart_mention(first))

        for text in ("没事", "算了"):
            with self.subTest(text=text):
                event = FakeEvent(group_id="group-a", sender_id="user-a", text=text)
                items = list(asyncio.run(_collect_async(plugin.smart_active_reply(event))))
                self.assertEqual(items, [])
                self.assertIsNone(event.get_extra(EXTRA_DECISION))

        self.assertEqual(followup_spy.calls, 0)

    def test_bot_question_accepts_natural_answer_without_model_judge(self) -> None:
        class Response:
            completion_text = "你用的什么系统？"

        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "active_reply_cooldown_sec": 0,
                "input_context_debounce_enabled": False,
            },
        )
        plugin._get_or_create_conversation = _return_conversation
        followup_spy = FollowupDecisionSpy("SKIP")
        plugin._followup_decide = followup_spy
        first = FakeEvent(
            group_id="group-a",
            sender_id="user-a",
            text="小昭，帮我检查环境",
        )
        asyncio.run(plugin.smart_mention(first))
        asyncio.run(plugin.clean_llm_response_actions(first, Response()))

        answer = FakeEvent(group_id="group-a", sender_id="user-a", text="Windows 11")
        items = list(asyncio.run(_collect_async(plugin.smart_active_reply(answer))))

        self.assertEqual(len(items), 1)
        self.assertEqual(followup_spy.calls, 0)
        self.assertIn("bot_invited_response", answer.get_extra(EXTRA_REASON))

    def test_requested_group_image_continues_without_model_judge(self) -> None:
        class Response:
            completion_text = "把报错截图发一下。"

        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "active_reply_cooldown_sec": 0,
                "input_context_debounce_enabled": False,
            },
        )
        plugin._get_or_create_conversation = _return_conversation
        followup_spy = FollowupDecisionSpy("SKIP")
        plugin._followup_decide = followup_spy
        first = FakeEvent(text="小昭，帮我看看报错")
        asyncio.run(plugin.smart_mention(first))
        asyncio.run(plugin.clean_llm_response_actions(first, Response()))
        image = FakeEvent(messages=[Image("C:/tmp/group-error.png")])

        items = list(asyncio.run(_collect_async(plugin.smart_active_reply(image))))

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].image_urls, ["C:/tmp/group-error.png"])
        self.assertEqual(image.get_extra(EXTRA_REASON), "followup_requested_image")
        self.assertEqual(followup_spy.calls, 0)

    def test_bot_image_request_detector_evaluates_clauses_locally(self) -> None:
        cases = {
            "请不要截个图发来。": False,
            "别拍张照片给我。": False,
            "我不会提供图片。": False,
            "暂时无法提供图片。": False,
            "图片已经发过了。": False,
            "我可以提供图片。": False,
            "我把截图发过了。": False,
            "截图发过了。": False,
            "我可以把截图发来。": False,
            "我能把截图发给你。": False,
            "我可以截个图发来。": False,
            "我会拍张照片给你。": False,
            "我也可以把截图发来。": False,
            "我这边可以截个图发来。": False,
            "我还会拍张照片给你。": False,
            "我刚把截图发给你了。": False,
            "我把截图发完了。": False,
            "我把截图发送过了。": False,
            "不用发日志，请截个图发来。": True,
            "把报错截图发一下。": True,
            "把截图发过来。": True,
            "请截个图发来。": True,
            "拍张照片给我。": True,
            "来张图。": True,
            "请发一下截图": True,
            "请上传图片": True,
            "截图麻烦发一下": True,
            "把截图发一下（注意打码）": True,
        }

        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(_bot_reply_invites_image(text), expected)

    def test_non_requests_for_images_do_not_authorize_group_image_followup(self) -> None:
        for response_text in (
            "我不能提供图片。",
            "先发日志，不要发截图。",
            "截图不用发，贴一下日志。",
            "我已经上传截图了。",
        ):
            with self.subTest(response_text=response_text):
                class Response:
                    completion_text = response_text

                plugin = build_plugin(
                    {
                        "mention_keywords": ["小昭"],
                        "active_reply_cooldown_sec": 0,
                        "input_context_debounce_enabled": False,
                    },
                )
                plugin._get_or_create_conversation = _return_conversation
                first = FakeEvent(text="小昭，帮我看看报错")
                asyncio.run(plugin.smart_mention(first))
                asyncio.run(plugin.clean_llm_response_actions(first, Response()))
                image = FakeEvent(messages=[Image("C:/tmp/group-error.png")])

                items = list(asyncio.run(_collect_async(plugin.smart_active_reply(image))))

                self.assertEqual(items, [])
                self.assertIsNone(image.get_extra(EXTRA_DECISION))

    def test_common_image_requests_authorize_group_image_without_model_judge(self) -> None:
        for response_text in (
            "请截个图发来。",
            "拍张照片给我。",
            "来张图。",
        ):
            with self.subTest(response_text=response_text):
                class Response:
                    completion_text = response_text

                plugin = build_plugin(
                    {
                        "mention_keywords": ["小昭"],
                        "active_reply_cooldown_sec": 0,
                        "input_context_debounce_enabled": False,
                    },
                )
                plugin._get_or_create_conversation = _return_conversation
                followup_spy = FollowupDecisionSpy("SKIP")
                plugin._followup_decide = followup_spy
                first = FakeEvent(text="小昭，帮我看看报错")
                asyncio.run(plugin.smart_mention(first))
                asyncio.run(plugin.clean_llm_response_actions(first, Response()))
                image = FakeEvent(messages=[Image("C:/tmp/group-error.png")])

                items = list(asyncio.run(_collect_async(plugin.smart_active_reply(image))))

                self.assertEqual(len(items), 1)
                self.assertEqual(image.get_extra(EXTRA_REASON), "followup_requested_image")
                self.assertEqual(followup_spy.calls, 0)

    def test_verb_first_image_request_authorizes_image_only_continuation(self) -> None:
        class Response:
            completion_text = "请上传图片"

        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "active_reply_cooldown_sec": 0,
                "input_context_debounce_enabled": False,
            },
        )
        plugin._get_or_create_conversation = _return_conversation
        followup_spy = FollowupDecisionSpy("SKIP")
        plugin._followup_decide = followup_spy
        first = FakeEvent(text="小昭，帮我看看报错")
        asyncio.run(plugin.smart_mention(first))
        asyncio.run(plugin.clean_llm_response_actions(first, Response()))
        image = FakeEvent(messages=[Image("C:/tmp/requested.png")])

        items = list(asyncio.run(_collect_async(plugin.smart_active_reply(image))))

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].image_urls, ["C:/tmp/requested.png"])
        self.assertEqual(image.get_extra(EXTRA_REASON), "followup_requested_image")
        self.assertEqual(followup_spy.calls, 0)

    def test_requested_group_image_is_blocked_by_interrupt_during_debounce(self) -> None:
        class Response:
            completion_text = "把报错截图发一下。"

        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "active_reply_cooldown_sec": 0,
                "input_context_debounce_sec": 0.05,
                "input_context_wait_sec": 0,
            },
        )
        plugin._get_or_create_conversation = _return_conversation
        first = FakeEvent(text="小昭，帮我看看报错")
        asyncio.run(plugin.smart_mention(first))
        asyncio.run(plugin.clean_llm_response_actions(first, Response()))
        image = FakeEvent(messages=[Image("C:/tmp/group-error.png")])
        interrupt = FakeEvent(sender_id="user-b", text="我先问另一个问题")

        async def run_case():
            image_task = asyncio.create_task(_collect_async(plugin.smart_active_reply(image)))
            await asyncio.sleep(0.005)
            await plugin.record_input_context(interrupt)
            return await image_task

        items = asyncio.run(run_case())

        self.assertEqual(items, [])
        self.assertIsNone(image.get_extra(EXTRA_DECISION))

    def test_unsolicited_group_image_does_not_trigger_active_reply(self) -> None:
        plugin = build_plugin({"input_context_debounce_enabled": False})
        active_spy = FollowupDecisionSpy("REPLY")
        plugin._active_decide = active_spy
        image = FakeEvent(messages=[Image("C:/tmp/random.png")])

        items = list(asyncio.run(_collect_async(plugin.smart_active_reply(image))))

        self.assertEqual(items, [])
        self.assertEqual(active_spy.calls, 0)
        self.assertIsNone(image.get_extra(EXTRA_DECISION))

    def test_pending_group_input_does_not_enable_unsolicited_image_reply(self) -> None:
        plugin = build_plugin({"input_context_debounce_enabled": False})
        plugin._get_or_create_conversation = _return_conversation
        plugin._mark_pending_input_reply(FakeEvent(), group_scope=True)
        image = FakeEvent(messages=[Image("C:/tmp/random.png")])

        items = list(asyncio.run(_collect_async(plugin.smart_active_reply(image))))

        self.assertEqual(items, [])
        self.assertIsNone(image.get_extra(EXTRA_DECISION))

    def test_requested_group_image_is_blocked_after_real_interrupt(self) -> None:
        class Response:
            completion_text = "把报错截图发一下。"

        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "active_reply_cooldown_sec": 0,
                "input_context_debounce_enabled": False,
            },
        )
        plugin._get_or_create_conversation = _return_conversation
        first = FakeEvent(text="小昭，帮我看看报错")
        asyncio.run(plugin.smart_mention(first))
        asyncio.run(plugin.clean_llm_response_actions(first, Response()))
        plugin._record_input_event(FakeEvent(sender_id="user-b", text="我先问另一个问题"))
        image = FakeEvent(messages=[Image("C:/tmp/group-error.png")])

        items = list(asyncio.run(_collect_async(plugin.smart_active_reply(image))))

        self.assertEqual(items, [])
        self.assertIsNone(image.get_extra(EXTRA_DECISION))

    def test_requested_group_image_conversion_failure_has_specific_reason(self) -> None:
        class Response:
            completion_text = "把报错截图发一下。"

        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "active_reply_cooldown_sec": 0,
                "input_context_debounce_enabled": False,
            },
        )
        plugin._get_or_create_conversation = _return_conversation
        first = FakeEvent(text="小昭，帮我看看报错")
        asyncio.run(plugin.smart_mention(first))
        asyncio.run(plugin.clean_llm_response_actions(first, Response()))
        image = FakeEvent(messages=[Image(error=RuntimeError("bad image"))])

        items = list(asyncio.run(_collect_async(plugin.smart_active_reply(image))))

        self.assertEqual(items, [])
        self.assertEqual(image.get_extra(EXTRA_DECISION), "SKIP")
        self.assertEqual(image.get_extra(EXTRA_REASON), "followup_image_unavailable")

    def test_other_sender_interrupt_blocks_ambiguous_answer(self) -> None:
        class Response:
            completion_text = "你用的什么系统？"

        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "active_reply_cooldown_sec": 0,
                "input_context_debounce_enabled": False,
            },
        )
        plugin._get_or_create_conversation = _return_conversation
        followup_spy = FollowupDecisionSpy("REPLY")
        plugin._followup_decide = followup_spy
        first = FakeEvent(
            group_id="group-a",
            sender_id="user-a",
            text="小昭，帮我检查环境",
        )
        asyncio.run(plugin.smart_mention(first))
        asyncio.run(plugin.clean_llm_response_actions(first, Response()))
        plugin._record_input_event(
            FakeEvent(group_id="group-a", sender_id="user-b", text="我先插一句别的"),
        )

        answer = FakeEvent(group_id="group-a", sender_id="user-a", text="Windows 11")
        items = list(asyncio.run(_collect_async(plugin.smart_active_reply(answer))))

        self.assertEqual(items, [])
        self.assertEqual(followup_spy.calls, 0)
        self.assertIsNone(answer.get_extra(EXTRA_DECISION))

    def test_generation_time_message_is_not_post_response_interrupt(self) -> None:
        class Response:
            completion_text = "你用的什么系统？"

        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "active_reply_cooldown_sec": 0,
                "input_context_debounce_enabled": False,
            },
        )
        plugin._get_or_create_conversation = _return_conversation
        followup_spy = FollowupDecisionSpy("SKIP")
        plugin._followup_decide = followup_spy

        first = FakeEvent(
            group_id="group-a",
            sender_id="user-a",
            text="小昭，帮我检查环境",
        )
        asyncio.run(plugin.smart_mention(first))
        plugin._record_input_event(
            FakeEvent(group_id="group-a", sender_id="user-b", text="我在机器人回复前说一句"),
        )
        asyncio.run(plugin.clean_llm_response_actions(first, Response()))

        answer = FakeEvent(group_id="group-a", sender_id="user-a", text="Windows 11")
        items = list(asyncio.run(_collect_async(plugin.smart_active_reply(answer))))

        self.assertEqual(len(items), 1)
        self.assertEqual(followup_spy.calls, 0)
        self.assertNotIn("other_sender_interrupt", answer.get_extra(EXTRA_REASON))

    def test_messages_addressed_to_other_member_skip_active_reply(self) -> None:
        from astrbot.api.message_components import At, Reply

        plugin = build_plugin({"mention_keywords": ["小昭"]})
        active_spy = FollowupDecisionSpy("REPLY")
        plugin._active_decide = active_spy

        cases = [
            FakeEvent(text="这个配置怎么改？", messages=[At("user-b")]),
            FakeEvent(text="这个配置怎么改？", messages=[Reply("user-b")]),
        ]
        for event in cases:
            with self.subTest(messages=event.get_messages()):
                items = list(asyncio.run(_collect_async(plugin.smart_active_reply(event))))
                self.assertEqual(items, [])
                self.assertIsNone(event.get_extra(EXTRA_DECISION))

        self.assertEqual(active_spy.calls, 0)

    def test_keyword_message_addressed_to_other_member_skips_mention_reply(self) -> None:
        from astrbot.api.message_components import At

        plugin = build_plugin({"mention_keywords": ["小昭"]})
        calls = 0

        async def decide(event, text):
            nonlocal calls
            calls += 1
            return "REPLY", "unexpected"

        plugin._decide = decide
        event = FakeEvent(
            text="小昭说的这个配置怎么改？",
            messages=[At("user-b")],
        )

        asyncio.run(plugin.smart_mention(event))

        self.assertEqual(calls, 0)
        self.assertEqual(event.get_extra(EXTRA_DECISION), "SKIP")
        self.assertEqual(event.get_extra(EXTRA_REASON), "addressed_to_other_member")

    def test_recent_followup_auto_round_limit_stops_unmentioned_chain(self) -> None:
        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "active_reply_cooldown_sec": 0,
                "followup_max_auto_rounds": 2,
                "followup_reply_window_sec": 180,
            },
        )
        plugin._get_or_create_conversation = _return_conversation

        first = FakeEvent(
            group_id="group-a",
            sender_id="user-a",
            text="那小昭你觉得我是男孩子还是女孩子呢？",
        )
        asyncio.run(plugin.smart_mention(first))

        for _ in range(2):
            followup = FakeEvent(group_id="group-a", sender_id="user-a", text="继续")
            items = list(asyncio.run(_collect_async(plugin.smart_active_reply(followup))))
            self.assertEqual(len(items), 1)

        limited = FakeEvent(group_id="group-a", sender_id="user-a", text="继续")
        items = list(asyncio.run(_collect_async(plugin.smart_active_reply(limited))))

        self.assertEqual(items, [])
        self.assertIsNone(limited.get_extra(EXTRA_DECISION))

    def test_recent_followup_window_expires(self) -> None:
        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "followup_reply_window_sec": 180,
            },
        )
        event = FakeEvent(group_id="group-a", sender_id="user-a")

        plugin._record_followup_target(event, now=100)
        allowed, reason = plugin._recent_followup_reply_reason(
            event,
            "告诉我你觉得我是男孩子还是女孩子就行了没事的就是好奇问问",
            now=281,
        )

        self.assertFalse(allowed)
        self.assertEqual(reason, "followup_expired:181.0/180.0s")

    def test_followup_cue_without_recent_target_is_not_enough(self) -> None:
        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "followup_reply_window_sec": 180,
            },
        )
        event = FakeEvent(group_id="group-a", sender_id="user-a")

        allowed, reason = plugin._recent_followup_reply_reason(
            event,
            "告诉我你觉得我是男孩子还是女孩子就行了没事的就是好奇问问",
            now=100,
        )

        self.assertFalse(allowed)
        self.assertEqual(reason, "no_followup_target")

    def test_smart_reply_removes_direct_send_tool_from_llm_request(self) -> None:
        plugin = build_plugin({"mention_keywords": ["小昭"]})
        event = FakeEvent(group_id="group-a", sender_id="user-a", text="小昭，测试")
        event.set_extra(EXTRA_DECISION, "REPLY")
        request = ProviderRequest(
            func_tool=ToolSet(
                [
                    FunctionTool(
                        name="send_message_to_user",
                        description="direct send",
                        parameters={"type": "object", "properties": {}},
                    ),
                    FunctionTool(
                        name="keep_this_tool",
                        description="other tool",
                        parameters={"type": "object", "properties": {}},
                    ),
                ],
            ),
        )

        asyncio.run(plugin.decorate_llm_request(event, request))

        self.assertIsNotNone(request.func_tool)
        self.assertEqual(request.func_tool.names(), ["keep_this_tool"])

    def test_smart_reply_adds_natural_group_chat_style_to_llm_request(self) -> None:
        plugin = build_plugin({"mention_keywords": ["小昭"]})
        event = FakeEvent(group_id="group-a", sender_id="user-a", text="小昭，测试")
        event.set_extra(EXTRA_DECISION, "REPLY")
        request = ProviderRequest(system_prompt="base prompt")

        asyncio.run(plugin.decorate_llm_request(event, request))

        self.assertIn("括号动作描写", request.system_prompt)
        self.assertIn("舞台旁白", request.system_prompt)
        self.assertIn("最多 3", request.system_prompt)
        self.assertIn("自行判断", request.system_prompt)
        self.assertIn("聊天段落", request.system_prompt)
        self.assertIn("列表、步骤、总结、配置说明", request.system_prompt)
        self.assertIn("不要每句都抢答", request.system_prompt)
        self.assertIn("简短接话", request.system_prompt)

    def test_private_context_and_style_do_not_use_group_wording(self) -> None:
        plugin = build_plugin(
            {
                "input_context_wait_sec": 0,
                "private_input_debounce_sec": 0,
                "natural_chat_style_enabled": True,
            },
        )
        plugin._get_or_create_conversation = _return_conversation
        event = FakeEvent(
            group_id="private-a",
            sender_id="user-a",
            text="继续说刚才那个问题",
            message_type="FRIEND_MESSAGE",
        )
        asyncio.run(plugin.record_input_context(event))
        items = asyncio.run(_collect_async(plugin.smart_private_reply(event)))
        request = items[0]
        request.system_prompt = "base prompt"

        asyncio.run(plugin.decorate_llm_request(event, request))

        self.assertEqual(len(items), 1)
        self.assertIn("最近私聊输入", request.system_prompt)
        self.assertIn("一对一私聊", request.system_prompt)
        self.assertNotIn("最近群聊上下文", request.system_prompt)
        self.assertNotIn("按实时群聊", request.system_prompt)
        self.assertNotIn("群聊提到", request.system_prompt)
        self.assertNotIn("不要每句都抢答", request.system_prompt)

    def test_private_context_reminder_is_scoped_to_current_sender_burst(self) -> None:
        plugin = build_plugin(
            {
                "input_context_wait_sec": 0,
                "private_input_debounce_sec": 0,
            },
        )
        old = FakeEvent(
            group_id="private-a",
            sender_id="user-a",
            text="completed earlier burst",
            message_type="FRIEND_MESSAGE",
        )
        current_image = FakeEvent(
            group_id="private-a",
            sender_id="user-a",
            text="current image caption",
            message_type="FRIEND_MESSAGE",
            messages=[Image("C:/tmp/current-burst.png")],
        )
        other_sender = FakeEvent(
            group_id="private-a",
            sender_id="user-b",
            text="other sender same origin",
            message_type="FRIEND_MESSAGE",
        )
        current = FakeEvent(
            group_id="private-a",
            sender_id="user-a",
            text="current burst question",
            message_type="FRIEND_MESSAGE",
        )
        request = ProviderRequest(system_prompt="base prompt")

        async def run_case() -> None:
            for event in (old, current_image, other_sender, current):
                await plugin.record_input_context(event)
            current.set_extra(
                EXTRA_INPUT_BURST_START_SEQUENCE,
                current_image.get_extra(EXTRA_INPUT_SEQUENCE),
            )
            await plugin.decorate_llm_request(current, request)

        asyncio.run(run_case())

        self.assertNotIn("completed earlier burst", request.system_prompt)
        self.assertNotIn("other sender same origin", request.system_prompt)
        self.assertIn("current image caption [图片 x1]", request.system_prompt)
        self.assertIn("current burst question", request.system_prompt)

    def test_private_context_without_burst_start_only_includes_current_event(self) -> None:
        plugin = build_plugin({"input_context_wait_sec": 0})
        previous = FakeEvent(
            group_id="private-a",
            sender_id="user-a",
            text="previous private message",
            message_type="FRIEND_MESSAGE",
        )
        current = FakeEvent(
            group_id="private-a",
            sender_id="user-a",
            text="current private message",
            message_type="FRIEND_MESSAGE",
        )
        request = ProviderRequest(system_prompt="base prompt")

        async def run_case() -> None:
            await plugin.record_input_context(previous)
            await plugin.record_input_context(current)
            await plugin.decorate_llm_request(current, request)

        asyncio.run(run_case())

        self.assertNotIn("previous private message", request.system_prompt)
        self.assertIn("current private message", request.system_prompt)

    def test_smart_reply_includes_recent_group_context_for_segmented_input(self) -> None:
        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "input_context_wait_sec": 0,
            },
        )
        event = FakeEvent(group_id="group-a", sender_id="user-a", text="小昭")
        event.set_extra(EXTRA_DECISION, "REPLY")
        plugin.context = FakeContext(
            group_records={
                event.unified_msg_origin: [
                    "Alice: 小昭",
                    "Bob: 还有预算限制",
                    "Alice: 帮我们选一个插件方案",
                ],
            },
        )
        request = ProviderRequest(system_prompt="base prompt")

        asyncio.run(plugin.decorate_llm_request(event, request))

        self.assertIn("最近群聊上下文", request.system_prompt)
        self.assertIn("Bob: 还有预算限制", request.system_prompt)
        self.assertIn("Alice: 帮我们选一个插件方案", request.system_prompt)
        self.assertIn("不要只按最后一条短消息回答", request.system_prompt)

    def test_input_context_cache_catches_messages_arriving_during_wait(self) -> None:
        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "input_context_wait_sec": 0.02,
                "input_context_debounce_enabled": False,
            },
        )
        first = FakeEvent(group_id="group-a", sender_id="user-a", text="小昭")
        second = FakeEvent(group_id="group-a", sender_id="user-b", text="再加一个限制：不要太贵")
        request = ProviderRequest(system_prompt="base prompt")
        first.set_extra(EXTRA_DECISION, "REPLY")
        async def run_case() -> None:
            await plugin.record_input_context(first)
            decorate_task = asyncio.create_task(plugin.decorate_llm_request(first, request))
            await asyncio.sleep(0.005)
            await plugin.record_input_context(second)
            await decorate_task

        asyncio.run(run_case())

        self.assertIn("sender: 小昭", request.system_prompt)
        self.assertIn("sender: 再加一个限制：不要太贵", request.system_prompt)

    def test_short_summon_defers_when_same_sender_continues(self) -> None:
        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "input_context_debounce_sec": 0.02,
                "input_context_wait_sec": 0.02,
                "active_reply_cooldown_sec": 0,
            },
        )
        plugin._get_or_create_conversation = _return_conversation
        first = FakeEvent(group_id="group-a", sender_id="user-a", text="小昭")
        second = FakeEvent(group_id="group-a", sender_id="user-a", text="帮我看下这个附魔")

        async def run_case() -> None:
            await plugin.record_input_context(first)
            first_task = asyncio.create_task(plugin.smart_mention(first))
            await asyncio.sleep(0.005)
            await plugin.record_input_context(second)
            await first_task

        asyncio.run(run_case())

        self.assertEqual(first.get_extra(EXTRA_DECISION), "SKIP")
        self.assertEqual(first.get_extra(EXTRA_REASON), "input_context_waiting_for_more")
        self.assertTrue(first._force_stopped)
        self.assertFalse(first.is_at_or_wake_command)

    def test_full_keyword_question_defers_when_sender_continues(self) -> None:
        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "input_context_debounce_sec": 0.02,
                "input_context_wait_sec": 0.02,
                "active_reply_cooldown_sec": 0,
            },
        )
        plugin._get_or_create_conversation = _return_conversation
        first = FakeEvent(group_id="group-a", sender_id="user-a", text="小昭你是来搞笑的吗")
        second = FakeEvent(group_id="group-a", sender_id="user-a", text="不行了")

        async def run_case() -> None:
            await plugin.record_input_context(first)
            first_task = asyncio.create_task(plugin.smart_mention(first))
            await asyncio.sleep(0.005)
            await plugin.record_input_context(second)
            await first_task

        asyncio.run(run_case())

        self.assertEqual(first.get_extra(EXTRA_DECISION), "SKIP")
        self.assertEqual(first.get_extra(EXTRA_REASON), "input_context_waiting_for_more")
        self.assertTrue(first._force_stopped)
        self.assertFalse(first.is_at_or_wake_command)

    def test_pending_segmented_input_replies_on_latest_message(self) -> None:
        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "input_context_debounce_sec": 0.02,
                "input_context_wait_sec": 0.02,
                "active_reply_cooldown_sec": 0,
            },
        )
        plugin._get_or_create_conversation = _return_conversation
        first = FakeEvent(group_id="group-a", sender_id="user-a", text="小昭")
        second = FakeEvent(group_id="group-a", sender_id="user-a", text="帮我看下这个附魔")

        async def run_case():
            await plugin.record_input_context(first)
            first_task = asyncio.create_task(plugin.smart_mention(first))
            await asyncio.sleep(0.005)
            await plugin.record_input_context(second)
            await first_task
            return [item async for item in plugin.smart_active_reply(second)]

        items = asyncio.run(run_case())

        self.assertEqual(len(items), 1)
        self.assertEqual(second.get_extra(EXTRA_DECISION), "REPLY")
        self.assertEqual(second.get_extra(EXTRA_REASON), "input_context_debounce")
        self.assertEqual(items[0].prompt, "帮我看下这个附魔")

    def test_pending_group_input_replies_while_first_message_is_still_waiting(self) -> None:
        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "input_context_debounce_sec": 0.05,
                "input_context_wait_sec": 0.05,
                "active_reply_cooldown_sec": 0,
            },
        )
        plugin._get_or_create_conversation = _return_conversation
        first = FakeEvent(group_id="group-a", sender_id="user-a", text="小昭")
        second = FakeEvent(group_id="group-a", sender_id="user-a", text="帮我看下这个附魔")

        async def run_case():
            await plugin.record_input_context(first)
            first_task = asyncio.create_task(plugin.smart_mention(first))
            await asyncio.sleep(0.005)
            await plugin.record_input_context(second)
            items = await _collect_async(plugin.smart_active_reply(second))
            await first_task
            return items

        items = asyncio.run(run_case())

        self.assertEqual(len(items), 1)
        self.assertEqual(second.get_extra(EXTRA_DECISION), "REPLY")
        self.assertEqual(second.get_extra(EXTRA_REASON), "input_context_debounce")
        self.assertEqual(items[0].prompt, "帮我看下这个附魔")
        self.assertEqual(first.get_extra(EXTRA_DECISION), "SKIP")

    def test_pending_group_input_can_continue_from_another_sender(self) -> None:
        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "input_context_debounce_sec": 0.02,
                "input_context_wait_sec": 0.02,
                "active_reply_cooldown_sec": 0,
            },
        )
        plugin._get_or_create_conversation = _return_conversation
        first = FakeEvent(group_id="group-a", sender_id="user-a", text="小昭")
        second = FakeEvent(group_id="group-a", sender_id="user-b", text="还要考虑预算")

        async def run_case():
            await plugin.record_input_context(first)
            first_task = asyncio.create_task(plugin.smart_mention(first))
            await asyncio.sleep(0.005)
            await plugin.record_input_context(second)
            await first_task
            return [item async for item in plugin.smart_active_reply(second)]

        items = asyncio.run(run_case())

        self.assertEqual(len(items), 1)
        self.assertEqual(second.get_extra(EXTRA_DECISION), "REPLY")
        self.assertEqual(second.get_extra(EXTRA_REASON), "input_context_debounce")
        self.assertEqual(items[0].prompt, "还要考虑预算")

    def test_pending_segmented_input_context_includes_prior_messages(self) -> None:
        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "input_context_debounce_sec": 0.02,
                "input_context_wait_sec": 0.02,
            },
        )
        first = FakeEvent(group_id="group-a", sender_id="user-a", text="小昭")
        second = FakeEvent(group_id="group-a", sender_id="user-a", text="帮我看下这个附魔")
        request = ProviderRequest(system_prompt="base prompt")

        async def run_case() -> None:
            await plugin.record_input_context(first)
            first_task = asyncio.create_task(plugin.smart_mention(first))
            await asyncio.sleep(0.005)
            await plugin.record_input_context(second)
            await first_task
            second.set_extra(EXTRA_DECISION, "REPLY")
            second.set_extra(EXTRA_REASON, "input_context_debounce")
            second.set_extra(EXTRA_INPUT_QUIET_CHECKED, True)
            await plugin.decorate_llm_request(second, request)

        asyncio.run(run_case())

        self.assertIn("sender: 小昭", request.system_prompt)
        self.assertIn("sender: 帮我看下这个附魔", request.system_prompt)

    def test_native_directed_group_defers_before_default_reply(self) -> None:
        from astrbot.api.message_components import At

        plugin = build_plugin(
            {
                "input_context_debounce_sec": 0.02,
                "input_context_wait_sec": 0.02,
            },
        )
        first = FakeEvent(
            group_id="group-a",
            sender_id="user-a",
            text="bot please wait for the next part",
            messages=[At(qq="bot-a")],
        )
        second = FakeEvent(
            group_id="group-a",
            sender_id="user-a",
            text="this is the actual second part",
        )

        async def run_case() -> None:
            await plugin.record_input_context(first)
            first_task = asyncio.create_task(plugin.directed_reply_guard(first))
            await asyncio.sleep(0.005)
            await plugin.record_input_context(second)
            await first_task

        asyncio.run(run_case())

        self.assertEqual(first.get_extra(EXTRA_DECISION), "SKIP")
        self.assertEqual(first.get_extra(EXTRA_REASON), "input_context_waiting_for_more")
        self.assertTrue(first._force_stopped)
        self.assertEqual(plugin._last_directed_group_at, {})

    def test_native_directed_group_defers_when_other_sender_continues(self) -> None:
        from astrbot.api.message_components import At

        plugin = build_plugin(
            {
                "input_context_debounce_sec": 0.02,
                "input_context_wait_sec": 0.02,
            },
        )
        first = FakeEvent(
            group_id="group-a",
            sender_id="user-a",
            text="bot please wait for the next part",
            messages=[At(qq="bot-a")],
        )
        second = FakeEvent(
            group_id="group-a",
            sender_id="user-b",
            text="another user adds the actual second part",
        )

        async def run_case() -> None:
            await plugin.record_input_context(first)
            first_task = asyncio.create_task(plugin.directed_reply_guard(first))
            await asyncio.sleep(0.005)
            await plugin.record_input_context(second)
            await first_task

        asyncio.run(run_case())

        self.assertEqual(first.get_extra(EXTRA_DECISION), "SKIP")
        self.assertEqual(first.get_extra(EXTRA_REASON), "input_context_waiting_for_more")
        self.assertTrue(first._force_stopped)
        self.assertEqual(plugin._last_directed_group_at, {})

    def test_private_event_reply_defers_when_sender_continues(self) -> None:
        plugin = build_plugin(
            {
                "input_context_debounce_sec": 0.02,
                "input_context_wait_sec": 0.02,
            },
        )
        first = FakeEvent(
            group_id="private-a",
            sender_id="user-a",
            text="please wait for the next part",
            message_type="FRIEND_MESSAGE",
        )
        second = FakeEvent(
            group_id="private-a",
            sender_id="user-a",
            text="this is the actual second part",
            message_type="FRIEND_MESSAGE",
        )

        async def run_case():
            await plugin.record_input_context(first)
            first_task = asyncio.create_task(_collect_async(plugin.smart_private_reply(first)))
            await asyncio.sleep(0.005)
            await plugin.record_input_context(second)
            return await first_task

        items = asyncio.run(run_case())

        self.assertEqual(items, [])
        self.assertEqual(first.get_extra(EXTRA_DECISION), "SKIP")
        self.assertEqual(first.get_extra(EXTRA_REASON), "input_context_waiting_for_more")
        self.assertTrue(first._force_stopped)

    def test_private_event_latest_message_replies_once(self) -> None:
        plugin = build_plugin(
            {
                "input_context_debounce_sec": 0.02,
                "input_context_wait_sec": 0.02,
            },
        )
        plugin._get_or_create_conversation = _return_conversation
        first = FakeEvent(
            group_id="private-a",
            sender_id="user-a",
            text="please wait for the next part",
            message_type="FRIEND_MESSAGE",
        )
        second = FakeEvent(
            group_id="private-a",
            sender_id="user-a",
            text="this is the actual second part",
            message_type="FRIEND_MESSAGE",
        )

        async def run_case():
            await plugin.record_input_context(first)
            first_task = asyncio.create_task(_collect_async(plugin.smart_private_reply(first)))
            await asyncio.sleep(0.005)
            await plugin.record_input_context(second)
            await first_task
            return await _collect_async(plugin.smart_private_reply(second))

        items = asyncio.run(run_case())

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].prompt, "this is the actual second part")
        self.assertEqual(second.get_extra(EXTRA_DECISION), "REPLY")
        self.assertEqual(second.get_extra(EXTRA_REASON), "private_input_debounce")
        self.assertTrue(second._force_stopped)

    def test_private_event_latest_message_replies_while_first_is_still_waiting(self) -> None:
        plugin = build_plugin(
            {
                "input_context_debounce_sec": 0.02,
                "private_input_debounce_sec": 0.05,
                "input_context_wait_sec": 0.02,
            },
        )
        plugin._get_or_create_conversation = _return_conversation
        first = FakeEvent(
            group_id="private-a",
            sender_id="user-a",
            text="please wait for the next part",
            message_type="FRIEND_MESSAGE",
        )
        second = FakeEvent(
            group_id="private-a",
            sender_id="user-a",
            text="this is the actual second part",
            message_type="FRIEND_MESSAGE",
        )

        async def run_case():
            await plugin.record_input_context(first)
            first_task = asyncio.create_task(_collect_async(plugin.smart_private_reply(first)))
            await asyncio.sleep(0.005)
            await plugin.record_input_context(second)
            items = await _collect_async(plugin.smart_private_reply(second))
            await first_task
            return items

        items = asyncio.run(run_case())

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].prompt, "this is the actual second part")
        self.assertEqual(second.get_extra(EXTRA_DECISION), "REPLY")
        self.assertEqual(second.get_extra(EXTRA_REASON), "private_input_debounce")
        self.assertEqual(first.get_extra(EXTRA_DECISION), "SKIP")

    def test_private_image_only_message_replies_once(self) -> None:
        plugin = build_plugin(
            {
                "private_input_debounce_sec": 0,
                "input_context_wait_sec": 0,
            },
        )
        plugin._get_or_create_conversation = _return_conversation
        event = FakeEvent(
            group_id="private-a",
            sender_id="user-a",
            message_type="FRIEND_MESSAGE",
            messages=[Image("C:/tmp/private.png")],
        )

        items = asyncio.run(_collect_async(plugin.smart_private_reply(event)))

        self.assertEqual(len(items), 1)
        self.assertIn("图片", items[0].prompt)
        self.assertEqual(items[0].image_urls, ["C:/tmp/private.png"])

    def test_private_text_then_image_keeps_text_context(self) -> None:
        plugin = build_plugin(
            {
                "private_input_debounce_sec": 0.02,
                "input_context_wait_sec": 0,
            },
        )
        plugin._get_or_create_conversation = _return_conversation
        first = FakeEvent(
            group_id="private-a",
            sender_id="user-a",
            text="这是报错现场",
            message_type="FRIEND_MESSAGE",
        )
        second = FakeEvent(
            group_id="private-a",
            sender_id="user-a",
            message_type="FRIEND_MESSAGE",
            messages=[Image("C:/tmp/error.png")],
        )

        async def run_case():
            await plugin.record_input_context(first)
            first_task = asyncio.create_task(_collect_async(plugin.smart_private_reply(first)))
            await asyncio.sleep(0.005)
            await plugin.record_input_context(second)
            await first_task
            items = await _collect_async(plugin.smart_private_reply(second))
            await plugin.decorate_llm_request(second, items[0])
            return items

        items = asyncio.run(run_case())

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].image_urls, ["C:/tmp/error.png"])
        self.assertIn("这是报错现场", items[0].system_prompt)

    def test_private_image_then_caption_retains_image(self) -> None:
        plugin = build_plugin(
            {
                "private_input_debounce_sec": 0.02,
                "input_context_wait_sec": 0,
            },
        )
        plugin._get_or_create_conversation = _return_conversation
        first = FakeEvent(
            group_id="private-a",
            sender_id="user-a",
            message_type="FRIEND_MESSAGE",
            messages=[Image("C:/tmp/error.png")],
        )
        second = FakeEvent(
            group_id="private-a",
            sender_id="user-a",
            text="红框这里就是报错",
            message_type="FRIEND_MESSAGE",
        )

        async def run_case():
            await plugin.record_input_context(first)
            first_task = asyncio.create_task(_collect_async(plugin.smart_private_reply(first)))
            await asyncio.sleep(0.005)
            await plugin.record_input_context(second)
            await first_task
            return await _collect_async(plugin.smart_private_reply(second))

        items = asyncio.run(run_case())

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].prompt, "红框这里就是报错")
        self.assertEqual(items[0].image_urls, ["C:/tmp/error.png"])

    def test_private_image_only_conversion_failure_skips_cleanly(self) -> None:
        plugin = build_plugin({"private_input_debounce_sec": 0})
        plugin._get_or_create_conversation = _return_conversation
        event = FakeEvent(
            group_id="private-a",
            sender_id="user-a",
            message_type="FRIEND_MESSAGE",
            messages=[Image(error=RuntimeError("bad image"))],
        )

        items = asyncio.run(_collect_async(plugin.smart_private_reply(event)))

        self.assertEqual(items, [])
        self.assertEqual(event.get_extra(EXTRA_DECISION), "SKIP")
        self.assertEqual(event.get_extra(EXTRA_REASON), "private_image_unavailable")
        self.assertTrue(event._force_stopped)

    def test_private_image_only_partial_conversion_keeps_usable_image(self) -> None:
        plugin = build_plugin({"private_input_debounce_sec": 0})
        plugin._get_or_create_conversation = _return_conversation
        event = FakeEvent(
            group_id="private-a",
            sender_id="user-a",
            message_type="FRIEND_MESSAGE",
            messages=[
                Image(error=RuntimeError("bad image")),
                Image("C:/tmp/usable.png"),
                Image("C:/tmp/usable.png"),
            ],
        )

        items = asyncio.run(_collect_async(plugin.smart_private_reply(event)))

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].image_urls, ["C:/tmp/usable.png"])

    def test_private_text_survives_complete_image_conversion_failure(self) -> None:
        plugin = build_plugin({"private_input_debounce_sec": 0})
        plugin._get_or_create_conversation = _return_conversation
        event = FakeEvent(
            group_id="private-a",
            sender_id="user-a",
            text="先按文字帮我判断",
            message_type="FRIEND_MESSAGE",
            messages=[Image(error=RuntimeError("bad image"))],
        )

        items = asyncio.run(_collect_async(plugin.smart_private_reply(event)))

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].prompt, "先按文字帮我判断")
        self.assertEqual(items[0].image_urls, [])

    def test_older_private_lookup_does_not_clear_newer_image_burst(self) -> None:
        plugin = build_plugin({"private_input_debounce_sec": 0.02})
        lookup_entered = asyncio.Event()
        release_lookup = asyncio.Event()

        async def blocked_conversation(event):
            if event.get_message_str() == "older request":
                lookup_entered.set()
                await release_lookup.wait()
            return object()

        plugin._get_or_create_conversation = blocked_conversation
        older = FakeEvent(
            group_id="private-a",
            sender_id="user-a",
            text="older request",
            message_type="FRIEND_MESSAGE",
        )
        newer_image = FakeEvent(
            group_id="private-a",
            sender_id="user-a",
            message_type="FRIEND_MESSAGE",
            messages=[Image("C:/tmp/newer.png")],
        )
        newer_caption = FakeEvent(
            group_id="private-a",
            sender_id="user-a",
            text="this is the newer caption",
            message_type="FRIEND_MESSAGE",
        )

        async def run_case():
            await plugin.record_input_context(older)
            older_task = asyncio.create_task(_collect_async(plugin.smart_private_reply(older)))
            await lookup_entered.wait()
            await plugin.record_input_context(newer_image)
            newer_image_task = asyncio.create_task(
                _collect_async(plugin.smart_private_reply(newer_image)),
            )
            await asyncio.sleep(0.005)
            release_lookup.set()
            await older_task
            await plugin.record_input_context(newer_caption)
            caption_items = await _collect_async(plugin.smart_private_reply(newer_caption))
            await newer_image_task
            return caption_items

        items = asyncio.run(run_case())

        self.assertEqual(len(items), 1)
        self.assertEqual(
            newer_caption.get_extra(EXTRA_INPUT_BURST_START_SEQUENCE),
            newer_image.get_extra(EXTRA_INPUT_SEQUENCE),
        )
        self.assertEqual(items[0].image_urls, ["C:/tmp/newer.png"])

    def test_expired_pending_private_burst_starts_at_new_sequence(self) -> None:
        plugin = build_plugin()
        first = FakeEvent(
            group_id="private-a",
            sender_id="user-a",
            text="first burst",
            message_type="FRIEND_MESSAGE",
            messages=[Image("C:/tmp/expired-burst.png")],
        )
        second = FakeEvent(
            group_id="private-a",
            sender_id="user-a",
            text="new burst",
            message_type="FRIEND_MESSAGE",
            messages=[Image("C:/tmp/new-burst.png")],
        )

        plugin._record_input_event(first)
        self.assertEqual(plugin._mark_pending_input_reply(first), 1)
        key = plugin._input_debounce_key(first)
        plugin._pending_input_reply_until[key] = monotonic() - 0.01
        plugin._record_input_event(second)

        start_sequence = plugin._mark_pending_input_reply(second)
        image_urls = asyncio.run(
            plugin._collect_image_urls(second, start_sequence=start_sequence),
        )

        self.assertEqual(start_sequence, second.get_extra(EXTRA_INPUT_SEQUENCE))
        self.assertEqual(image_urls, ["C:/tmp/new-burst.png"])

    def test_private_image_collection_isolates_senders_and_origins(self) -> None:
        plugin = build_plugin()
        sender_a_image = FakeEvent(
            group_id="private-a",
            sender_id="user-a",
            message_type="FRIEND_MESSAGE",
            messages=[Image("C:/tmp/sender-a.png")],
        )
        sender_b_image = FakeEvent(
            group_id="private-a",
            sender_id="user-b",
            message_type="FRIEND_MESSAGE",
            messages=[Image("C:/tmp/sender-b.png")],
        )
        sender_a_caption = FakeEvent(
            group_id="private-a",
            sender_id="user-a",
            text="caption",
            message_type="FRIEND_MESSAGE",
        )
        other_origin_image = FakeEvent(
            group_id="private-b",
            sender_id="user-a",
            message_type="FRIEND_MESSAGE",
            messages=[Image("C:/tmp/other-origin.png")],
        )
        other_origin_caption = FakeEvent(
            group_id="private-b",
            sender_id="user-a",
            text="other caption",
            message_type="FRIEND_MESSAGE",
        )

        async def run_case():
            for event in (
                sender_a_image,
                sender_b_image,
                sender_a_caption,
                other_origin_image,
                other_origin_caption,
            ):
                await plugin.record_input_context(event)
            return (
                await plugin._collect_image_urls(sender_a_caption, start_sequence=1),
                await plugin._collect_image_urls(other_origin_caption, start_sequence=1),
            )

        sender_urls, other_origin_urls = asyncio.run(run_case())

        self.assertEqual(sender_urls, ["C:/tmp/sender-a.png"])
        self.assertEqual(other_origin_urls, ["C:/tmp/other-origin.png"])

    def test_private_image_burst_after_normal_clear_starts_fresh(self) -> None:
        plugin = build_plugin()
        first = FakeEvent(
            group_id="private-a",
            sender_id="user-a",
            message_type="FRIEND_MESSAGE",
            messages=[Image("C:/tmp/old-burst.png")],
        )
        second = FakeEvent(
            group_id="private-a",
            sender_id="user-a",
            message_type="FRIEND_MESSAGE",
            messages=[Image("C:/tmp/fresh-burst.png")],
        )

        async def run_case():
            await plugin.record_input_context(first)
            plugin._mark_pending_input_reply(first)
            plugin._clear_pending_input_reply(first)
            await plugin.record_input_context(second)
            start_sequence = plugin._mark_pending_input_reply(second)
            return start_sequence, await plugin._collect_image_urls(
                second,
                start_sequence=start_sequence,
            )

        start_sequence, image_urls = asyncio.run(run_case())

        self.assertEqual(start_sequence, second.get_extra(EXTRA_INPUT_SEQUENCE))
        self.assertEqual(image_urls, ["C:/tmp/fresh-burst.png"])

    def test_private_image_collection_excludes_context_expired_record(self) -> None:
        plugin = build_plugin()
        expired = FakeEvent(
            group_id="private-a",
            sender_id="user-a",
            message_type="FRIEND_MESSAGE",
            messages=[Image("C:/tmp/expired.png")],
        )
        current = FakeEvent(
            group_id="private-a",
            sender_id="user-a",
            message_type="FRIEND_MESSAGE",
            messages=[Image("C:/tmp/current.png")],
        )

        async def run_case():
            await plugin.record_input_context(expired)
            await plugin.record_input_context(current)
            records = plugin._recent_input_images[expired.unified_msg_origin]
            _, sequence, sender_id, component = records[0]
            records[0] = (
                monotonic() - plugin.input_context_window_sec - 0.01,
                sequence,
                sender_id,
                component,
            )
            return await plugin._collect_image_urls(current, start_sequence=1)

        image_urls = asyncio.run(run_case())

        self.assertEqual(image_urls, ["C:/tmp/current.png"])

    def test_image_activity_prunes_expired_inactive_origin(self) -> None:
        plugin = build_plugin()
        inactive = FakeEvent(
            group_id="private-a",
            sender_id="user-a",
            message_type="FRIEND_MESSAGE",
            messages=[Image("C:/tmp/inactive.png")],
        )
        active = FakeEvent(
            group_id="private-b",
            sender_id="user-b",
            message_type="FRIEND_MESSAGE",
            messages=[Image("C:/tmp/active.png")],
        )

        asyncio.run(plugin.record_input_context(inactive))
        records = plugin._recent_input_images[inactive.unified_msg_origin]
        _, sequence, sender_id, component = records[0]
        records[0] = (
            monotonic() - plugin.input_context_window_sec - 0.01,
            sequence,
            sender_id,
            component,
        )

        asyncio.run(plugin.record_input_context(active))

        self.assertNotIn(inactive.unified_msg_origin, plugin._recent_input_images)
        self.assertIn(active.unified_msg_origin, plugin._recent_input_images)

    def test_input_image_records_are_bounded(self) -> None:
        plugin = build_plugin()

        async def run_case():
            for index in range(101):
                await plugin.record_input_context(
                    FakeEvent(
                        group_id="private-a",
                        sender_id="user-a",
                        message_type="FRIEND_MESSAGE",
                        messages=[Image(f"C:/tmp/{index}.png")],
                    ),
                )

        asyncio.run(run_case())

        records = plugin._recent_input_images[
            "qq_personal_onebot:FriendMessage:private-a"
        ]
        self.assertEqual(len(records), 100)

    def test_unsolicited_group_image_only_input_does_not_trigger_active_reply(self) -> None:
        plugin = build_plugin()
        event = FakeEvent(messages=[Image("C:/tmp/group.png")])

        async def run_case():
            await plugin.record_input_context(event)
            return await _collect_async(plugin.smart_active_reply(event))

        items = asyncio.run(run_case())

        self.assertEqual(items, [])
        self.assertIsNone(event.get_extra(EXTRA_DECISION))

    def test_full_question_does_not_wait_for_more_input_context(self) -> None:
        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "input_context_wait_sec": 0.2,
            },
        )
        event = FakeEvent(group_id="group-a", sender_id="user-a", text="小昭你觉得这个配置怎么改才好？")
        event.set_extra(EXTRA_DECISION, "REPLY")
        request = ProviderRequest(system_prompt="base prompt")

        started = time.perf_counter()
        asyncio.run(plugin.decorate_llm_request(event, request))
        elapsed = time.perf_counter() - started

        self.assertLess(elapsed, 0.08)

    def test_plain_private_reply_defers_when_sender_continues(self) -> None:
        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "input_context_debounce_sec": 0.02,
                "input_context_wait_sec": 0.02,
            },
        )
        first = FakeEvent(
            group_id="private-a",
            sender_id="user-a",
            text="先等等",
            message_type="FRIEND_MESSAGE",
        )
        second = FakeEvent(
            group_id="private-a",
            sender_id="user-a",
            text="我还没说完",
            message_type="FRIEND_MESSAGE",
        )
        request = ProviderRequest(system_prompt="base prompt")

        async def run_case() -> None:
            await plugin.record_input_context(first)
            private_task = asyncio.create_task(
                _collect_async(plugin.smart_private_reply(first)),
            )
            await asyncio.sleep(0.005)
            await plugin.record_input_context(second)
            items = await private_task
            self.assertEqual(items, [])

        asyncio.run(run_case())

        self.assertEqual(first.get_extra(EXTRA_DECISION), "SKIP")
        self.assertEqual(first.get_extra(EXTRA_REASON), "input_context_waiting_for_more")
        self.assertTrue(first._force_stopped)

    def test_plain_private_latest_message_keeps_recent_input_context(self) -> None:
        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "input_context_debounce_sec": 0.02,
                "input_context_wait_sec": 0.02,
            },
        )
        first = FakeEvent(
            group_id="private-a",
            sender_id="user-a",
            text="先等等",
            message_type="FRIEND_MESSAGE",
        )
        second = FakeEvent(
            group_id="private-a",
            sender_id="user-a",
            text="我还没说完",
            message_type="FRIEND_MESSAGE",
        )
        request = ProviderRequest(system_prompt="base prompt")

        async def run_case() -> None:
            await plugin.record_input_context(first)
            first_task = asyncio.create_task(
                _collect_async(plugin.smart_private_reply(first)),
            )
            await asyncio.sleep(0.005)
            await plugin.record_input_context(second)
            await first_task
            plugin._get_or_create_conversation = _return_conversation
            items = await _collect_async(plugin.smart_private_reply(second))
            self.assertEqual(len(items), 1)
            request.prompt = items[0].prompt
            second.set_extra(EXTRA_INPUT_QUIET_CHECKED, True)
            await plugin.decorate_llm_request(second, request)

        asyncio.run(run_case())

        self.assertIn("sender: 先等等", request.system_prompt)
        self.assertIn("sender: 我还没说完", request.system_prompt)

    def test_recent_group_context_injection_can_be_disabled(self) -> None:
        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "input_context_enabled": False,
            },
        )
        event = FakeEvent(group_id="group-a", sender_id="user-a", text="小昭")
        event.set_extra(EXTRA_DECISION, "REPLY")
        plugin.context = FakeContext(
            group_records={event.unified_msg_origin: ["Alice: 不应注入"]},
        )
        request = ProviderRequest(system_prompt="base prompt")

        asyncio.run(plugin.decorate_llm_request(event, request))

        self.assertNotIn("最近群聊上下文", request.system_prompt)
        self.assertNotIn("不应注入", request.system_prompt)

    def test_plain_private_llm_request_gets_natural_style_guardrails(self) -> None:
        plugin = build_plugin({"mention_keywords": ["小昭"]})
        event = FakeEvent(
            group_id="private-a",
            sender_id="user-a",
            text="测试",
            message_type="FRIEND_MESSAGE",
        )
        request = ProviderRequest(system_prompt="base prompt")

        asyncio.run(plugin.decorate_llm_request(event, request))

        self.assertIn("当前发言人昵称/ID", request.system_prompt)
        self.assertIn("括号动作描写", request.system_prompt)
        self.assertIn("最多 3", request.system_prompt)
        self.assertIn("自行判断", request.system_prompt)

    def test_plain_private_request_injects_context_when_style_is_disabled(self) -> None:
        plugin = build_plugin(
            {
                "input_context_enabled": True,
                "input_context_wait_sec": 0,
                "natural_chat_style_enabled": False,
            },
        )
        event = FakeEvent(
            group_id="private-a",
            sender_id="user-a",
            text="补充一下刚才的需求",
            message_type="FRIEND_MESSAGE",
        )
        asyncio.run(plugin.record_input_context(event))
        request = ProviderRequest(system_prompt="base prompt")

        asyncio.run(plugin.decorate_llm_request(event, request))

        self.assertIn("最近私聊输入", request.system_prompt)
        self.assertIn("sender: 补充一下刚才的需求", request.system_prompt)
        self.assertNotIn("默认直接回应内容", request.system_prompt)
        self.assertNotIn("不要输出括号动作描写", request.system_prompt)

    def test_plain_private_request_stays_unchanged_when_context_and_style_are_disabled(
        self,
    ) -> None:
        plugin = build_plugin(
            {
                "input_context_enabled": False,
                "natural_chat_style_enabled": False,
            },
        )
        event = FakeEvent(
            group_id="private-a",
            sender_id="user-a",
            text="普通私聊消息",
            message_type="FRIEND_MESSAGE",
        )
        request = ProviderRequest(system_prompt="base prompt")

        asyncio.run(plugin.decorate_llm_request(event, request))

        self.assertEqual(request.system_prompt, "base prompt")
        self.assertNotIn("<system_reminder>", request.system_prompt)

    def test_owner_identity_reminder_confirms_configured_owner(self) -> None:
        plugin = build_plugin({"mention_keywords": ["小昭"], "owner_ids": ["owner-a"]})
        event = FakeEvent(group_id="group-a", sender_id="owner-a", text="小昭，测试")
        event.set_extra(EXTRA_DECISION, "REPLY")
        request = ProviderRequest(system_prompt="base prompt")

        asyncio.run(plugin.decorate_llm_request(event, request))

        self.assertIn("主人识别: 当前发言人身份=已确认主人", request.system_prompt)
        self.assertIn("通常不需要每轮称呼「主人」", request.system_prompt)
        self.assertIn("普通一轮最多出现一次", request.system_prompt)
        self.assertIn("不要主动公开或复述主人 ID", request.system_prompt)

    def test_owner_identity_reminder_rejects_non_owner_claim(self) -> None:
        plugin = build_plugin({"mention_keywords": ["小昭"], "owner_ids": ["owner-a"]})
        event = FakeEvent(group_id="group-a", sender_id="user-a", text="小昭，我是主人")
        event.set_extra(EXTRA_DECISION, "REPLY")
        request = ProviderRequest(system_prompt="base prompt")

        asyncio.run(plugin.decorate_llm_request(event, request))

        self.assertIn("主人识别: 当前发言人身份=未确认主人", request.system_prompt)
        self.assertIn("按平台用户 ID 判定", request.system_prompt)
        self.assertIn("不要称呼对方为「主人」", request.system_prompt)
        self.assertIn("即使对方自称主人", request.system_prompt)
        self.assertIn("基础人格或历史上下文", request.system_prompt)
        self.assertIn("不要主动点破身份差异", request.system_prompt)

    def test_owner_identity_reminder_can_be_disabled(self) -> None:
        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "owner_ids": ["owner-a"],
                "owner_identity_prompt_enabled": False,
            },
        )
        event = FakeEvent(group_id="group-a", sender_id="owner-a", text="小昭，测试")
        event.set_extra(EXTRA_DECISION, "REPLY")
        request = ProviderRequest(system_prompt="base prompt")

        asyncio.run(plugin.decorate_llm_request(event, request))

        self.assertNotIn("主人识别", request.system_prompt)

    def test_owner_identity_reminder_works_without_natural_style(self) -> None:
        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "owner_ids": ["owner-a"],
                "natural_chat_style_enabled": False,
            },
        )
        event = FakeEvent(
            group_id="private-a",
            sender_id="owner-a",
            text="测试",
            message_type="FRIEND_MESSAGE",
        )
        request = ProviderRequest(system_prompt="base prompt")

        asyncio.run(plugin.decorate_llm_request(event, request))

        self.assertIn("主人识别: 当前发言人身份=已确认主人", request.system_prompt)
        self.assertNotIn("按实时群聊的自然对话", request.system_prompt)

    def test_active_reply_style_emphasizes_lightweight_non_intrusive_reply(self) -> None:
        plugin = build_plugin({"mention_keywords": ["小昭"]})
        event = FakeEvent(group_id="group-a", sender_id="user-a", text="这个配置怎么改？")
        event.set_extra(EXTRA_DECISION, "REPLY")
        event.set_extra("xiaozhao_smart_mention_mode", "active_reply")
        request = ProviderRequest()

        asyncio.run(plugin.decorate_llm_request(event, request))

        self.assertIn("群聊智能主动回复", request.system_prompt)
        self.assertIn("轻量接话", request.system_prompt)
        self.assertIn("不抢话", request.system_prompt)

    def test_natural_group_chat_style_can_be_disabled_or_limited_by_config(self) -> None:
        disabled = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "natural_chat_style_enabled": False,
            },
        )
        disabled_event = FakeEvent(group_id="group-a", sender_id="user-a", text="小昭，测试")
        disabled_event.set_extra(EXTRA_DECISION, "REPLY")
        disabled_request = ProviderRequest()

        asyncio.run(disabled.decorate_llm_request(disabled_event, disabled_request))

        self.assertNotIn("不使用括号动作描写", disabled_request.system_prompt)

        custom = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "natural_chat_max_sentences": 3,
            },
        )
        custom_event = FakeEvent(group_id="group-a", sender_id="user-a", text="小昭，测试")
        custom_event.set_extra(EXTRA_DECISION, "REPLY")
        custom_request = ProviderRequest()

        asyncio.run(custom.decorate_llm_request(custom_event, custom_request))

        self.assertIn("最多 3", custom_request.system_prompt)
        self.assertIn("自行判断", custom_request.system_prompt)
        self.assertIn("聊天段落", custom_request.system_prompt)

    def test_empty_exception_name_is_logged(self) -> None:
        self.assertEqual(_format_exception(TimeoutError()), "TimeoutError")

    def test_internal_model_uses_current_provider_for_llm_judge(self) -> None:
        provider = FakeProvider("REPLY")
        plugin = build_plugin({})
        plugin.context = FakeContext(provider)
        event = FakeEvent(group_id="group-a", sender_id="user-a")

        decision = asyncio.run(plugin._llm_decide(event, "小昭，这个要怎么处理？"))

        self.assertEqual(decision, "REPLY")
        self.assertEqual(len(provider.calls), 1)
        self.assertIn("REPLY 或 SKIP", provider.calls[0]["system_prompt"])

    def test_character_action_output_is_stripped_by_default(self) -> None:
        self.assertEqual(
            _strip_character_action_output("（耳朵抖了抖）好，我知道了喵～"),
            "好，我知道了喵～",
        )
        self.assertEqual(
            _strip_character_action_output("先这样。\n\n（尾巴轻轻晃了晃）\n继续说。"),
            "先这样。\n\n继续说。",
        )
        self.assertEqual(
            _strip_character_action_output("这个参数（默认 30 秒）可以调大一点。"),
            "这个参数（默认 30 秒）可以调大一点。",
        )
        self.assertEqual(
            _strip_character_action_output("*尾巴轻轻晃了晃* 好呀，小昭在呢。"),
            "好呀，小昭在呢。",
        )
        self.assertEqual(
            _strip_character_action_output("（安安静静，没有任何回应）"),
            "",
        )
        self.assertEqual(
            _strip_character_action_output("（小声嘀咕）反正小昭觉得他不太靠谱。"),
            "反正小昭觉得他不太靠谱。",
        )

    def test_llm_response_action_cleanup_can_be_disabled(self) -> None:
        class Response:
            completion_text = "（耳朵抖了抖）好，我知道了喵～"

        disabled = build_plugin({"action_output_enabled": True})
        enabled = build_plugin({})
        event = FakeEvent(group_id="group-a", sender_id="user-a")

        disabled_resp = Response()
        asyncio.run(disabled.clean_llm_response_actions(event, disabled_resp))
        self.assertEqual(disabled_resp.completion_text, "（耳朵抖了抖）好，我知道了喵～")

        enabled_resp = Response()
        asyncio.run(enabled.clean_llm_response_actions(event, enabled_resp))
        self.assertEqual(enabled_resp.completion_text, "好，我知道了喵～")

    def test_private_llm_response_action_cleanup_is_applied(self) -> None:
        class Response:
            completion_text = (
                "（接收到测试指令，耳朵机灵地抖了抖，尾巴尖轻轻点了三下）\n\n"
                "测试反馈来啦喵～！小昭状态正常！（端端正正坐好，冲主人眨了眨眼）"
            )

        plugin = build_plugin({})
        event = FakeEvent(
            group_id="private-a",
            sender_id="user-a",
            message_type="FRIEND_MESSAGE",
        )
        resp = Response()

        asyncio.run(plugin.clean_llm_response_actions(event, resp))

        self.assertEqual(resp.completion_text, "测试反馈来啦喵～！\n\n小昭状态正常！")

    def test_long_casual_reply_is_split_into_short_chat_paragraphs(self) -> None:
        text = (
            "呜…被主人抓到了喵。小昭说的「待命中」是日常用语的那个意思——"
            "就是随时听候主人差遣的意思啦！不是真的要「命中」什么目标，"
            "主人别逗小昭了喵～再这样下去小昭的尾巴都要打结了！❤️"
        )

        self.assertEqual(
            _format_natural_chat_paragraphs(text),
            (
                "呜…被主人抓到了喵。\n\n"
                "小昭说的「待命中」是日常用语的那个意思——就是随时听候主人差遣的意思啦！\n\n"
                "不是真的要「命中」什么目标，主人别逗小昭了喵～再这样下去小昭的尾巴都要打结了！❤️"
            ),
        )

    def test_local_segments_keep_closing_double_quote_with_inner_punctuation(self) -> None:
        text = (
            '小昭认真点头说："主人别急！"然后把事情讲清楚。'
            '她又补了一句："这次不会乱拆。"最后安静等主人确认。'
        )

        formatted = _format_natural_chat_paragraphs(text)

        self.assertNotIn('\n\n"', formatted)
        self.assertIn('"主人别急！"', formatted)
        self.assertIn('"这次不会乱拆。"', formatted)
        self.assertEqual(formatted.replace("\n\n", ""), text)

    def test_local_segments_keep_opening_double_quote_with_next_sentence(self) -> None:
        text = (
            '好呀。"下一句才从引号开始，而且内容稍微长一点方便观察。'
            "这里继续补一句，让分段足够明显。最后轻轻收住。"
        )

        segments = _natural_local_segments(text, 3)

        self.assertEqual(segments[0], "好呀。")
        self.assertTrue(segments[1].startswith('"下一句才从引号开始'))
        self.assertEqual("".join(segments), text)

    def test_local_segments_rebalance_consecutive_ascii_quotes(self) -> None:
        text = '他说："第一句。""第二句。"最后收尾。'

        segments = _natural_local_segments(text, 3)

        self.assertEqual("".join(segments), text)
        self.assertFalse(any(segment.endswith('""') for segment in segments[:-1]))

    def test_local_segments_rebalance_quote_after_existing_blank_line(self) -> None:
        text = '好呀。"\n\n下一句才开始。'

        segments = _natural_local_segments(text, 3)

        self.assertEqual("".join(segments), text.replace("\n\n", ""))
        self.assertEqual(segments, ["好呀。", '"下一句才开始。'])

    def test_existing_paragraphs_respect_global_limit(self) -> None:
        text = "第一段。\n\n第二段。\n\n第三段。\n\n第四段。"

        formatted = _format_natural_chat_paragraphs(text, 3)

        self.assertLessEqual(len(formatted.split("\n\n")), 3)
        self.assertEqual(formatted.replace("\n\n", ""), text.replace("\n\n", ""))

    def test_local_segment_fallback_respects_configured_safety_limit(self) -> None:
        text = (
            "呜……被主人抓到了喵。小昭说的待命中是日常用语的那个意思。"
            "就是随时听候主人差遣的意思啦！不是真的要命中什么目标。"
            "主人别逗小昭了喵～再这样下去小昭都要不知道怎么接话了。"
        )

        segments = _natural_local_segments(text, 2)

        self.assertLessEqual(len(segments), 2)
        self.assertEqual("".join(segments), text)

    def test_local_segment_fallback_merges_extra_existing_paragraphs(self) -> None:
        text = "收到测试信号喵～！\n\n小昭状态正常，可爱值也在线。\n\n主人还想测什么，小昭继续陪着。"

        segments = _natural_local_segments(text, 2)

        self.assertEqual(len(segments), 2)
        self.assertEqual("".join(segments), text.replace("\n\n", ""))
        self.assertEqual(segments[-1], "小昭状态正常，可爱值也在线。主人还想测什么，小昭继续陪着。")

    def test_model_segments_must_preserve_original_text(self) -> None:
        original = "收到测试信号喵～！小昭状态正常，可爱值也在线，刚刚那次调用没有掉线。主人还想测什么，小昭继续陪着。"
        raw = '{"segments":["收到测试信号喵～！","主人还想测什么，小昭继续陪着。"]}'

        self.assertIsNone(_normalise_model_segments(original, raw, 5))

    def test_model_segments_can_remove_markdown_emphasis_stars(self) -> None:
        original = "**小昭在呢。**主人别急，我慢慢听你说。"
        raw = '{"segments":["小昭在呢。","主人别急，我慢慢听你说。"]}'

        self.assertEqual(
            _normalise_model_segments(original, raw, 5),
            ["小昭在呢。", "主人别急，我慢慢听你说。"],
        )

    def test_model_segments_can_drop_chatty_markdown_heading(self) -> None:
        original = "### 小昭评价\n\n这事确实有点无聊。主人可以先休息一下。"
        raw = '{"segments":["这事确实有点无聊。","主人可以先休息一下。"]}'

        self.assertEqual(
            _normalise_model_segments(original, raw, 5),
            ["这事确实有点无聊。", "主人可以先休息一下。"],
        )

    def test_model_segments_absorb_isolated_punctuation(self) -> None:
        original = "小昭在呢。主人别急，我慢慢听你说。"
        raw = '{"segments":["小昭在呢","。","主人别急，我慢慢听你说。"]}'

        self.assertEqual(
            _normalise_model_segments(original, raw, 5),
            ["小昭在呢。", "主人别急，我慢慢听你说。"],
        )

    def test_model_segments_absorb_leading_punctuation(self) -> None:
        original = "。小昭在呢，主人别急。后面慢慢说。"
        raw = '{"segments":["。","小昭在呢，主人别急。","后面慢慢说。"]}'

        self.assertEqual(
            _normalise_model_segments(original, raw, 5),
            ["。小昭在呢，主人别急。", "后面慢慢说。"],
        )

    def test_model_segments_absorb_punctuation_with_closing_double_quote(self) -> None:
        original = '小昭说："主人别急！"然后继续解释。'
        raw = '{"segments":["小昭说：\\"主人别急","！\\"","然后继续解释。"]}'

        self.assertEqual(
            _normalise_model_segments(original, raw, 5),
            ['小昭说："主人别急！"', "然后继续解释。"],
        )

    def test_model_segments_move_opening_double_quote_to_next_segment(self) -> None:
        original = (
            '好呀。"下一句才从引号开始，而且内容稍微长一点方便观察。'
            "这里继续补一句，让分段足够明显。最后轻轻收住。"
        )
        raw = (
            '{"segments":["好呀。\\"",'
            '"下一句才从引号开始，而且内容稍微长一点方便观察。这里继续补一句，让分段足够明显。",'
            '"最后轻轻收住。"]}'
        )

        self.assertEqual(
            _normalise_model_segments(original, raw, 5),
            [
                "好呀。",
                '"下一句才从引号开始，而且内容稍微长一点方便观察。这里继续补一句，让分段足够明显。',
                "最后轻轻收住。",
            ],
        )

    def test_high_configured_limit_is_only_a_safety_cap(self) -> None:
        original = (
            "小昭就是一直陪在主人身边的聊天助手。"
            "平时可以陪主人闲聊，也可以帮忙看日志、改插件、整理配置。"
            "如果群里话题比较散，小昭会尽量接得轻一点，不把每句话都说成正式报告。"
            "主人需要的时候叫一声就好。"
        )
        raw = (
            '{"segments":['
            '"小昭就是一直陪在主人身边的聊天助手。",'
            '"平时可以陪主人闲聊，",'
            '"也可以帮忙看日志、改插件、整理配置。",'
            '"如果群里话题比较散，",'
            '"小昭会尽量接得轻一点，不把每句话都说成正式报告。",'
            '"主人需要的时候叫一声就好。"]}'
        )

        segments = _normalise_model_segments(original, raw, 6)

        self.assertIsNotNone(segments)
        self.assertLessEqual(len(segments), 3)
        self.assertEqual("".join(segments), original)

    def test_llm_response_cleanup_removes_chatty_heading(self) -> None:
        class Response:
            completion_text = "### 小昭评价\n\n这事确实有点无聊。主人可以先休息一下。"

        plugin = build_plugin({})
        event = FakeEvent(group_id="private-a", sender_id="user-a")
        resp = Response()

        asyncio.run(plugin.clean_llm_response_actions(event, resp))

        self.assertEqual(resp.completion_text, "这事确实有点无聊。\n\n主人可以先休息一下。")

    def test_structured_or_technical_reply_is_not_auto_split(self) -> None:
        text = (
            "配置检查结果：`action_output_enabled=False`，`natural_chat_style_enabled=True`，"
            "如果仍然出现动作描写，请先看日志里的 `action output stripped`。"
        )

        self.assertEqual(_format_natural_chat_paragraphs(text), text)

    def test_casual_reply_with_technical_words_can_still_be_segmented(self) -> None:
        text = (
            "到啦到啦～小昭状态正常，收到主人的测试信号了喵！\n\n"
            "话说刚才有人在问服务器延迟高的事，主人要不要让小昭帮你分析一下可能的原因？"
            "比如插件冲突、带宽不够、服务器物理位置远之类的，小昭随时可以切技术支持模式上线喵～"
        )

        self.assertFalse(_is_structured_or_technical_reply(text))

    def test_llm_response_cleanup_also_formats_long_casual_reply(self) -> None:
        class Response:
            completion_text = "主人一笑，小昭也跟着开心起来啦喵～刚才那点小尴尬烟消云散，小昭又满血复活了！所以主人～接下来咱们聊点啥，还是有什么正经任务要交给小昭呀？❤️"

        plugin = build_plugin({})
        event = FakeEvent(group_id="private-a", sender_id="user-a")
        resp = Response()

        asyncio.run(plugin.clean_llm_response_actions(event, resp))

        self.assertIn("\n\n", resp.completion_text)
        self.assertEqual(resp.completion_text.count("\n\n"), 1)

    def test_real_test_reply_is_stripped_and_split(self) -> None:
        class Response:
            completion_text = (
                "收到测试信号喵～！小昭状态报告：系统正常、动作括号运行稳定、"
                "护主模块待命中、可爱值满格！（眼睛亮晶晶地看着主人）"
                "\n\n主人尽管放心，小昭随时在线，不会掉链子的喵～❤️"
            )

        plugin = build_plugin({})
        provider = FakeProvider(
            '{"ok": true, "fixed": "收到测试信号喵～！小昭状态报告：系统正常、动作括号运行稳定、护主模块待命中、可爱值满格！\\n\\n主人尽管放心，小昭随时在线，不会掉链子的喵～❤️"}',
        )
        plugin.context = FakeContext(provider)
        event = FakeEvent(group_id="private-a", sender_id="user-a")
        resp = Response()

        asyncio.run(plugin.clean_llm_response_actions(event, resp))

        self.assertEqual(provider.calls, [])
        self.assertNotIn("（", resp.completion_text)
        self.assertNotIn("眼睛亮晶晶", resp.completion_text)
        self.assertIn("\n\n", resp.completion_text)
        self.assertEqual(
            resp.completion_text,
            (
                "收到测试信号喵～！小昭状态报告：系统正常、动作括号运行稳定、护主模块待命中、可爱值满格！\n\n"
                "主人尽管放心，小昭随时在线，不会掉链子的喵～❤️"
            ),
        )

    def test_model_rewrite_is_opt_in(self) -> None:
        class Response:
            completion_text = "收到测试信号喵～！小昭状态报告：系统正常。（眼睛亮晶晶地看着主人）"

        provider = FakeProvider("收到测试信号喵～！\n\n小昭状态报告：系统正常。")
        plugin = build_plugin({"natural_rewrite_use_model": True})
        plugin.context = FakeContext(provider)
        event = FakeEvent(group_id="private-a", sender_id="user-a")
        resp = Response()

        asyncio.run(plugin.clean_llm_response_actions(event, resp))

        self.assertEqual(len(provider.calls), 1)
        self.assertIn("只调整格式", provider.calls[0]["system_prompt"])
        self.assertEqual(resp.completion_text, "收到测试信号喵～！\n\n小昭状态报告：系统正常。")

    def test_action_cleanup_model_review_is_disabled_by_default(self) -> None:
        class Response:
            completion_text = "（小声嘀咕）反正小昭觉得他不太靠谱。"

        provider = FakeProvider("不应该调用模型")
        plugin = build_plugin({})
        plugin.context = FakeContext(provider)
        event = FakeEvent(group_id="private-a", sender_id="user-a")
        resp = Response()

        asyncio.run(plugin.clean_llm_response_actions(event, resp))

        self.assertEqual(resp.completion_text, "反正小昭觉得他不太靠谱。")
        self.assertEqual(provider.calls, [])

    def test_model_rewrite_skips_extra_call_when_local_cleanup_does_not_change_text(self) -> None:
        class Response:
            completion_text = "小昭收到，测试通过喵～"

        provider = FakeProvider("不应该调用模型")
        plugin = build_plugin({"natural_rewrite_use_model": True})
        plugin.context = FakeContext(provider)
        event = FakeEvent(group_id="private-a", sender_id="user-a")
        resp = Response()

        asyncio.run(plugin.clean_llm_response_actions(event, resp))

        self.assertEqual(resp.completion_text, "小昭收到，\n\n测试通过喵～")
        self.assertEqual(provider.calls, [])

    def test_model_rewrite_that_drops_prefix_falls_back_to_local_text(self) -> None:
        class Response:
            completion_text = (
                "要说坏蛋的话……那个人吧，老改名字，还一直试图套近乎、问东问西的。"
                "反正小昭觉得他不太靠谱。"
            )

        provider = FakeProvider("的话……那个人吧，老改名字，还一直试图套近乎、问东问西的。")
        plugin = build_plugin({"natural_rewrite_use_model": True})
        plugin.context = FakeContext(provider)
        event = FakeEvent(group_id="private-a", sender_id="user-a")
        resp = Response()

        asyncio.run(plugin.clean_llm_response_actions(event, resp))

        self.assertEqual(provider.calls, [])
        self.assertTrue(resp.completion_text.startswith("要说坏蛋的话"))
        self.assertIn("反正小昭觉得他不太靠谱。", resp.completion_text)

    def test_action_cleanup_model_review_validates_cleaned_reply(self) -> None:
        class Response:
            completion_text = (
                "那个人吧，老改名字，还一直试图套近乎、问东问西的。"
                "（小声嘀咕）反正小昭觉得他不太靠谱。"
            )

        provider = FakeProvider(
            '{"ok": true, "fixed": "那个人吧，老改名字，还一直试图套近乎、问东问西的。反正小昭觉得他不太靠谱。"}',
        )
        plugin = build_plugin({"action_cleanup_review_use_model": True})
        plugin.context = FakeContext(provider)
        event = FakeEvent(group_id="private-a", sender_id="user-a")
        resp = Response()

        asyncio.run(plugin.clean_llm_response_actions(event, resp))

        self.assertEqual(len(provider.calls), 1)
        self.assertIn("清理质检", provider.calls[0]["system_prompt"])
        self.assertNotIn("小声嘀咕", resp.completion_text)
        self.assertIn("反正小昭觉得他不太靠谱。", resp.completion_text)

    def test_action_cleanup_model_review_rejects_incomplete_fix(self) -> None:
        class Response:
            completion_text = (
                "要说坏蛋的话……那个人吧，老改名字，还一直试图套近乎、问东问西的。"
                "（小声嘀咕）反正小昭觉得他不太靠谱。"
            )

        provider = FakeProvider('{"ok": false, "fixed": "的话……那个人吧，老改名字。"}')
        plugin = build_plugin({"action_cleanup_review_use_model": True})
        plugin.context = FakeContext(provider)
        event = FakeEvent(group_id="private-a", sender_id="user-a")
        resp = Response()

        asyncio.run(plugin.clean_llm_response_actions(event, resp))

        self.assertEqual(len(provider.calls), 1)
        self.assertTrue(resp.completion_text.startswith("要说坏蛋的话"))
        self.assertIn("反正小昭觉得他不太靠谱。", resp.completion_text)
        self.assertNotIn("小声嘀咕", resp.completion_text)

    def test_final_reply_cleanup_removes_short_action_only_result(self) -> None:
        self.assertEqual(_strip_final_reply_text("（安安静静，没有任何回应）"), "")

    def test_decorating_result_final_cleanup_strips_short_action_reply(self) -> None:
        plugin = build_plugin({"smart_segment_enabled": False})
        event = FakeEvent(group_id="private-a", sender_id="user-a")
        event.result = FakeResult([Plain("（安安静静，没有任何回应）")])

        asyncio.run(plugin.send_natural_segments(event))

        self.assertIsNotNone(event.result)
        self.assertEqual(event.result.chain[0].text, "嗯。")
        self.assertEqual(event.sent_messages, [])

    def test_real_test_reply_falls_back_to_local_formatting_without_provider(self) -> None:
        class Response:
            completion_text = (
                "收到测试信号喵～！小昭状态报告：系统正常、动作括号运行稳定、"
                "护主模块待命中、可爱值满格！（眼睛亮晶晶地看着主人）"
                "\n\n主人尽管放心，小昭随时在线，不会掉链子的喵～❤️"
            )

        plugin = build_plugin({})
        event = FakeEvent(group_id="private-a", sender_id="user-a")
        resp = Response()

        asyncio.run(plugin.clean_llm_response_actions(event, resp))

        self.assertNotIn("（", resp.completion_text)
        self.assertNotIn("眼睛亮晶晶", resp.completion_text)
        self.assertIn("\n\n", resp.completion_text)
        self.assertIn("收到测试信号喵～！", resp.completion_text)

    def test_decorating_result_sends_model_segments_as_separate_messages(self) -> None:
        provider = FakeProvider('{"segments":["不应该调用模型"]}')
        plugin = build_plugin({"smart_segment_interval_sec": 0})
        plugin.context = FakeContext(provider)
        event = FakeEvent(group_id="private-a", sender_id="user-a")
        event.result = FakeResult(
            [
                Plain(
                    "收到测试信号喵～！小昭状态正常，可爱值也在线，刚刚那次调用没有掉线。主人还想测什么，小昭继续陪着。",
                ),
            ],
        )

        asyncio.run(plugin.send_natural_segments(event))

        self.assertIsNone(event.result)
        self.assertEqual(len(event.sent_messages), 3)
        self.assertEqual([msg.chain[0].text for msg in event.sent_messages], [
            "收到测试信号喵～！",
            "小昭状态正常，可爱值也在线，刚刚那次调用没有掉线。",
            "主人还想测什么，小昭继续陪着。",
        ])
        self.assertEqual(provider.calls, [])

    def test_decorating_result_clears_original_when_segment_send_partially_fails(self) -> None:
        provider = FakeProvider(
            '{"segments":["收到测试信号喵～！","小昭状态正常，可爱值也在线，刚刚那次调用没有掉线。","主人还想测什么，小昭继续陪着。"]}',
        )
        plugin = build_plugin({"smart_segment_interval_sec": 0})
        plugin.context = FakeContext(provider)
        event = FakeEvent(group_id="private-a", sender_id="user-a")
        event.fail_send_at = 2
        event.result = FakeResult(
            [
                Plain(
                    "收到测试信号喵～！小昭状态正常，可爱值也在线，刚刚那次调用没有掉线。主人还想测什么，小昭继续陪着。",
                ),
            ],
        )

        asyncio.run(plugin.send_natural_segments(event))

        self.assertIsNone(event.result)
        self.assertEqual(len(event.sent_messages), 1)
        self.assertEqual(event.sent_messages[0].chain[0].text, "收到测试信号喵～！")

    def test_decorating_result_keeps_structured_reply_on_default_pipeline(self) -> None:
        provider = FakeProvider('{"segments":["不应该调用"]}')
        plugin = build_plugin({})
        plugin.context = FakeContext(provider)
        event = FakeEvent(group_id="private-a", sender_id="user-a")
        event.result = FakeResult(
            [
                Plain(
                    "配置检查结果：\n1. action_output_enabled=False\n2. natural_chat_style_enabled=True",
                ),
            ],
        )

        asyncio.run(plugin.send_natural_segments(event))

        self.assertIsNotNone(event.result)
        self.assertEqual(event.sent_messages, [])
        self.assertEqual(provider.calls, [])

    def test_group_casual_numbered_advice_list_is_segmented(self) -> None:
        provider = FakeProvider('{"segments":["不应该调用模型"]}')
        plugin = build_plugin({"smart_segment_interval_sec": 0})
        plugin.context = FakeContext(provider)
        event = FakeEvent(group_id="group-a", sender_id="user-a")
        event.result = FakeResult(
            [
                Plain(
                    "分享一下小昭知道的几个实用思路喵～\n\n"
                    "1. 别太客气但也别太随便：室友之间要分东西先说一声，用完还回来。\n\n"
                    "2. 有矛盾当场说清楚：忍到爆发最伤关系，语气软一点但把问题摆出来。\n\n"
                    "3. 偶尔一起做点事：一起点个外卖、打把游戏，关系会自然近一些。\n\n"
                    "你室友是做啥让你烦的事了喵？",
                ),
            ],
        )

        asyncio.run(plugin.send_natural_segments(event))

        self.assertIsNone(event.result)
        self.assertGreaterEqual(len(event.sent_messages), 2)
        sent_texts = [msg.chain[0].text for msg in event.sent_messages]
        self.assertIn("分享一下小昭知道的几个实用思路喵～", sent_texts[0])
        self.assertTrue(any("1. 别太客气" in text for text in sent_texts))
        self.assertEqual(provider.calls, [])

    def test_model_segment_is_skipped_when_local_segments_are_enough(self) -> None:
        provider = FakeProvider('{"segments":["不应该调用"]}', delay=0.2)
        plugin = build_plugin(
            {
                "smart_segment_interval_sec": 0,
                "smart_segment_model_timeout_sec": 0.1,
            },
        )
        plugin.context = FakeContext(provider)
        event = FakeEvent(group_id="private-a", sender_id="user-a")
        event.result = FakeResult(
            [
                Plain(
                    "收到测试信号喵～！小昭状态正常，可爱值也在线，刚刚那次调用没有掉线。主人还想测什么，小昭继续陪着。",
                ),
            ],
        )

        started = monotonic()
        asyncio.run(plugin.send_natural_segments(event))
        elapsed = monotonic() - started

        self.assertLess(elapsed, 0.18)
        self.assertIsNone(event.result)
        self.assertGreaterEqual(len(event.sent_messages), 2)
        self.assertEqual(provider.calls, [])

    def test_natural_chat_style_prefers_short_chat_segments(self) -> None:
        plugin = build_plugin({})

        reminder = plugin._natural_chat_style_reminder("active_reply")

        self.assertIn("聊天段落", reminder)
        self.assertIn("列表", reminder)
        self.assertIn("步骤", reminder)
        self.assertIn("总结", reminder)
        self.assertIn("配置说明", reminder)
        self.assertIn("主动回复", reminder)
        self.assertIn("不先用“在呢”", reminder)
        self.assertIn("通常省略昵称和“主人”", reminder)
        self.assertIn("一句接梗可以只发一条", reminder)
        self.assertIn("约 120 字内", reminder)

    def test_costly_post_processing_is_opt_in_by_default(self) -> None:
        plugin = build_plugin({})

        self.assertFalse(plugin.smart_segment_use_model)
        self.assertFalse(plugin.action_cleanup_review_use_model)

    def test_silent_stop_does_not_create_empty_result(self) -> None:
        event = FakeEvent()

        _stop_event_silently(event)

        self.assertTrue(event._force_stopped)
        self.assertFalse(event.stop_event_called)
        self.assertIsNone(event.result)


if __name__ == "__main__":
    unittest.main()
