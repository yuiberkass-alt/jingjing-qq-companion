from __future__ import annotations

from dataclasses import dataclass


QQ_OFFICIAL_PLATFORM_NAMES = {"qq_official", "qq_official_webhook"}
QQ_OFFICIAL_SELF_IDS = {"", "qq_official", "unknown_selfid"}


@dataclass(frozen=True)
class PlatformIdentity:
    platform_name: str
    platform_id: str
    bot_id: str
    group_id: str
    sender_id: str

    @property
    def bot_key(self) -> str:
        return f"{self.platform_id}:bot:{self.bot_id}"

    @property
    def sender_key(self) -> str:
        return f"{self.bot_key}:sender:{self.sender_id}"


def event_identity(event) -> PlatformIdentity:
    platform_name = _event_value(event, "get_platform_name")
    platform_id = _event_value(event, "get_platform_id") or _session_platform_id(event)
    self_id = _event_value(event, "get_self_id")
    group_id = _event_value(event, "get_group_id") or _session_id(event)
    sender_id = _event_value(event, "get_sender_id")

    if platform_name in QQ_OFFICIAL_PLATFORM_NAMES or self_id in QQ_OFFICIAL_SELF_IDS:
        bot_id = platform_id or self_id or "qq_official"
    else:
        bot_id = self_id or platform_id

    return PlatformIdentity(
        platform_name=platform_name,
        platform_id=platform_id,
        bot_id=bot_id,
        group_id=group_id,
        sender_id=sender_id,
    )


def is_qq_official_event(event) -> bool:
    identity = event_identity(event)
    return identity.platform_name in QQ_OFFICIAL_PLATFORM_NAMES


def is_official_at_self(event, at_id: str) -> bool:
    if not is_qq_official_event(event):
        return False
    return str(at_id or "") in QQ_OFFICIAL_SELF_IDS


def _event_value(event, method_name: str) -> str:
    method = getattr(event, method_name, None)
    if callable(method):
        try:
            value = method()
        except Exception:
            return ""
        return str(value or "")
    return ""


def _session_platform_id(event) -> str:
    umo = str(getattr(event, "unified_msg_origin", "") or "")
    if ":" not in umo:
        return ""
    return umo.split(":", 1)[0]


def _session_id(event) -> str:
    session_id = getattr(event, "session_id", "")
    if session_id:
        return str(session_id)
    umo = str(getattr(event, "unified_msg_origin", "") or "")
    parts = umo.split(":", 2)
    if len(parts) == 3:
        return parts[2]
    return ""
