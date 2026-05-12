"""
AutoJob AI — CAPTCHA Solver
Supports auto-solving via 2Captcha or CapSolver APIs, with fallback to manual solve.

This module is platform-agnostic — it works with LinkedIn, Naukri, Indeed, etc.

Usage:
    solver = CaptchaSolver()
    solved = await solver.solve(page)  # Detects type, solves, and injects token
"""

import asyncio
import logging
import httpx

from playwright.async_api import Page

from app.config import settings

logger = logging.getLogger("autojob.captcha_solver")


# ── Known CAPTCHA selectors across platforms ─────────
CAPTCHA_SELECTORS = {
    "recaptcha_iframe": "iframe[src*='recaptcha'], iframe[src*='google.com/recaptcha']",
    "recaptcha_div": ".g-recaptcha, [data-sitekey]",
    "arkose_iframe": "iframe[src*='arkoselabs'], iframe[src*='funcaptcha']",
    "arkose_div": "#arkose-challenge, #FunCaptcha",
    "captcha_internal": "#captcha-internal, .captcha-container",
    "hcaptcha": "iframe[src*='hcaptcha'], .h-captcha",
}

# Text indicators that suggest a CAPTCHA or security challenge
CHALLENGE_TEXT_INDICATORS = [
    "security verification",
    "let's do a quick security check",
    "unusual activity",
    "verify you're not a robot",
    "complete the security check",
    "please verify",
    "we need to confirm",
]


