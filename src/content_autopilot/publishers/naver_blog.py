import asyncio
import importlib
import json
from pathlib import Path

from content_autopilot.common.logger import get_logger
from content_autopilot.config import settings
from content_autopilot.schemas import ArticleDraft, PublishResult

log = get_logger("publishers.naver_blog")
COOKIE_PATH = Path("data/naver_cookies.json")
NAVER_BLOG_WRITE_URL = "https://blog.naver.com/{blog_id}/postwrite"


class NaverBlogPublisher:
    def __init__(
        self,
        naver_id: str | None = None,
        naver_password: str | None = None,
        blog_id: str | None = None,
    ):
        self._naver_id = naver_id or settings.naver_id
        self._naver_password = naver_password or settings.naver_password
        self._blog_id = blog_id or settings.naver_blog_id or self._naver_id

    async def publish(self, draft: ArticleDraft) -> PublishResult:
        if not self._naver_id or not self._naver_password:
            return PublishResult(channel="naver_blog", status="skipped", error="No credentials")

        try:
            importlib.import_module("playwright.async_api")
        except ImportError:
            return PublishResult(
                channel="naver_blog",
                status="skipped",
                error="playwright not installed",
            )

        try:
            published_url = await self._post_via_browser(draft)
            return PublishResult(channel="naver_blog", status="success", external_url=published_url)
        except Exception as exc:
            log.error("naver_blog_error", error=str(exc))
            return PublishResult(channel="naver_blog", status="failed", error=str(exc)[:200])

    async def _post_via_browser(self, draft: ArticleDraft) -> str:
        async_playwright = importlib.import_module("playwright.async_api").async_playwright

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context()

            if COOKIE_PATH.exists():
                cookies = json.loads(COOKIE_PATH.read_text())
                await context.add_cookies(cookies)

            page = await context.new_page()

            await page.goto("https://blog.naver.com/MyBlog.naver")
            await page.wait_for_load_state("networkidle")

            if "login" in page.url.lower() or "nid.naver.com" in page.url:
                await self._login(page)
                cookies = await context.cookies()
                COOKIE_PATH.parent.mkdir(parents=True, exist_ok=True)
                COOKIE_PATH.write_text(json.dumps(cookies))

            write_url = NAVER_BLOG_WRITE_URL.format(blog_id=self._blog_id)
            await page.goto(write_url)
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)

            title_selector = 'input[placeholder*="제목"], .se-title-input, #post-title-inp'
            await page.wait_for_selector(title_selector, timeout=10000)
            await page.fill(title_selector, draft.title_ko)

            content_area = '.se-main-container, .se-content, [contenteditable="true"]'
            content_text = draft.content_ko[:2000]

            try:
                await page.click(content_area, timeout=5000)
                await page.keyboard.type(content_text)
            except Exception:
                await page.evaluate(
                    """
                    (content) => {
                        const editor = document.querySelector('[contenteditable="true"]');
                        if (editor) {
                            editor.innerHTML = content;
                        }
                    }
                    """,
                    content_text,
                )

            source_text = f"\n\n출처: {draft.source_attribution}"
            await page.keyboard.type(source_text)

            publish_btn = 'button:has-text("발행"), .btn_publish, #publish-btn'
            await page.click(publish_btn, timeout=5000)
            await asyncio.sleep(3)

            current_url = page.url
            await browser.close()

            log.info("naver_blog_published", title=draft.title_ko[:30], url=current_url)
            return current_url

    async def _login(self, page) -> None:
        await page.goto("https://nid.naver.com/nidlogin.login")
        await page.wait_for_load_state("networkidle")

        await page.evaluate(
            """
            (credentials) => {
                const idInput = document.querySelector('#id');
                const pwInput = document.querySelector('#pw');
                if (idInput) {
                    idInput.value = credentials.naverId;
                }
                if (pwInput) {
                    pwInput.value = credentials.naverPassword;
                }
            }
            """,
            {"naverId": self._naver_id, "naverPassword": self._naver_password},
        )
        await page.click('#log\\.login')
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(3)

        if "captcha" in page.url.lower() or "2fa" in page.url.lower():
            raise RuntimeError(
                "Naver requires CAPTCHA or 2FA. Please login manually first and save cookies."
            )
