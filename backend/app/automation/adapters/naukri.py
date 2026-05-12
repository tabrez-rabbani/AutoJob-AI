"""
AutoJob AI — Naukri.com Platform Adapter
Implements job search and auto-apply automation for Naukri.com using Playwright.

Naukri is more lenient with automation than LinkedIn, but we still use:
- Human-like typing, delays, scrolling
- Session cookie persistence
- Daily rate limiting (100 scrapes, 25 applies)
"""

import asyncio
import json
import logging
import random
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from app.automation.adapters.base import JobListing, JobPlatformAdapter

try:
    from app.utils.llm import client as llm_client, model as llm_model
    LLM_AVAILABLE = True
except Exception:
    LLM_AVAILABLE = False

from app.automation.browser_manager import BrowserManager
from app.automation.stealth import get_random_delay, get_typing_delay

logger = logging.getLogger("autojob.naukri")

# ── Constants ────────────────────────────────────────
NAUKRI_LOGIN_URL = "https://www.naukri.com/nlogin/login"
NAUKRI_HOME_URL = "https://www.naukri.com/"
NAUKRI_SEARCH_URL = "https://www.naukri.com/jobs-in-india"

# Rate limits (per session)
MAX_SEARCHES_PER_SESSION = 15
MAX_PAGES_PER_SEARCH = 5

# Session storage
SESSIONS_DIR = Path(__file__).parent.parent.parent.parent / "sessions"
SESSIONS_DIR.mkdir(exist_ok=True)


