"""
AutoJob AI — LinkedIn Platform Adapter
Implements job search and login automation for LinkedIn using Playwright.

WARNING: LinkedIn actively detects automation. This adapter includes:
- Human-like typing, delays, scrolling
- Session cookie persistence (avoid repeated logins)
- Rate limiting (max actions per session)
- Error detection for CAPTCHAs and account restrictions
"""

import asyncio
import json
import logging
import random
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from app.automation.adapters.base import JobListing, JobPlatformAdapter
from app.automation.browser_manager import BrowserManager
from app.automation.stealth import get_random_delay, get_typing_delay
from app.automation.captcha_solver import captcha_solver

logger = logging.getLogger("autojob.linkedin")

# ── Constants ────────────────────────────────────────
LINKEDIN_LOGIN_URL = "https://www.linkedin.com/login"
LINKEDIN_FEED_URL = "https://www.linkedin.com/feed/"
LINKEDIN_JOBS_URL = "https://www.linkedin.com/jobs/search/"

# Rate limits (per session)
MAX_SEARCHES_PER_SESSION = 10
MAX_PAGES_PER_SEARCH = 3

# LinkedIn geoId codes for country-level filtering
# Extensible: add more countries as needed (other platforms can have their own mappings)
COUNTRY_GEO_IDS = {
    "India": "102713980",
    "USA": "103644278",
    "United States": "103644278",
    "UK": "101165590",
    "United Kingdom": "101165590",
    "Canada": "101174742",
    "Germany": "101282230",
    "Australia": "101452733",
    "Singapore": "102454443",
    "UAE": "104305776",
    "Remote": "",
    "Worldwide": "",
}

# Session storage
SESSIONS_DIR = Path(__file__).parent.parent.parent.parent / "sessions"
SESSIONS_DIR.mkdir(exist_ok=True)


