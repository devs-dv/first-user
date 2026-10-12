"""look() returns the URL of the screenshot it published, so the look step links it, and the model never sees it."""

import test_support  # noqa: F401  (first: keeps tests from sending traces to neatlogs)

import contextlib
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import tools


class FakePage:
    async def url(self):
        return "https://shop.example/cart"

    async def title(self):
        return "Cart"

    async def evaluate(self, script):
        return "Your cart"


def fake_ctx(page) -> tools.RunContext:
    extract = mock.AsyncMock(return_value=SimpleNamespace(
        data=SimpleNamespace(summary="A cart with one item.", interactive=["Checkout button"])))
    ctx_usage = mock.Mock()
    stagehand = SimpleNamespace(extract=extract, metrics=mock.AsyncMock(return_value={}))
    ctx = tools.RunContext(url="https://shop.example/", goal="Buy", run_id="r1", stagehand=stagehand, page=page,
                           usage=ctx_usage)
    return ctx


class LookScreenshot(unittest.IsolatedAsyncioTestCase):
    async def look_with(self, published: str | None) -> dict:
        page = FakePage()
        ctx = fake_ctx(page)
        token = tools.current_run.set(ctx)
        page.screenshot = mock.AsyncMock(return_value=b"png-bytes")
        try:
            with mock.patch.object(tools, "_active_page", mock.AsyncMock(return_value=page)), \
                    mock.patch.object(tools, "stop_at_bot_check", mock.AsyncMock(return_value=None)), \
                    mock.patch.object(tools.hidden_text, "sweep", mock.AsyncMock()), \
                    mock.patch.object(tools, "page_fingerprint", mock.AsyncMock(return_value="fp")), \
                    mock.patch.object(tools, "publish_image", mock.AsyncMock(return_value=published)), \
                    mock.patch.object(tools.credentials_module, "redacted_page",
                                      lambda page: contextlib.nullcontext()), \
                    mock.patch.object(tools.trace_media, "register_url"):
                return await tools.look()
        finally:
            tools.current_run.reset(token)

    async def test_a_published_screenshot_is_returned_with_the_look(self):
        result = await self.look_with("https://img.example/look_1.png")
        self.assertEqual(result["screenshot_url"], "https://img.example/look_1.png")
        self.assertTrue(result["screenshot_attached"])

    async def test_without_an_upload_there_is_no_link(self):
        result = await self.look_with(None)
        self.assertNotIn("screenshot_url", result)

    async def test_the_look_step_gets_the_screenshot_linked(self):
        import browse

        ctx = fake_ctx(FakePage())
        ctx.tool_calls = 3
        result = await self.look_with("https://img.example/look_2.png")
        await browse._record(ctx, "look", "", {}, result, 0, 0)
        self.assertEqual(ctx.step_shots[3], "https://img.example/look_2.png")


if __name__ == "__main__":
    unittest.main()