class NaukriAdapter(JobPlatformAdapter):
    """
    Naukri.com job platform adapter.
    Handles login, session management, job search, and one-click apply.
    """

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.browser_manager = BrowserManager(headless=headless)
        self._page: Page | None = None
        self._is_logged_in = False
        self._search_count = 0

    # ══════════════════════════════════════════════════
    # LOGIN
    # ══════════════════════════════════════════════════

    async def login(self, credentials: dict) -> bool:
        """
        Log into Naukri.com with human-like behavior.

        Args:
            credentials: {"email": "...", "password": "..."}

        Returns:
            True if login successful, False otherwise.
        """
        email = credentials.get("email", "")
        password = credentials.get("password", "")

        if not email or not password:
            logger.error("Naukri credentials missing (email or password empty)")
            return False

        logger.info(f"Attempting Naukri login for: {email[:3]}***")

        if not self._page:
            await self.browser_manager.start()
            self._page = await self.browser_manager.new_page()

        # Try loading saved session first
        session_loaded = await self.load_session(email)
        if session_loaded:
            if await self._verify_login():
                logger.info("✅ Session restored — already logged in to Naukri")
                self._is_logged_in = True
                return True
            else:
                logger.info("Saved session expired — logging in fresh")

        try:
            # Navigate to Naukri login page (generous timeout for slow connections)
            logger.info("Navigating to Naukri login page...")
            await self._page.goto(NAUKRI_LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
            await self.browser_manager.human_delay(2, 4)

            # Check if already logged in (redirected to home/dashboard)
            if "/nlogin" not in self._page.url and "/login" not in self._page.url:
                logger.info("✅ Already logged in to Naukri (redirected)")
                self._is_logged_in = True
                await self.save_session(email)
                return True

            # ── Find & Fill email ──
            logger.info("Waiting for Naukri login form...")
            # IMPORTANT: Do NOT use generic `input[type='text']` — it matches the
            # search bar in the navbar. Use exact placeholders from the real page.
            email_input = self._page.locator(
                "input[placeholder='Enter Email ID / Username'], "
                "input[placeholder*='Email ID' i], "
                "input[placeholder*='Username' i], "
                "input#usernameField"
            )

            try:
                await email_input.first.wait_for(state="visible", timeout=20000)
            except Exception:
                logger.warning("Login form not found — refreshing page...")
                await self._page.reload(wait_until="domcontentloaded", timeout=30000)
                await self.browser_manager.human_delay(3, 5)
                await email_input.first.wait_for(state="visible", timeout=20000)

            logger.info("Filling email...")
            await email_input.first.click()
            await self.browser_manager.human_delay(0.5, 1)
            # Use fill() for email — Naukri is lenient, no need for char-by-char
            await email_input.first.fill("")
            await self.browser_manager.human_delay(0.3, 0.5)
            await email_input.first.fill(email)
            await self.browser_manager.human_delay(1, 2)

            # ── Find & Fill password ──
            logger.info("Typing password...")
            password_input = self._page.locator(
                "input[placeholder='Enter Password'], "
                "input[placeholder*='Password' i], "
                "input#passwordField, "
                "input[type='password']"
            )
            await password_input.first.wait_for(state="visible", timeout=10000)
            await password_input.first.click()
            await self.browser_manager.human_delay(0.5, 1)

            # Type password with slight delays (more human-like for the sensitive field)
            await password_input.first.fill("")
            for char in password:
                await password_input.first.type(char, delay=get_typing_delay())

            await self.browser_manager.human_delay(1, 2)

            # ── Click Login button ──
            # IMPORTANT: Naukri has two "Login" elements — one in the navbar (link)
            # and one inside the login form (button). Target the form button specifically.
            logger.info("Clicking Login button...")
            login_btn = self._page.locator(
                "button[type='submit']:has-text('Login'), "
                "form button:has-text('Login'), "
                "div.login-layer button:has-text('Login'), "
                "button.loginButton"
            )
            await login_btn.first.click()

            # Wait for navigation after login click
            logger.info("Waiting for login response...")
            try:
                await self._page.wait_for_load_state("domcontentloaded", timeout=30000)
            except PlaywrightTimeout:
                logger.warning("Page load slow after login click — continuing anyway...")

            await self.browser_manager.human_delay(3, 5)

            # Check for OTP/verification
            if await self._detect_otp():
                logger.warning("⚠️ OTP verification required — waiting up to 90s for manual entry")
                for _ in range(18):  # 18 * 5 = 90 seconds
                    await asyncio.sleep(5)
                    if "/nlogin" not in self._page.url and "/login" not in self._page.url:
                        logger.info("✅ OTP completed")
                        break
                else:
                    logger.error("❌ OTP timeout")
                    return False

            # Check for login errors
            error_el = self._page.locator(
                "div.err-message, "
                "span.error-msg, "
                "div[class*='error'], "
                "span[class*='error']"
            )
            if await error_el.count() > 0:
                try:
                    error_text = await error_el.first.inner_text()
                    if error_text.strip() and len(error_text.strip()) < 200:
                        logger.error(f"❌ Naukri login error: {error_text.strip()}")
                        return False
                except Exception:
                    pass

            # Verify login succeeded
            await self.browser_manager.human_delay(1, 2)
            if await self._verify_login():
                logger.info("✅ Naukri login successful")
                self._is_logged_in = True
                await self.save_session(email)
                return True

            # Second chance: maybe page is still loading
            logger.info("First verify failed — waiting a bit more...")
            await self.browser_manager.human_delay(3, 5)
            if await self._verify_login():
                logger.info("✅ Naukri login successful (delayed verification)")
                self._is_logged_in = True
                await self.save_session(email)
                return True

            # Check URL as last resort
            current_url = self._page.url
            if "/nlogin" not in current_url and "/login" not in current_url:
                logger.info("✅ Naukri login likely successful (not on login page)")
                self._is_logged_in = True
                await self.save_session(email)
                return True

            logger.error("❌ Login failed — could not verify logged-in state")
            return False

        except PlaywrightTimeout:
            logger.error("❌ Login timeout — page did not load in time")
            # Take screenshot for debugging
            try:
                screenshot_path = SESSIONS_DIR / "naukri_login_fail.png"
                await self._page.screenshot(path=str(screenshot_path))
                logger.info(f"Debug screenshot saved: {screenshot_path}")
            except Exception:
                pass
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
        Search Naukri jobs and extract listings.

        Naukri URL format:
          https://www.naukri.com/<keywords>-jobs-in-<location>
          e.g. https://www.naukri.com/python-developer-jobs-in-bangalore
        """
        if not self._is_logged_in:
            logger.error("Cannot search — not logged in to Naukri")
            return []

        if self._search_count >= MAX_SEARCHES_PER_SESSION:
            logger.warning(f"Rate limit reached ({MAX_SEARCHES_PER_SESSION} searches/session)")
            return []

        self._search_count += 1
        logger.info(f"🔍 Searching Naukri: '{keywords}' | Location: '{location or 'Any'}'")

        jobs: list[JobListing] = []

        try:
            search_url = self._build_search_url(keywords, location)

            for attempt in range(2):
                try:
                    await self._page.goto(search_url, wait_until="domcontentloaded", timeout=45000)
                    await self.browser_manager.human_delay(3, 5)

                    current_url = self._page.url
                    if "/nlogin" in current_url or "/login" in current_url:
                        logger.warning("Redirected to login during search — session lost")
                        return jobs

                    break
                except PlaywrightTimeout:
                    if attempt == 0:
                        logger.warning("Search page slow to load — retrying...")
                        await self.browser_manager.human_delay(3, 5)
                        continue
                    else:
                        logger.error("Search timeout after retry")
                        return jobs

            # Scrape more pages to compensate for external apply jobs that will be filtered
            # We target 2x the requested amount since ~50-60% can be external
            target_count = max_results * 2
            pages_scraped = 0
            external_skipped = 0
            seen_urls: set[str] = set()  # Dedup by job URL

            while len(jobs) < target_count and pages_scraped < MAX_PAGES_PER_SEARCH:
                await self._human_scroll()

                page_jobs, page_external = await self._extract_job_cards(filter_external=True)
                
                # Deduplicate: only add jobs we haven't seen before
                new_jobs = []
                for job in page_jobs:
                    if job.apply_url and job.apply_url not in seen_urls:
                        seen_urls.add(job.apply_url)
                        new_jobs.append(job)
                
                dupes_on_page = len(page_jobs) - len(new_jobs)
                jobs.extend(new_jobs)
                external_skipped += page_external

                logger.info(f"  Page {pages_scraped + 1}: found {len(new_jobs)} direct-apply jobs, skipped {page_external} external{f', {dupes_on_page} duplicates' if dupes_on_page else ''} (total: {len(jobs)})")

                pages_scraped += 1

                # Stop if no new unique jobs on this page (we've exhausted results)
                if len(new_jobs) == 0 and page_external == 0:
                    logger.info("  No new jobs found — stopping pagination")
                    break

                if len(jobs) < target_count:
                    has_next = await self._go_to_next_page()
                    if not has_next:
                        break
                    await self.browser_manager.human_delay(3, 6)

            jobs = jobs[:max_results]
            logger.info(f"✅ Naukri search complete: {len(jobs)} direct-apply jobs found ({external_skipped} external filtered out)")

        except PlaywrightTimeout:
            logger.error("Search timeout")
        except Exception as e:
            logger.error(f"Search error: {e}")

        return jobs

    async def get_job_details(self, job_url: str) -> dict:
        """Get full details for a specific Naukri job page."""
        if not self._is_logged_in or not self._page:
            return {}

        try:
            await self._page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
            await self.browser_manager.human_delay(2, 4)

            description = ""
            desc_selectors = [
                "section.job-desc",
                "div.job-desc",
                "div.styles_JDC__dang-inner-html__h0K4t",
                "div[class*='job-desc']",
                "div[class*='jobDescription']",
                "section.styles_job-desc-container",
            ]
            for sel in desc_selectors:
                desc_el = self._page.locator(sel)
                if await desc_el.count() > 0:
                    description = await desc_el.first.inner_text()
                    if description.strip():
                        break

            return {
                "description": description.strip(),
                "url": job_url,
            }

        except Exception as e:
            logger.error(f"Error getting job details: {e}")
            return {}

    # ══════════════════════════════════════════════════
    # APPLY TO JOB
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
        Apply to a Naukri job.

        Naukri has a simpler apply flow than LinkedIn:
        1. Navigate to job page
        2. Click "Apply" button
        3. Some jobs: single-click apply (profile already on Naukri)
        4. Some jobs: redirect to external site (marked as external_apply)
        5. Some jobs: brief questionnaire form

        Returns:
            {"status": "applied|external_apply|skipped|failed", "message": "..."}
        """
        if not self._page or not self._is_logged_in:
            return {"status": "failed", "message": "Not logged in"}

        logger.info(f"Opening Naukri job: {job_url}")

        try:
            await self._page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
            await self.browser_manager.human_delay(2, 4)

            # Check if already applied
            already_applied = self._page.locator(
                "button:has-text('Already Applied'), "
                "span:has-text('Already Applied'), "
                "div:has-text('You have already applied')"
            )
            if await already_applied.count() > 0:
                logger.info("  Already applied to this job — skipping")
                return {"status": "skipped", "message": "Already applied"}

            # Look for the Apply button
            apply_btn = self._page.locator(
                "button#apply-button, "
                "button[class*='apply-button'], "
                "button:has-text('Apply'), "
                "a:has-text('Apply on company site'), "
                "button:has-text('Apply on company site')"
            )

            if await apply_btn.count() == 0:
                logger.info("  No Apply button found — may be external or expired")
                return {"status": "skipped", "message": "No Apply button found"}

            # Check if it's an external apply link
            first_btn = apply_btn.first
            btn_text = (await first_btn.inner_text()).strip().lower()

            if "company site" in btn_text or "external" in btn_text:
                logger.info("  External apply — marking as external_apply")
                return {"status": "external_apply", "message": "External application (company site)"}

            if dry_run:
                logger.info("  🏁 DRY RUN — would click Apply here. Stopping.")
                return {"status": "applied", "message": "Dry run — apply skipped"}

            # Click Apply
            logger.info("  Clicking Apply...")
            await first_btn.click()
            await self.browser_manager.human_delay(2, 4)

            # Handle post-click scenarios
            # Scenario 1: Simple "Applied Successfully" confirmation
            confirmation = await self._check_application_confirmation()
            if confirmation:
                logger.info("  ✅ Application submitted successfully!")
                return {"status": "applied", "message": "Application submitted"}

            # Scenario 2: A small questionnaire appeared
            questionnaire = self._page.locator(
                "div[class*='chatbot'], "
                "div[class*='questionnaire'], "
                "div[class*='apply-form'], "
                "form[class*='apply']"
            )
            if await questionnaire.count() > 0:
                logger.info("  Questionnaire detected — attempting to fill...")
                result = await self._handle_questionnaire(
                    resume_path=resume_path,
                    answers=answers,
                    user_profile=user_profile,
                    job_info=job_info,
                )
                return result

            # Scenario 3: Check if the button text changed to "Applied"
            await self.browser_manager.human_delay(1, 2)
            new_btn = self._page.locator(
                "button:has-text('Applied'), "
                "span:has-text('Applied')"
            )
            if await new_btn.count() > 0:
                logger.info("  ✅ Button changed to 'Applied' — success!")
                return {"status": "applied", "message": "Application submitted"}

            # Fallback: assume apply was attempted
            logger.warning("  Apply clicked but no confirmation detected")
            return {"status": "applied", "message": "Applied (no confirmation seen)"}

        except PlaywrightTimeout:
            logger.error("  Timeout during application")
            return {"status": "failed", "message": "Page load timeout"}
        except Exception as e:
            logger.error(f"  Application error: {e}")
            return {"status": "failed", "message": str(e)}

    async def _handle_questionnaire(
        self,
        resume_path: str,
        answers: dict | None = None,
        user_profile: dict | None = None,
        job_info: dict | None = None,
    ) -> dict:
        """Handle Naukri's post-apply chatbot questionnaire.
        
        CONFIRMED FLOW (from manual testing):
        1. Chatbot panel slides in from right side
        2. Welcome message + first question appears
        3. For text Q: type answer in "Type message here..." → click "Save"
        4. For radio/checkbox Q: select option → click "Save"
        5. Next question loads in same panel
        6. After last Q: "Thank you for your responses." appears
        7. Chatbot auto-closes after 1-3 seconds
        8. Main page shows "Applied to 'Job Title'" green banner
        
        Button is ALWAYS "Save" (not Submit/Next/Send).
        Save button is DISABLED until an answer is provided.
        """
        logger.info("  Handling Naukri Chatbot Questionnaire...")
        max_steps = 25
        last_question = ""
        answered_count = 0
        same_q_count = 0  # track repeated questions to avoid infinite loop
        
        # Give chatbot panel time to slide in
        await self.browser_manager.human_delay(2, 3)
        
        # ── DETECT CHATBOT CONTEXT ──
        # The chatbot lives inside a container div on the main page.
        # We MUST scope all selectors to this container, otherwise we'll
        # click the wrong "Save" button (job listing's bookmark button)
        # and read navbar text instead of chatbot questions.
        ctx = self._page  # fallback
        use_iframe = False
        chatbot_found = False
        
        try:
            # Step 1: Look for chatbot container DIV on main page
            chatbot_container = self._page.locator(
                "div[class*='chatBotContainer'], "
                "div[id*='ChatbotContainer'], "
                "div[class*='chatbot_Container'], "
                "div[class*='chatbot-container']"
            )
            
            if await chatbot_container.count() > 0:
                ctx = chatbot_container.first
                chatbot_found = True
                logger.info("  📌 CHATBOT container found on main page!")
            else:
                # Step 2: Try broader chatbot selectors
                chatbot_panel = self._page.locator(
                    "div[class*='chatbot'], "
                    "div[class*='ChatBot']"
                )
                if await chatbot_panel.count() > 0:
                    ctx = chatbot_panel.first
                    chatbot_found = True
                    logger.info("  📌 CHATBOT panel found on main page!")
            
            # Step 3: If no chatbot div, check iframes
            if not chatbot_found:
                frame_count = len(self._page.frames)
                logger.info(f"  📌 No chatbot div. Page has {frame_count} frame(s)")
                
                if frame_count > 1:
                    for frame in self._page.frames:
                        if frame == self._page.main_frame:
                            continue
                        try:
                            frame_url = frame.url or "unknown"
                            # Skip ad/tracking iframes
                            if "doubleclick" in frame_url or "google" in frame_url:
                                continue
                            logger.info(f"  📌 Checking frame: {frame_url[:80]}")
                            test_el = frame.locator(
                                "input[placeholder*='message' i], "
                                "input[type='radio'], "
                                "input[type='checkbox']"
                            )
                            if await test_el.count() > 0:
                                ctx = frame
                                use_iframe = True
                                chatbot_found = True
                                logger.info("  📌 CHATBOT FOUND in iframe!")
                                break
                        except Exception:
                            continue
                
                if not chatbot_found:
                    try:
                        fl = self._page.frame_locator("iframe")
                        test_fl = fl.locator("input[placeholder*='message' i]")
                        if await test_fl.count() > 0:
                            ctx = fl
                            use_iframe = True
                            chatbot_found = True
                            logger.info("  📌 CHATBOT FOUND via frame_locator!")
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"  Context detection error: {e}")
        
        if not chatbot_found:
            logger.warning("  ⚠ No chatbot container found! Using main page.")
        
        for step in range(max_steps):
            await self.browser_manager.human_delay(1, 2)
            
            # ── CHECK: Are we done? ──
            # 1. Check main page for "Applied to..." banner
            if await self._check_application_confirmation():
                logger.info("  ✅ Application confirmed!")
                return {"status": "applied", "message": "Applied via questionnaire"}
            
            # 2. Check for "Thank you for your responses" in chatbot
            if answered_count > 0:
                try:
                    thank_you = ctx.locator("text=/[Tt]hank you for your response/i")
                    if await thank_you.first.is_visible(timeout=1000):
                        logger.info("  ✅ 'Thank you for your responses.' — Done!")
                        await self.browser_manager.human_delay(2, 4)
                        return {"status": "applied", "message": "Applied via questionnaire"}
                except Exception:
                    pass
            
            # ── STEP 1: Handle "I Accept" consent (radio + Save) ──
            try:
                i_accept = ctx.locator(
                    "label.ssrc__label[for='I Accept'], "
                    "label:has-text('I Accept'), "
                    "span:text-is('I Accept')"
                )
                if await i_accept.count() > 0:
                    await i_accept.first.click()
                    logger.info("    ✓ Clicked 'I Accept'")
                    answered_count += 1
                    await self.browser_manager.human_delay(0.5, 1)
                    await self._click_save_button(ctx)
                    continue
            except Exception:
                pass
            
            # ── STEP 2: Handle Radio/Checkbox questions (select + Save) ──
            try:
                # Naukri chatbot radios: input.ssrc__radio + label.ssrc__label
                radio_options = ctx.locator(
                    "input.ssrc__radio, "
                    "input[type='radio'][name='radio-button'], "
                    "input[type='radio'], "
                    "input[type='checkbox']"
                )
                radio_count = await radio_options.count()
                
                if radio_count > 0:
                    # Read the question to make smart choice
                    question_text = await self._get_latest_chatbot_question_ctx(ctx)
                    
                    # Try exact Naukri chatbot labels first
                    yes_label = ctx.locator(
                        "label.ssrc__label[for='Yes'], "
                        "label[for='Yes']"
                    )
                    no_label = ctx.locator(
                        "label.ssrc__label[for='No'], "
                        "label[for='No']"
                    )
                    
                    if await yes_label.count() > 0:
                        await yes_label.first.click()
                        logger.info(f"    ✓ Selected 'Yes' (Q: {question_text[:50]})")
                    elif await no_label.count() > 0:
                        await no_label.first.click()
                        logger.info(f"    ✓ Selected 'No' (Q: {question_text[:50]})")
                    else:
                        # Click first available label
                        first_label = ctx.locator("label.ssrc__label, label[for]").first
                        try:
                            await first_label.click()
                            label_text = (await first_label.inner_text()).strip()
                            logger.info(f"    ✓ Selected '{label_text}' (Q: {question_text[:50]})")
                        except Exception:
                            await radio_options.first.click()
                            logger.info(f"    ✓ Selected first radio (Q: {question_text[:50]})")
                    
                    answered_count += 1
                    await self.browser_manager.human_delay(0.5, 1)
                    await self._click_save_button(ctx)
                    continue
            except Exception:
                pass
            
            # ── STEP 2.5: Handle Naukri Chatbot Chips (Yes/No buttons) ──
            # These are <div class="chatbot_Chip chipItem"><span>Yes</span></div>
            # NOT radio buttons, NOT checkboxes — clickable div chips!
            try:
                chip_items = ctx.locator(
                    "div.chatbot_Chip, "
                    "div.chipItem"
                )
                chip_count = await chip_items.count()
                
                if chip_count > 0:
                    question_text = await self._get_latest_chatbot_question_ctx(ctx)
                    clicked = False
                    q_lower = question_text.lower()
                    
                    # Collect all chip texts
                    chip_texts = []
                    for i in range(chip_count):
                        try:
                            chip_texts.append((i, (await chip_items.nth(i).inner_text()).strip()))
                        except Exception:
                            continue
                    
                    skip_words = ["skip", "skip this", "skip this question", "none", "not applicable"]
                    
                    # ── CONTEXT-AWARE CHIP SELECTION ──
                    
                    # A. Experience questions → match user's years to range chip
                    if not clicked and any(kw in q_lower for kw in ["experience", "years of exp", "how many year"]):
                        exp_years = float(user_profile.get("experience_years", 1)) if user_profile else 1.0
                        
                        # Try to find the range that contains user's experience
                        import re
                        for idx, text in chip_texts:
                            t_lower = text.lower()
                            if t_lower in [s.lower() for s in skip_words]:
                                continue
                            # Match ranges like "1-3 years", "1 - 3", "1 to 3"
                            range_match = re.search(r'(\d+)\s*[-–to]+\s*(\d+)', t_lower)
                            if range_match:
                                low, high = float(range_match.group(1)), float(range_match.group(2))
                                if low <= exp_years <= high:
                                    await chip_items.nth(idx).click()
                                    logger.info(f"    ✓ Clicked chip '{text}' (exp={exp_years}) (Q: {question_text[:50]})")
                                    clicked = True
                                    break
                            # Match single number like "1 year", "2 years"
                            single_match = re.search(r'^(\d+)\s*(?:year|yr)', t_lower)
                            if single_match and float(single_match.group(1)) == exp_years:
                                await chip_items.nth(idx).click()
                                logger.info(f"    ✓ Clicked chip '{text}' (exact exp) (Q: {question_text[:50]})")
                                clicked = True
                                break
                        
                        # If no range matched, pick the closest lower range (don't pick "No experience")
                        if not clicked:
                            best_idx, best_text = None, None
                            for idx, text in chip_texts:
                                t_lower = text.lower()
                                if "no experience" in t_lower or "no exp" in t_lower or t_lower in [s.lower() for s in skip_words]:
                                    continue
                                range_match = re.search(r'(\d+)', t_lower)
                                if range_match:
                                    best_idx, best_text = idx, text
                                    break  # Pick first non-zero range
                            if best_idx is not None:
                                await chip_items.nth(best_idx).click()
                                logger.info(f"    ✓ Clicked chip '{best_text}' (closest exp) (Q: {question_text[:50]})")
                                clicked = True
                    
                    # B. CTC / Salary questions → match user's CTC to range chip
                    if not clicked and any(kw in q_lower for kw in ["ctc", "salary", "package", "lpa", "lakh", "compensation"]):
                        import re
                        ctc_val = None
                        if user_profile:
                            if any(kw in q_lower for kw in ["current", "present", "last drawn"]):
                                ctc_val = user_profile.get("current_ctc")
                            elif any(kw in q_lower for kw in ["expected", "desired"]):
                                ctc_val = user_profile.get("expected_ctc")
                            if not ctc_val:
                                ctc_val = user_profile.get("expected_ctc") or user_profile.get("current_ctc")
                        
                        if ctc_val:
                            ctc_num = float(ctc_val)
                            for idx, text in chip_texts:
                                t_lower = text.lower()
                                if t_lower in [s.lower() for s in skip_words]:
                                    continue
                                range_match = re.search(r'(\d+(?:\.\d+)?)\s*[-–to]+\s*(\d+(?:\.\d+)?)', t_lower)
                                if range_match:
                                    low, high = float(range_match.group(1)), float(range_match.group(2))
                                    if low <= ctc_num <= high:
                                        await chip_items.nth(idx).click()
                                        logger.info(f"    ✓ Clicked chip '{text}' (CTC={ctc_val}) (Q: {question_text[:50]})")
                                        clicked = True
                                        break
                            # If no range matched, pick closest
                            if not clicked:
                                for idx, text in chip_texts:
                                    t_lower = text.lower()
                                    if "negotiable" in t_lower:
                                        await chip_items.nth(idx).click()
                                        logger.info(f"    ✓ Clicked chip 'Negotiable' (CTC fallback) (Q: {question_text[:50]})")
                                        clicked = True
                                        break
                    
                    # C. Notice period questions → match user's notice days
                    if not clicked and any(kw in q_lower for kw in ["notice", "notice period", "joining"]):
                        notice_days = user_profile.get("notice_period_days") if user_profile else None
                        
                        if notice_days is not None:
                            for idx, text in chip_texts:
                                t_lower = text.lower()
                                if notice_days == 0 and ("immediate" in t_lower or "0" in t_lower):
                                    await chip_items.nth(idx).click()
                                    logger.info(f"    ✓ Clicked chip '{text}' (immediate joiner) (Q: {question_text[:50]})")
                                    clicked = True
                                    break
                                elif notice_days <= 15 and ("15" in t_lower or "immediate" in t_lower or "less" in t_lower):
                                    await chip_items.nth(idx).click()
                                    logger.info(f"    ✓ Clicked chip '{text}' (notice={notice_days}d) (Q: {question_text[:50]})")
                                    clicked = True
                                    break
                                elif notice_days <= 30 and ("30" in t_lower or "1 month" in t_lower):
                                    await chip_items.nth(idx).click()
                                    logger.info(f"    ✓ Clicked chip '{text}' (notice={notice_days}d) (Q: {question_text[:50]})")
                                    clicked = True
                                    break
                                elif notice_days <= 60 and ("60" in t_lower or "2 month" in t_lower):
                                    await chip_items.nth(idx).click()
                                    logger.info(f"    ✓ Clicked chip '{text}' (notice={notice_days}d) (Q: {question_text[:50]})")
                                    clicked = True
                                    break
                    
                    # D. Career break / gap questions → answer "No" (most users aren't on breaks)
                    if not clicked and any(kw in q_lower for kw in ["career break", "career gap", "on a break", "employment gap"]):
                        for idx, text in chip_texts:
                            if text.lower() == "no":
                                await chip_items.nth(idx).click()
                                logger.info(f"    ✓ Clicked chip 'No' (career break) (Q: {question_text[:50]})")
                                clicked = True
                                break
                    
                    # E. Simple Yes/No — try "Yes" first
                    if not clicked:
                        for idx, text in chip_texts:
                            if text.lower() == "yes":
                                await chip_items.nth(idx).click()
                                logger.info(f"    ✓ Clicked chip 'Yes' (Q: {question_text[:50]})")
                                clicked = True
                                break
                    
                    # F. Try AI-determined best answer
                    if not clicked:
                        try:
                            ai_answer = await self._determine_answer_ai(question_text, user_profile,
                                [t for _, t in chip_texts])
                            if ai_answer:
                                for idx, text in chip_texts:
                                    if text.lower() == ai_answer.lower():
                                        await chip_items.nth(idx).click()
                                        logger.info(f"    ✓ Clicked chip '{text}' (AI) (Q: {question_text[:50]})")
                                        clicked = True
                                        break
                        except Exception:
                            pass
                    
                    # G. Click first NON-skip chip
                    if not clicked:
                        for idx, text in chip_texts:
                            if text.lower() not in skip_words:
                                await chip_items.nth(idx).click()
                                logger.info(f"    ✓ Clicked chip '{text}' (Q: {question_text[:50]})")
                                clicked = True
                                break
                    
                    # H. Last resort: click first chip (even if skip)
                    if not clicked and chip_texts:
                        idx, text = chip_texts[0]
                        await chip_items.nth(idx).click()
                        logger.info(f"    ✓ Clicked chip '{text}' (fallback) (Q: {question_text[:50]})")
                    
                    answered_count += 1
                    await self.browser_manager.human_delay(1, 2)
                    
                    # Chips may auto-submit (no Save needed)
                    # Check if chatbot already closed or moved to next Q
                    if await self._check_application_confirmation():
                        return {"status": "applied", "message": "Applied via questionnaire"}
                    
                    # Try Save only if chatbot still active and Save enabled
                    try:
                        save_div = ctx.locator("div.sendMsg")
                        if await save_div.count() > 0:
                            parent_class = await save_div.first.locator("..").get_attribute("class") or ""
                            if "disabled" not in parent_class:
                                await self._click_save_button(ctx)
                            else:
                                logger.info("    ℹ Save disabled after chip click (auto-submitted)")
                    except Exception:
                        pass
                    continue
            except Exception:
                pass
            
            # ── STEP 3: Handle Text input ("Type message here..." + Save) ──
            # Naukri chatbot input is a contenteditable DIV, not <input>!
            # <div class="textArea" contenteditable="true" data-placeholder="Type message here..."></div>
            try:
                chat_input = ctx.locator(
                    "div.textArea[contenteditable='true'], "
                    "div[data-placeholder*='message' i][contenteditable], "
                    "div[contenteditable='true'][data-placeholder], "
                    "input[placeholder*='message' i], "
                    "textarea[placeholder*='message' i]"
                )
                
                if await chat_input.count() > 0 and await chat_input.first.is_visible(timeout=2000):
                    # Read the question
                    question_text = await self._get_latest_chatbot_question_ctx(ctx)
                    
                    if question_text == last_question and step > 0:
                        same_q_count += 1
                        if same_q_count > 3:
                            # Stuck on same question — skip this job
                            logger.warning(f"    ❌ Stuck on same question {same_q_count}x, skipping...")
                            break
                        # Re-read with a longer wait (new Q might not have loaded yet)
                        await self.browser_manager.human_delay(1, 2)
                        question_text = await self._get_latest_chatbot_question_ctx(ctx)
                        if question_text == last_question:
                            # Still same — try re-typing and saving
                            answer = self._determine_answer(question_text, user_profile)
                            await chat_input.first.click()
                            try:
                                await chat_input.first.fill(answer)
                            except Exception:
                                await chat_input.first.evaluate("el => el.textContent = ''")
                                await self._page.keyboard.type(answer, delay=30)
                            logger.info(f"    ⚠ Re-typed: '{answer}' (retry {same_q_count})")
                            await self.browser_manager.human_delay(0.5, 1)
                            await self._click_save_button(ctx)
                            continue
                    else:
                        same_q_count = 0  # reset counter on new question
                    
                    last_question = question_text
                    
                    # For questions where we have reliable profile data,
                    # use keyword matching FIRST (AI can hallucinate names etc.)
                    q_lower_check = question_text.lower()
                    has_profile_data = any(kw in q_lower_check for kw in [
                        "location", "city", "residing", "relocat",  # current_city
                        "salary", "ctc", "compensation", "lpa", "package",  # CTC
                        "notice period", "notice",  # notice period
                        "experience", "year",  # experience years
                        "career break", "gap",  # career break
                    ])
                    
                    if has_profile_data:
                        # Keyword first (reliable), AI fallback
                        answer = self._determine_answer(question_text, user_profile)
                        if answer in ["Yes", "Open to relocation"]:
                            # Generic fallback — try AI for better answer
                            ai_answer = await self._determine_answer_ai(question_text, user_profile)
                            if ai_answer:
                                answer = ai_answer
                    else:
                        # AI first (creative), keyword fallback
                        answer = await self._determine_answer_ai(question_text, user_profile)
                        if not answer:
                            answer = self._determine_answer(question_text, user_profile)
                    
                    # Type into the contenteditable div
                    await chat_input.first.click()
                    await self.browser_manager.human_delay(0.3, 0.5)
                    
                    # Clear existing text and type answer
                    try:
                        await chat_input.first.fill(answer)
                    except Exception:
                        # Fallback for contenteditable: use JS + keyboard
                        await chat_input.first.evaluate("el => el.textContent = ''")
                        await self._page.keyboard.type(answer, delay=30)
                    
                    logger.info(f"    ✓ Typed: '{answer}' (Q: {question_text[:60]})")
                    
                    await self.browser_manager.human_delay(0.5, 1)
                    
                    # Click "Save" div (this is how Naukri chatbot works!)
                    await self._click_save_button(ctx)
                    
                    answered_count += 1
                    continue
            except Exception:
                pass
            
            # ── STEP 4: Handle dropdowns ──
            try:
                selects = ctx.locator("select")
                if await selects.count() > 0:
                    await selects.first.select_option(index=1)
                    logger.info("    ✓ Selected dropdown option")
                    answered_count += 1
                    await self.browser_manager.human_delay(0.5, 1)
                    await self._click_save_button(ctx)
                    continue
            except Exception:
                pass
            
            # ── STEP 4.5: Handle Date Picker (MM/YYYY Calendar) ──
            # Naukri chatbot uses a custom calendar widget: div.desktop-calender
            try:
                calendar_container = ctx.locator(
                    "div.desktop-calender, "
                    "div.calendar-container"
                )
                if await calendar_container.count() > 0:
                    question_text = await self._get_latest_chatbot_question_ctx(ctx)
                    logger.info(f"    📅 Date picker detected (Q: {question_text[:50]})")
                    
                    # Click the calendar icon to open the picker
                    cal_icon = ctx.locator(
                        "span.cc__calendar-icon, "
                        "span.chatBot-calendar"
                    )
                    if await cal_icon.count() > 0:
                        await cal_icon.first.click()
                        await self.browser_manager.human_delay(0.5, 1)
                    
                    # Determine which date to pick based on question
                    # For career break / gap questions → pick recent date (current month)
                    # For general date questions → pick current month/year
                    import datetime
                    now = datetime.datetime.now()
                    current_month_short = now.strftime("%b")  # e.g. "Apr"
                    current_year = str(now.year)  # e.g. "2026"
                    
                    # Check if calendar box is visible, if not click icon again
                    cal_box = ctx.locator("div.cc__calendar-box")
                    if await cal_box.count() > 0:
                        # Check if it has d-none class (hidden)
                        cal_class = await cal_box.first.get_attribute("class") or ""
                        if "d-none" in cal_class:
                            if await cal_icon.count() > 0:
                                await cal_icon.first.click()
                                await self.browser_manager.human_delay(0.5, 1)
                    
                    # Step 1: Select Month — click the month that matches current month
                    month_items = ctx.locator("div.cc__calendar-month span.cc__calendar-month-text")
                    month_count = await month_items.count()
                    month_clicked = False
                    if month_count > 0:
                        for i in range(month_count):
                            try:
                                m_text = (await month_items.nth(i).inner_text()).strip()
                                if m_text.lower().startswith(current_month_short.lower()[:3]):
                                    await month_items.nth(i).click()
                                    logger.info(f"    ✓ Selected month: {m_text}")
                                    month_clicked = True
                                    break
                            except Exception:
                                continue
                        if not month_clicked:
                            # Fallback: click current month indicator
                            current_m = ctx.locator("span.cc__calendar-month-current")
                            if await current_m.count() > 0:
                                await current_m.first.click()
                                logger.info("    ✓ Selected current month (highlight)")
                                month_clicked = True
                    
                    await self.browser_manager.human_delay(0.3, 0.5)
                    
                    # Step 2: Select Year — click year tab, then current year
                    year_nav = ctx.locator("#cc__year-navitem, div#cc__year-navitem")
                    if await year_nav.count() > 0:
                        await year_nav.first.click()
                        await self.browser_manager.human_delay(0.3, 0.5)
                        
                        year_items = ctx.locator("div.cc__calendar-year span.cc__calendar-year-text")
                        year_count = await year_items.count()
                        year_clicked = False
                        if year_count > 0:
                            for i in range(year_count):
                                try:
                                    y_text = (await year_items.nth(i).inner_text()).strip()
                                    if y_text == current_year:
                                        await year_items.nth(i).click()
                                        logger.info(f"    ✓ Selected year: {y_text}")
                                        year_clicked = True
                                        break
                                except Exception:
                                    continue
                            if not year_clicked:
                                # Fallback: click current year indicator
                                current_y = ctx.locator("span.cc__calendar-year-current")
                                if await current_y.count() > 0:
                                    await current_y.first.click()
                                    logger.info("    ✓ Selected current year (highlight)")
                    
                    answered_count += 1
                    await self.browser_manager.human_delay(0.5, 1)
                    
                    # Click Save after selecting date
                    await self._click_save_button(ctx)
                    continue
            except Exception:
                pass
            
            # ── NOTHING FOUND — debug and break ──
            if await self._check_application_confirmation():
                return {"status": "applied", "message": "Applied (late confirmation)"}
            
            # Debug logging
            try:
                logger.warning(
                    f"  Step {step+1}: No interactive elements found. "
                    f"Frames: {len(self._page.frames)}, iframe: {use_iframe}, "
                    f"answered: {answered_count}"
                )
                # Dump what we can see in chatbot
                for sel_name, sel in [
                    ("div.sendMsg", "div.sendMsg"),
                    ("InputDiv", "div.textArea[contenteditable]"),
                    ("Radio", "input.ssrc__radio"),
                    ("Chips", "div.chatbot_Chip"),
                    ("Checkbox", "input[type='checkbox']"),
                    ("Any label", "label.ssrc__label"),
                    ("Send container", "div.sendMsgbtn_container"),
                ]:
                    try:
                        c = await ctx.locator(sel).count()
                        if c > 0:
                            logger.warning(f"  DEBUG: {sel_name} = {c} found")
                    except Exception:
                        pass
                # Also dump chatbot container visibility
                try:
                    container_html = await ctx.evaluate("el => el.className")
                    logger.warning(f"  DEBUG: ctx class = {container_html}")
                except Exception:
                    pass
            except Exception:
                pass
            
            break

        return {"status": "applied", "message": "Questionnaire handled (best effort)"}

    # ══════════════════════════════════════════════════
    # CHATBOT HELPER METHODS
    # ══════════════════════════════════════════════════

    async def _click_save_button(self, ctx):
        """Click the 'Save' div in Naukri chatbot.
        
        The Save is a <div class="sendMsg" tabindex="0">Save</div>
        NOT a <button>! Its parent div has class "send disabled" when
        inactive and "send" (no disabled) when active.
        
        We use force=True fallback to bypass overlay interception.
        """
        try:
            # Primary: exact Naukri chatbot Save div
            save_div = ctx.locator(
                "div.sendMsg, "
                "div[class='sendMsg']"
            )
            
            if await save_div.count() > 0:
                # Wait for parent to lose "disabled" class
                await self.browser_manager.human_delay(0.5, 1)
                
                try:
                    # Check if parent still has "disabled" class
                    parent_class = await save_div.first.locator("..").get_attribute("class") or ""
                    if "disabled" in parent_class:
                        logger.info("    ⏳ Save button still disabled, waiting...")
                        await self.browser_manager.human_delay(1, 2)
                except Exception:
                    pass
                
                try:
                    await save_div.first.click(timeout=3000)
                    logger.info("    ✓ Clicked 'Save' (div.sendMsg)")
                except Exception:
                    try:
                        await save_div.first.click(force=True)
                        logger.info("    ✓ Clicked 'Save' (force)")
                    except Exception:
                        try:
                            await save_div.first.dispatch_event("click")
                            logger.info("    ✓ Clicked 'Save' (dispatch)")
                        except Exception as e:
                            err_msg = str(e)[:80]
                            logger.warning(f"    ⚠ div.sendMsg click failed: {err_msg}")
                
                await self.browser_manager.human_delay(2, 3)
                return
            
            # Fallback: try button-based Save (some companies may differ)
            save_btn = ctx.locator(
                "button:has-text('Save'), "
                "button:has-text('Submit'), "
                "button:has-text('Next'), "
                "button[type='submit']"
            )
            if await save_btn.count() > 0:
                await self.browser_manager.human_delay(0.5, 1)
                try:
                    await save_btn.first.click(timeout=3000)
                    logger.info("    ✓ Clicked Save button (fallback)")
                except Exception:
                    await save_btn.first.click(force=True)
                    logger.info("    ✓ Clicked Save button (force fallback)")
                await self.browser_manager.human_delay(2, 3)
                return
            
            # Last resort: Enter key
            logger.warning("    ⚠ No Save element found, trying Enter key")
            await self._page.keyboard.press("Enter")
            await self.browser_manager.human_delay(1, 2)
            
        except Exception as e:
            logger.warning(f"    ⚠ Save error: {e}")
            try:
                await self._page.keyboard.press("Enter")
                await self.browser_manager.human_delay(1, 2)
            except Exception:
                pass

    async def _get_latest_chatbot_question(self) -> str:
        """Read the latest question text from the Naukri chatbot bubbles."""
        try:
            # Chatbot messages appear in bubble-like divs
            # We need the LAST message from the bot (not from the user)
            all_messages = self._page.locator(
                "div[class*='chatbot'] div[class*='message'], "
                "div[class*='chat'] div[class*='msg'], "
                "div[class*='chat'] p, "
                "div[class*='chatbot'] p, "
                "div.bot-message, "
                "div[class*='bot-msg'], "
                "div[class*='recruiter']"
            )
            count = await all_messages.count()
            if count > 0:
                # Get the last message text
                last_msg = await all_messages.nth(count - 1).inner_text()
                return last_msg.strip()
            
            # Fallback: try to get any visible text near the chat input
            visible_text = self._page.locator(
                "div[class*='chatbot']:visible, "
                "div[class*='chat-window']:visible"
            )
            if await visible_text.count() > 0:
                full_text = await visible_text.first.inner_text()
                # Get the last meaningful line
                lines = [l.strip() for l in full_text.split("\n") if l.strip() and len(l.strip()) > 10]
                if lines:
                    return lines[-1]
        except Exception:
            pass
        return ""

    async def _get_latest_chatbot_question_ctx(self, ctx) -> str:
        """Read the latest chatbot question from the chatbot's message container.
        
        Naukri chatbot structure:
          div.chatbot_MessageContainer
            div (bot message bubble)
            div (user answer bubble)
            div (bot message bubble)  ← we want the LAST bot message
        
        We look for the last text element that's long enough to be a question,
        skipping user answers, labels, and short UI texts.
        """
        try:
            # Try specific Naukri chatbot message container
            msg_container = ctx.locator(
                "div[class*='chatbot_MessageContainer'], "
                "div[class*='MessageContainer'], "
                "div[id*='Messages']"
            )
            
            if await msg_container.count() > 0:
                # Get all direct children (each is a message bubble)
                full_text = await msg_container.first.inner_text()
                lines = [l.strip() for l in full_text.split("\n") if l.strip()]
                
                # Find the last line that looks like a question
                # (skip short lines, radio labels like 'Yes'/'No', timestamps)
                for line in reversed(lines):
                    if (
                        len(line) > 20
                        and line.lower() not in ["yes", "no", "skip", "skip this question", "save"]
                        and "type message" not in line.lower()
                        and not line.startswith("http")
                    ):
                        return line
            
            # Fallback: search within ctx directly
            # Get all text elements, find the longest recent one
            all_text = await ctx.inner_text()
            lines = [l.strip() for l in all_text.split("\n") if l.strip()]
            for line in reversed(lines):
                if (
                    len(line) > 20
                    and line.lower() not in ["yes", "no", "skip", "skip this question", "save"]
                    and "type message" not in line.lower()
                ):
                    return line
                    
        except Exception:
            pass
        
        return ""

    def _determine_answer(self, question: str, user_profile: dict | None) -> str:
        """Determine the best answer for a chatbot question.
        Uses keyword matching for fast, reliable answers.
        """
        q = question.lower()
        
        # Experience / years
        if any(kw in q for kw in ["experience", "year", "years of exp"]):
            exp = str(user_profile.get("experience_years", 1)) if user_profile else "1"
            return f"{exp} years"
        
        # Salary / CTC
        if any(kw in q for kw in ["salary", "ctc", "compensation", "lakh", "lpa", "package"]):
            if user_profile:
                # Distinguish current vs expected CTC
                if any(kw in q for kw in ["current", "present", "existing", "last drawn"]):
                    ctc = user_profile.get("current_ctc")
                    if ctc:
                        return f"{ctc} LPA"
                if any(kw in q for kw in ["expected", "desired", "asking"]):
                    ctc = user_profile.get("expected_ctc")
                    if ctc:
                        return f"{ctc} LPA"
                # Generic CTC question — give expected if available, else current
                expected = user_profile.get("expected_ctc")
                current = user_profile.get("current_ctc")
                if expected:
                    return f"{expected} LPA"
                if current:
                    return f"{current} LPA"
            return "Negotiable"
        
        # Notice period
        if any(kw in q for kw in ["notice period", "notice", "serving notice"]):
            if user_profile:
                days = user_profile.get("notice_period_days")
                if days is not None:
                    if days == 0:
                        return "Immediate"
                    return f"{days} days"
            return "30 days"
        
        # Joining / availability / immediately / LWD
        if any(kw in q for kw in ["joining", "immediately", "lwd", "last working", "available", "start date", "join"]):
            return "Yes, I can join immediately"
        
        # Location / relocation / city
        if any(kw in q for kw in ["location", "city", "relocat", "willing to relocate", "current location", "residing"]):
            if user_profile:
                city = user_profile.get("current_city") or user_profile.get("location", "")
                if city:
                    return city
            return "Open to relocation"
        
        # Work from office / remote / hybrid
        if any(kw in q for kw in ["work from office", "wfo", "remote", "hybrid", "onsite", "on-site"]):
            return "Yes, I am comfortable with any work mode"
        
        # Skills / technology specific  
        if any(kw in q for kw in ["proficien", "skill", "technology", "tech stack", "framework"]):
            return "Yes, I have relevant experience"
        
        # Education / degree
        if any(kw in q for kw in ["education", "degree", "qualification", "graduate"]):
            edu = user_profile.get("education", "B.Tech in Computer Science") if user_profile else "B.Tech in Computer Science"
            return edu
        
        # PAN / Aadhaar / ID
        if any(kw in q for kw in ["pan", "aadhaar", "aadhar", "passport"]):
            return "Will provide upon selection"
        
        # Confirm / agree / consent
        if any(kw in q for kw in ["confirm", "agree", "consent", "accept"]):
            return "Yes, I confirm"
        
        # Gender
        if "gender" in q:
            return "Male"
        
        # Career break
        if any(kw in q for kw in ["career break", "gap", "unemployed"]):
            return "No"
        
        # Generic fallback — short affirmative answer
        return "Yes"

    async def _determine_answer_ai(
        self, question: str, user_profile: dict | None,
        options: list[str] | None = None
    ) -> str | None:
        """Use LLM to determine the best answer for a chatbot question.
        
        Args:
            question: The chatbot question text
            user_profile: User's profile dict
            options: Available chip/radio options (if any)
            
        Returns:
            Best answer string, or None if LLM unavailable/failed
        """
        if not LLM_AVAILABLE:
            return None
        
        try:
            profile_text = ""
            if user_profile:
                parts = []
                for key in ["name", "full_name", "experience_years", "skills",
                            "location", "education", "current_role", "summary",
                            "phone", "linkedin_url"]:
                    val = user_profile.get(key)
                    if val:
                        if isinstance(val, list):
                            parts.append(f"{key}: {', '.join(str(v) for v in val)}")
                        else:
                            parts.append(f"{key}: {val}")
                # Add CTC and notice period with clear labels
                if user_profile.get("current_ctc"):
                    parts.append(f"Current CTC: {user_profile['current_ctc']} LPA")
                if user_profile.get("expected_ctc"):
                    parts.append(f"Expected CTC: {user_profile['expected_ctc']} LPA")
                if user_profile.get("notice_period_days") is not None:
                    days = user_profile["notice_period_days"]
                    parts.append(f"Notice Period: {days} days" if days > 0 else "Notice Period: Immediate joiner")
                profile_text = "\n".join(parts)
            
            prompt = (
                "You are answering a job application chatbot question on behalf of a candidate.\n"
                "Answer concisely (1-5 words for simple questions, 1-2 sentences max for others).\n"
                "Be positive and professional. Lean towards answers that help get the job.\n\n"
            )
            if profile_text:
                prompt += f"Candidate Profile:\n{profile_text}\n\n"
            
            prompt += f"Question: {question}\n"
            
            if options:
                prompt += f"Available Options: {', '.join(options)}\n"
                prompt += "Pick ONE of the available options exactly as written. Do NOT skip unless no option fits.\n"
            
            prompt += "\nAnswer (just the answer, no explanation):"
            
            response = await llm_client.chat.completions.create(
                model=llm_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=50,
            )
            
            answer = response.choices[0].message.content.strip()
            # Clean up quotes if LLM wrapped it
            answer = answer.strip('"').strip("'").strip()
            if answer:
                logger.info(f"    🤖 AI answer: '{answer}'")
                return answer
        except Exception as e:
            logger.debug(f"    AI answer failed (using keyword fallback): {str(e)[:60]}")
        
        return None

    async def _pick_best_option(
        self, buttons, count: int, question: str, user_profile: dict | None
    ):
        """Pick the best option button from chatbot choices based on question context.
        
        Returns the Playwright Locator for the best button, or None.
        """
        q = question.lower()
        
        # Collect all option texts
        options = []
        for i in range(count):
            try:
                text = (await buttons.nth(i).inner_text()).strip()
                options.append((i, text, text.lower()))
            except Exception:
                continue
        
        if not options:
            return None
        
        # ── Notice Period ──
        if any(kw in q for kw in ["notice", "notice period", "serving notice"]):
            # Use actual notice_period_days from profile
            notice_days = user_profile.get("notice_period_days") if user_profile else None
            
            if notice_days is not None:
                if notice_days == 0:
                    # Immediate joiner — pick shortest option
                    for idx, text, lower in options:
                        if "immediate" in lower or "0" in lower or "currently" in lower:
                            return buttons.nth(idx)
                    for idx, text, lower in options:
                        if "15" in lower or "less" in lower:
                            return buttons.nth(idx)
                elif notice_days <= 15:
                    for idx, text, lower in options:
                        if "15" in lower or "less" in lower or "immediate" in lower:
                            return buttons.nth(idx)
                elif notice_days <= 30:
                    for idx, text, lower in options:
                        if "30" in lower or "1 month" in lower or "one month" in lower:
                            return buttons.nth(idx)
                elif notice_days <= 60:
                    for idx, text, lower in options:
                        if "60" in lower or "2 month" in lower or "two month" in lower:
                            return buttons.nth(idx)
                elif notice_days <= 90:
                    for idx, text, lower in options:
                        if "90" in lower or "3 month" in lower or "three month" in lower:
                            return buttons.nth(idx)
            
            # Fallback: pick shortest available
            for idx, text, lower in options:
                if "immediate" in lower or "15" in lower or "less" in lower:
                    return buttons.nth(idx)
            return buttons.nth(options[0][0])
        
        # ── Experience related ──
        if any(kw in q for kw in ["experience", "years", "year"]):
            exp_years = user_profile.get("experience_years", 1) if user_profile else 1
            exp_str = str(exp_years)
            for idx, text, lower in options:
                if exp_str in lower:
                    return buttons.nth(idx)
            # Pick first option as fallback
            return buttons.nth(options[0][0])
        
        # ── Salary / CTC ──
        if any(kw in q for kw in ["salary", "ctc", "lpa", "lakh", "package"]):
            # Try to match actual CTC range from profile
            if user_profile:
                expected = user_profile.get("expected_ctc")
                current = user_profile.get("current_ctc")
                ctc_val = expected or current
                if ctc_val:
                    ctc_str = str(ctc_val)
                    for idx, text, lower in options:
                        if ctc_str in lower:
                            return buttons.nth(idx)
            # Pick "Negotiable" if available, else first option
            for idx, text, lower in options:
                if "negotiable" in lower:
                    return buttons.nth(idx)
            return buttons.nth(options[0][0])
        
        # ── Location / relocation ──
        if any(kw in q for kw in ["location", "relocat", "city"]):
            loc = user_profile.get("location", "delhi") if user_profile else "delhi"
            loc_lower = loc.lower()
            for idx, text, lower in options:
                if loc_lower in lower:
                    return buttons.nth(idx)
            # Pick "Yes" if asking about relocation willingness
            if "relocat" in q:
                for idx, text, lower in options:
                    if "yes" in lower:
                        return buttons.nth(idx)
            return buttons.nth(options[0][0])
        
        # ── Joining / availability ──
        if any(kw in q for kw in ["join", "immediately", "available", "start"]):
            for idx, text, lower in options:
                if "immediate" in lower or "yes" in lower or "15" in lower:
                    return buttons.nth(idx)
            return buttons.nth(options[0][0])
        
        # ── Generic Yes/No ──
        for idx, text, lower in options:
            if lower == "yes" or lower.startswith("yes"):
                return buttons.nth(idx)
        
        # Ultimate fallback: pick first option
        return buttons.nth(options[0][0])

    # ══════════════════════════════════════════════════
    # SESSION MANAGEMENT
    # ══════════════════════════════════════════════════

    async def save_session(self, filepath: str) -> None:
        """Save Naukri session cookies for reuse."""
        if not self.browser_manager._context:
            return

        safe_name = filepath.replace("@", "_at_").replace(".", "_")
        session_path = SESSIONS_DIR / f"naukri_{safe_name}.json"

        storage = await self.browser_manager._context.storage_state()

        session_data = {
            "storage_state": storage,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }

        session_path.write_text(json.dumps(session_data, indent=2))
        logger.info(f"Session saved: {session_path.name}")

    async def load_session(self, filepath: str) -> bool:
        """Load a saved Naukri session."""
        safe_name = filepath.replace("@", "_at_").replace(".", "_")
        session_path = SESSIONS_DIR / f"naukri_{safe_name}.json"

        if not session_path.exists():
            logger.info("No saved Naukri session found")
            return False

        try:
            session_data = json.loads(session_path.read_text())

            saved_at = datetime.fromisoformat(session_data["saved_at"])
            age_hours = (datetime.now(timezone.utc) - saved_at).total_seconds() / 3600

            if age_hours > 24:
                logger.info(f"Session expired ({age_hours:.1f}h old) — will re-login")
                session_path.unlink()
                return False

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

            logger.info(f"Naukri session loaded ({age_hours:.1f}h old)")
            return True

        except Exception as e:
            logger.error(f"Failed to load session: {e}")
            return False

    async def close(self) -> None:
        """Clean up browser resources."""
        await self.browser_manager.close()
        self._page = None
        self._is_logged_in = False
        logger.info("Naukri adapter closed")

    # ══════════════════════════════════════════════════
    # PRIVATE HELPERS
    # ══════════════════════════════════════════════════

    def _build_search_url(self, keywords: str, location: str | None = None) -> str:
        """Build Naukri job search URL."""
        from urllib.parse import quote_plus

        # Naukri URL format: /keyword1-keyword2-jobs-in-location
        kw_slug = keywords.strip().replace(" ", "-").lower()
        url = f"https://www.naukri.com/{quote_plus(kw_slug)}-jobs"

        if location and location.strip():
            loc_slug = location.strip().replace(" ", "-").lower()
            url += f"-in-{quote_plus(loc_slug)}"

        # Sort by date (most recent first)
        url += "?sortBy=date"

        return url

    async def _extract_job_cards(self, filter_external: bool = False) -> tuple[list[JobListing], int]:
        """Extract job listings from the current Naukri search results page.
        
        Returns:
            Tuple of (jobs, external_count) where external_count is the number
            of external-apply jobs that were filtered out.
        """
        jobs = []
        external_count = 0

        card_selectors = [
            "article.jobTuple",
            "div.srp-jobtuple-wrapper",
            "div[class*='jobTuple']",
            "div.cust-job-tuple",
            "div[data-job-id]",
            "article[class*='job']",
        ]

        cards = None
        for selector in card_selectors:
            cards_el = self._page.locator(selector)
            count = await cards_el.count()
            if count > 0:
                cards = cards_el
                break

        if not cards:
            logger.warning("No job cards found on Naukri page")
            return jobs, external_count

        count = await cards.count()
        logger.info(f"  Found {count} job cards on page")

        for i in range(count):
            try:
                card = cards.nth(i)

                # ── Pre-filter external apply jobs ──
                if filter_external:
                    is_external = False
                    
                    # Check 1: "Apply on company site" text in card
                    ext_text = card.locator(
                        "span:has-text('Apply on company site'), "
                        "a:has-text('Apply on company site'), "
                        "span:has-text('company site'), "
                        "div:has-text('Apply on company site')"
                    )
                    if await ext_text.count() > 0:
                        is_external = True
                    
                    # Check 2: External link icon or "external" class
                    if not is_external:
                        ext_icon = card.locator(
                            "i[class*='external'], "
                            "span[class*='external'], "
                            "svg[class*='external'], "
                            "a[target='_blank'][class*='apply']"
                        )
                        if await ext_icon.count() > 0:
                            is_external = True
                    
                    if is_external:
                        external_count += 1
                        continue

                # Extract title
                title_el = card.locator(
                    "a.title, "
                    "a[class*='title'], "
                    "h2 a, "
                    "a[class*='jobTitle']"
                )
                title = ""
                if await title_el.count() > 0:
                    title = (await title_el.first.inner_text()).strip()

                # Extract company
                company_el = card.locator(
                    "a.comp-name, "
                    "a[class*='comp-name'], "
                    "span[class*='comp-name'], "
                    "a.subTitle"
                )
                company = ""
                if await company_el.count() > 0:
                    company = (await company_el.first.inner_text()).strip()

                # Extract location
                location_el = card.locator(
                    "span.loc, "
                    "span[class*='loc'], "
                    "li.location, "
                    "span[class*='location']"
                )
                loc = ""
                if await location_el.count() > 0:
                    loc = (await location_el.first.inner_text()).strip()

                # Extract job link
                link_el = card.locator("a[href*='job-listings'], a[href*='job/']")
                if await link_el.count() == 0:
                    link_el = card.locator("a.title, a[class*='title'], h2 a")

                job_url = ""
                job_id = ""
                if await link_el.count() > 0:
                    href = await link_el.first.get_attribute("href")
                    if href:
                        job_url = href if href.startswith("http") else f"https://www.naukri.com{href}"
                        # Extract job ID from URL (last numeric segment)
                        parts = href.rstrip("/").split("-")
                        for part in reversed(parts):
                            cleaned = part.split("?")[0]
                            if cleaned.isdigit():
                                job_id = cleaned
                                break
                        if not job_id:
                            job_id = f"nk_{i}_{random.randint(1000, 9999)}"

                # Extract description snippet
                description = None
                desc_el = card.locator(
                    "div.job-desc, "
                    "span.job-desc, "
                    "div[class*='job-desc'], "
                    "span[class*='ellipsis']"
                )
                if await desc_el.count() > 0:
                    description = (await desc_el.first.inner_text()).strip()

                # Extract salary if available
                salary_range = None
                salary_el = card.locator(
                    "span.sal, "
                    "span[class*='sal'], "
                    "li.salary, "
                    "span[class*='salary']"
                )
                if await salary_el.count() > 0:
                    sal_text = (await salary_el.first.inner_text()).strip()
                    if sal_text and sal_text != "Not disclosed":
                        salary_range = sal_text

                # Extract experience range
                job_type = None
                exp_el = card.locator(
                    "span.exp, "
                    "span[class*='exp'], "
                    "li.experience, "
                    "span[class*='experience']"
                )
                if await exp_el.count() > 0:
                    job_type = (await exp_el.first.inner_text()).strip()

                if title and job_url:
                    jobs.append(
                        JobListing(
                            platform="naukri",
                            platform_job_id=job_id,
                            title=title,
                            company=company,
                            location=loc,
                            description=description,
                            salary_range=salary_range,
                            job_type=job_type,
                            apply_url=job_url,
                            posted_date=None,
                        )
                    )

            except Exception as e:
                logger.warning(f"  Error extracting card {i}: {e}")
                continue

        return jobs, external_count

    async def _human_scroll(self) -> None:
        """Scroll the page in a human-like pattern."""
        if not self._page:
            return

        scroll_count = random.randint(3, 5)
        for _ in range(scroll_count):
            scroll_distance = random.randint(200, 500)
            await self._page.evaluate(f"window.scrollBy(0, {scroll_distance})")
            await self.browser_manager.human_delay(0.5, 1.5)

    async def _go_to_next_page(self) -> bool:
        """Click the next page button on Naukri. Returns False if no next page."""
        try:
            next_btn = self._page.locator(
                "a.fright.fs14.btn-secondary.br2, "
                "a[class*='btn-secondary']:has-text('Next'), "
                "a:has-text('Next')"
            )
            if await next_btn.count() > 0:
                await next_btn.first.click()
                await self._page.wait_for_load_state("domcontentloaded", timeout=15000)
                return True
        except Exception:
            pass
        return False

    async def _verify_login(self) -> bool:
        """Check if we're currently logged in to Naukri."""
        if not self._page:
            return False

        try:
            await self._page.goto(NAUKRI_HOME_URL, wait_until="domcontentloaded", timeout=20000)
            await self.browser_manager.human_delay(3, 5)

            current_url = self._page.url
            # If redirected to login, not logged in
            if "/nlogin" in current_url or "/login" in current_url:
                return False

            # Check for logged-in indicators
            logged_in_els = self._page.locator(
                "div.nI-gNb-drawer, "
                "a[href*='/mnjuser/homepage'], "
                "div[class*='user-info'], "
                "a[class*='nI-gNb-hp'], "
                "div.nI-gNb-sb__main"
            )
            if await logged_in_els.count() > 0:
                return True

            # Alternative: check if navbar shows user's profile icon
            profile_icon = self._page.locator(
                "div.nI-gNb-drawer__icon, "
                "img[class*='user-img'], "
                "a[title='View profile']"
            )
            if await profile_icon.count() > 0:
                return True

            return False

        except Exception:
            return False

    async def _detect_otp(self) -> bool:
        """Detect if OTP verification is required."""
        if not self._page:
            return False

        otp_indicators = [
            "input[placeholder*='OTP']",
            "input[placeholder*='otp']",
            "div:has-text('Enter OTP')",
            "span:has-text('OTP sent')",
        ]

        for selector in otp_indicators:
            try:
                if await self._page.locator(selector).count() > 0:
                    return True
            except Exception:
                continue

        return False

    async def _check_application_confirmation(self) -> bool:
        """Check if application was successfully submitted on Naukri.
        
        Real Naukri confirmations (from live testing):
        - Top-left green banner: 'Applied to "Job Title"'
        - Chatbot panel text: 'Thank you for your response'
        - Button text changes to 'Applied'
        """
        try:
            success_selectors = [
                # Real Naukri confirmation banner (green, top-left)
                "text=Applied to",
                "div:has-text('Applied to')",
                # Chatbot thank-you message after questionnaire submit
                "text=Thank you for your response",
                # Button state change
                "button:has-text('Applied')",
                # Legacy / fallback
                "div:has-text('applied successfully')",
                "div:has-text('You have successfully applied')",
            ]
            for selector in success_selectors:
                try:
                    el = self._page.locator(selector).first
                    if await el.is_visible(timeout=2000):
                        return True
                except Exception:
                    continue
        except Exception:
            pass
        return False
