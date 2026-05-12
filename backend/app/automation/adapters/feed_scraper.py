"""
AutoJob AI — LinkedIn Feed Scraper
Scrolls the user's LinkedIn feed, extracts post text from visible posts.
Used by the Feed Scanner pipeline to find job posts from connections/follows.
"""

import logging
import hashlib
import re
from dataclasses import dataclass, field

from app.automation.browser_manager import BrowserManager

logger = logging.getLogger("autojob.feed_scraper")

# Feed URL
LINKEDIN_FEED_URL = "https://www.linkedin.com/feed/"

# Safety limits
MAX_SCROLLS = 10          # Max scroll iterations (increased for deeper scanning)
MAX_POSTS_RAW = 80        # Max raw posts to extract before filtering
MAX_RELEVANT_POSTS = 30   # Max relevant posts to send to AI
SCROLL_PAUSE_MIN = 3.0    # Min pause between scrolls (seconds)
SCROLL_PAUSE_MAX = 6.0    # Max pause between scrolls (seconds)

# Common job-related keywords (always included in filter)
JOB_KEYWORDS_COMMON = [
    "hiring", "hire", "we're hiring", "we are hiring", "job opening",
    "job opportunity", "looking for", "position", "vacancy", "vacancies",
    "apply", "application", "resume", "cv", "send your", "drop your",
    "open role", "urgent requirement", "immediate joining", "walk-in",
    "recruitment", "recruiter", "talent acquisition", "career",
    "internship", "fresher", "experience required", "work from home",
    "remote", "onsite", "hybrid", "full time", "full-time", "part time",
    "contract", "freelance", "ctc", "lpa", "salary", "compensation",
]


@dataclass
class FeedPost:
    """A single LinkedIn feed post."""
    author: str
    text: str
    post_url: str
    post_id: str = ""      # Unique hash for dedup

    def __post_init__(self):
        if not self.post_id:
            # Generate deterministic ID from author+text
            content = f"{self.author}:{self.text[:200]}"
            self.post_id = hashlib.md5(content.encode()).hexdigest()[:12]


