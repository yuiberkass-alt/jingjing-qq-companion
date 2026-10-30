import json, types, unittest, asyncio
from unittest.mock import AsyncMock, patch
from test_jingjing_repairs import FakeEvent, Plain, Image
import main
from test_directed_guard import FakeResult
import test_jingjing_r3 as r3

class SemanticStickerTests(unittest.IsolatedAsyncioTestCase):
    def setup_case(self, incoming='我可没提饭哈', reply='行行行，是我自己馋，跟你没关系行了吧🙃'):
        p=r3.FallbackTests().setup_plugin()
        e=FakeEvent(text=incoming)
        e.set_extra(main.EXTRA_JJ_STICKER_STATUS,'no_marker')
        e.set_extra('JJ_STICKER_ALLOWED_NAMES_V01',[])
        e.result=FakeResult([Plain(reply)])
        return p,e

    async def test_screenshot_banter_without_keywords_attaches_real_catalog_choice(self):
        p,e=self.setup_case()
        async def choose(event,**kwargs):
            data=json.loads(kwargs['prompt'])
            self.assertIn('是我自己馋',data['reply'])
            categories={a['category'] for a in data['candidates']}
            self.assertIn('吐槽与傲娇',categories)
            chosen=next(a for a in data['candidates'] if a['category']=='吐槽与傲娇')
            return json.dumps({'name':chosen['name']})
        p._call_internal_model=AsyncMock(side_effect=choose)
        with patch.object(Image,'fromFileSystem',side_effect=lambda path:Image(path),create=True):
            await p.send_natural_segments(e)
        self.assertEqual(sum(isinstance(c,Image) for c in e.result.chain),1)
        self.assertEqual(p._call_internal_model.await_count,1)
        await p.send_natural_segments(e)
        self.assertEqual(p._call_internal_model.await_count,1)

    async def test_none_is_respected_even_when_keyword_fallback_would_match(self):
        p,e=self.setup_case('想你了','我也想你')
        p._call_internal_model=AsyncMock(return_value='{"name":"NONE"}')
        await p._jj_choose_contextual_sticker(e,e.result)
        p._jj_prepare_sticker(e,e.result)
        self.assertFalse(any(isinstance(c,Image) for c in e.result.chain))
        self.assertEqual(e.get_extra(main.EXTRA_JJ_STICKER_STATUS),'semantic_skip')

    async def test_untrusted_name_cannot_be_attached(self):
        for raw in ['{"name":"../secret"}','{"name":"jj9999"}','[]','not json']:
            p,e=self.setup_case();p._call_internal_model=AsyncMock(return_value=raw)
            await p._jj_choose_contextual_sticker(e,e.result)
            p._jj_prepare_sticker(e,e.result)
            self.assertFalse(any(isinstance(c,Image) for c in e.result.chain))

    async def test_timeout_does_not_drop_text(self):
        p,e=self.setup_case();p._call_internal_model=AsyncMock(side_effect=asyncio.TimeoutError)
        text=e.result.chain[0].text
        await p._jj_choose_contextual_sticker(e,e.result)
        p._jj_prepare_sticker(e,e.result)
        self.assertEqual(e.result.chain[0].text,text)

    async def test_serious_and_optout_make_no_model_call(self):
        for text in ['不要表情包','我住院了','帮我调试配置']:
            p,e=self.setup_case(text,'好的')
            p._call_internal_model=AsyncMock()
            await p._jj_choose_contextual_sticker(e,e.result)
            p._call_internal_model.assert_not_awaited()

    async def test_cooldown_prevents_call(self):
        p,e=self.setup_case();p._jj_group_sticker_at[p._directed_group_key(e)]=main.monotonic()
        p._call_internal_model=AsyncMock()
        await p._jj_choose_contextual_sticker(e,e.result)
        p._call_internal_model.assert_not_awaited()

    async def test_concurrent_selections_still_only_attach_one(self):
        p,e=self.setup_case();_,other=self.setup_case()
        async def choose(event,**kwargs):
            await asyncio.sleep(0)
            return json.dumps({'name':json.loads(kwargs['prompt'])['candidates'][0]['name']})
        p._call_internal_model=AsyncMock(side_effect=choose)
        await asyncio.gather(p._jj_choose_contextual_sticker(e,e.result),p._jj_choose_contextual_sticker(other,other.result))
        with patch.object(Image,'fromFileSystem',side_effect=lambda path:Image(path),create=True):
            p._jj_prepare_sticker(e,e.result);p._jj_prepare_sticker(other,other.result)
        self.assertEqual(sum(isinstance(c,Image) for event in [e,other] for c in event.result.chain),1)
