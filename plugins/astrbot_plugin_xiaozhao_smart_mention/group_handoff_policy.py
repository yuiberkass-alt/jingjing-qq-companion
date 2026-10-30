"""Conservative, group-scoped candidate screening for JingJing handoff.
Does not call any API; actual decisions go through the existing AstrBot provider.
"""
from __future__ import annotations
import re

_CUE = re.compile(
    r"[?？]|(?:那你|你不是|你刚|你说|你还|你怎么|怎么又|咋又|别装|真的假的|刚才|"
    r"上一句|刚刚|不是说|明明|为啥|为什么|接着说|继续说|你觉得|你认为|还没回答)"
)
_ACK = re.compile(r"^(?:哈+|啊+|嗯+|哦+|笑死|好|好的|ok|OK|收到|[?!？！，。~～\\s]+)$")

def make_key(bot_key: str, group_id: str) -> str:
    if not bot_key or not group_id:
        return ''
    return f'{bot_key}:group:{group_id}'

def candidate(text: str, *, allowlisted: bool, elapsed: float,
              window: float, current_sender: str, last_sender: str,
              rounds: int, max_rounds: int) -> tuple[bool, str]:
    if not allowlisted:
        return False, 'test_group_not_allowlisted'
    if not last_sender or not current_sender or current_sender == last_sender:
        return False, 'same_sender_or_unknown'
    if elapsed < 0 or window <= 0 or elapsed > window:
        return False, 'group_topic_expired'
    if max_rounds > 0 and rounds >= max_rounds:
        return False, 'group_handoff_round_limit'
    compact = re.sub(r'\s+', '', text or '')
    if len(compact) < 4 or len(compact) > 220 or _ACK.fullmatch(compact):
        return False, 'short_ack_or_oversized'
    if not _CUE.search(compact):
        return False, 'no_handoff_cue'
    return True, 'group_handoff_candidate'
