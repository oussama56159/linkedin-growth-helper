"""
Manages LinkedIn browser sessions using Playwright.

Two modes:
  - REAL BROWSER (recommended): Connects to your already-running Chrome via
    remote debugging. LinkedIn sees your real browser fingerprint.
  - HEADLESS FALLBACK: Launches a fresh Chromium with anti-detection patches.
    Higher ban risk — only use if real browser mode isn't possible.

To enable real browser mode:
  1. Close all Chrome windows
  2. Launch Chrome with remote debugging:
       Windows: chrome.exe --remote-debugging-port=9222 --user-data-dir=C:\\ChromeDebug
       Mac/Linux: google-chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-debug
  3. Log into LinkedIn manually in that Chrome window
  4. Set use_real_browser=True in SessionManager (or in settings.yaml)
"""

import logging
import time
import random
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page

logger = logging.getLogger(__name__)


class SessionManager:
    def __init__(
        self,
        session_file: str,
        headless: bool = True,
        use_real_browser: bool = False,
        real_browser_port: int = 9222,
    ):
        self.session_file = Path(session_file)
        self.session_file.parent.mkdir(parents=True, exist_ok=True)
        self.headless = headless
        self.use_real_browser = use_real_browser
        self.real_browser_port = real_browser_port
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    def start(self) -> Page:
        """Start browser session."""
        self._playwright = sync_playwright().start()

        if self.use_real_browser:
            return self._start_real_browser()
        else:
            return self._start_headless()

    def _start_real_browser(self) -> Page:
        """
        Connect to an already-running Chrome instance via CDP.
        This is the safest mode — LinkedIn sees your real browser.
        """
        logger.info(
            "Connecting to real Chrome on port %d...", self.real_browser_port
        )
        try:
            self._browser = self._playwright.chromium.connect_over_cdp(
                f"http://localhost:{self.real_browser_port}"
            )
            # Use the existing context (already logged in)
            contexts = self._browser.contexts
            if contexts:
                self._context = contexts[0]
                pages = self._context.pages
                self._page = pages[0] if pages else self._context.new_page()
            else:
                self._context = self._browser.new_context()
                self._page = self._context.new_page()

            logger.info("Connected to real Chrome successfully.")
            return self._page

        except Exception as e:
            logger.error(
                "Could not connect to Chrome on port %d: %s\n"
                "Make sure Chrome is running with --remote-debugging-port=%d",
                self.real_browser_port, e, self.real_browser_port,
            )
            raise

    def _start_headless(self) -> Page:
        """
        Launch a fresh Chromium with anti-detection patches applied.
        Less safe than real browser mode but works without manual Chrome setup.
        """
        logger.info("Starting headless Chromium (use_real_browser=False)...")

        # Randomize viewport slightly to avoid fixed-size fingerprint
        width = random.randint(1280, 1440)
        height = random.randint(720, 900)

        self._browser = self._playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-infobars",
                "--disable-extensions",
                f"--window-size={width},{height}",
            ],
        )

        context_kwargs = {
            # Randomize user-agent Chrome version slightly
            "user_agent": self._random_user_agent(),
            "viewport": {"width": width, "height": height},
            "locale": "en-US",
            "timezone_id": "America/New_York",
            # Realistic device memory and hardware concurrency
            "extra_http_headers": {
                "Accept-Language": "en-US,en;q=0.9",
                "sec-ch-ua-platform": '"Windows"',
            },
        }

        if self.session_file.exists():
            logger.info("Restoring saved session from %s", self.session_file)
            context_kwargs["storage_state"] = str(self.session_file)

        self._context = self._browser.new_context(**context_kwargs)
        self._apply_stealth_scripts()
        self._page = self._context.new_page()
        return self._page

    def _apply_stealth_scripts(self):
        """Inject JS to mask common automation detection signals."""
        self._context.add_init_script("""
            // Remove webdriver flag
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

            // Fake plugins array (empty in headless)
            Object.defineProperty(navigator, 'plugins', {
                get: () => [
                    { name: 'Chrome PDF Plugin' },
                    { name: 'Chrome PDF Viewer' },
                    { name: 'Native Client' }
                ]
            });

            // Fake languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });

            // Fake hardware concurrency (headless often returns 2)
            Object.defineProperty(navigator, 'hardwareConcurrency', {
                get: () => 8
            });

            // Fake device memory
            Object.defineProperty(navigator, 'deviceMemory', {
                get: () => 8
            });

            // Chrome runtime object
            window.chrome = {
                runtime: {
                    connect: () => {},
                    sendMessage: () => {},
                },
                loadTimes: () => {},
                csi: () => {},
            };

            // Permissions API fix (headless returns 'denied' for notifications)
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) =>
                parameters.name === 'notifications'
                    ? Promise.resolve({ state: Notification.permission })
                    : originalQuery(parameters);
        """)

    def login(self, email: str, password: str) -> bool:
        """Perform LinkedIn login if not already authenticated."""
        if not self._page:
            raise RuntimeError("Call start() before login()")

        self._page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
        self._random_delay(2, 4)

        if "feed" in self._page.url:
            logger.info("Already logged in.")
            return True

        if self.use_real_browser:
            logger.warning(
                "Real browser mode: not logged in. "
                "Please log into LinkedIn manually in the Chrome window."
            )
            return False

        logger.info("Logging in to LinkedIn...")
        self._page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
        self._random_delay(1, 3)

        self._human_type(self._page.locator("#username"), email)
        self._random_delay(0.8, 2.0)
        self._human_type(self._page.locator("#password"), password)
        self._random_delay(0.5, 1.2)

        self._page.click("button[type='submit']")
        self._page.wait_for_load_state("domcontentloaded")
        self._random_delay(3, 6)

        if "feed" in self._page.url:
            logger.info("Login successful.")
            self._save_session()
            return True

        logger.warning("Login may have failed. URL: %s", self._page.url)
        return False

    def _save_session(self):
        if self._context and not self.use_real_browser:
            self._context.storage_state(path=str(self.session_file))
            logger.info("Session saved to %s", self.session_file)

    def save_session(self):
        self._save_session()

    def get_page(self) -> Page:
        if not self._page:
            raise RuntimeError("Session not started. Call start() first.")
        return self._page

    def close(self):
        if not self.use_real_browser:
            # Only save/close if we own the browser
            self._save_session()
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
        if self._playwright:
            self._playwright.stop()
        logger.info("Browser session closed.")

    def _human_type(self, locator, text: str):
        """Type text with random per-keystroke delays."""
        locator.click()
        self._random_delay(0.2, 0.5)
        for char in text:
            locator.type(char, delay=random.randint(60, 180))
            # Occasional longer pause (simulates hesitation)
            if random.random() < 0.08:
                time.sleep(random.uniform(0.3, 1.0))

    @staticmethod
    def _random_user_agent() -> str:
        """Return a slightly randomized but realistic Chrome user-agent."""
        chrome_versions = ["124.0.0.0", "123.0.0.0", "122.0.6261.112", "121.0.6167.185"]
        version = random.choice(chrome_versions)
        return (
            f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            f"AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{version} Safari/537.36"
        )

    @staticmethod
    def _random_delay(min_s: float, max_s: float):
        time.sleep(random.uniform(min_s, max_s))
