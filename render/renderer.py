"""Renders Jinja HTML card templates to cropped PNG bytes via headless Chromium.

Each template is a self-contained HTML document holding just the `.card`
element (see templates/). We load it into a headless page, wait for the
self-hosted Rajdhani / Space Mono / Inter font files (templates/fonts/) to
actually finish loading, then screenshot only the `.card` element so the
PNG is cropped tightly to the card itself with a transparent background.

Rendered HTML is written to a temp file inside templates/ and loaded via
a file:// URL (rather than page.set_content, which has no base URL to
resolve the templates' relative "fonts/*.woff2" @font-face references
against).
"""
import asyncio
import os
import uuid
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.async_api import async_playwright, Browser

TEMPLATES_DIR = Path(__file__).parent / "templates"

# In some sandboxes the pre-installed Chromium revision doesn't match the
# one this pinned Playwright version expects to auto-download. If a
# pre-installed browser directory is present, launch it explicitly instead
# of letting Playwright look for its own pinned revision.
_PW_BROWSERS_PATH = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
_PRESET_CHROMIUM = Path(_PW_BROWSERS_PATH) / "chromium" if _PW_BROWSERS_PATH else None
CHROMIUM_EXECUTABLE_PATH = str(_PRESET_CHROMIUM) if _PRESET_CHROMIUM and _PRESET_CHROMIUM.exists() else None

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
)

# Rendered at 2x for crisp text on Discord's image previews.
DEVICE_SCALE_FACTOR = 2
VIEWPORT = {"width": 400, "height": 100}


class CardRenderer:
    """Owns one headless Chromium instance for the bot process's lifetime."""

    def __init__(self):
        self._playwright = None
        self._browser: Browser | None = None

    async def start(self):
        self._playwright = await async_playwright().start()
        launch_kwargs = {}
        if CHROMIUM_EXECUTABLE_PATH:
            launch_kwargs["executable_path"] = CHROMIUM_EXECUTABLE_PATH
        self._browser = await self._playwright.chromium.launch(**launch_kwargs)

    async def stop(self):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def render(self, template_name: str, context: dict) -> bytes:
        if self._browser is None:
            raise RuntimeError("CardRenderer.start() must be called before render().")

        template = _env.get_template(template_name)
        html = template.render(**context)

        # Written next to the templates so relative "fonts/*.woff2" URLs
        # resolve correctly when loaded as a file:// URL.
        tmp_path = TEMPLATES_DIR / f".render-{uuid.uuid4().hex}.html"
        tmp_path.write_text(html, encoding="utf-8")

        page = await self._browser.new_page(
            viewport=VIEWPORT,
            device_scale_factor=DEVICE_SCALE_FACTOR,
        )
        try:
            await page.goto(f"file://{tmp_path}", wait_until="networkidle")
            await page.evaluate("document.fonts.ready")
            card = page.locator(".card")
            return await card.screenshot(type="png")
        finally:
            await page.close()
            tmp_path.unlink(missing_ok=True)


async def _standalone_test():
    """Quick manual check: render taste.html with dummy data to a local file."""
    renderer = CardRenderer()
    await renderer.start()
    try:
        png = await renderer.render(
            "taste.html",
            {
                "score": 73,
                "archetype": "Hidden-Gem Hunter",
                "archetype_blurb": "actively seeks out what the crowd missed",
                "driven_by": [],
                "user_tag": "No. 003847291",
                "username": "example",
                "issued_date": "05 jul 2026",
            },
        )
        Path("preview.png").write_bytes(png)
    finally:
        await renderer.stop()


if __name__ == "__main__":
    asyncio.run(_standalone_test())