class LinkedInAdapter(JobPlatformAdapter):
    """
    LinkedIn job platform adapter.
    Handles login, session management, and job search scraping.
    """

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.browser_manager = BrowserManager(headless=headless)
        self._page: Page | None = None
        self._is_logged_in = False
        self._search_count = 0  # Rate limiting tracker

    # ══════════════════════════════════════════════════
    # LOGIN
    # ══════════════════════════════════════════════════

    async def login(self, credentials: dict) -> bool:
        """
        Log into LinkedIn with human-like behavior.

        Args:
            credentials: {"email": "...", "password": "..."}

        Returns:
            True if login successful, False otherwise.

        Raises:
            LoginError on CAPTCHA or account restriction detection.
        """
        email = credentials.get("email", "")
        password = credentials.get("password", "")

        if not email or not password:
            logger.error("LinkedIn credentials missing (email or password empty)")
            return False

        logger.info(f"Attempting LinkedIn login for: {email[:3]}***")

        # Start browser if not already running
        if not self._page:
            await self.browser_manager.start()
            self._page = await self.browser_manager.new_page()

        # Try loading saved session first
        session_loaded = await self.load_session(email)
        if session_loaded:
            # Verify session is still valid
            if await self._verify_login():
                logger.info("✅ Session restored — already logged in")
                self._is_logged_in = True
                return True
            else:
                logger.info("Saved session expired — logging in fresh")

        # Navigate to login page
        try:
            await self._page.goto(LINKEDIN_LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
            await self.browser_manager.human_delay(2, 4)

            # Check if already logged in (redirected to feed)
            if "/feed" in self._page.url:
                logger.info("✅ Already logged in (redirected to feed)")
                self._is_logged_in = True
                await self.save_session(email)
                return True

            # ── Detect CAPTCHA before login ──
            if await self._detect_captcha():
                logger.warning("⚠️ CAPTCHA detected on login page — attempting to solve...")
                captcha_solved = await captcha_solver.detect_and_solve(self._page)
                if not captcha_solved:
                    logger.error("❌ CAPTCHA on login page could not be solved")
                    self.browser_manager.report_proxy_failure()
                    return False

                # Wait for page to stabilize after CAPTCHA solve
                await self.browser_manager.human_delay(3, 5)
                await self._page.wait_for_load_state("domcontentloaded", timeout=10000)

                # Check if CAPTCHA solve already logged us in (redirect to feed)
                current_url = self._page.url
                if "/feed" in current_url or "/mynetwork" in current_url:
                    logger.info("✅ Already logged in after CAPTCHA solve (redirected to feed)")
                    self._is_logged_in = True
                    await self.save_session(email)
                    return True

                # If redirected away from login page but not to feed, go back to login
                if "/login" not in current_url and "/checkpoint" not in current_url:
                    logger.info(f"Redirected to {current_url} after CAPTCHA — navigating back to login")
                    await self._page.goto(LINKEDIN_LOGIN_URL, wait_until="domcontentloaded", timeout=15000)
                    await self.browser_manager.human_delay(2, 3)

            # ── Check for "Sign in as [Name]" / "Welcome Back" profile card ──
            # LinkedIn remembers the user and shows a profile card instead of login form.
            # Screenshot 1: linkedin.com/login → "Welcome Back" with profile card
            # Screenshot 2: linkedin.com → "Sign in as Tabrez" card
            sign_in_as_card = self._page.locator(
                # "Welcome Back" page profile card (linkedin.com/login)
                "div.login__form_action_container button, "
                "div[data-tracking-control-name='login_remember_me_submit'] button, "
                # Profile card with name (clickable row)
                "div.profile-card, "
                "button.profile-card, "
                # "Sign in as [Name]" on homepage (linkedin.com)
                "a[data-tracking-control-name*='sign_in_as'], "
                "div[data-tracking-control-name*='login_remember_me'], "
                # Generic profile row that acts as login button
                "li.profile-card button, "
                "li.profile-card a"
            )

            try:
                if await sign_in_as_card.count() > 0 and await sign_in_as_card.first.is_visible():
                    logger.info("  'Sign in as' profile card found — clicking to login...")
                    await sign_in_as_card.first.click()
                    await self.browser_manager.human_delay(3, 5)

                    # Check if we're logged in now
                    if "/feed" in self._page.url or "/mynetwork" in self._page.url:
                        logger.info("✅ Logged in via 'Sign in as' profile card!")
                        self._is_logged_in = True
                        await self.save_session(email)
                        return True
            except Exception:
                pass

            # Also try clicking the profile name/email text directly
            # (the entire row with "Tabrez Rabbani" / "t****@gmail.com" is clickable)
            try:
                profile_row = self._page.locator(
                    "div:has(> img[alt*='profile']):has-text('" + email.split('@')[0][:4] + "'), "
                    "div.remember-me-card, "
                    "a:has-text('Sign in as')"
                )
                if await profile_row.count() > 0 and await profile_row.first.is_visible():
                    logger.info("  Profile row found — clicking to login...")
                    await profile_row.first.click()
                    await self.browser_manager.human_delay(3, 5)

                    if "/feed" in self._page.url or "/mynetwork" in self._page.url:
                        logger.info("✅ Logged in via profile row click!")
                        self._is_logged_in = True
                        await self.save_session(email)
                        return True
            except Exception:
                pass

            # Last attempt: use JavaScript to find and click any element with the user's name
            try:
                email_prefix = email.split('@')[0][:5].lower()
                clicked = await self._page.evaluate(f"""
                    () => {{
                        // Find any clickable element containing the email or name
                        const allEls = document.querySelectorAll('a, button, div[role="button"], li');
                        for (const el of allEls) {{
                            const text = (el.textContent || '').toLowerCase();
                            if (text.includes('{email_prefix}') || text.includes('sign in as')) {{
                                // Check if it looks like a profile card (not a tiny link)
                                const rect = el.getBoundingClientRect();
                                if (rect.height > 30 && rect.width > 100) {{
                                    el.click();
                                    return true;
                                }}
                            }}
                        }}
                        return false;
                    }}
                """)
                if clicked:
                    logger.info("  Clicked profile card via JavaScript")
                    await self.browser_manager.human_delay(3, 5)
                    if "/feed" in self._page.url or "/mynetwork" in self._page.url:
                        logger.info("✅ Logged in via JS profile card click!")
                        self._is_logged_in = True
                        await self.save_session(email)
                        return True
            except Exception:
                pass

            # ── Fill email (standard login form path) ──
            logger.info("Waiting for login form...")
            
            # Multiple selectors for the email field (handles CSS-less pages too)
            email_selector = "#username, input[name='session_key'], input[autocomplete='username']"
            email_input = self._page.locator(email_selector)
            
            # Try up to 3 times to find the login form
            login_form_found = False
            for attempt in range(3):
                try:
                    await email_input.first.wait_for(state="visible", timeout=10000)
                    login_form_found = True
                    break
                except Exception:
                    if attempt < 2:
                        logger.warning(f"Login form not found (attempt {attempt + 1}/3) — retrying...")
                        
                        # Check if we got redirected to feed (already logged in)
                        if "/feed" in self._page.url:
                            logger.info("✅ Already logged in (redirected to feed on retry)")
                            self._is_logged_in = True
                            await self.save_session(email)
                            return True
                        
                        # Refresh and wait longer
                        await self._page.goto(LINKEDIN_LOGIN_URL, wait_until="domcontentloaded", timeout=20000)
                        await self.browser_manager.human_delay(4, 7)
                        email_input = self._page.locator(email_selector)
            
            if not login_form_found:
                logger.error("❌ Login form not found after 3 attempts")
                return False
            
            logger.info("Typing email...")
            await email_input.click()
            await self.browser_manager.human_delay(0.5, 1.5)

            # Clear any existing text
            await email_input.fill("")
            await self.browser_manager.human_delay(0.3, 0.8)

            # Type email character by character (human-like)
            for char in email:
                await email_input.type(char, delay=get_typing_delay())

            await self.browser_manager.human_delay(1, 2)

            # ── Fill password ──
            logger.info("Typing password...")
            password_input = self._page.locator("#password")
            await password_input.click()
            await self.browser_manager.human_delay(0.5, 1)

            for char in password:
                await password_input.type(char, delay=get_typing_delay())

            await self.browser_manager.human_delay(1, 3)

            # ── Click Sign In ──
            logger.info("Clicking Sign In...")
            sign_in_btn = self._page.locator('button[type="submit"]')
            await sign_in_btn.click()

            # Wait for navigation
            await self._page.wait_for_load_state("domcontentloaded", timeout=15000)
            await self.browser_manager.human_delay(3, 5)

            # ── Check for login errors ──
            # CAPTCHA / security challenge — use the advanced solver
            if await self._detect_captcha():
                captcha_solved = await captcha_solver.detect_and_solve(self._page)
                if not captcha_solved:
                    logger.error("❌ CAPTCHA could not be solved")
                    self.browser_manager.report_proxy_failure()
                    return False

            # Account restriction
            if await self._detect_restriction():
                logger.error("❌ Account restriction detected")
                return False

            # 2FA / verification
            if await self._detect_2fa():
                logger.warning("⚠️ 2FA verification required — manual intervention needed")
                # Wait up to 60 seconds for user to complete 2FA manually
                for i in range(12):
                    await asyncio.sleep(5)
                    if "/feed" in self._page.url or "/mynetwork" in self._page.url:
                        logger.info("✅ 2FA completed — login successful")
                        break
                else:
                    logger.error("❌ 2FA timeout — login failed")
                    return False

            # Check if login was successful
            if await self._verify_login():
                logger.info("✅ LinkedIn login successful")
                self._is_logged_in = True
                self.browser_manager.report_proxy_success()
                await self.save_session(email)
                return True
            else:
                logger.error("❌ Login failed — could not verify logged-in state")
                return False

        except PlaywrightTimeout:
            logger.error("❌ Login timeout — page did not load in time")
            return False
        except Exception as e:
            logger.error(f"❌ Login error: {e}")
            return False

    # ══════════════════════════════════════════════════
    # JOB SEARCH
    # ══════════════════════════════════════════════════

    async def search_jobs(
        self,
        keywords: str,
        location: str | None = None,
        country: str | None = None,
        filters: dict | None = None,
        max_results: int = 25,
    ) -> list[JobListing]:
        """
        Search LinkedIn jobs and extract listings.

        Args:
            keywords: Job title or search terms (e.g. "Python Developer")
            location: Location filter (e.g. "Bangalore")
            filters: Additional filters (not implemented yet)
            max_results: Maximum number of jobs to return

        Returns:
            List of standardized JobListing objects.
        """
        if not self._is_logged_in:
            logger.error("Cannot search — not logged in")
            return []

        # Rate limiting
        if self._search_count >= MAX_SEARCHES_PER_SESSION:
            logger.warning(f"Rate limit reached ({MAX_SEARCHES_PER_SESSION} searches/session)")
            return []

        self._search_count += 1
        logger.info(f"🔍 Searching LinkedIn: '{keywords}' | Location: '{location or 'Any'}'")

        jobs: list[JobListing] = []

        try:
            # Build search URL
            search_url = self._build_search_url(keywords, location, country)
            
            # Navigate with retry (LinkedIn search pages are heavy)
            for attempt in range(2):
                try:
                    await self._page.goto(search_url, wait_until="domcontentloaded", timeout=45000)
                    await self.browser_manager.human_delay(3, 5)
                    
                    # Verify we're actually on a search page (not redirected)
                    current_url = self._page.url
                    if "/login" in current_url:
                        logger.warning("Redirected to login during search — re-verifying session...")
                        # Wait for possible auto-redirect back
                        await self.browser_manager.human_delay(5, 8)
                        current_url = self._page.url
                        if "/login" in current_url:
                            logger.error("Session lost during search")
                            return jobs
                    
                    break  # Navigation succeeded
                except PlaywrightTimeout:
                    if attempt == 0:
                        logger.warning(f"Search page slow to load — retrying...")
                        await self.browser_manager.human_delay(3, 5)
                        continue
                    else:
                        logger.error("Search timeout — page did not load after retry")
                        return jobs

            # Scroll and extract jobs across pages
            pages_scraped = 0
            while len(jobs) < max_results and pages_scraped < MAX_PAGES_PER_SEARCH:
                # Scroll through the page (human-like)
                await self._human_scroll()

                # Extract job cards from current page
                page_jobs = await self._extract_job_cards()
                jobs.extend(page_jobs)

                logger.info(f"  Page {pages_scraped + 1}: found {len(page_jobs)} jobs (total: {len(jobs)})")

                pages_scraped += 1

                # Try next page
                if len(jobs) < max_results:
                    has_next = await self._go_to_next_page()
                    if not has_next:
                        break
                    await self.browser_manager.human_delay(3, 6)

            # Trim to max_results
            jobs = jobs[:max_results]
            logger.info(f"✅ Search complete: {len(jobs)} jobs found")

        except PlaywrightTimeout:
            logger.error("Search timeout — page did not load")
        except Exception as e:
            logger.error(f"Search error: {e}")

        return jobs

    async def get_job_details(self, job_url: str) -> dict:
        """Get full details for a specific job page."""
        if not self._is_logged_in or not self._page:
            return {}

        try:
            await self._page.goto(job_url, wait_until="domcontentloaded")
            await self.browser_manager.human_delay(2, 4)

            # Extract job description
            description = ""
            desc_el = self._page.locator(".jobs-description__content, .jobs-box__html-content")
            if await desc_el.count() > 0:
                description = await desc_el.first.inner_text()

            # Extract additional details
            details = {
                "description": description.strip(),
                "url": job_url,
            }

            return details

        except Exception as e:
            logger.error(f"Error getting job details: {e}")
            return {}

    async def apply_to_job(
        self,
        job_url: str,
        resume_path: str,
        cover_letter: str | None = None,
        answers: dict | None = None,
    ) -> dict:
        """NOT IMPLEMENTED YET — Phase 3."""
        raise NotImplementedError("Job application is not implemented yet (Phase 3)")

    # ══════════════════════════════════════════════════
    # SESSION MANAGEMENT
    # ══════════════════════════════════════════════════

    async def save_session(self, filepath: str) -> None:
        """Save LinkedIn session cookies for reuse."""
        if not self.browser_manager._context:
            return

        safe_name = filepath.replace("@", "_at_").replace(".", "_")
        session_path = SESSIONS_DIR / f"linkedin_{safe_name}.json"

        storage = await self.browser_manager._context.storage_state()

        session_data = {
            "storage_state": storage,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }

        session_path.write_text(json.dumps(session_data, indent=2))
        logger.info(f"Session saved: {session_path.name}")

    async def load_session(self, filepath: str) -> bool:
        """Load a saved LinkedIn session."""
        safe_name = filepath.replace("@", "_at_").replace(".", "_")
        session_path = SESSIONS_DIR / f"linkedin_{safe_name}.json"

        if not session_path.exists():
            logger.info("No saved session found")
            return False

        try:
            session_data = json.loads(session_path.read_text())

            # Check if session is older than 24 hours
            saved_at = datetime.fromisoformat(session_data["saved_at"])
            age_hours = (datetime.now(timezone.utc) - saved_at).total_seconds() / 3600

            if age_hours > 24:
                logger.info(f"Session expired ({age_hours:.1f}h old) — will re-login")
                session_path.unlink()  # Delete expired session
                return False

            # Restore browser context with saved cookies
            storage_state = session_data["storage_state"]

            if self.browser_manager._context:
                await self.browser_manager._context.close()

            from app.automation.stealth import get_random_viewport, get_random_user_agent, STEALTH_SCRIPTS

            viewport = get_random_viewport()
            user_agent = get_random_user_agent()

            self.browser_manager._context = await self.browser_manager._browser.new_context(
                viewport=viewport,
                user_agent=user_agent,
                locale="en-US",
                timezone_id="Asia/Kolkata",
                storage_state=storage_state,
            )

            for script in STEALTH_SCRIPTS:
                await self.browser_manager._context.add_init_script(script)

            self._page = await self.browser_manager._context.new_page()

            logger.info(f"Session loaded ({age_hours:.1f}h old)")
            return True

        except Exception as e:
            logger.error(f"Failed to load session: {e}")
            return False

    async def close(self) -> None:
        """Clean up browser resources."""
        await self.browser_manager.close()
        self._page = None
        self._is_logged_in = False
        logger.info("LinkedIn adapter closed")

    # ══════════════════════════════════════════════════
    # PRIVATE HELPERS
    # ══════════════════════════════════════════════════

    def _build_search_url(self, keywords: str, location: str | None = None, country: str | None = None) -> str:
        """Build LinkedIn job search URL with parameters."""
        from urllib.parse import quote_plus

        url = f"{LINKEDIN_JOBS_URL}?keywords={quote_plus(keywords)}"

        if location:
            url += f"&location={quote_plus(location)}"

        # Country-level geoId filter
        if country:
            geo_id = COUNTRY_GEO_IDS.get(country, "")
            if geo_id:
                url += f"&geoId={geo_id}"

        # Default to past week
        url += "&f_TPR=r604800"

        # Only show Easy Apply jobs (bot can only apply to these)
        url += "&f_AL=true"

        return url

    async def _extract_job_cards(self) -> list[JobListing]:
        """Extract job listings from the current search results page."""
        jobs = []

        # LinkedIn job cards are in a scrollable list
        card_selectors = [
            ".jobs-search-results__list-item",
            ".job-card-container",
            "li.jobs-search-results-list__list-item",
        ]

        cards = None
        for selector in card_selectors:
            cards_el = self._page.locator(selector)
            count = await cards_el.count()
            if count > 0:
                cards = cards_el
                break

        if not cards:
            logger.warning("No job cards found on page")
            return jobs

        count = await cards.count()
        logger.info(f"  Found {count} job cards on page")

        for i in range(count):
            try:
                # ── Detect mid-scrape redirect (LinkedIn anti-bot) ──
                current_url = self._page.url
                needs_recovery = False
                
                if "/login" in current_url or "/checkpoint" in current_url:
                    needs_recovery = True
                elif "/jobs/search" not in current_url and "/jobs/collections" not in current_url and "/feed" not in current_url:
                    # Could be homepage redirect (https://www.linkedin.com/) for "Sign in as"
                    needs_recovery = True
                    
                if needs_recovery:
                    logger.warning(f"  ⚠️ LinkedIn redirected mid-scrape to {current_url} — checking for re-verification...")
                    
                    # Try to auto-confirm identity
                    reauth_success = await self._handle_sign_in_as_page()
                    
                    if reauth_success:
                        logger.info("  Recovered session during scrape — returning to search page")
                        try:
                            # Try going back to the search page
                            await self._page.go_back()
                            await self.browser_manager.human_delay(3, 5)
                            
                            # Verify we made it back to a jobs page
                            if "/jobs/search" in self._page.url or "/jobs/collections" in self._page.url:
                                logger.info("  Successfully returned to search results. Continuing scrape.")
                                # Need to wait for cards to render again
                                await self._page.wait_for_selector(".job-card-container", timeout=10000)
                                continue # Skip the rest of this loop iteration, but continue scraping next cards
                            else:
                                logger.warning("  Could not return to search results. Stopping card extraction.")
                                break
                        except Exception as e:
                            logger.warning(f"  Failed to return to search page: {e}")
                            break
                    else:
                        logger.warning("  Could not recover session. Stopping card extraction.")
                        break

                card = cards.nth(i)

                # Click on the card to load details in the right panel
                await card.scroll_into_view_if_needed()
                await self.browser_manager.human_delay(0.3, 0.8)
                await card.click()
                await self.browser_manager.human_delay(2, 4)  # Wait longer for right panel to load

                # Extract title
                title_el = card.locator(
                    ".job-card-list__title, "
                    ".job-card-container__link, "
                    "a.job-card-list__title--link"
                )
                title = ""
                if await title_el.count() > 0:
                    raw = (await title_el.first.inner_text()).strip()
                    # LinkedIn duplicates title in nested elements — take first line
                    lines = [l.strip() for l in raw.split("\n") if l.strip()]
                    title = lines[0] if lines else raw

                # Extract company
                company_el = card.locator(
                    ".job-card-container__primary-description, "
                    ".artdeco-entity-lockup__subtitle"
                )
                company = ""
                if await company_el.count() > 0:
                    raw = (await company_el.first.inner_text()).strip()
                    company = raw.split("\n")[0].strip()

                # Extract location
                location_el = card.locator(
                    ".job-card-container__metadata-item, "
                    ".artdeco-entity-lockup__caption"
                )
                location = ""
                if await location_el.count() > 0:
                    raw = (await location_el.first.inner_text()).strip()
                    location = raw.split("\n")[0].strip()

                # Extract job link
                link_el = card.locator("a[href*='/jobs/view/']")
                job_url = ""
                job_id = ""
                if await link_el.count() > 0:
                    href = await link_el.first.get_attribute("href")
                    if href:
                        # Extract job ID from URL
                        parts = href.split("/jobs/view/")
                        if len(parts) > 1:
                            job_id = parts[1].split("/")[0].split("?")[0]
                        # Clean URL — strip tracking params, keep only the job link
                        job_url = f"https://www.linkedin.com/jobs/view/{job_id}/" if job_id else ""

                # ── Extract description from the right detail panel ──
                description = None
                try:
                    desc_selectors = [
                        ".jobs-description__content",
                        ".jobs-box__html-content",
                        ".jobs-description-content__text",
                        "#job-details",
                        "div[class*='jobs-description']",
                    ]
                    
                    # Try extraction with retry (LinkedIn right panel loads lazily)
                    for attempt in range(2):
                        for desc_sel in desc_selectors:
                            desc_el = self._page.locator(desc_sel)
                            if await desc_el.count() > 0:
                                description = (await desc_el.first.inner_text()).strip()
                                if description and len(description) > 50:
                                    break
                        if description and len(description) > 50:
                            break
                        # Panel hasn't loaded yet — wait and retry
                        if attempt == 0:
                            await self.browser_manager.human_delay(2, 3)
                except Exception as desc_err:
                    logger.debug(f"  Could not extract description for card {i}: {desc_err}")

                # ── Extract salary if available ──
                salary_range = None
                try:
                    salary_selectors = [
                        ".job-details-jobs-unified-top-card__job-insight--highlight span",
                        "li.jobs-unified-top-card__job-insight span:has-text('₹')",
                        "li.jobs-unified-top-card__job-insight span:has-text('$')",
                        "span:has-text('/yr')",
                        "span:has-text('/month')",
                    ]
                    for sal_sel in salary_selectors:
                        sal_el = self._page.locator(sal_sel)
                        if await sal_el.count() > 0:
                            sal_text = (await sal_el.first.inner_text()).strip()
                            if sal_text and any(c in sal_text for c in ['₹', '$', '€', '/yr', '/month', 'per']):
                                salary_range = sal_text
                                break
                except Exception:
                    pass

                if title and (job_url or job_id):
                    jobs.append(
                        JobListing(
                            platform="linkedin",
                            platform_job_id=job_id or f"li_{i}",
                            title=title,
                            company=company,
                            location=location,
                            description=description,
                            salary_range=salary_range,
                            job_type=None,
                            apply_url=job_url,
                            posted_date=None,
                        )
                    )
                    if description:
                        logger.info(f"  ✅ Card {i}: '{title}' — description extracted ({len(description)} chars)")
                    else:
                        logger.info(f"  ⚠️ Card {i}: '{title}' — no description found in panel")

            except Exception as e:
                logger.warning(f"  Error extracting card {i}: {e}")
                continue

        return jobs

    async def _human_scroll(self) -> None:
        """Scroll the page in a human-like pattern."""
        if not self._page:
            return

        # Scroll 3-5 times with random distances
        scroll_count = random.randint(3, 5)
        for _ in range(scroll_count):
            scroll_distance = random.randint(200, 500)
            await self._page.evaluate(f"window.scrollBy(0, {scroll_distance})")
            await self.browser_manager.human_delay(0.5, 1.5)

    async def _go_to_next_page(self) -> bool:
        """Click the next page button. Returns False if no next page."""
        try:
            next_btn = self._page.locator(
                "button[aria-label='Next'], "
                "li.artdeco-pagination__indicator--number.active + li button"
            )
            if await next_btn.count() > 0 and await next_btn.first.is_enabled():
                await next_btn.first.click()
                await self._page.wait_for_load_state("domcontentloaded", timeout=10000)
                return True
        except Exception:
            pass
        return False

    async def _verify_login(self) -> bool:
        """Check if we're currently logged in to LinkedIn."""
        if not self._page:
            return False

        try:
            # Use longer timeout — LinkedIn is slow, especially with saved sessions
            await self._page.goto(LINKEDIN_FEED_URL, wait_until="domcontentloaded", timeout=20000)
            await self.browser_manager.human_delay(3, 5)

            # If we're on the feed page, we're logged in
            current_url = self._page.url
            if "/feed" in current_url or "/mynetwork" in current_url:
                return True

            # LinkedIn sometimes redirects to checkpoint but session is still valid
            if "/checkpoint" in current_url:
                # Wait a bit — checkpoint often auto-resolves
                await self.browser_manager.human_delay(3, 5)
                current_url = self._page.url
                if "/feed" in current_url or "/mynetwork" in current_url:
                    return True

            # Check for profile menu (another sign of being logged in)
            profile_el = self._page.locator(".global-nav__me, .feed-identity-module")
            try:
                if await profile_el.count() > 0:
                    return True
            except Exception:
                pass

            return False
        except Exception:
            return False

    async def _detect_captcha(self) -> bool:
        """Detect if a CAPTCHA challenge is shown."""
        if not self._page:
            return False

        captcha_indicators = [
            "#captcha-internal",
            ".captcha-container",
            "iframe[src*='captcha']",
            "iframe[src*='recaptcha']",
            "#arkose-challenge",
        ]

        for selector in captcha_indicators:
            try:
                if await self._page.locator(selector).count() > 0:
                    return True
            except Exception:
                continue

        # Check page text
        try:
            body_text = await self._page.inner_text("body")
            if any(phrase in body_text.lower() for phrase in [
                "security verification",
                "let's do a quick security check",
                "unusual activity",
            ]):
                return True
        except Exception:
            pass

        return False

    async def _detect_restriction(self) -> bool:
        """Detect if account is restricted."""
        if not self._page:
            return False

        try:
            body_text = await self._page.inner_text("body")
            restriction_phrases = [
                "your account has been restricted",
                "account temporarily restricted",
                "we've restricted your account",
            ]
            return any(phrase in body_text.lower() for phrase in restriction_phrases)
        except Exception:
            return False

    async def _detect_2fa(self) -> bool:
        """Detect if 2FA verification is required."""
        if not self._page:
            return False

        two_fa_indicators = [
            "input[name='pin']",
            "#input__phone_verification_pin",
            "#input__email_verification_pin",
            "#two-step-challenge",
        ]

        for selector in two_fa_indicators:
            try:
                if await self._page.locator(selector).count() > 0:
                    return True
            except Exception:
                continue

        try:
            body_text = await self._page.inner_text("body")
            if any(phrase in body_text.lower() for phrase in [
                "two-step verification",
                "enter the code",
                "verification code",
            ]):
                return True
        except Exception:
            pass

        return False

    # ══════════════════════════════════════════════════
    # AUTO APPLY (Easy Apply)
    # ══════════════════════════════════════════════════

    async def apply_to_job(
        self,
        job_url: str,
        resume_path: str,
        cover_letter: str | None = None,
        answers: dict | None = None,
        user_profile: dict | None = None,
        job_info: dict | None = None,
        dry_run: bool = False,
    ) -> dict:
        """
        Apply to a LinkedIn job via Easy Apply.

        Args:
            job_url: LinkedIn job URL
            resume_path: Path to resume file (PDF)
            cover_letter: AI-generated cover letter text (optional)
            answers: Pre-filled answers for basic fields like phone (optional)
            user_profile: User's full profile dict for AI screening (optional)
            job_info: Job details dict for AI screening context (optional)
            dry_run: If True, stops before final submit (for testing)

        Returns:
            {"status": "applied|external_apply|skipped|failed", "message": "..."}
        """
        if not self._page or not self._is_logged_in:
            return {"status": "failed", "message": "Not logged in"}

        logger.info(f"Opening job: {job_url}")

        try:
            # Navigate to job page
            await self._page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
            await self.browser_manager.human_delay(3, 5)

            # Check if session is still valid (LinkedIn may log us out mid-run)
            # Primary signal: URL redirect to login/authwall/checkpoint page
            current_url = self._page.url
            needs_reauth = False

            if "/login" in current_url or "/authwall" in current_url:
                needs_reauth = True
            elif "/checkpoint" in current_url:
                # LinkedIn "Sign in as [Name]" soft re-verification page
                # Auto-click the profile card to confirm identity
                logger.info("  LinkedIn checkpoint detected — attempting auto-confirm...")
                reauth_success = await self._handle_sign_in_as_page()
                if reauth_success:
                    # Re-navigate to job page after confirmation
                    await self._page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
                    await self.browser_manager.human_delay(3, 5)
                else:
                    needs_reauth = True
            else:
                # Check for "Sign in as" page that may appear without URL change
                # LinkedIn sometimes shows profile card on the same URL
                sign_in_as = self._page.locator(
                    "button[data-litms-control-urn*='login-submit'], "
                    "div.login-submit__form button, "
                    "button.profile-card__cta, "
                    "div[data-test-modal-id='join-now-modal'], "
                    "div.authwall-join-form, "
                    "form.login__form"
                )
                try:
                    if await sign_in_as.count() > 0 and await sign_in_as.first.is_visible():
                        logger.info("  'Sign in as' page detected — auto-clicking...")
                        await sign_in_as.first.click()
                        await self.browser_manager.human_delay(3, 5)
                        # Re-navigate to job
                        if "/jobs/view/" not in self._page.url:
                            await self._page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
                            await self.browser_manager.human_delay(3, 5)
                except Exception:
                    pass

            if needs_reauth:
                logger.warning("  Session expired — attempting recovery...")
                # Try going to feed first (may auto-login with cookies)
                await self._page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30000)
                await self.browser_manager.human_delay(3, 5)

                # Check if recovery worked
                if "/login" in self._page.url or "/authwall" in self._page.url:
                    # Try the checkpoint/sign-in-as handler
                    reauth_ok = await self._handle_sign_in_as_page()
                    if not reauth_ok:
                        logger.error("  Session fully expired — cannot re-login mid-run")
                        return {"status": "failed", "message": "Session expired, re-login needed"}

                # Re-navigate to job page
                await self._page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
                await self.browser_manager.human_delay(3, 5)

            # Check if Easy Apply button exists
            # Strategy: Use multiple detection methods because LinkedIn's DOM varies
            easy_apply_btn = None

            # Method 1: Standard Playwright selectors (buttons + links)
            standard_selectors = (
                "#jobs-apply-button-id, "
                "button.jobs-apply-button, "
                "button[aria-label*='Easy Apply'], "
                "button:has-text('Easy Apply'), "
                "a:has-text('Easy Apply'), "
                "div[role='button']:has-text('Easy Apply')"
            )
            locator = self._page.locator(standard_selectors)
            try:
                await locator.first.wait_for(state="visible", timeout=15000)
                easy_apply_btn = locator.first
                logger.info("  Easy Apply found via standard selectors")
            except Exception:
                logger.info("  Standard selectors failed — trying JavaScript...")

            # Method 2: JavaScript-based detection (finds ANY element with exact text)
            if not easy_apply_btn:
                await self.browser_manager.human_delay(3, 5)

                # Use JS to find the element containing "Easy Apply" text
                js_result = await self._page.evaluate("""
                    () => {
                        // Check all elements for "Easy Apply" text
                        const all = document.querySelectorAll('button, a, div[role="button"], span');
                        for (const el of all) {
                            const text = el.textContent.trim();
                            if (text === 'Easy Apply' || text.includes('Easy Apply')) {
                                // Return identifying info
                                return {
                                    tag: el.tagName,
                                    id: el.id || '',
                                    className: el.className || '',
                                    ariaLabel: el.getAttribute('aria-label') || '',
                                    found: true
                                };
                            }
                        }
                        return { found: false };
                    }
                """)

                if js_result.get("found"):
                    logger.info(f"  Easy Apply found via JS: tag={js_result['tag']} id='{js_result['id']}' class='{js_result['className'][:60]}'")

                    # Now click it via JavaScript (most reliable)
                    clicked = await self._page.evaluate("""
                        () => {
                            const all = document.querySelectorAll('button, a, div[role="button"], span');
                            for (const el of all) {
                                const text = el.textContent.trim();
                                if (text === 'Easy Apply' || text.includes('Easy Apply')) {
                                    el.click();
                                    return true;
                                }
                            }
                            return false;
                        }
                    """)

                    if clicked:
                        logger.info("  Easy Apply clicked via JavaScript!")
                        await self.browser_manager.human_delay(2, 3)

                        # Handle the Easy Apply modal
                        result = await self._handle_easy_apply_modal(
                            resume_path=resume_path,
                            cover_letter=cover_letter,
                            answers=answers,
                            user_profile=user_profile,
                            job_info=job_info,
                            dry_run=dry_run,
                        )
                        return result

                # If JS also didn't find it — comprehensive debug
                if not easy_apply_btn:
                    # ── COMPREHENSIVE DEBUG ──
                    page_url = self._page.url
                    page_title = await self._page.title()
                    logger.warning(f"  DEBUG: Page URL = {page_url}")
                    logger.warning(f"  DEBUG: Page Title = '{page_title}'")

                    # Take screenshot to see what bot actually sees
                    try:
                        screenshot_path = f"debug_job_page_{page_url.split('/')[-2]}.png"
                        await self._page.screenshot(path=screenshot_path)
                        logger.warning(f"  DEBUG: Screenshot saved → {screenshot_path}")
                    except Exception:
                        pass

                    # Search ALL elements for "Easy Apply" or "Apply"
                    any_apply = self._page.locator("*:has-text('Easy Apply')")
                    any_apply_count = await any_apply.count()
                    logger.warning(f"  DEBUG: Elements with 'Easy Apply' text: {any_apply_count}")

                    apply_links = self._page.locator("a:has-text('Apply'), a:has-text('Easy Apply')")
                    link_count = await apply_links.count()
                    logger.warning(f"  DEBUG: <a> links with 'Apply' text: {link_count}")
                    for li in range(min(link_count, 5)):
                        try:
                            link_text = (await apply_links.nth(li).inner_text()).strip()[:60]
                            link_href = await apply_links.nth(li).get_attribute("href") or ""
                            logger.warning(f"    Link {li}: text='{link_text}' href='{link_href[:60]}'")
                        except Exception:
                            pass

                    all_buttons = self._page.locator("button")
                    btn_count = await all_buttons.count()
                    logger.warning(f"  DEBUG: Found {btn_count} total buttons on page")
                    for bi in range(min(btn_count, 10)):
                        try:
                            btn_text = (await all_buttons.nth(bi).inner_text()).strip()[:60]
                            btn_aria = await all_buttons.nth(bi).get_attribute("aria-label") or ""
                            logger.warning(f"    Button {bi}: text='{btn_text}' aria='{btn_aria[:40]}'")
                        except Exception:
                            pass
                    logger.info("  No Easy Apply button — marking as external_apply")
                    return {"status": "external_apply", "message": "No Easy Apply button found"}

            # Click Easy Apply (standard path)
            logger.info("  Easy Apply button found — clicking...")
            await easy_apply_btn.click()
            await self.browser_manager.human_delay(2, 3)

            # Handle the Easy Apply modal
            result = await self._handle_easy_apply_modal(
                resume_path=resume_path,
                cover_letter=cover_letter,
                answers=answers,
                user_profile=user_profile,
                job_info=job_info,
                dry_run=dry_run,
            )
            return result

        except PlaywrightTimeout:
            logger.error("  Timeout during application")
            return {"status": "failed", "message": "Page load timeout"}
        except Exception as e:
            logger.error(f"  Application error: {e}")
            return {"status": "failed", "message": str(e)}

    async def _handle_easy_apply_modal(
        self,
        resume_path: str,
        cover_letter: str | None = None,
        answers: dict | None = None,
        user_profile: dict | None = None,
        job_info: dict | None = None,
        dry_run: bool = False,
    ) -> dict:
        """Handle the Easy Apply modal form (multi-step)."""
        max_steps = 12
        step = 0
        previous_questions_hash = ""  # Track if form is stuck on same step
        stuck_count = 0

        while step < max_steps:
            step += 1
            logger.info(f"  Step {step}/{max_steps}")
            await self.browser_manager.human_delay(1, 2)

            # Check for the modal — wait for it to appear (LinkedIn can be slow)
            modal = self._page.locator(
                "div.jobs-easy-apply-modal, "
                "div[role='dialog'][aria-label*='Easy Apply'], "
                "div.artdeco-modal"
            )

            # On first step, give more time for modal to load
            modal_found = False
            max_wait_attempts = 5 if step == 1 else 2
            for wait_attempt in range(max_wait_attempts):
                if await modal.count() > 0:
                    # Double-check it's actually visible
                    try:
                        if await modal.first.is_visible():
                            modal_found = True
                            break
                    except Exception:
                        pass
                await self.browser_manager.human_delay(0.8, 1.5)

            if not modal_found:
                logger.warning(f"  Easy Apply modal not found after {max_wait_attempts} attempts")
                return {"status": "failed", "message": "Modal not found"}

            # ── Stuck-loop detection ──
            # Get current form content to detect if we're on the same step
            try:
                current_questions = await self._page.evaluate("""
                    () => {
                        const labels = document.querySelectorAll(
                            '.artdeco-modal label, .artdeco-modal .fb-dash-form-element__label, ' +
                            '.artdeco-modal legend, .artdeco-modal .t-14.t-bold'
                        );
                        return Array.from(labels)
                            .map(l => l.textContent.trim().substring(0, 40))
                            .filter(t => t.length > 0)
                            .join('|');
                    }
                """)
                current_hash = str(hash(current_questions))

                if current_hash == previous_questions_hash and current_hash != str(hash("")):
                    stuck_count += 1
                    logger.warning(f"  ⚠️ Form stuck on same step (attempt {stuck_count}/2)")
                    if stuck_count >= 2:
                        logger.warning("  Form stuck — required fields may be unfilled. Skipping.")
                        await self._close_easy_apply_modal()
                        return {"status": "skipped", "message": "Form stuck on validation errors"}
                else:
                    stuck_count = 0
                    previous_questions_hash = current_hash
            except Exception:
                pass  # If JS fails, continue normally

            # Try to upload resume if file input exists
            await self._try_upload_resume(resume_path)

            # Try to fill cover letter if AI generated one
            if cover_letter:
                await self._fill_cover_letter(cover_letter)

            # Fill screening questions with AI
            if user_profile:
                await self._fill_screening_questions_with_ai(
                    user_profile=user_profile,
                    job_info=job_info or {},
                    basic_answers=answers or {},
                )
            else:
                # Fallback: use basic field filling
                await self._fill_basic_fields(answers)

            # Handle "Save" button inside repeatable groupings (e.g. Work Experience card)
            await self._click_save_if_present()

            # Check for Submit button (final step)
            submit_btn = self._page.locator(
                "button[data-live-test-easy-apply-submit-button], "
                "button[aria-label='Submit application'], "
                "button:has-text('Submit application')"
            )

            if await submit_btn.count() > 0:
                if dry_run:
                    logger.info("  🏁 DRY RUN — would click Submit here. Stopping.")
                    await self._close_easy_apply_modal()
                    return {"status": "applied", "message": "Dry run — submit skipped"}

                logger.info("  Clicking Submit...")
                await submit_btn.first.click()
                await self.browser_manager.human_delay(2, 4)

                confirmation = await self._check_application_confirmation()
                if confirmation:
                    logger.info("  ✅ Application submitted successfully!")
                    return {"status": "applied", "message": "Application submitted"}
                else:
                    logger.warning("  Submit clicked but no confirmation detected")
                    return {"status": "applied", "message": "Submitted (no confirmation seen)"}

            # Check for Next button (multi-step form)
            next_btn = self._page.locator(
                "button[data-easy-apply-next-button], "
                "button[aria-label='Continue to next step'], "
                "button:has-text('Next'), "
                "button:has-text('Continue')"
            )

            if await next_btn.count() > 0:
                logger.info(f"  Clicking Next (step {step})...")
                await next_btn.first.click()
                await self.browser_manager.human_delay(1.5, 3)
                continue

            # Check for Review button
            review_btn = self._page.locator(
                "button[aria-label='Review your application'], "
                "button:has-text('Review')"
            )

            if await review_btn.count() > 0:
                logger.info("  Clicking Review...")
                await review_btn.first.click()
                await self.browser_manager.human_delay(1.5, 3)
                continue

            # No recognizable button — complex form, skip
            logger.warning("  Complex form detected (no Next/Submit/Review) — skipping")
            await self._close_easy_apply_modal()
            return {"status": "skipped", "message": "Complex form — no recognizable buttons"}

        # Exceeded max steps — too complex
        logger.warning(f"  Form has more than {max_steps} steps — skipping")
        await self._close_easy_apply_modal()
        return {"status": "skipped", "message": f"Form exceeded {max_steps} steps"}

    async def _try_upload_resume(self, resume_path: str) -> None:
        """Upload resume only if no resume is already selected on LinkedIn."""
        try:
            # Check if a resume is already selected (LinkedIn shows radio buttons)
            selected_resume = self._page.locator(
                "input[type='radio']:checked, "
                "div[data-test-document-row] input:checked, "
                "label[data-test-document-row].artdeco-radio--is-checked"
            )
            if await selected_resume.count() > 0:
                logger.info("  Resume already selected on LinkedIn — skipping upload")
                return

            # No resume selected — upload user's resume
            file_input = self._page.locator("input[type='file']")
            if await file_input.count() > 0:
                from pathlib import Path
                if Path(resume_path).exists():
                    await file_input.first.set_input_files(resume_path)
                    logger.info(f"  ✅ Resume uploaded: {Path(resume_path).name}")
                    await self.browser_manager.human_delay(2, 3)
                else:
                    logger.warning(f"  Resume file not found: {resume_path}")
            else:
                logger.warning("  No file input found and no resume selected — may cause issues")
        except Exception as e:
            logger.warning(f"  Resume upload attempt: {e}")

    async def _fill_cover_letter(self, cover_letter: str) -> None:
        """Detect and fill cover letter text area in the Easy Apply modal."""
        try:
            cl_selectors = [
                "textarea[name*='cover']",
                "textarea[aria-label*='cover letter']",
                "textarea[aria-label*='Cover Letter']",
                "textarea[id*='cover']",
                "div.jobs-easy-apply-modal textarea",
            ]

            for selector in cl_selectors:
                field = self._page.locator(selector)
                if await field.count() > 0:
                    current_val = await field.first.input_value()
                    if not current_val:  # Only fill if empty
                        await field.first.fill(cover_letter)
                        logger.info(f"  ✅ Cover letter filled ({len(cover_letter)} chars)")
                        await self.browser_manager.human_delay(0.5, 1)
                        return

            logger.debug("  No cover letter field found in this step")
        except Exception as e:
            logger.warning(f"  Cover letter fill attempt: {e}")

    async def _fill_screening_questions_with_ai(
        self,
        user_profile: dict,
        job_info: dict,
        basic_answers: dict,
    ) -> None:
        """
        Scrape all screening questions from the current modal step,
        send them to the AI agent, and fill the answers.
        """
        # First fill basic fields (phone etc.) from pre-set answers
        await self._fill_basic_fields(basic_answers)

        # Scrape questions from the current form step
        questions = await self._scrape_screening_questions()

        if not questions:
            logger.debug("  No screening questions found in this step")
            return

        logger.info(f"  Found {len(questions)} screening questions — asking AI...")

        # Call AI agent to get answers
        try:
            from app.agents.screening_answerer import answer_screening_questions
            ai_answers = await answer_screening_questions(
                user_profile=user_profile,
                job_info=job_info,
                questions=questions,
            )
        except Exception as e:
            logger.error(f"  AI screening answerer failed: {e}")
            return

        if not ai_answers:
            logger.warning("  AI returned no answers")
            return

        # Fill the answers into the form
        await self._apply_ai_answers(questions, ai_answers)

    async def _scrape_screening_questions(self) -> list[dict]:
        """Scrape question labels, types, and options from the current form step."""
        questions = []

        try:
            form_groups = self._page.locator(
                "div.jobs-easy-apply-form-section__grouping, "
                "div.fb-dash-form-element, "
                "fieldset, "
                "div[data-test-form-element]"
            )

            count = await form_groups.count()
            for i in range(count):
                group = form_groups.nth(i)

                # Skip hidden/invisible groups (e.g. video player caption settings)
                try:
                    if not await group.is_visible():
                        continue
                except Exception:
                    continue

                # Get the label/question text
                # Priority: legend > fb-dash label > artdeco label > generic label
                label = ""
                for label_selector in [
                    "legend span.fb-dash-form-element__label",
                    "legend",
                    "span.fb-dash-form-element__label",
                    "label.artdeco-text-input--label",
                    "label.fb-dash-form-element__label",
                    "span[data-test-form-element-label]",
                ]:
                    label_el = group.locator(label_selector)
                    if await label_el.count() > 0:
                        label = (await label_el.first.inner_text()).strip()
                        if label and len(label) > 3:
                            break

                if not label or len(label) < 3:
                    continue

                # Skip file upload fields
                if any(skip in label.lower() for skip in ["resume", "cv", "upload"]):
                    continue

                # Determine field type and get options
                field_type = "text"
                options = []

                # Check for select/dropdown
                select_el = group.locator("select")
                if await select_el.count() > 0:
                    # Skip hidden selects (video player caption settings)
                    try:
                        if not await select_el.first.is_visible():
                            continue
                    except Exception:
                        continue
                    # Skip video.js caption selects by ID pattern
                    sel_id = await select_el.first.get_attribute("id") or ""
                    aria_label = await select_el.first.get_attribute("aria-labelledby") or ""
                    if sel_id.startswith("vjs_") or "captions-" in aria_label:
                        continue
                    field_type = "select"
                    option_els = select_el.first.locator("option")
                    opt_count = await option_els.count()
                    for oi in range(opt_count):
                        opt_text = (await option_els.nth(oi).inner_text()).strip()
                        if opt_text and opt_text != "Select an option":
                            options.append(opt_text)

                # Check for radio buttons
                elif await group.locator("input[type='radio']").count() > 0:
                    field_type = "radio"
                    # LinkedIn radio options: labels with data-test-text-selectable-option__label
                    radio_labels = group.locator(
                        "label[data-test-text-selectable-option__label], "
                        "div[data-test-text-selectable-option] label"
                    )
                    rl_count = await radio_labels.count()
                    if rl_count == 0:
                        # Fallback: all labels inside the group (question is in <legend>, not <label>)
                        radio_labels = group.locator("label")
                        rl_count = await radio_labels.count()
                    for ri in range(rl_count):
                        opt_text = (await radio_labels.nth(ri).inner_text()).strip()
                        if opt_text:
                            options.append(opt_text)

                # Check for textarea
                elif await group.locator("textarea").count() > 0:
                    field_type = "textarea"

                # Check for number input
                elif await group.locator("input[type='number']").count() > 0:
                    field_type = "number"

                # Check for typeahead/combobox (e.g. City field)
                elif await group.locator("input[role='combobox']").count() > 0:
                    field_type = "typeahead"

                # Default: text input
                elif await group.locator("input[type='text'], input:not([type])").count() > 0:
                    field_type = "text"
                else:
                    continue

                questions.append({
                    "label": label,
                    "type": field_type,
                    "options": options if options else None,
                    "group_index": i,
                })

        except Exception as e:
            logger.warning(f"  Error scraping screening questions: {e}")

        return questions

    async def _apply_ai_answers(self, questions: list[dict], ai_answers: dict) -> None:
        """Fill AI-generated answers into the form fields."""
        form_groups = self._page.locator(
            "div.jobs-easy-apply-form-section__grouping, "
            "div.fb-dash-form-element, "
            "fieldset, "
            "div[data-test-form-element]"
        )

        for q in questions:
            answer = ai_answers.get(q["label"])
            if not answer:
                # Try partial match
                answer = next(
                    (v for k, v in ai_answers.items()
                     if k.lower() in q["label"].lower() or q["label"].lower() in k.lower()),
                    None
                )
            if not answer:
                # For Yes/No dropdowns with no AI answer, default to a reasonable answer
                if q["type"] == "select" and q.get("options"):
                    opts_lower = [o.lower() for o in q["options"]]
                    if "yes" in opts_lower and "no" in opts_lower:
                        answer = "Yes"  # Default to Yes for Yes/No questions
                        logger.info(f"  Using default 'Yes' for unanswered Yes/No: {q['label'][:50]}")
                    else:
                        logger.warning(f"  ⚠️ No AI answer for dropdown: {q['label'][:50]} (options: {q['options'][:3]})")
                        continue
                else:
                    logger.warning(f"  ⚠️ No AI answer for: {q['label'][:50]}")
                    continue

            answer = str(answer).strip()
            group_idx = q.get("group_index", 0)

            try:
                group = form_groups.nth(group_idx)

                if q["type"] == "select":
                    select_el = group.locator("select")
                    if await select_el.count() > 0:
                        option_els = select_el.first.locator("option")
                        opt_count = await option_els.count()
                        best_match_text = None
                        for oi in range(opt_count):
                            opt_text = (await option_els.nth(oi).inner_text()).strip()
                            if opt_text.lower() == answer.lower():
                                best_match_text = opt_text
                                break
                            if answer.lower() in opt_text.lower() or opt_text.lower() in answer.lower():
                                best_match_text = opt_text
                        if best_match_text:
                            # Verify select is visible before interacting
                            try:
                                if not await select_el.first.is_visible():
                                    logger.debug(f"  Skipping hidden select: {q['label'][:40]}")
                                    continue
                            except Exception:
                                continue
                            # Use label= to match by visible text (most reliable)
                            await select_el.first.select_option(label=best_match_text)
                            logger.info(f"  ✅ Selected '{best_match_text}' for: {q['label'][:50]}")
                        else:
                            # Log available options for debugging
                            available = []
                            for oi in range(min(opt_count, 5)):
                                available.append((await option_els.nth(oi).inner_text()).strip())
                            logger.warning(f"  ⚠️ No matching option for '{answer}' in: {available}")

                elif q["type"] == "radio":
                    radio_labels = group.locator("label")
                    rl_count = await radio_labels.count()
                    for ri in range(rl_count):
                        opt_text = (await radio_labels.nth(ri).inner_text()).strip()
                        if opt_text.lower() == answer.lower() or answer.lower() in opt_text.lower():
                            await radio_labels.nth(ri).click()
                            logger.info(f"  ✅ Selected radio '{answer}' for: {q['label'][:50]}")
                            break

                elif q["type"] in ("text", "number"):
                    input_el = group.locator("input[type='text'], input[type='number'], input:not([type])")
                    if await input_el.count() > 0:
                        current = await input_el.first.input_value()
                        if not current:
                            # Sanitize if HTML input is type="number" OR label suggests numeric field
                            input_type = await input_el.first.get_attribute("type") or ""
                            label_lower = q["label"].lower()
                            needs_number = (
                                input_type == "number" or
                                any(kw in label_lower for kw in [
                                    "experience", "ctc", "salary", "compensation",
                                    "notice period", "how many year", "lpa", "inr",
                                    "last working day", "years of",
                                ])
                            )

                            fill_value = answer
                            if needs_number:
                                fill_value = self._sanitize_number_answer(answer, label_lower)

                            await input_el.first.fill(fill_value)
                            logger.info(f"  ✅ Filled '{fill_value}' for: {q['label'][:50]}")

                elif q["type"] == "typeahead":
                    # City and similar autocomplete fields
                    combobox = group.locator("input[role='combobox']")
                    if await combobox.count() > 0:
                        current = await combobox.first.input_value()
                        if not current:
                            await combobox.first.fill(answer)
                            await self.browser_manager.human_delay(1, 2)
                            # Select first dropdown suggestion
                            dropdown_option = self._page.locator(
                                "div[role='listbox'] div[role='option'], "
                                "ul[role='listbox'] li, "
                                "div.basic-typeahead__triggered-content li"
                            )
                            if await dropdown_option.count() > 0:
                                await dropdown_option.first.click()
                                logger.info(f"  ✅ Selected typeahead '{answer}' for: {q['label'][:50]}")
                            else:
                                logger.info(f"  ✅ Typed '{answer}' for: {q['label'][:50]} (no dropdown)")

                elif q["type"] == "textarea":
                    ta_el = group.locator("textarea")
                    if await ta_el.count() > 0:
                        current = await ta_el.first.input_value()
                        if not current:
                            await ta_el.first.fill(answer)
                            logger.info(f"  ✅ Filled textarea for: {q['label'][:50]}")

                await self.browser_manager.human_delay(0.3, 0.8)

            except Exception as e:
                logger.warning(f"  Error filling answer for '{q['label'][:40]}': {e}")

    def _sanitize_number_answer(self, answer: str, label_lower: str) -> str:
        """Extract pure number from AI answer for fields with type='number'.
        
        Only called when HTML input has type='number'.
        When label says 'in INR', converts LPA/lakh to absolute (e.g., 3.5 LPA → 350000).
        Otherwise just extracts the plain number (e.g., 30 days → 30).
        """
        import re
        
        answer_lower = answer.lower().strip()
        wants_inr = any(kw in label_lower for kw in ["in inr", "in rupees", "in rs"])

        # Handle "None", "N/A" etc. → 0
        if answer_lower in ("none", "n/a", "not applicable", "na", "nil"):
            return "0"

        # ── INR fields: convert LPA/lakh to absolute ──
        if wants_inr and ("lpa" in answer_lower or "lakh" in answer_lower or "lac" in answer_lower):
            # "3-5 LPA" → take higher → 5 * 100000 = 500000
            range_match = re.search(r'(\d+\.?\d*)\s*[-–to]+\s*(\d+\.?\d*)', answer)
            if range_match:
                num = float(range_match.group(2))
                return str(int(num * 100000))
            # "3.5 LPA" → 3.5 * 100000 = 350000
            numbers = re.findall(r'\d+\.?\d*', answer)
            if numbers:
                num = float(numbers[0])
                return str(int(num * 100000))
            return "0"

        # ── INR fields: small number likely in LPA ──
        if wants_inr:
            numbers = re.findall(r'\d+\.?\d*', answer)
            if numbers:
                num = float(numbers[0])
                if num < 100:  # Probably LPA (e.g., "5" means 5 LPA)
                    return str(int(num * 100000))
                return str(int(num))
            return "0"

        # ── Non-INR fields: just extract number ──
        # Handle range (e.g., "3-5") → take higher number
        range_match = re.search(r'(\d+\.?\d*)\s*[-–to]+\s*(\d+\.?\d*)', answer)
        if range_match:
            num = float(range_match.group(2))
            return str(int(num))

        # Extract first number (e.g., "30 days" → 30, "1 year" → 1)
        numbers = re.findall(r'\d+\.?\d*', answer)
        if numbers:
            num = float(numbers[0])
            return str(int(num)) if num == int(num) else str(num)

        # No number found
        return "0"

    async def _fill_basic_fields(self, answers: dict | None) -> None:
        """Try to fill basic form fields (phone, etc.)."""
        answers = answers or {}

        # Phone number field — LinkedIn uses artdeco-text-input with label "Mobile phone number"
        phone = answers.get("phone", "")
        if phone:
            phone_selectors = [
                # LinkedIn's actual structure: label with "phone" text → sibling input
                "input[id*='phoneNumber-nationalNumber']",
                "input[id*='phone']",
                "input.artdeco-text-input--input",
                # Fallback: standard selectors
                "input[name*='phone']",
                "input[aria-label*='phone']",
                "input[aria-label*='Phone']",
            ]
            for selector in phone_selectors:
                try:
                    fields = self._page.locator(selector)
                    count = await fields.count()
                    for fi in range(count):
                        field = fields.nth(fi)
                        # Verify this is actually a phone field by checking nearby label
                        parent = field.locator("xpath=ancestor::div[@data-test-form-element or contains(@class,'fb-dash-form-element')]")
                        if await parent.count() > 0:
                            label_el = parent.first.locator("label")
                            if await label_el.count() > 0:
                                label_text = (await label_el.first.inner_text()).strip().lower()
                                if "phone" not in label_text and "mobile" not in label_text:
                                    continue
                        
                        current_val = await field.input_value()
                        if not current_val:
                            await field.fill(phone)
                            logger.info(f"  Filled phone number: {phone}")
                        break
                    else:
                        continue
                    break
                except Exception:
                    continue

        # Additional answer fields can be handled via the answers dict
        # Format: {"field_label": "value"}
        for label, value in answers.items():
            if label == "phone":
                continue  # Already handled
            try:
                field = self._page.locator(f"input[aria-label*='{label}']")
                if await field.count() > 0:
                    current_val = await field.first.input_value()
                    if not current_val:
                        await field.first.fill(str(value))
                        logger.info(f"  Filled field: {label}")
            except Exception:
                continue

    async def _click_save_if_present(self) -> None:
        """Click 'Save' or 'Cancel' inside repeatable grouping cards (e.g. Work Experience).
        Saves if fields were filled, Cancels if form is empty (e.g. fresher)."""
        try:
            card = self._page.locator(
                "div.artdeco-card, "
                "div.jobs-easy-apply-repeatable-groupings__groupings"
            )
            if await card.count() == 0:
                return

            # Check if Save button exists inside the card
            save_btn = card.first.locator("button:has-text('Save')")
            cancel_btn = card.first.locator("button:has-text('Cancel')")

            if await save_btn.count() == 0:
                return  # No Save button = not a repeatable grouping

            # Check if any text fields inside the card have been filled
            text_inputs = card.first.locator("input.artdeco-text-input--input, input[type='text']")
            has_filled_fields = False
            input_count = await text_inputs.count()
            for idx in range(input_count):
                val = await text_inputs.nth(idx).input_value()
                if val and val.strip():
                    has_filled_fields = True
                    break

            if has_filled_fields:
                # Fields filled (has experience) → Save
                logger.info("  Clicking Save (repeatable grouping)...")
                await save_btn.first.click()
                await self.browser_manager.human_delay(1.5, 2.5)
            else:
                # Fields empty (fresher) → Cancel to dismiss empty card
                if await cancel_btn.count() > 0:
                    logger.info("  No data filled (fresher) — clicking Cancel...")
                    await cancel_btn.first.click()
                    await self.browser_manager.human_delay(1, 2)
        except Exception as e:
            logger.debug(f"  Save/Cancel button check: {e}")

    async def _handle_sign_in_as_page(self) -> bool:
        """Handle LinkedIn's 'Sign in as [Name]' soft re-verification page.
        
        LinkedIn shows this page when it detects automation-like behavior.
        It displays the user's profile card and requires a click to confirm identity.
        Returns True if successfully handled, False if full re-login needed.
        """
        try:
            await self.browser_manager.human_delay(1, 2)

            # Multiple selectors for the "Sign in as" confirmation button/card
            confirm_selectors = [
                # Profile card click-to-confirm
                "button[data-litms-control-urn*='login-submit']",
                "div.login-submit__form button[type='submit']",
                "button.profile-card__cta",
                "button[type='submit']",
                # "Sign in" button on checkpoint page
                "button:has-text('Sign in')",
                "button:has-text('Continue')",
                "button:has-text('Confirm')",
                # Profile image/card that acts as confirm button
                "div.login-submit__profile-card",
                "div[data-test-id='profile-card']",
                # Generic submit on checkpoint forms
                "form button[type='submit']",
            ]

            for selector in confirm_selectors:
                try:
                    el = self._page.locator(selector)
                    if await el.count() > 0 and await el.first.is_visible():
                        logger.info(f"  Auto-clicking re-verification: {selector[:50]}")
                        await el.first.click()
                        await self.browser_manager.human_delay(3, 5)

                        # Check if we're now on a normal page (feed or jobs)
                        current = self._page.url
                        if "/feed" in current or "/jobs" in current or "/in/" in current:
                            logger.info("  Re-verification successful — session restored")
                            return True
                        # If still on checkpoint, try next selector
                        if "/checkpoint" not in current and "/login" not in current:
                            logger.info("  Re-verification successful — session restored")
                            return True
                except Exception:
                    continue
            # Try JavaScript-based click (most reliable for both page variants)
            try:
                clicked = await self._page.evaluate("""
                    () => {
                        const allEls = document.querySelectorAll('a, button, div[role="button"], li, div');
                        for (const el of allEls) {
                            const text = (el.textContent || '').toLowerCase();
                            if (text.includes('sign in as') || text.includes('sign in using')) {
                                const rect = el.getBoundingClientRect();
                                if (rect.height > 20 && rect.width > 80) {
                                    el.click();
                                    return true;
                                }
                            }
                        }
                        // Try profile cards with email patterns
                        for (const el of allEls) {
                            const text = (el.textContent || '').toLowerCase();
                            if (text.includes('@gmail.com') || text.includes('@yahoo.com') || text.includes('@outlook.com')) {
                                const rect = el.getBoundingClientRect();
                                if (rect.height > 30 && rect.width > 100) {
                                    el.click();
                                    return true;
                                }
                            }
                        }
                        return false;
                    }
                """)
                if clicked:
                    logger.info("  Clicked 'Sign in as' via JavaScript")
                    await self.browser_manager.human_delay(3, 5)
                    current = self._page.url
                    if "/feed" in current or "/jobs" in current:
                        logger.info("  Re-verification successful via JS — session restored")
                        return True
                    if "/checkpoint" not in current and "/login" not in current:
                        return True
            except Exception:
                pass

            # Last resort: wait a bit and check if page auto-redirected
            await self.browser_manager.human_delay(3, 5)
            current = self._page.url
            if "/feed" in current or "/jobs" in current:
                logger.info("  Session auto-restored after wait")
                return True

            logger.warning("  Could not auto-confirm identity — manual intervention may be needed")
            return False

        except Exception as e:
            logger.warning(f"  Error handling sign-in-as page: {e}")
            return False

    async def _close_easy_apply_modal(self) -> None:
        """Close the Easy Apply modal safely."""
        try:
            # Try dismiss button first
            dismiss_btn = self._page.locator(
                "button[aria-label='Dismiss'], "
                "button[data-test-modal-close-btn], "
                "button.artdeco-modal__dismiss"
            )
            if await dismiss_btn.count() > 0:
                await dismiss_btn.first.click()
                await self.browser_manager.human_delay(0.5, 1)

            # Confirm discard if prompted
            discard_btn = self._page.locator(
                "button[data-test-dialog-primary-btn], "
                "button:has-text('Discard')"
            )
            if await discard_btn.count() > 0:
                await discard_btn.first.click()
                await self.browser_manager.human_delay(0.5, 1)
        except Exception:
            pass

    async def _check_application_confirmation(self) -> bool:
        """Check if application was successfully submitted and dismiss post-apply popup."""
        try:
            # Wait a moment for the modal to close and page to update
            await self.browser_manager.human_delay(2, 3)

            # LinkedIn shows "Applied X ago" or a success popup after submit
            success_selectors = [
                "span:has-text('Applied')",
                "span:has-text('applied')",
                "div:has-text('Applied 1 second ago')",
                "a:has-text('See application')",
                "h2:has-text('application was sent')",
                "h2:has-text('Application submitted')",
                "div:has-text('Your application was sent')",
            ]
            for selector in success_selectors:
                if await self._page.locator(selector).count() > 0:
                    # Dismiss the post-apply popup ("No thanks" or X)
                    await self._dismiss_post_apply_popup()
                    return True

            # Also check if the modal has disappeared (means submit was successful)
            modal = self._page.locator(
                "div.jobs-easy-apply-modal, "
                "div.artdeco-modal"
            )
            if await modal.count() == 0:
                # Modal gone = likely submitted successfully
                await self._dismiss_post_apply_popup()
                return True

        except Exception:
            pass
        return False

    async def _dismiss_post_apply_popup(self) -> None:
        """Dismiss LinkedIn's post-apply popup (Open to Work, etc.)."""
        try:
            # Try "No thanks" button first
            no_thanks = self._page.locator(
                "button:has-text('No thanks'), "
                "button:has-text('Dismiss'), "
                "button[aria-label='Dismiss']"
            )
            if await no_thanks.count() > 0:
                await no_thanks.first.click()
                logger.info("  Dismissed post-apply popup")
                await self.browser_manager.human_delay(0.5, 1)
                return

            # Try X/close button on the popup
            close_btn = self._page.locator(
                "div.artdeco-modal button.artdeco-modal__dismiss"
            )
            if await close_btn.count() > 0:
                await close_btn.first.click()
                logger.info("  Closed post-apply modal")
                await self.browser_manager.human_delay(0.5, 1)
        except Exception:
            pass