class LinkedInFeedScraper:
    """Scrolls LinkedIn feed and extracts post content with keyword pre-filtering."""

    def __init__(self, browser_manager: BrowserManager, page, user_keywords: list[str] | None = None):
        self.browser_manager = browser_manager
        self._page = page
        # Build the keyword filter from user's profile data + common job terms
        self._filter_keywords = self._build_keyword_list(user_keywords or [])

    def _build_keyword_list(self, user_keywords: list[str]) -> list[str]:
        """Build a combined lowercase keyword list from user profile + common job terms."""
        combined = set()
        # Add user's preferred roles and skills (lowercase)
        for kw in user_keywords:
            kw_lower = kw.strip().lower()
            if kw_lower:
                combined.add(kw_lower)
                # Also add individual words from multi-word terms
                # e.g. "React Developer" → "react", "developer"
                for word in kw_lower.split():
                    if len(word) >= 3:  # Skip tiny words like "ai", "ui"
                        combined.add(word)
        # Add common job-related keywords
        for kw in JOB_KEYWORDS_COMMON:
            combined.add(kw.lower())
        logger.info(f"🔑 Filter keywords ({len(combined)}): {sorted(list(combined))[:20]}...")
        return list(combined)

    def _is_relevant(self, text: str) -> bool:
        """Check if a post's text contains any user-relevant keyword."""
        text_lower = text.lower()
        for kw in self._filter_keywords:
            if kw in text_lower:
                return True
        return False

    async def scroll_and_extract(self) -> list[FeedPost]:
        """
        Navigate to feed, scroll human-like, extract posts, and pre-filter by keywords.

        Returns:
            List of FeedPost objects matching user's profile keywords.
        """
        logger.info("📜 Navigating to LinkedIn feed...")

        try:
            # LinkedIn sometimes redirects /feed/ to / mid-navigation (especially new accounts)
            for attempt in range(1, 4):
                try:
                    logger.info(f"  Attempt {attempt}/3 to load feed...")
                    await self._page.goto(LINKEDIN_FEED_URL, wait_until="load", timeout=30000)
                    await self.browser_manager.human_delay(3, 5)

                    current_url = self._page.url
                    if "/feed" in current_url:
                        logger.info("  ✅ Feed page loaded successfully")
                        break
                    else:
                        logger.warning(f"  Redirected to {current_url}, retrying...")
                        await self.browser_manager.human_delay(3, 5)
                        continue

                except Exception as nav_err:
                    logger.warning(f"  Navigation attempt {attempt} failed: {nav_err}")
                    if attempt < 3:
                        await self.browser_manager.human_delay(3, 5)
                        continue
                    else:
                        raise nav_err

            if "/feed" not in self._page.url:
                logger.error(f"Could not reach feed after 3 attempts (on: {self._page.url})")
                return []

        except Exception as e:
            logger.error(f"Failed to load feed: {e}")
            return []

        all_raw_posts: list[FeedPost] = []
        relevant_posts: list[FeedPost] = []
        seen_ids: set[str] = set()
        skipped_count = 0
        no_new_streak = 0  # Track consecutive scrolls with 0 new posts

        for scroll_num in range(1, MAX_SCROLLS + 1):
            logger.info(f"  Scroll {scroll_num}/{MAX_SCROLLS}...")

            # Extract posts currently visible on screen
            new_posts = await self._extract_visible_posts(seen_ids)
            all_raw_posts.extend(new_posts)

            # Pre-filter: only keep posts matching user's keywords
            for post in new_posts:
                if self._is_relevant(post.text):
                    relevant_posts.append(post)
                else:
                    skipped_count += 1

            logger.info(
                f"  Raw: {len(new_posts)} new | "
                f"Relevant: {len(relevant_posts)} total | "
                f"Skipped: {skipped_count} irrelevant"
            )

            # Track consecutive empty scrolls
            if len(new_posts) == 0:
                no_new_streak += 1
                if no_new_streak >= 3:
                    logger.info("  ⏹️ 3 scrolls with no new posts — stopping early")
                    break
            else:
                no_new_streak = 0

            # Stop if we've found enough relevant posts
            if len(relevant_posts) >= MAX_RELEVANT_POSTS:
                logger.info(f"  ✅ Found enough relevant posts ({MAX_RELEVANT_POSTS})")
                break

            # Stop if we've scraped too many raw posts
            if len(all_raw_posts) >= MAX_POSTS_RAW:
                logger.info(f"  Reached raw posts limit ({MAX_POSTS_RAW})")
                break

            # Scroll down and wait for new content to load
            await self._human_scroll()
            await self.browser_manager.human_delay(SCROLL_PAUSE_MIN, SCROLL_PAUSE_MAX)

        logger.info(
            f"✅ Feed scan complete: {len(all_raw_posts)} raw posts → "
            f"{len(relevant_posts)} relevant (skipped {skipped_count} irrelevant)"
        )
        return relevant_posts[:MAX_RELEVANT_POSTS]

    async def _extract_visible_posts(self, seen_ids: set[str]) -> list[FeedPost]:
        """Extract post text from currently visible feed items."""
        posts = []

        try:
            # ── Strategy 1: Try multiple known LinkedIn selectors ──
            post_selectors = [
                # Modern LinkedIn (2025-2026)
                "div.feed-shared-update-v2",
                "div[data-urn*='activity']",
                "div[data-id*='urn:li:activity']",
                # Older LinkedIn
                "div.occludable-update",
                # Generic feed containers
                "div[class*='feed-shared-update']",
                "div[class*='update-components']",
                "article[class*='feed']",
                # Very generic — any main feed item
                "main div[data-urn]",
            ]

            matched_selector = None
            containers = None

            for selector in post_selectors:
                loc = self._page.locator(selector)
                count = await loc.count()
                if count > 0:
                    logger.info(f"    ✅ Selector matched: '{selector}' → {count} elements")
                    containers = loc
                    matched_selector = selector
                    break
                else:
                    logger.debug(f"    ❌ Selector miss: '{selector}'")

            # ── Strategy 2: JS-based fallback — find containers with text > 50 chars ──
            if containers is None or await containers.count() == 0:
                logger.warning("    ⚠️ No standard selectors matched. Trying JS-based extraction...")

                # Dump actual class names at the top level of feed for debugging
                debug_classes = await self._page.evaluate("""
                    () => {
                        const main = document.querySelector('main') || document.body;
                        const children = main.querySelectorAll(':scope > div > div > div');
                        const classes = [];
                        for (let i = 0; i < Math.min(children.length, 15); i++) {
                            classes.push({
                                tag: children[i].tagName,
                                className: children[i].className?.substring(0, 120) || '',
                                textLen: children[i].innerText?.length || 0,
                                dataUrn: children[i].getAttribute('data-urn') || ''
                            });
                        }
                        return classes;
                    }
                """)
                logger.info(f"    🔍 DOM Debug — top-level containers: {debug_classes}")

                # JS fallback: grab all divs that look like feed posts
                js_posts = await self._page.evaluate("""
                    () => {
                        const results = [];
                        // Look for any div with data-urn attribute (LinkedIn's post identifier)
                        let candidates = document.querySelectorAll('[data-urn]');
                        
                        // If no data-urn, try divs inside main with substantial text
                        if (candidates.length === 0) {
                            const main = document.querySelector('main');
                            if (main) {
                                candidates = main.querySelectorAll('div');
                            }
                        }

                        const seen = new Set();
                        for (const el of candidates) {
                            const text = el.innerText?.trim() || '';
                            // Only consider posts with meaningful text (50+ chars)
                            if (text.length < 50 || text.length > 5000) continue;
                            
                            // Deduplicate by first 100 chars
                            const key = text.substring(0, 100);
                            if (seen.has(key)) continue;
                            seen.add(key);

                            // Try to extract author (usually first bold/link text)
                            let author = '';
                            const nameEl = el.querySelector('span[class*="actor__name"], a[class*="actor"] span, span[class*="name"]');
                            if (nameEl) author = nameEl.innerText?.trim() || '';

                            // Try to extract post URL
                            let postUrl = '';
                            const linkEl = el.querySelector('a[href*="/posts/"], a[href*="/activity/"], a[href*="/feed/update/"]');
                            if (linkEl) postUrl = linkEl.href || '';

                            results.push({ author, text, postUrl });
                            if (results.length >= 100) break;
                        }
                        return results;
                    }
                """)

                if js_posts:
                    logger.info(f"    📦 JS fallback found {len(js_posts)} candidate posts")
                    for jp in js_posts:
                        post = FeedPost(
                            author=jp.get("author", ""),
                            text=jp.get("text", ""),
                            post_url=jp.get("postUrl", ""),
                        )
                        if post.post_id not in seen_ids and len(post.text) >= 30:
                            seen_ids.add(post.post_id)
                            posts.append(post)
                    return posts
                else:
                    logger.warning("    ⚠️ JS fallback also found 0 posts")
                    return posts

            # ── Standard extraction from matched selector ──
            count = await containers.count()
            for i in range(min(count, MAX_POSTS)):
                try:
                    container = containers.nth(i)

                    # Get post text content — try multiple sub-selectors
                    text_selectors = [
                        "div.feed-shared-text",
                        "span.break-words",
                        "div.update-components-text",
                        "div[dir='ltr']",
                        "span[dir='ltr']",
                        "div[class*='text'] span",
                    ]
                    text = ""
                    for ts in text_selectors:
                        text_el = container.locator(ts)
                        if await text_el.count() > 0:
                            text = (await text_el.first.inner_text()).strip()
                            if len(text) >= 30:
                                break
                            text = ""

                    # If still no text, try getting the full container text
                    if not text:
                        full_text = (await container.inner_text()).strip()
                        if len(full_text) >= 50:
                            text = full_text

                    # Skip empty or very short posts
                    if len(text) < 30:
                        continue

                    # Get author name
                    author_selectors = [
                        "span.feed-shared-actor__name",
                        "span.update-components-actor__name",
                        "a.update-components-actor__meta-link span",
                        "span[class*='actor__name']",
                        "a[class*='actor'] span",
                    ]
                    author = ""
                    for aus in author_selectors:
                        author_el = container.locator(aus)
                        if await author_el.count() > 0:
                            author = (await author_el.first.inner_text()).strip()
                            if author:
                                break

                    # Get post URL (if available)
                    post_url = ""
                    link_el = container.locator("a[href*='/posts/'], a[href*='/activity/'], a[href*='/feed/update/']")
                    if await link_el.count() > 0:
                        post_url = await link_el.first.get_attribute("href") or ""
                        if post_url and not post_url.startswith("http"):
                            post_url = f"https://www.linkedin.com{post_url}"

                    # Create FeedPost and deduplicate
                    post = FeedPost(author=author, text=text, post_url=post_url)
                    if post.post_id not in seen_ids:
                        seen_ids.add(post.post_id)
                        posts.append(post)

                except Exception as e:
                    logger.debug(f"  Skipping post {i}: {e}")
                    continue

        except Exception as e:
            logger.warning(f"Post extraction error: {e}")

        return posts

    async def _human_scroll(self) -> None:
        """Scroll down using mouse wheel to trigger LinkedIn's lazy loading.
        
        Uses mouse.wheel() which fires real WheelEvent — the most authentic
        scroll simulation that triggers IntersectionObserver-based lazy loading.
        """
        try:
            import random

            # Get current state before scrolling
            scroll_info = await self._page.evaluate("""
                () => ({
                    scrollY: window.scrollY,
                    scrollHeight: document.body.scrollHeight,
                    clientHeight: window.innerHeight
                })
            """)
            prev_scroll_y = scroll_info["scrollY"]
            prev_height = scroll_info["scrollHeight"]
            logger.info(
                f"    📍 Before scroll: scrollY={prev_scroll_y}, "
                f"pageHeight={prev_height}, viewport={scroll_info['clientHeight']}"
            )

            # Step 1: Click on the center of the page to ensure feed area has focus
            viewport = self._page.viewport_size
            if viewport:
                cx = viewport["width"] // 2
                cy = viewport["height"] // 2
                await self._page.mouse.click(cx, cy)
                await self.browser_manager.human_delay(0.3, 0.5)

            # Step 2: Use mouse.wheel() — fires real WheelEvent
            # Scroll in multiple smaller chunks (more human-like and more likely to trigger lazy load)
            total_delta = 0
            num_wheel_events = random.randint(6, 10)
            for _ in range(num_wheel_events):
                delta = random.randint(400, 800)
                await self._page.mouse.wheel(0, delta)
                total_delta += delta
                await self.browser_manager.human_delay(0.15, 0.35)

            logger.info(f"    🖱️ Mouse wheel: {num_wheel_events} events, total Δ={total_delta}px")

            # Wait for new content to load
            await self.browser_manager.human_delay(2.0, 3.5)

            # Step 3: Check if page grew (new content loaded)
            new_info = await self._page.evaluate("""
                () => ({
                    scrollY: window.scrollY,
                    scrollHeight: document.body.scrollHeight
                })
            """)
            new_scroll_y = new_info["scrollY"]
            new_height = new_info["scrollHeight"]

            scroll_moved = new_scroll_y - prev_scroll_y
            height_grew = new_height - prev_height

            if height_grew > 0:
                logger.info(f"    📏 Page grew: {prev_height} → {new_height} (+{height_grew}px)")
            else:
                logger.info(f"    📏 Page height unchanged: {new_height}")

            if scroll_moved > 0:
                logger.info(f"    ↕️ Scrolled: {prev_scroll_y} → {new_scroll_y} (+{scroll_moved}px)")
            else:
                # If mouse wheel didn't scroll, try keyboard as fallback
                logger.warning("    ⚠️ Mouse wheel didn't scroll — trying keyboard fallback")
                for _ in range(5):
                    await self._page.keyboard.press("PageDown")
                    await self.browser_manager.human_delay(0.3, 0.5)
                await self.browser_manager.human_delay(2.0, 3.0)

                # Final check
                final_scroll = await self._page.evaluate("window.scrollY")
                if final_scroll > prev_scroll_y:
                    logger.info(f"    ↕️ Keyboard scrolled to: {final_scroll}")
                else:
                    # Last resort: programmatic scroll
                    await self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    logger.warning("    ⚠️ Using programmatic scrollTo as last resort")
                    await self.browser_manager.human_delay(3.0, 4.0)

        except Exception as e:
            logger.warning(f"Scroll error: {e}")
