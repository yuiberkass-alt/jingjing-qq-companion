"""r21: lookups should only fire on links or explicit search requests."""
import unittest

import web_tools


class TriggerTests(unittest.TestCase):
    def test_finds_links(self):
        self.assertEqual(web_tools.find_url("看看这个 https://example.com/a?b=1 挺有意思"),
                         "https://example.com/a?b=1")
        self.assertIsNone(web_tools.find_url("今天天气不错"))

    def test_search_cues(self):
        for text in ("帮我查一下明天的天气", "搜一下 deepseek 是什么", "最新消息是什么"):
            self.assertTrue(web_tools.wants_search(text), text)
        for text in ("今天吃什么", "哈哈哈哈", "这个图你看怎么样"):
            self.assertFalse(web_tools.wants_search(text), text)

    def test_private_targets_are_refused(self):
        self.assertIsNone(web_tools.fetch_page("http://127.0.0.1:8080/admin"))
        self.assertIsNone(web_tools.fetch_page("http://169.254.169.254/latest/meta-data"))

    def test_unsupported_scheme(self):
        self.assertIsNone(web_tools.fetch_page("file:///etc/passwd"))

    def test_text_extraction(self):
        html = "<html><head><title>标题</title><script>x=1</script></head><body><p>正文 内容</p></body></html>"
        self.assertIn("正文 内容", web_tools._text_of(html))
        self.assertNotIn("x=1", web_tools._text_of(html))

class ImageValidationTests(unittest.TestCase):
    def test_real_png_passes_and_garbage_fails(self):
        import tempfile
        from pathlib import Path
        import main
        with tempfile.TemporaryDirectory() as tmp:
            png = Path(tmp) / "a.png"
            png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 40)
            self.assertTrue(main._jj_is_readable_image(str(png)))
            bad = Path(tmp) / "b.png"
            bad.write_bytes(b"<html>not an image</html>" + b"0" * 40)
            self.assertFalse(main._jj_is_readable_image(str(bad)))
            self.assertTrue(main._jj_is_readable_image(str(Path(tmp) / "missing.png")))
