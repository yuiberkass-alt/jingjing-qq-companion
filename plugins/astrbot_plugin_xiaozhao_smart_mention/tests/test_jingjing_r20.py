"""r20: pictures must reach the model on the @mention path too.

Observed 14:50: an image was @-mentioned to the bot; the request carried
images=0, so it answered "还是空白欸" about a picture it never received.
"""
import types
import unittest
from unittest.mock import AsyncMock

from test_jingjing_repairs import plugin, FakeEvent, Image, Plain
import main


class MentionImageTests(unittest.IsolatedAsyncioTestCase):
    async def test_mention_request_gets_the_picture(self):
        p = plugin()
        image = Image("/synthetic/m.png")
        image.convert_to_file_path = AsyncMock(return_value="/synthetic/m.png")
        event = FakeEvent(text="这张图你看怎么样", messages=[image])
        event.set_extra(main.EXTRA_MODE, "mention")
        req = types.SimpleNamespace(image_urls=[], system_prompt="", contexts=[],
                                    prompt="这张图你看怎么样", func_tool=None)
        await p.decorate_llm_request(event, req)
        self.assertEqual(req.image_urls, ["/synthetic/m.png"])

    async def test_existing_images_are_not_duplicated(self):
        p = plugin()
        image = Image("/synthetic/m.png")
        image.convert_to_file_path = AsyncMock(return_value="/synthetic/m.png")
        event = FakeEvent(text="看图", messages=[image])
        req = types.SimpleNamespace(image_urls=["/already/there.png"], system_prompt="",
                                    contexts=[], prompt="看图", func_tool=None)
        await p.decorate_llm_request(event, req)
        self.assertEqual(req.image_urls, ["/already/there.png"])