class CaptchaSolver:
    """
    Auto-detect and solve CAPTCHAs using third-party APIs.

    Supported providers:
    - 2captcha (https://2captcha.com)
    - capsolver (https://capsolver.com)
    - manual (wait for user to solve in browser)
    """

    def __init__(self):
        self.provider = settings.captcha_provider.lower().strip()
        self.api_key = settings.captcha_api_key
        self.timeout = settings.captcha_timeout

        if self.provider and not self.api_key:
            logger.warning(f"CAPTCHA provider '{self.provider}' configured but no API key set!")
            self.provider = ""

        if self.provider:
            logger.info(f"CAPTCHA solver initialized: provider={self.provider}")
        else:
            logger.info("CAPTCHA solver: manual mode (no auto-solver configured)")

    # ── Main Entry Point ─────────────────────────────

    async def detect_and_solve(self, page: Page) -> bool:
        """
        Detect if a CAPTCHA is present, attempt to solve it.

        Returns:
            True if CAPTCHA was solved or no CAPTCHA found.
            False if CAPTCHA couldn't be solved.
        """
        captcha_type = await self.detect_captcha_type(page)

        if not captcha_type:
            return True  # No CAPTCHA detected

        logger.info(f"🔒 CAPTCHA detected: {captcha_type}")

        # Try automatic solving first
        if self.provider:
            solved = await self._auto_solve(page, captcha_type)
            if solved:
                logger.info(f"✅ CAPTCHA auto-solved via {self.provider}")
                return True
            logger.warning(f"Auto-solve failed for {captcha_type} — falling back to manual")

        # Fallback: manual solve
        return await self._manual_solve(page)

    # ── Detection ────────────────────────────────────

    async def detect_captcha_type(self, page: Page) -> str | None:
        """
        Detect the type of CAPTCHA present on the page.
        Returns: "recaptcha", "arkose", "hcaptcha", "generic", or None
        """
        try:
            # Check reCAPTCHA
            for sel_key in ("recaptcha_iframe", "recaptcha_div"):
                if await page.locator(CAPTCHA_SELECTORS[sel_key]).count() > 0:
                    return "recaptcha"

            # Check Arkose/FunCaptcha (used by LinkedIn)
            for sel_key in ("arkose_iframe", "arkose_div"):
                if await page.locator(CAPTCHA_SELECTORS[sel_key]).count() > 0:
                    return "arkose"

            # Check hCaptcha
            if await page.locator(CAPTCHA_SELECTORS["hcaptcha"]).count() > 0:
                return "hcaptcha"

            # Check generic/internal CAPTCHA
            if await page.locator(CAPTCHA_SELECTORS["captcha_internal"]).count() > 0:
                return "generic"

            # Check page text for challenge indicators
            body_text = (await page.inner_text("body")).lower()
            if any(phrase in body_text for phrase in CHALLENGE_TEXT_INDICATORS):
                return "generic"

        except Exception as e:
            logger.debug(f"CAPTCHA detection error: {e}")

        return None

    # ── Auto Solve ───────────────────────────────────

    async def _auto_solve(self, page: Page, captcha_type: str) -> bool:
        """Attempt to auto-solve using the configured API provider."""
        try:
            if captcha_type == "recaptcha":
                return await self._solve_recaptcha(page)
            elif captcha_type == "arkose":
                return await self._solve_arkose(page)
            elif captcha_type == "hcaptcha":
                return await self._solve_hcaptcha(page)
            else:
                logger.info(f"No auto-solver available for CAPTCHA type: {captcha_type}")
                return False
        except Exception as e:
            logger.error(f"Auto-solve error: {e}")
            return False

    async def _solve_recaptcha(self, page: Page) -> bool:
        """Solve reCAPTCHA v2 via API."""
        # Extract sitekey from the page
        sitekey = await self._extract_sitekey(page, "recaptcha")
        if not sitekey:
            logger.warning("Could not find reCAPTCHA sitekey")
            return False

        page_url = page.url
        logger.info(f"Solving reCAPTCHA (sitekey={sitekey[:10]}...)")

        token = await self._request_solve(
            task_type="RecaptchaV2TaskProxyless",
            website_url=page_url,
            website_key=sitekey,
        )

        if not token:
            return False

        # Inject the token
        await page.evaluate(f"""
            document.getElementById('g-recaptcha-response').value = '{token}';
            if (typeof ___grecaptcha_cfg !== 'undefined') {{
                Object.entries(___grecaptcha_cfg.clients).forEach(([k, v]) => {{
                    if (v && v.callback) v.callback('{token}');
                }});
            }}
        """)

        await asyncio.sleep(2)
        return True

    async def _solve_arkose(self, page: Page) -> bool:
        """Solve Arkose/FunCaptcha (LinkedIn's preferred CAPTCHA)."""
        # Extract public key from iframe src
        public_key = await self._extract_arkose_key(page)
        if not public_key:
            logger.warning("Could not find Arkose public key")
            return False

        page_url = page.url
        logger.info(f"Solving Arkose FunCaptcha (key={public_key[:10]}...)")

        token = await self._request_solve(
            task_type="FunCaptchaTaskProxyless",
            website_url=page_url,
            website_key=public_key,
        )

        if not token:
            return False

        # Inject token into Arkose callback
        await page.evaluate(f"""
            if (window.ArkoseEnforcement) {{
                window.ArkoseEnforcement.setConfig({{ data: {{ token: '{token}' }} }});
            }}
        """)

        await asyncio.sleep(2)
        return True

    async def _solve_hcaptcha(self, page: Page) -> bool:
        """Solve hCaptcha via API."""
        sitekey = await self._extract_sitekey(page, "hcaptcha")
        if not sitekey:
            return False

        token = await self._request_solve(
            task_type="HCaptchaTaskProxyless",
            website_url=page.url,
            website_key=sitekey,
        )

        if not token:
            return False

        await page.evaluate(f"""
            document.querySelector('[name="h-captcha-response"]').value = '{token}';
            document.querySelector('[name="g-recaptcha-response"]').value = '{token}';
        """)

        await asyncio.sleep(2)
        return True

    # ── API Communication ────────────────────────────

    async def _request_solve(
        self,
        task_type: str,
        website_url: str,
        website_key: str,
    ) -> str | None:
        """
        Send a solve request to the CAPTCHA API and poll for result.
        Returns the solution token, or None on failure.
        """
        if self.provider == "2captcha":
            return await self._solve_via_2captcha(task_type, website_url, website_key)
        elif self.provider == "capsolver":
            return await self._solve_via_capsolver(task_type, website_url, website_key)
        return None

    async def _solve_via_2captcha(self, task_type: str, url: str, key: str) -> str | None:
        """2Captcha API integration."""
        # Map task types to 2captcha method names
        method_map = {
            "RecaptchaV2TaskProxyless": "userrecaptcha",
            "FunCaptchaTaskProxyless": "funcaptcha",
            "HCaptchaTaskProxyless": "hcaptcha",
        }
        method = method_map.get(task_type)
        if not method:
            return None

        async with httpx.AsyncClient(timeout=30) as client:
            # Submit task
            submit_params = {
                "key": self.api_key,
                "method": method,
                "pageurl": url,
                "json": 1,
            }
            if method == "userrecaptcha":
                submit_params["googlekey"] = key
            elif method == "funcaptcha":
                submit_params["publickey"] = key
            elif method == "hcaptcha":
                submit_params["sitekey"] = key

            resp = await client.get("https://2captcha.com/in.php", params=submit_params)
            data = resp.json()

            if data.get("status") != 1:
                logger.error(f"2Captcha submit error: {data}")
                return None

            task_id = data.get("request")
            logger.info(f"2Captcha task submitted: {task_id}")

            # Poll for result
            for _ in range(self.timeout // 5):
                await asyncio.sleep(5)
                result_resp = await client.get(
                    "https://2captcha.com/res.php",
                    params={"key": self.api_key, "action": "get", "id": task_id, "json": 1},
                )
                result = result_resp.json()

                if result.get("status") == 1:
                    return result.get("request")
                elif result.get("request") != "CAPCHA_NOT_READY":
                    logger.error(f"2Captcha solve error: {result}")
                    return None

        logger.warning("2Captcha solve timed out")
        return None

    async def _solve_via_capsolver(self, task_type: str, url: str, key: str) -> str | None:
        """CapSolver API integration."""
        async with httpx.AsyncClient(timeout=30) as client:
            # Create task
            payload = {
                "clientKey": self.api_key,
                "task": {
                    "type": task_type,
                    "websiteURL": url,
                    "websiteKey": key,
                },
            }

            resp = await client.post("https://api.capsolver.com/createTask", json=payload)
            data = resp.json()

            if data.get("errorId", 0) != 0:
                logger.error(f"CapSolver error: {data.get('errorDescription')}")
                return None

            task_id = data.get("taskId")
            logger.info(f"CapSolver task submitted: {task_id}")

            # Poll for result
            for _ in range(self.timeout // 5):
                await asyncio.sleep(5)
                result_resp = await client.post(
                    "https://api.capsolver.com/getTaskResult",
                    json={"clientKey": self.api_key, "taskId": task_id},
                )
                result = result_resp.json()

                status = result.get("status")
                if status == "ready":
                    solution = result.get("solution", {})
                    return solution.get("gRecaptchaResponse") or solution.get("token")
                elif status == "failed":
                    logger.error(f"CapSolver solve failed: {result}")
                    return None

        logger.warning("CapSolver solve timed out")
        return None

    # ── Helpers ───────────────────────────────────────

    async def _extract_sitekey(self, page: Page, captcha_type: str) -> str | None:
        """Extract the sitekey from the page for reCAPTCHA or hCaptcha."""
        try:
            if captcha_type == "recaptcha":
                sitekey = await page.evaluate("""
                    (() => {
                        const el = document.querySelector('[data-sitekey]');
                        return el ? el.getAttribute('data-sitekey') : null;
                    })()
                """)
                if sitekey:
                    return sitekey

                # Try iframe src
                iframe = page.locator("iframe[src*='recaptcha']").first
                src = await iframe.get_attribute("src") if await iframe.count() > 0 else None
                if src and "k=" in src:
                    return src.split("k=")[1].split("&")[0]

            elif captcha_type == "hcaptcha":
                sitekey = await page.evaluate("""
                    (() => {
                        const el = document.querySelector('[data-sitekey]') || document.querySelector('.h-captcha');
                        return el ? el.getAttribute('data-sitekey') : null;
                    })()
                """)
                return sitekey

        except Exception as e:
            logger.debug(f"Sitekey extraction error: {e}")

        return None

    async def _extract_arkose_key(self, page: Page) -> str | None:
        """Extract the Arkose/FunCaptcha public key from the page."""
        try:
            # Check iframe src for key
            iframe = page.locator("iframe[src*='arkoselabs'], iframe[src*='funcaptcha']").first
            if await iframe.count() > 0:
                src = await iframe.get_attribute("src")
                if src and "pk=" in src:
                    return src.split("pk=")[1].split("&")[0]
                if src and "public_key=" in src:
                    return src.split("public_key=")[1].split("&")[0]

            # Check for data attribute
            key = await page.evaluate("""
                (() => {
                    const el = document.querySelector('[data-public-key]');
                    return el ? el.getAttribute('data-public-key') : null;
                })()
            """)
            return key

        except Exception as e:
            logger.debug(f"Arkose key extraction error: {e}")

        return None

    # ── Manual Solve Fallback ────────────────────────

    async def _manual_solve(self, page: Page) -> bool:
        """
        Wait for the user to manually solve the CAPTCHA in the browser window.
        """
        logger.warning(f"⚠️ CAPTCHA detected — waiting up to {self.timeout}s for manual solve...")
        logger.warning("👉 Please solve the CAPTCHA in the browser window!")

        check_interval = 5
        for i in range(self.timeout // check_interval):
            await asyncio.sleep(check_interval)
            remaining = self.timeout - (i + 1) * check_interval

            # Check if we've moved past the challenge
            captcha_type = await self.detect_captcha_type(page)
            if not captcha_type:
                logger.info("✅ CAPTCHA solved (challenge cleared)!")
                return True

            # Check if redirected to a logged-in page
            url = page.url
            if "/feed" in url or "/mynetwork" in url or "/jobs" in url:
                logger.info("✅ CAPTCHA solved (redirected past challenge)!")
                return True

            if remaining > 0 and remaining % 30 == 0:
                logger.info(f"  ⏳ Waiting for CAPTCHA solve... {remaining}s remaining")

        logger.error(f"❌ CAPTCHA not solved within {self.timeout}s")
        return False


# ── Singleton Instance ──────────────────────────────
captcha_solver = CaptchaSolver()
