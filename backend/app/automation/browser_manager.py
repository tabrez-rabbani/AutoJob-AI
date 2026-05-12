"""
AutoJob AI — Browser Manager (Advanced)
Manages Playwright browser instances with stealth configuration,
proxy support, and fingerprint randomization.
"""

import asyncio
import logging
from pathlib import Path
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from app.automation.stealth import (
    STEALTH_SCRIPTS,
    get_random_user_agent,
    get_random_viewport,
    get_random_timezone_locale,
    get_random_delay,
    get_typing_delay,
    get_chrome_args,
)
from app.automation.proxy_manager import proxy_manager

logger = logging.getLogger(__name__)

# Directory to store session cookies
SESSIONS_DIR = Path(__file__).parent.parent.parent / "sessions"
SESSIONS_DIR.mkdir(exist_ok=True)


class BrowserManager:
    """
    Manages a Playwright browser instance with stealth settings,
    proxy rotation, and fingerprint randomization.
    Use as an async context manager for automatic cleanup.
    """

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._active_proxy: dict | None = None  # Track which proxy is being used

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def start(self) -> None:
        """Launch browser with stealth configuration and optional proxy."""
        self._playwright = await async_playwright().start()

        viewport = get_random_viewport()
        user_agent = get_random_user_agent()
        tz_locale = get_random_timezone_locale()
        chrome_args = get_chrome_args()

        # Get proxy from pool (if available)
        self._active_proxy = proxy_manager.get_next_proxy()

        launch_options = {
            "headless": self.headless,
            "args": chrome_args,
        }

        # Playwright proxy goes on launch, not on context
        if self._active_proxy:
            launch_options["proxy"] = self._active_proxy
            logger.info(f"Using proxy: {self._active_proxy['server']}")

        self._browser = await self._playwright.chromium.launch(**launch_options)

        self._context = await self._browser.new_context(
            viewport=viewport,
            user_agent=user_agent,
            locale=tz_locale["locale"],
            timezone_id=tz_locale["timezone_id"],
            color_scheme="light",  # Most real users use light mode
            java_script_enabled=True,
            has_touch=False,
            is_mobile=False,
            ignore_https_errors=True,  # Needed for some proxies
        )

        # Inject all stealth scripts on every new page
        for script in STEALTH_SCRIPTS:
            await self._context.add_init_script(script)

        logger.info(
            f"Browser started — viewport={viewport['width']}x{viewport['height']}, "
            f"tz={tz_locale['timezone_id']}, headless={self.headless}, "
            f"proxy={'yes' if self._active_proxy else 'no'}"
        )

    async def new_page(self) -> Page:
        """Create a new stealth-configured page."""
        if not self._context:
            raise RuntimeError("Browser not started. Call start() first.")
        return await self._context.new_page()

    def report_proxy_success(self) -> None:
        """Call this after successful scraping/login to report proxy health."""
        if self._active_proxy:
            proxy_manager.report_success(self._active_proxy["server"])

    def report_proxy_failure(self) -> None:
        """Call this after failed scraping/login to report proxy failure."""
        if self._active_proxy:
            proxy_manager.report_failure(self._active_proxy["server"])

    async def save_session(self, name: str) -> Path:
        """Save browser session cookies to disk."""
        if not self._context:
            raise RuntimeError("No active browser context.")

        filepath = SESSIONS_DIR / f"{name}.json"
        storage = await self._context.storage_state()

        import json
        filepath.write_text(json.dumps(storage, indent=2))
        logger.info(f"Session saved: {filepath}")
        return filepath

    async def load_session(self, name: str) -> bool:
        """Load a saved session. Returns True if file exists and was loaded."""
        filepath = SESSIONS_DIR / f"{name}.json"

        if not filepath.exists():
            logger.warning(f"No saved session found: {filepath}")
            return False

        # Re-create context with saved storage state
        if self._context:
            await self._context.close()

        viewport = get_random_viewport()
        user_agent = get_random_user_agent()
        tz_locale = get_random_timezone_locale()

        self._context = await self._browser.new_context(
            viewport=viewport,
            user_agent=user_agent,
            locale=tz_locale["locale"],
            timezone_id=tz_locale["timezone_id"],
            color_scheme="light",
            has_touch=False,
            is_mobile=False,
            ignore_https_errors=True,
            storage_state=str(filepath),
        )

        for script in STEALTH_SCRIPTS:
            await self._context.add_init_script(script)

        logger.info(f"Session loaded: {filepath}")
        return True

    async def human_type(self, page: Page, selector: str, text: str) -> None:
        """Type text with human-like delays between keystrokes."""
        await page.click(selector)
        for char in text:
            await page.type(selector, char, delay=get_typing_delay())

    async def human_delay(self, min_sec: float = 1.5, max_sec: float = 5.0) -> None:
        """Wait for a random human-like duration."""
        delay = get_random_delay(min_sec, max_sec)
        await asyncio.sleep(delay)

    async def close(self) -> None:
        """Clean up all browser resources."""
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("Browser closed.")
