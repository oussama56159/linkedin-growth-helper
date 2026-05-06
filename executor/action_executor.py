"""
Executes approved LinkedIn actions using Playwright.
Handles: like, comment, repost, connect.
All actions include human-like behavior (random delays, scrolling).
"""

import logging
import time
import random
from typing import Dict, Any, Optional

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from .rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class ActionExecutor:
    def __init__(self, page: Page, rate_limiter: RateLimiter, db):
        self.page = page
        self.rate_limiter = rate_limiter
        self.db = db

    # ── Public API ─────────────────────────────────────────────────────────

    def execute(self, suggestion: Dict[str, Any]) -> bool:
        """
        Execute an approved suggestion.
        Returns True on success, False on failure.
        """
        action_type = suggestion["suggestion_type"]
        target_url = suggestion["target_url"]
        suggestion_id = suggestion["id"]

        if not self.rate_limiter.can_perform(action_type):
            logger.warning("Daily limit reached for %s, skipping.", action_type)
            self.db.log_action(action_type, target_url, "skipped", suggestion_id,
                               "Daily limit reached")
            return False

        logger.info("Executing %s on %s", action_type, target_url)

        try:
            success = False
            if action_type == "like":
                success = self._like_post(target_url)
            elif action_type == "comment":
                draft = suggestion.get("comment_draft", "")
                success = self._comment_post(target_url, draft)
            elif action_type == "repost":
                success = self._repost_post(target_url)
            elif action_type == "connect":
                success = self._connect_profile(target_url)
            elif action_type == "follow":
                success = self._follow_page(target_url)
            else:
                logger.error("Unknown action type: %s", action_type)
                return False

            status = "success" if success else "failed"
            self.db.log_action(action_type, target_url, status, suggestion_id)

            if success:
                self.rate_limiter.record_action(action_type)
                self.db.update_suggestion_status(suggestion_id, "executed")
                logger.info("✅ %s executed successfully", action_type)
            else:
                self.db.update_suggestion_status(suggestion_id, "failed")
                logger.warning("❌ %s failed", action_type)

            return success

        except Exception as e:
            logger.error("Error executing %s: %s", action_type, e)
            self.db.log_action(action_type, target_url, "failed", suggestion_id, str(e))
            self.db.update_suggestion_status(suggestion_id, "failed")
            return False

    def execute_batch(self, suggestions: list) -> Dict[str, int]:
        """Execute a list of approved suggestions with delays between each."""
        results = {"success": 0, "failed": 0, "skipped": 0}

        for suggestion in suggestions:
            self.rate_limiter.wait_between_actions()
            success = self.execute(suggestion)
            if success:
                results["success"] += 1
            else:
                results["failed"] += 1

        logger.info("Batch execution complete: %s", results)
        return results

    # ── Action implementations ─────────────────────────────────────────────

    def _like_post(self, post_url: str) -> bool:
        """Navigate to a post and click the Like button."""
        try:
            self.page.goto(post_url, wait_until="domcontentloaded")
            self._random_delay(2, 4)
            self._scroll_to_middle()

            # LinkedIn like button selectors (may need updating if LinkedIn changes DOM)
            like_btn = self.page.query_selector(
                "button[aria-label*='Like'][aria-pressed='false'], "
                "button.react-button__trigger[aria-label*='Like']"
            )

            if not like_btn:
                logger.warning("Like button not found on %s", post_url)
                return False

            # Check if already liked
            pressed = like_btn.get_attribute("aria-pressed")
            if pressed == "true":
                logger.info("Post already liked: %s", post_url)
                return True  # Count as success

            like_btn.hover()
            self._random_delay(0.5, 1.5)
            self._human_click(like_btn)
            self._random_delay(1, 2)

            return True

        except PlaywrightTimeout:
            logger.error("Timeout loading post: %s", post_url)
            return False

    def _comment_post(self, post_url: str, comment_text: str) -> bool:
        """Navigate to a post and submit a comment."""
        if not comment_text or len(comment_text.strip()) < 5:
            logger.warning("Comment text too short or empty, skipping.")
            return False

        try:
            self.page.goto(post_url, wait_until="domcontentloaded")
            self._random_delay(2, 5)
            self._scroll_to_middle()

            # Click the comment button to open the comment box
            comment_btn = self.page.query_selector(
                "button[aria-label*='comment'], "
                ".comment-button, "
                "button.social-actions-button"
            )
            if comment_btn:
                comment_btn.click()
                self._random_delay(1, 2)

            # Find the comment input
            comment_box = self.page.query_selector(
                ".ql-editor[contenteditable='true'], "
                "div[role='textbox'][aria-label*='comment']"
            )

            if not comment_box:
                logger.warning("Comment box not found on %s", post_url)
                return False

            comment_box.click()
            self._random_delay(0.5, 1.0)

            # Type comment with human-like speed
            self._human_type_text(comment_box, comment_text)
            self._random_delay(1, 3)

            # Submit
            submit_btn = self.page.query_selector(
                "button[class*='comments-comment-box__submit-button'], "
                "button[type='submit'][aria-label*='Post']"
            )
            if not submit_btn:
                logger.warning("Comment submit button not found")
                return False

            submit_btn.click()
            self._random_delay(2, 4)
            return True

        except PlaywrightTimeout:
            logger.error("Timeout on comment action: %s", post_url)
            return False

    def _repost_post(self, post_url: str) -> bool:
        """Repost (reshare) a LinkedIn post."""
        try:
            self.page.goto(post_url, wait_until="domcontentloaded")
            self._random_delay(2, 4)
            self._scroll_to_middle()

            # Click the repost/share button
            repost_btn = self.page.query_selector(
                "button[aria-label*='Repost'], "
                "button[aria-label*='Share'], "
                ".share-button"
            )

            if not repost_btn:
                logger.warning("Repost button not found on %s", post_url)
                return False

            repost_btn.click()
            self._random_delay(1, 2)

            # Select "Repost" option from dropdown (not "Share with thoughts")
            repost_option = self.page.query_selector(
                "button[aria-label*='Repost instantly'], "
                ".repost-menu-item"
            )
            if repost_option:
                repost_option.click()
                self._random_delay(1, 2)
                return True

            logger.warning("Repost option not found in menu")
            return False

        except PlaywrightTimeout:
            logger.error("Timeout on repost action: %s", post_url)
            return False

    def _connect_profile(self, profile_url: str) -> bool:
        """Send a connection request to a LinkedIn profile."""
        try:
            self.page.goto(profile_url, wait_until="domcontentloaded")
            self._random_delay(3, 6)
            self._scroll_to_middle()

            # Find the Connect button
            connect_btn = self.page.query_selector(
                "button[aria-label*='Connect'], "
                "button.pv-s-profile-actions__action[aria-label*='Connect']"
            )

            if not connect_btn:
                logger.info("No Connect button found (may already be connected): %s", profile_url)
                return False

            self._human_click(connect_btn)
            self._random_delay(1, 2)

            # Handle "How do you know X?" modal — click "Connect" without note
            send_btn = self.page.query_selector(
                "button[aria-label*='Send now'], "
                "button[aria-label*='Send without a note']"
            )
            if send_btn:
                send_btn.click()
                self._random_delay(1, 2)
                return True

            # Some flows show a direct "Send" button
            send_btn2 = self.page.query_selector("button[aria-label='Send invitation']")
            if send_btn2:
                send_btn2.click()
                self._random_delay(1, 2)
                return True

            logger.warning("Could not complete connection request for %s", profile_url)
            return False

        except PlaywrightTimeout:
            logger.error("Timeout on connect action: %s", profile_url)
            return False

    def _follow_page(self, page_url: str) -> bool:
        """Follow a LinkedIn company/page profile."""
        try:
            self.page.goto(page_url, wait_until="domcontentloaded")
            self._random_delay(3, 6)
            self._scroll_to_middle()

            follow_btn = self.page.query_selector(
                "button[aria-label*='Follow'], "
                "button[aria-label*='Suivre'], "
                "button:has-text('Follow'), "
                "button:has-text('Suivre')"
            )

            if not follow_btn:
                logger.info("No Follow button found (may already be followed): %s", page_url)
                return True

            pressed = follow_btn.get_attribute("aria-pressed")
            if pressed == "true":
                logger.info("Page already followed: %s", page_url)
                return True

            self._human_click(follow_btn)
            self._random_delay(1, 2)
            return True

        except PlaywrightTimeout:
            logger.error("Timeout on follow action: %s", page_url)
            return False

    # ── Helpers ────────────────────────────────────────────────────────────

    def _human_type_text(self, element, text: str):
        """Type text into an element with random per-character delays."""
        element.click()
        for char in text:
            element.type(char, delay=random.randint(40, 120))
            # Occasional longer pause (simulates thinking)
            if random.random() < 0.05:
                time.sleep(random.uniform(0.3, 0.8))

    def _human_click(self, element):
        """
        Click an element with realistic mouse movement.
        Moves to a random point near the element first, then to the element.
        """
        try:
            box = element.bounding_box()
            if not box:
                element.click()
                return

            # Target: random point within the element (not always dead center)
            target_x = box["x"] + random.uniform(box["width"] * 0.2, box["width"] * 0.8)
            target_y = box["y"] + random.uniform(box["height"] * 0.2, box["height"] * 0.8)

            # Move to a random intermediate point first
            mid_x = target_x + random.uniform(-80, 80)
            mid_y = target_y + random.uniform(-40, 40)
            self.page.mouse.move(mid_x, mid_y)
            time.sleep(random.uniform(0.1, 0.3))

            # Move to target with slight overshoot correction
            self.page.mouse.move(target_x, target_y)
            time.sleep(random.uniform(0.05, 0.2))

            self.page.mouse.click(target_x, target_y)

        except Exception:
            # Fallback to regular click
            element.click()

    def _scroll_to_middle(self):
        """Scroll to the middle of the page to simulate reading."""
        # Scroll in small increments, not one jump
        steps = random.randint(3, 6)
        for _ in range(steps):
            scroll_amount = random.randint(150, 350)
            self.page.evaluate(f"window.scrollBy(0, {scroll_amount})")
            time.sleep(random.uniform(0.3, 0.8))

    @staticmethod
    def _random_delay(min_s: float, max_s: float):
        time.sleep(random.uniform(min_s, max_s))
