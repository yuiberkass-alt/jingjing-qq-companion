"""r16: a burst must not lose every reply to stale-suppression.

Observed live at 13:26: the user sent "鲸鲸" then "在吗", and the finished
reply to each was discarded because the next line had arrived. The first
delivered reply only came 10 seconds later for the third message.
"""
import unittest

from test_jingjing_repairs import plugin, FakeEvent, FakeResult, Plain
import main


class StaleDropTests(unittest.TestCase):
    def _event(self, p, text="在吗"):
        event = FakeEvent(text=text)
        p._record_input_event(event)
        event.result = FakeResult([Plain("在呢")])
        return event

    @staticmethod
    def _seq(event):
        return event.get_extra(main.EXTRA_INPUT_SEQUENCE)

    def test_first_stale_reply_is_dropped(self):
        p = plugin()
        event = self._event(p, "鲸鲸")
        p._record_input_event(FakeEvent(text="在吗"))  # newer input exists
        self.assertTrue(p._jj_may_drop_stale(event, self._seq(event)))

    def test_second_stale_reply_is_delivered(self):
        p = plugin()
        first = self._event(p, "鲸鲸")
        p._record_input_event(FakeEvent(text="在吗"))
        self.assertTrue(p._jj_may_drop_stale(first, self._seq(first)))

        second = self._event(p, "在吗")
        p._record_input_event(FakeEvent(text="我刚吃完饭"))
        self.assertFalse(p._jj_may_drop_stale(second, self._seq(second)))

    def test_no_newer_input_never_drops(self):
        p = plugin()
        event = self._event(p)
        self.assertFalse(p._jj_may_drop_stale(event, self._seq(event)))

    def test_drop_window_expires(self):
        p = plugin()
        first = self._event(p, "鲸鲸")
        p._record_input_event(FakeEvent(text="在吗"))
        self.assertTrue(p._jj_may_drop_stale(first, self._seq(first)))
        later = self._event(p, "在吗")
        p._record_input_event(FakeEvent(text="还在吗"))
        key = later.unified_msg_origin
        p._jj_last_stale_drop_at[key] -= 60.0
        self.assertTrue(p._jj_may_drop_stale(later, self._seq(later)))
