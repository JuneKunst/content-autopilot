import asyncio
import importlib
import json
from pathlib import Path

import markdown

from content_autopilot.common.logger import get_logger
from content_autopilot.config import settings
from content_autopilot.schemas import ArticleDraft, PublishResult

log = get_logger("publishers.tistory")
COOKIE_PATH = Path("data/tistory_cookies.json")


class TistoryPublisher:
    def __init__(
        self,
        email: str | None = None,
        password: str | None = None,
        blog_name: str | None = None,
    ):
        self._email = email or settings.tistory_email
        self._password = password or settings.tistory_password
        self._blog_name = blog_name or settings.tistory_blog_name

    async def publish(self, draft: ArticleDraft) -> PublishResult:
        if not self._email or not self._password or not self._blog_name:
            return PublishResult(channel="tistory", status="skipped", error="No credentials")

        try:
            importlib.import_module("playwright.async_api")
        except ImportError:
            return PublishResult(
                channel="tistory", status="skipped",
                error="playwright not installed",
            )

        try:
            published_url = await self._post_via_browser(draft)
            return PublishResult(channel="tistory", status="success", external_url=published_url)
        except Exception as exc:
            log.error("tistory_error", error=str(exc))
            return PublishResult(channel="tistory", status="failed", error=str(exc)[:200])

    async def _post_via_browser(self, draft: ArticleDraft) -> str:
        async_playwright = importlib.import_module("playwright.async_api").async_playwright

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context()

            if COOKIE_PATH.exists():
                cookies = json.loads(COOKIE_PATH.read_text())
                await context.add_cookies(cookies)

            page = await context.new_page()

            write_url = f"https://{self._blog_name}.tistory.com/manage/newpost"
            await page.goto(write_url)
            await page.wait_for_load_state("networkidle")

            if "accounts.kakao.com" in page.url or "tistory.com/auth/login" in page.url:
                await self._login(page)
                cookies = await context.cookies()
                COOKIE_PATH.parent.mkdir(parents=True, exist_ok=True)
                COOKIE_PATH.write_text(json.dumps(cookies))
                await page.goto(write_url)
                await page.wait_for_load_state("networkidle")

            await asyncio.sleep(2)

            title_input = "#post-title-inp"
            await page.wait_for_selector(title_input, timeout=10000)
            await page.fill(title_input, draft.title_ko)

            try:
                html_btn = 'button:has-text("HTML"), .btn-mode-html'
                await page.click(html_btn, timeout=3000)
                await asyncio.sleep(1)
            except Exception:
                pass

            html_content = markdown.markdown(draft.content_ko)
            if draft.source_attribution:
                url = draft.source_attribution
                html_content += (
                    f'<p>출처: <a href="{url}">{url}</a></p>'
                )

            try:
                await page.evaluate(
                    """
                    (content) => {
                        const cm = document.querySelector('.CodeMirror');
                        if (cm && cm.CodeMirror) {
                            cm.CodeMirror.setValue(content);
                            return;
                        }
                        const sel = '[contenteditable="true"], .mce-content-body';
                        const editor = document.querySelector(sel);
                        if (editor) {
                            editor.innerHTML = content;
                        }
                    }
                    """,
                    html_content,
                )
            except Exception:
                editor_area = '[contenteditable="true"], textarea.content'
                await page.click(editor_area, timeout=5000)
                await page.keyboard.type(draft.content_ko[:3000])

            for tag in draft.tags[:5]:
                try:
                    tag_input = '#tagText, input[placeholder*="태그"]'
                    await page.fill(tag_input, tag)
                    await page.keyboard.press("Enter")
                except Exception:
                    break

            publish_btn = '#publish-layer-btn, button:has-text("발행"), button:has-text("완료")'
            await page.click(publish_btn, timeout=5000)
            await asyncio.sleep(1)

            try:
                confirm_btn = '#publish-btn, button:has-text("발행")'
                await page.click(confirm_btn, timeout=3000)
            except Exception:
                pass

            await asyncio.sleep(3)
            current_url = page.url
            await browser.close()

            log.info("tistory_published", title=draft.title_ko[:30], url=current_url)
            return current_url

    async def _login(self, page) -> None:
        await page.goto("https://accounts.kakao.com/login")
        await page.wait_for_load_state("networkidle")

        await page.fill('input[name="loginId"], #loginId--1', self._email)
        await page.fill('input[name="password"], #password--2', self._password)
        await page.click('button[type="submit"], .btn_submit')
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(3)
