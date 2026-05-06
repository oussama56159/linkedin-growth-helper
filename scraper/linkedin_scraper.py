"""
LinkedIn post and profile scraper using Playwright.
Searches by hashtag and keyword, extracts post metadata and author profiles.
"""

import logging
import time
import random
import re
import unicodedata
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from pathlib import Path

from playwright.sync_api import Page

from .filters import is_spam, extract_hashtags, normalize_url, is_relevant
from .session_manager import SessionManager

logger = logging.getLogger(__name__)

# How many posts to scrape per hashtag search
POSTS_PER_HASHTAG = 10
# How many profile suggestions to scrape per run
PROFILES_PER_RUN = 15

POST_URL_PATTERNS = (
    "/feed/update/",
    "/posts/",
)


class LinkedInScraper:
    def __init__(self, session: SessionManager, config: Dict[str, Any]):
        self.session = session
        self.config = config
        self.page: Page = session.get_page()
        self.keywords: List[str] = config["targeting"]["keywords"]
        self.hashtags: List[str] = config["targeting"]["hashtags"]
        self.target_roles: List[str] = config["targeting"]["target_roles"]
        self.target_locations: List[str] = config["targeting"].get(
            "target_locations", []
        )
        self.target_company_pages: List[Dict[str, str]] = config["targeting"].get(
            "target_company_pages", []
        )
        self.company_search_terms: List[str] = config["targeting"].get(
            "company_search_terms", []
        )
        self.max_age_hours: int = config["scoring"]["max_post_age_hours"]

    # ── Public API ─────────────────────────────────────────────────────────

    def scrape_posts(self) -> List[Dict[str, Any]]:
        """
        Scrape posts using LinkedIn's content search (Posts tab).
        Works for new accounts — no hashtag feed access required.
        """
        all_posts = []
        seen_urls = set()

        max_company_pages = self.config.get("limits", {}).get("max_company_pages_per_run", 3)
        for company_page in self.target_company_pages[:max_company_pages]:
            try:
                posts = self._scrape_company_page_posts(company_page)
                for post in posts:
                    url = normalize_url(post.get("post_url", ""))
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_posts.append(post)
                self._random_delay(5, 10)
            except Exception as e:
                logger.error("Error scraping company page %s: %s", company_page.get("name"), e)

        max_hashtags = self.config.get("limits", {}).get("max_hashtags_per_run", 8)
        for hashtag in self.hashtags[:max_hashtags]:
            try:
                posts = self._scrape_posts_search(hashtag)
                for post in posts:
                    url = normalize_url(post.get("post_url", ""))
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_posts.append(post)
                self._random_delay(5, 12)
            except Exception as e:
                logger.error("Error scraping hashtag %s: %s", hashtag, e)

        if len(all_posts) < self.config["limits"].get("max_suggestions_per_run", 10):
            try:
                logger.info(
                    "Only found %d posts from search; checking main feed for exact post URLs",
                    len(all_posts),
                )
                posts = self._scrape_main_feed()
                for post in posts:
                    url = normalize_url(post.get("post_url", ""))
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_posts.append(post)
            except Exception as e:
                logger.error("Error scraping main feed fallback: %s", e)

        logger.info("Scraped %d unique posts total", len(all_posts))
        return all_posts

    def _scrape_posts_search(self, hashtag: str) -> List[Dict[str, Any]]:
        """
        Search for posts using LinkedIn's content search URL.
        This directly hits the Posts tab, bypassing hashtag feed restrictions.
        """
        clean_tag = hashtag.lstrip("#")
        # Use the content search URL — this is the Posts tab directly
        url = (
            f"https://www.linkedin.com/search/results/content/"
            f"?keywords=%23{clean_tag.lower()}"
            f"&origin=SWITCH_SEARCH_VERTICAL"
            f"&sortBy=date_posted"  # Sort by recent
        )
        logger.info("Searching posts for: #%s", clean_tag)

        self.page.goto(url, wait_until="domcontentloaded")  # Use domcontentloaded to avoid networkidle timeouts
        self._random_delay(4, 7)

        # Scroll to load posts
        for _ in range(3):
            self.page.evaluate("window.scrollBy(0, window.innerHeight * 0.8)")
            self._random_delay(2, 3)

        self._random_delay(2, 4)

        posts = []

        post_elements = self._find_post_candidate_elements()

        logger.info("Found %d post elements for #%s", len(post_elements), clean_tag)

        for i, el in enumerate(post_elements[:POSTS_PER_HASHTAG]):
            try:
                # Try simple extraction first (most resilient)
                post = self._extract_simple_post(el)
                
                # Try search result extraction if simple didn't work
                if not post:
                    post = self._extract_search_result_post(el)
                
                # Try the robust extraction method
                if not post:
                    post = self._extract_post_data(el)
                
                # Fallback to URN-based extraction if needed
                if not post:
                    post = self._extract_post_from_urn_element(el, hashtag)
                
                if post:
                    if not self._is_actionable_post_url(post.get("post_url", "")):
                        logger.debug(
                            "Skipping non-actionable search result URL: %s",
                            post.get("post_url", ""),
                        )
                        continue
                    post["relevance_score"] = is_relevant(
                        post.get("content", ""), self.keywords, self.hashtags
                    )
                    post["is_spam"] = is_spam(post)
                    if not post["is_spam"] and post["relevance_score"] > 0:
                        posts.append(post)
            except Exception as e:
                logger.debug("Failed to extract post %d: %s", i, e)

        logger.info("Extracted %d posts for #%s", len(posts), clean_tag)
        return posts

    def _scrape_company_page_posts(self, company_page: Dict[str, str]) -> List[Dict[str, Any]]:
        """Scrape recent posts from a configured high-signal company/news page."""
        name = company_page.get("name", "Unknown")
        base_url = company_page.get("url", "")
        if not base_url:
            return []

        posts_url = normalize_url(base_url) + "/posts/"
        logger.info("Scraping posts from page: %s", name)
        self.page.goto(posts_url, wait_until="domcontentloaded")
        self._random_delay(4, 7)
        self._scroll_feed(scrolls=2)

        posts = []
        for el in self._find_post_candidate_elements()[:POSTS_PER_HASHTAG]:
            try:
                post = self._extract_simple_post(el) or self._extract_post_data(el)
                if not post or not self._is_actionable_post_url(post.get("post_url", "")):
                    continue

                post["author_name"] = post.get("author_name") or name
                post["author_profile_url"] = post.get("author_profile_url") or normalize_url(base_url)
                relevance_text = " ".join([
                    post.get("content", ""),
                    name,
                    company_page.get("headline", ""),
                ])
                post["relevance_score"] = max(
                    is_relevant(relevance_text, self.keywords, self.hashtags),
                    0.25,
                )
                post["is_spam"] = is_spam(post)
                if not post["is_spam"]:
                    posts.append(post)
            except Exception as e:
                logger.debug("Failed to extract page post for %s: %s", name, e)

        logger.info("Extracted %d posts from page: %s", len(posts), name)
        return posts

    def _extract_post_from_urn_element(
        self, element, hashtag: str
    ) -> Optional[Dict[str, Any]]:
        """
        Extract post data using stable attributes (data-urn, aria-*, href).
        Avoids obfuscated class names that change frequently.
        """
        try:
            # ── Post URL ──────────────────────────────────────────────────
            post_url = None

            # Method 1: data-urn attribute on the element itself
            urn = element.get_attribute("data-urn") or ""
            if "activity" in urn:
                post_url = f"https://www.linkedin.com/feed/update/{urn}"

            # Method 2: find any link containing posts/ or feed/update
            if not post_url:
                all_links = element.query_selector_all("a[href]")
                for link in all_links:
                    href = link.get_attribute("href") or ""
                    if "/posts/" in href or "feed/update" in href:
                        post_url = (
                            href if href.startswith("http")
                            else "https://www.linkedin.com" + href.split("?")[0]
                        )
                        break

            # Method 3: find any link with activity in href
            if not post_url:
                all_links = element.query_selector_all("a[href]")
                for link in all_links:
                    href = link.get_attribute("href") or ""
                    if "activity" in href:
                        post_url = (
                            href if href.startswith("http")
                            else "https://www.linkedin.com" + href.split("?")[0]
                        )
                        break

            # Method 4: Check parent element
            if not post_url:
                parent = element
                for _ in range(3):  # Check up to 3 parent levels
                    parent = parent.query_selector("..")
                    if not parent:
                        break
                    parent_urn = parent.get_attribute("data-urn") or ""
                    if "activity" in parent_urn:
                        post_url = f"https://www.linkedin.com/feed/update/{parent_urn}"
                        break

            if not post_url:
                logger.debug("Could not find post URL in element")
                return None

            if not self._is_actionable_post_url(post_url):
                return None

            # ── Author name ───────────────────────────────────────────────
            author_name = "Unknown"

            # Try aria-label on actor links
            actor_link = element.query_selector("a[href*='/in/'], a[href*='/company/']")
            if actor_link:
                aria = actor_link.get_attribute("aria-label")
                if aria:
                    author_name = aria.strip()
                else:
                    # Get visible text from the link
                    spans = actor_link.query_selector_all(
                        "span[aria-hidden='true']"
                    )
                    for span in spans:
                        text = span.inner_text().strip()
                        if text and len(text) > 1:
                            author_name = text
                            break

            # ── Author profile URL ────────────────────────────────────────
            author_profile_url = None
            if actor_link:
                href = actor_link.get_attribute("href") or ""
                if href:
                    author_profile_url = (
                        href if href.startswith("http")
                        else "https://www.linkedin.com" + href.split("?")[0]
                    )

            # ── Post content ──────────────────────────────────────────────
            content = ""

            # Try multiple content selectors
            content_selectors = [
                "span[dir='ltr']",  # LinkedIn text spans
                "div[dir='ltr']",  # Text divs
                ".feed-shared-update-v2__description",  # Feed post description
                ".update-components-text",  # Update text container
                ".feed-shared-inline-show-more-text",  # Show more text
                "[data-test-id='main-feed-activity-card__commentary']",  # Comment area
            ]

            for selector in content_selectors:
                containers = element.query_selector_all(selector)
                for container in containers:
                    text = container.inner_text().strip()
                    if len(text) > 30:  # Meaningful content
                        content = text
                        break
                if content:
                    break

            # Fallback: get all text from element, clean it up
            if not content:
                raw = element.inner_text()
                content = self._clean_post_content(raw, author_name)

            # If still no content, that's okay - use empty string
            if not content:
                logger.debug("No content found for post %s", post_url)

            hashtags = extract_hashtags(content) if content else []

            return {
                "post_url": normalize_url(post_url),
                "author_name": author_name,
                "author_profile_url": author_profile_url,
                "content": content[:2000] if content else "",
                "likes_count": 0,
                "comments_count": 0,
                "reposts_count": 0,
                "hashtags": hashtags,
                "post_age_hours": None,
            }

        except Exception as e:
            logger.debug("Post extraction error: %s", e)
            return None

    def _scrape_main_feed(self) -> List[Dict[str, Any]]:
        """Scrape posts from your main LinkedIn feed."""
        logger.info("Scraping main LinkedIn feed...")
        url = "https://www.linkedin.com/feed/"
        
        self.page.goto(url, wait_until="domcontentloaded")
        self._random_delay(5, 8)  # Longer wait for JS to render
        
        # Wait for feed to load - try multiple selectors
        feed_loaded = False
        wait_selectors = [
            "div.feed-shared-update-v2",
            ".scaffold-finite-scroll",
            "main",
        ]
        
        for selector in wait_selectors:
            try:
                self.page.wait_for_selector(selector, timeout=15000)
                logger.info("Feed loaded, found selector: %s", selector)
                feed_loaded = True
                break
            except Exception:
                logger.debug("Selector not found: %s", selector)
        
        if not feed_loaded:
            logger.warning("Feed did not load properly")
        
        # Scroll to load more posts - with pauses to let JS render
        for i in range(5):
            self.page.evaluate("window.scrollBy(0, window.innerHeight * 0.8)")
            self._random_delay(2, 4)  # Longer delays between scrolls
        
        # Wait a bit more after scrolling
        self._random_delay(3, 5)
        
        posts = []
        
        # Try multiple selectors for feed posts
        post_selectors = [
            "div.feed-shared-update-v2",
            "div[data-urn*='activity']",
            "div[data-id*='urn:li:activity']",
            ".scaffold-finite-scroll__content > div",
            "main div[class*='feed-shared']",
        ]
        
        post_elements = []
        for selector in post_selectors:
            post_elements = self.page.query_selector_all(selector)
            if post_elements:
                logger.info("Found %d posts in main feed with selector: %s", len(post_elements), selector)
                break
            else:
                logger.debug("No posts with selector: %s", selector)
        
        if not post_elements:
            logger.warning("No posts found in main feed")
            
            # DEBUG: Save HTML
            html = self.page.content()
            debug_file = "storage/logs/debug_main_feed.html"
            Path(debug_file).parent.mkdir(parents=True, exist_ok=True)
            with open(debug_file, "w", encoding="utf-8") as f:
                f.write(html)
            logger.info("Saved main feed HTML to %s for debugging", debug_file)
            
            # Count total elements
            all_divs = self.page.query_selector_all("div")
            logger.info("Total <div> elements on page: %d", len(all_divs))
            
            return []
        
        for el in post_elements[:20]:  # Get up to 20 posts from main feed
            try:
                post = self._extract_post_data(el)
                if post:
                    if not self._is_actionable_post_url(post.get("post_url", "")):
                        continue
                    # Score relevance based on keywords
                    post["relevance_score"] = is_relevant(
                        post.get("content", ""), self.keywords, self.hashtags
                    )
                    post["is_spam"] = is_spam(post)
                    
                    # Only keep posts that match our interests
                    if post["relevance_score"] > 0.1:  # At least some relevance
                        posts.append(post)
            except Exception as e:
                logger.debug("Failed to extract post from main feed: %s", e)
        
        logger.info("Found %d relevant posts in main feed", len(posts))
        return posts

    def scrape_profiles(self) -> List[Dict[str, Any]]:
        """Scrape suggested profiles from 'People You May Know' and search."""
        profiles = []
        profiles.extend(self._curated_company_pages())
        logger.info("Loaded %d configured technology/news pages as follow targets", len(profiles))

        for term in self.company_search_terms[:3]:
            try:
                profiles.extend(self._search_company_pages(term))
                self._random_delay(5, 10)
            except Exception as e:
                logger.error("Error searching company pages %s: %s", term, e)

        try:
            profiles.extend(self._scrape_people_you_may_know())
            self._random_delay(5, 10)
        except Exception as e:
            logger.error("Error scraping PYMK: %s", e)

        people_queries = self._build_people_search_queries()
        for query in people_queries:
            try:
                profiles.extend(self._search_people_by_query(query))
                self._random_delay(6, 12)
            except Exception as e:
                logger.error("Error searching people query %s: %s", query, e)

        # Deduplicate by URL
        seen = set()
        unique = []
        for p in profiles:
            url = normalize_url(p.get("profile_url", ""))
            if url and url not in seen:
                seen.add(url)
                unique.append(p)

        logger.info("Scraped %d unique profiles", len(unique))
        companies = [p for p in unique if p.get("suggestion_type") == "follow"]
        people = [p for p in unique if p.get("suggestion_type") != "follow"]
        max_follows = self.config.get("limits", {}).get("max_follow_suggestions_per_run", 3)
        max_connections = self.config.get("limits", {}).get("max_connection_suggestions_per_run", 5)
        return people[:max_connections] + companies[:max_follows]

    def _build_people_search_queries(self) -> List[str]:
        """Build focused people searches, including Tunisia/local tech queries."""
        queries = []
        locations = self.target_locations or ["Tunisia"]

        for role in self.target_roles[:4]:
            queries.append(role)
            for location in locations[:2]:
                queries.append(f"{role} {location}")

        queries.extend([
            "AI Engineer Tunisia",
            "Software Engineer Tunisia",
            "Embedded Engineer Tunisia",
            "Full Stack Developer Tunis",
            "Startup Founder Tunisia technology",
        ])

        deduped = []
        seen = set()
        max_queries = self.config.get("limits", {}).get("max_people_searches_per_run", 8)
        for query in queries:
            key = query.lower()
            if key not in seen:
                seen.add(key)
                deduped.append(query)
            if len(deduped) >= max_queries:
                break
        return deduped

    # ── Internal scrapers ──────────────────────────────────────────────────

    def _scrape_hashtag_feed(self, hashtag: str) -> List[Dict[str, Any]]:
        """Navigate to a hashtag feed and extract posts."""
        clean_tag = hashtag.lstrip("#")
        url = f"https://www.linkedin.com/feed/hashtag/{clean_tag.lower()}/"
        logger.info("Scraping hashtag: #%s", clean_tag)

        self.page.goto(url, wait_until="domcontentloaded")
        self._random_delay(3, 6)
        
        # Wait for content to load
        try:
            self.page.wait_for_selector("main", timeout=10000)
        except Exception:
            logger.warning("Main content area not found")
        
        self._scroll_feed(scrolls=4)

        # Check if we're on search results instead of hashtag feed
        if "search/results" in self.page.url:
            logger.info("Redirected to search results, using search scraper")
            return self._scrape_search_results()
        
        # Check if we're actually on the hashtag page
        if "hashtag" not in self.page.url:
            logger.warning("Not on hashtag page, redirected to: %s", self.page.url)
            return []

        posts = []
        
        # Try multiple post container selectors
        post_selectors = [
            "div.feed-shared-update-v2",
            "div[data-urn*='activity']",
            "div[data-id*='urn:li:activity']",
            ".scaffold-finite-scroll__content > div",
            "main div[class*='feed']",
            "article",
            "[data-test-id*='feed']",
        ]
        
        post_elements = []
        for selector in post_selectors:
            post_elements = self.page.query_selector_all(selector)
            if post_elements:
                logger.info("Found %d elements with selector: %s", len(post_elements), selector)
                break
            else:
                logger.debug("No elements found with selector: %s", selector)
        
        if not post_elements:
            logger.warning("No post elements found for #%s with any selector", clean_tag)
            return []

        for el in post_elements[:POSTS_PER_HASHTAG]:
            try:
                post = self._extract_post_data(el)
                if post:
                    # Score relevance
                    post["relevance_score"] = is_relevant(
                        post.get("content", ""), self.keywords, self.hashtags
                    )
                    post["is_spam"] = is_spam(post)
                    posts.append(post)
            except Exception as e:
                logger.debug("Failed to extract post: %s", e)

        logger.info("Found %d posts for #%s", len(posts), clean_tag)
        return posts

    def _scrape_search_results(self) -> List[Dict[str, Any]]:
        """
        Scrape posts from LinkedIn search results page.
        This is used when hashtag URLs redirect to search.
        """
        logger.info("Scraping search results page...")
        logger.info("Current URL: %s", self.page.url)
        
        # Wait for search results to load
        self._random_delay(4, 7)
        
        # Scroll to load more results - with longer pauses
        for i in range(3):
            self.page.evaluate("window.scrollBy(0, window.innerHeight * 0.8)")
            self._random_delay(2, 4)
        
        # Wait after scrolling
        self._random_delay(3, 5)
        
        # DEBUG: Save the HTML to see what's actually there
        html = self.page.content()
        debug_file = "storage/logs/debug_search_results.html"
        Path(debug_file).parent.mkdir(parents=True, exist_ok=True)
        with open(debug_file, "w", encoding="utf-8") as f:
            f.write(html)
        logger.info("Saved search results HTML to %s", debug_file)
        
        posts = []
        
        # Search results have different HTML structure
        search_selectors = [
            ".search-results-container li",
            ".reusable-search__result-container",
            "li.reusable-search__result-container",
            ".search-results__list > li",
            "ul.reusable-search__entity-result-list > li",
            ".search-results-container div",
            "main li",
            ".search-results__list li",
            "div[class*='search-result']",
            "div[class*='entity-result']",
        ]
        
        result_elements = []
        for selector in search_selectors:
            result_elements = self.page.query_selector_all(selector)
            if result_elements:
                logger.info("Found %d search results with selector: %s", len(result_elements), selector)
                break
            else:
                logger.debug("No results with selector: %s", selector)
        
        if not result_elements:
            logger.warning("No search results found with any selector")
            
            # Try to find ANY list items or divs
            all_li = self.page.query_selector_all("li")
            all_divs = self.page.query_selector_all("div")
            logger.info("Total <li> elements on page: %d", len(all_li))
            logger.info("Total <div> elements on page: %d", len(all_divs))
            
            return []
        
        for el in result_elements[:POSTS_PER_HASHTAG]:
            try:
                post = self._extract_search_result_post(el)
                if post:
                    post["relevance_score"] = is_relevant(
                        post.get("content", ""), self.keywords, self.hashtags
                    )
                    post["is_spam"] = is_spam(post)
                    posts.append(post)
            except Exception as e:
                logger.debug("Failed to extract search result: %s", e)
        
        logger.info("Found %d posts from search results", len(posts))
        return posts

    def _extract_search_result_post(self, element) -> Optional[Dict[str, Any]]:
        """Extract post data from a search result item."""
        try:
            # Find the post link
            post_url = None
            link_selectors = [
                "a[href*='/posts/']",
                "a[href*='feed/update']",
                "a.app-aware-link",
            ]
            
            for selector in link_selectors:
                link_el = element.query_selector(selector)
                if link_el:
                    href = link_el.get_attribute("href")
                    if href and ("posts" in href or "update" in href):
                        post_url = href if href.startswith("http") else "https://www.linkedin.com" + href.split("?")[0]
                        break
            
            if not post_url:
                return None

            if not self._is_actionable_post_url(post_url):
                return None
            
            # Author name
            author_name = "Unknown"
            author_selectors = [
                ".entity-result__title-text a span[aria-hidden='true']",
                ".update-components-actor__name",
                "span.entity-result__title-text",
            ]
            
            for selector in author_selectors:
                author_el = element.query_selector(selector)
                if author_el:
                    author_name = self._clean_author_name(author_el.inner_text())
                    if author_name:
                        break
            
            # Content/snippet
            content = ""
            content_selectors = [
                ".entity-result__summary",
                ".feed-shared-update-v2__description",
                "p.entity-result__summary",
            ]
            
            for selector in content_selectors:
                content_el = element.query_selector(selector)
                if content_el:
                    content = self._clean_post_content(
                        content_el.inner_text(), author_name
                    )
                    if content:
                        break
            
            # If no content found, try getting any text from the element
            if not content:
                content = element.inner_text()[:500]
            
            hashtags = extract_hashtags(content)
            
            return {
                "post_url": normalize_url(post_url),
                "author_name": author_name,
                "author_profile_url": None,
                "content": content[:2000],
                "likes_count": self._parse_count_v2(element),
                "comments_count": self._parse_comment_count(element),
                "reposts_count": 0,
                "hashtags": hashtags,
                "post_age_hours": None,
            }
        except Exception as e:
            logger.debug("Search result extraction error: %s", e)
            return None

    def _extract_post_data(self, element) -> Optional[Dict[str, Any]]:
        """Extract structured data from a post DOM element."""
        try:
            # Post URL — try multiple selectors for LinkedIn's various post formats
            post_url = None
            
            # Try different link selectors
            link_selectors = [
                "a[href*='/posts/']",
                "a[href*='/feed/update/']",
                "a[data-control-name='feed_post']",
                "a.app-aware-link[href*='activity']",
                ".feed-shared-update-v2__content a[href*='activity']",
            ]
            
            for selector in link_selectors:
                link_el = element.query_selector(selector)
                if link_el:
                    post_url = link_el.get_attribute("href")
                    if post_url:
                        if not post_url.startswith("http"):
                            post_url = "https://www.linkedin.com" + post_url
                        break
            
            if not post_url:
                # Try getting from parent element's data attributes
                urn = element.get_attribute("data-urn")
                if urn and "activity" in urn:
                    post_url = f"https://www.linkedin.com/feed/update/{urn}"
                    logger.debug("Found post URL from data-urn: %s", urn)
                else:
                    logger.debug("Could not find post URL in element")
                    return None

            if not self._is_actionable_post_url(post_url):
                return None

            # Author info — try multiple selectors
            author_name = "Unknown"
            author_selectors = [
                ".update-components-actor__name",
                ".feed-shared-actor__name",
                ".feed-shared-actor__title",
                "[data-control-name='actor'] span[aria-hidden='true']",
            ]
            
            for selector in author_selectors:
                author_el = element.query_selector(selector)
                if author_el:
                    author_name = author_el.inner_text().strip()
                    if author_name:
                        break

            # Author profile URL
            author_profile_url = None
            author_link_selectors = [
                ".update-components-actor__meta-link",
                ".feed-shared-actor__meta-link",
                "a[data-control-name='actor']",
            ]
            
            for selector in author_link_selectors:
                author_link_el = element.query_selector(selector)
                if author_link_el:
                    href = author_link_el.get_attribute("href")
                    if href:
                        author_profile_url = (
                            href if href.startswith("http")
                            else "https://www.linkedin.com" + href.split("?")[0]
                        )
                        break

            # Post content — try multiple selectors
            content = ""
            content_selectors = [
                ".feed-shared-update-v2__description",
                ".update-components-text",
                ".feed-shared-text",
                "[data-test-id='main-feed-activity-card__commentary']",
                ".feed-shared-inline-show-more-text",
            ]
            
            for selector in content_selectors:
                content_el = element.query_selector(selector)
                if content_el:
                    content = content_el.inner_text().strip()
                    if content:
                        break

            # Engagement counts
            likes = self._parse_count_v2(element)
            comments = self._parse_comment_count(element)

            hashtags = extract_hashtags(content)

            logger.debug("Successfully extracted post: URL=%s, Author=%s, Content=%s...", 
                        post_url[:50], author_name, content[:50] if content else "(empty)")

            return {
                "post_url": normalize_url(post_url),
                "author_name": author_name,
                "author_profile_url": author_profile_url,
                "content": content[:2000],  # Truncate very long posts
                "likes_count": likes,
                "comments_count": comments,
                "reposts_count": 0,
                "hashtags": hashtags,
                "post_age_hours": None,
            }
        except Exception as e:
            logger.debug("Post extraction error: %s", e)
            return None

    def _parse_count_v2(self, element) -> int:
        """Parse engagement count with multiple selector attempts."""
        selectors = [
            ".social-details-social-counts__reactions-count",
            "[data-test-id='social-actions__reaction-count']",
            "button[aria-label*='reaction'] span[aria-hidden='true']",
            ".social-details-social-counts__item--reactions-count",
        ]
        
        for selector in selectors:
            try:
                el = element.query_selector(selector)
                if el:
                    text = el.inner_text().strip()
                    return self._parse_count_text(text)
            except Exception:
                continue
        return 0

    def _parse_comment_count(self, element) -> int:
        """Parse comment count with multiple selector attempts."""
        selectors = [
            ".social-details-social-counts__comments",
            "[data-test-id='social-actions__comment-count']",
            "button[aria-label*='comment'] span[aria-hidden='true']",
            ".social-details-social-counts__item--comments",
        ]
        
        for selector in selectors:
            try:
                el = element.query_selector(selector)
                if el:
                    text = el.inner_text().strip()
                    return self._parse_count_text(text)
            except Exception:
                continue
        return 0

    def _parse_count_text(self, text: str) -> int:
        """Parse a count string like '1,234' or '1.2K' into an integer."""
        if not text:
            return 0
        try:
            # Remove non-numeric except K, M, comma, period
            text = text.replace(",", "").replace(".", "")
            
            # Handle K (thousands) and M (millions)
            if "K" in text.upper():
                return int(float(text.upper().replace("K", "")) * 1000)
            if "M" in text.upper():
                return int(float(text.upper().replace("M", "")) * 1000000)
            
            # Extract just the numbers
            numbers = re.sub(r"[^\d]", "", text)
            return int(numbers) if numbers else 0
        except Exception:
            return 0

    def _extract_simple_post(self, element) -> Optional[Dict[str, Any]]:
        """
        Extract post data with a simple, resilient approach.
        Get any content and links from the element without strict selectors.
        """
        try:
            # Try to find ANY link that looks like a post
            post_url = None
            links = element.query_selector_all("a[href]")
            logger.debug("Element has %d links", len(links))
            
            for link in links:
                href = link.get_attribute("href") or ""
                logger.debug("  Link href: %s", href[:80] if href else "(empty)")
                if self._is_actionable_post_url(href):
                    post_url = href if href.startswith("http") else "https://www.linkedin.com" + href.split("?")[0]
                    logger.debug("Found post URL: %s", post_url[:80])
                    break
            
            if not post_url:
                logger.debug("No post URL found in element's links")
                return None

            # Get all text from the element as content
            content = self._clean_post_content(element.inner_text(), author_name)
            if not content:
                logger.debug("Element has no text content")
                return None

            # Try to extract author from links that point to profiles
            author_name = "Unknown"
            author_profile_url = None
            for link in links:
                href = link.get_attribute("href") or ""
                if "/in/" in href or "/company/" in href:
                    text = link.inner_text().strip()
                    if text and len(text) > 1 and len(text) < 100:
                        author_name = self._clean_author_name(text)
                        author_profile_url = (
                            href if href.startswith("http")
                            else "https://www.linkedin.com" + href.split("?")[0]
                        )
                        break

            content = self._clean_post_content(element.inner_text(), author_name)

            # Extract hashtags from content
            hashtags = extract_hashtags(content)

            logger.debug("Successfully extracted post with simple method: URL=%s", post_url[:80])

            return {
                "post_url": normalize_url(post_url),
                "author_name": author_name,
                "author_profile_url": normalize_url(author_profile_url) if author_profile_url else None,
                "content": content[:2000],
                "likes_count": self._parse_count_v2(element),
                "comments_count": self._parse_comment_count(element),
                "reposts_count": 0,
                "hashtags": hashtags,
                "post_age_hours": None,
            }
        except Exception as e:
            logger.debug("Simple post extraction error: %s", e)
            return None

    def _find_post_candidate_elements(self):
        """Find likely post cards without falling back to generic page elements."""
        selectors = [
            "div[data-urn*='activity']",
            "li[data-urn*='activity']",
            "div.feed-shared-update-v2",
            "li.reusable-search__result-container",
            "div[class*='feed-shared-update']",
            "main article",
        ]
        candidates = []
        seen = set()
        for selector in selectors:
            for element in self.page.query_selector_all(selector):
                try:
                    key = element.evaluate(
                        """el => {
                            const rect = el.getBoundingClientRect();
                            return `${Math.round(rect.top)}:${Math.round(rect.left)}:${el.innerText.slice(0, 80)}`;
                        }"""
                    )
                    if key not in seen:
                        seen.add(key)
                        candidates.append(element)
                except Exception:
                    candidates.append(element)

        if candidates:
            return candidates

        post_links = self.page.query_selector_all(
            "a[href*='/feed/update/'], a[href*='/posts/']"
        )
        for link in post_links:
            try:
                card = link.evaluate_handle(
                    """node => {
                        let el = node;
                        for (let i = 0; i < 8 && el; i += 1) {
                            const text = (el.innerText || '').trim();
                            if ((el.matches('li, article, div') && text.length > 80) || el.matches('main')) {
                                return el;
                            }
                            el = el.parentElement;
                        }
                        return node;
                    }"""
                ).as_element()
                if card:
                    candidates.append(card)
            except Exception:
                continue
        return candidates

    @classmethod
    def _clean_post_content(cls, raw: str, author_name: str = "") -> str:
        """Remove common LinkedIn chrome from a scraped card's visible text."""
        if not raw:
            return ""

        author_norm = cls._normalize_for_match(author_name)
        cleaned = []
        previous = None
        for line in raw.splitlines():
            text = re.sub(r"\s+", " ", line).strip()
            if not text:
                continue

            norm = cls._normalize_for_match(text)
            if not norm or norm == previous:
                continue
            previous = norm

            if author_norm and norm == author_norm:
                continue
            if cls._is_linkedin_noise_line(norm):
                continue
            if re.match(r"^\d+\s*(min|h|hr|hrs|j|d|day|days|sem|w|mo)\b", norm):
                continue
            if len(text) <= 2:
                continue

            cleaned.append(text)

        return "\n".join(cleaned[:12])[:2000]

    @classmethod
    def _clean_author_name(cls, raw: str) -> str:
        """Keep the actor name without timestamps or action text."""
        if not raw:
            return "Unknown"
        for line in raw.splitlines():
            text = re.sub(r"\s+", " ", line).strip()
            if not text:
                continue
            norm = cls._normalize_for_match(text)
            if cls._is_linkedin_noise_line(norm):
                continue
            text = re.split(r"\s+[0-9]+\s*(?:min|h|hr|hrs|j|d|day|days)\b", text)[0]
            text = text.strip(" -|•")
            if 1 < len(text) < 120:
                return text
        return "Unknown"

    @staticmethod
    def _normalize_for_match(text: str) -> str:
        text = text.replace("\u2018", "'").replace("\u2019", "'")
        text = unicodedata.normalize("NFKD", text)
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        return re.sub(r"\s+", " ", text).strip().lower()

    @staticmethod
    def _is_linkedin_noise_line(norm: str) -> bool:
        exact_noise = {
            "post du fil d'actualite",
            "feed post",
            "suivre",
            "follow",
            "like",
            "comment",
            "comments",
            "repost",
            "send",
            "share",
            "voir plus",
            "see more",
            "afficher plus",
            "show more",
            "1st",
            "2nd",
            "3rd",
            "1er",
            "2e",
            "3e",
        }
        if norm in exact_noise:
            return True
        if re.match(r"^[•\-\s]*(1st|2nd|3rd|1er|2e|3e)\b", norm, re.IGNORECASE):
            return True
        return norm.startswith((
            "activez pour voir",
            "activate to view",
            "post du fil",
        ))

    @staticmethod
    def _is_actionable_post_url(url: str) -> bool:
        """Return True only for URLs that can be opened as a concrete LinkedIn post."""
        if not url:
            return False
        clean = url.split("?")[0].lower().rstrip("/")
        if "/search/results/" in clean:
            return False
        if clean.endswith("/posts"):
            return False
        return any(pattern in clean for pattern in POST_URL_PATTERNS)

    def _scrape_people_you_may_know(self) -> List[Dict[str, Any]]:
        """Scrape LinkedIn's 'People You May Know' suggestions."""
        logger.info("Scraping People You May Know...")
        self.page.goto(
            "https://www.linkedin.com/mynetwork/", wait_until="domcontentloaded"
        )
        self._random_delay(3, 6)
        self._scroll_feed(scrolls=2)

        profiles = []
        cards = self.page.query_selector_all(
            ".discover-entity-type-card, .mn-pymk-list__item"
        )

        for card in cards[:10]:
            try:
                profile = self._extract_profile_card(card)
                if profile:
                    profiles.append(profile)
            except Exception as e:
                logger.debug("Profile card extraction error: %s", e)

        return profiles

    def _search_people_by_role(self, role: str) -> List[Dict[str, Any]]:
        """Search LinkedIn for people with a specific role/title."""
        return self._search_people_by_query(role)

    def _search_people_by_query(self, query: str) -> List[Dict[str, Any]]:
        """Search LinkedIn for people with a specific role/location query."""
        logger.info("Searching people with query: %s", query)
        search_url = (
            f"https://www.linkedin.com/search/results/people/"
            f"?keywords={query.replace(' ', '%20')}&origin=GLOBAL_SEARCH_HEADER"
        )
        self.page.goto(search_url, wait_until="domcontentloaded")
        self._random_delay(3, 6)

        profiles = []
        result_cards = self.page.query_selector_all(
            ".reusable-search__result-container, .entity-result"
        )

        for card in result_cards[:5]:
            try:
                profile = self._extract_search_profile(card)
                if profile:
                    profile["search_query"] = query
                    profiles.append(profile)
            except Exception as e:
                logger.debug("Search profile extraction error: %s", e)

        seen_urls = {normalize_url(p.get("profile_url", "")) for p in profiles}
        profile_links = self.page.query_selector_all("a[href*='/in/']")
        logger.info("Found %d raw profile links for query: %s", len(profile_links), query)
        for link in profile_links[:15]:
            try:
                profile = self._extract_profile_from_link(link, query)
                url = normalize_url(profile.get("profile_url", "")) if profile else ""
                if profile and url and url not in seen_urls:
                    seen_urls.add(url)
                    profiles.append(profile)
            except Exception as e:
                logger.debug("Profile link extraction error: %s", e)

        return profiles

    def _extract_profile_from_link(self, link, query: str) -> Optional[Dict[str, Any]]:
        """Extract a people-search profile from a profile link and nearby text."""
        href = link.get_attribute("href") or ""
        if "/in/" not in href:
            return None
        profile_url = href if href.startswith("http") else "https://www.linkedin.com" + href
        profile_url = normalize_url(profile_url)

        raw_name = link.inner_text().strip()
        name = self._clean_author_name(raw_name)

        nearby_text = ""
        try:
            nearby_text = link.evaluate(
                """node => {
                    let el = node;
                    for (let i = 0; i < 6 && el; i += 1) {
                        const text = (el.innerText || '').trim();
                        if (text.length > 80) return text;
                        el = el.parentElement;
                    }
                    return node.innerText || '';
                }"""
            )
        except Exception:
            nearby_text = raw_name

        lines = [
            re.sub(r"\s+", " ", line).strip()
            for line in nearby_text.splitlines()
            if re.sub(r"\s+", " ", line).strip()
        ]
        normalized_name = self._normalize_for_match(name)
        useful_lines = [
            line
            for line in lines
            if self._normalize_for_match(line) != normalized_name
            and not self._is_linkedin_noise_line(self._normalize_for_match(line))
        ]

        headline = next(
            (
                line
                for line in useful_lines
                if len(line) > 8
                and not re.match(r"^[•\-\s]*(1st|2nd|3rd|1er|2e|3e)\b", line, re.IGNORECASE)
            ),
            query,
        )
        location = None
        for line in useful_lines[1:]:
            if any(loc.lower() in line.lower() for loc in self.target_locations):
                location = line
                break

        relevance_blob = " ".join([name, headline, location or "", query])
        relevance = self._score_profile_headline(relevance_blob)
        if relevance <= 0.05:
            return None

        return {
            "profile_url": profile_url,
            "full_name": name,
            "headline": headline,
            "industry": None,
            "location": location,
            "connections_count": None,
            "mutual_connections": 0,
            "relevance_score": relevance,
            "search_query": query,
        }

    def _curated_company_pages(self) -> List[Dict[str, Any]]:
        """Return configured high-signal company/news pages as follow targets."""
        pages = []
        for page in self.target_company_pages:
            url = page.get("url", "")
            name = page.get("name", "Unknown")
            headline = page.get("headline", "")
            if not url:
                continue
            pages.append({
                "profile_url": normalize_url(url),
                "full_name": name,
                "headline": headline,
                "industry": "Technology",
                "location": None,
                "connections_count": None,
                "mutual_connections": 0,
                "relevance_score": 1.0,
                "profile_type": "company",
                "suggestion_type": "follow",
            })
        return pages

    def _search_company_pages(self, term: str) -> List[Dict[str, Any]]:
        """Search LinkedIn company pages for follow targets."""
        logger.info("Searching company pages with term: %s", term)
        search_url = (
            "https://www.linkedin.com/search/results/companies/"
            f"?keywords={term.replace(' ', '%20')}&origin=GLOBAL_SEARCH_HEADER"
        )
        self.page.goto(search_url, wait_until="domcontentloaded")
        self._random_delay(3, 6)

        profiles = []
        result_cards = self.page.query_selector_all(
            ".reusable-search__result-container, .entity-result, main li"
        )

        for card in result_cards[:5]:
            try:
                profile = self._extract_company_result(card)
                if profile:
                    profiles.append(profile)
            except Exception as e:
                logger.debug("Company result extraction error: %s", e)

        return profiles

    def _extract_company_result(self, element) -> Optional[Dict[str, Any]]:
        """Extract a company/page search result."""
        link_el = element.query_selector("a[href*='/company/']")
        if not link_el:
            return None

        href = link_el.get_attribute("href") or ""
        profile_url = href if href.startswith("http") else "https://www.linkedin.com" + href
        profile_url = normalize_url(profile_url)

        name = self._clean_author_name(link_el.inner_text())
        raw = element.inner_text().strip()
        lines = [
            line.strip()
            for line in raw.splitlines()
            if line.strip() and self._normalize_for_match(line) != self._normalize_for_match(name)
        ]
        headline = lines[0] if lines else ""
        relevance = is_relevant(f"{name} {headline}", self.keywords, self.hashtags)

        if relevance < 0.1:
            return None

        return {
            "profile_url": profile_url,
            "full_name": name,
            "headline": headline,
            "industry": "Technology",
            "location": None,
            "connections_count": None,
            "mutual_connections": 0,
            "relevance_score": max(relevance, 0.5),
            "profile_type": "company",
            "suggestion_type": "follow",
        }

    def _extract_profile_card(self, element) -> Optional[Dict[str, Any]]:
        """Extract profile data from a PYMK card."""
        name_el = element.query_selector(
            ".discover-person-card__name, .mn-pymk-list__name"
        )
        headline_el = element.query_selector(
            ".discover-person-card__occupation, .mn-pymk-list__occupation"
        )
        link_el = element.query_selector("a[href*='/in/']")

        if not link_el:
            return None

        href = link_el.get_attribute("href") or ""
        profile_url = href if href.startswith("http") else "https://www.linkedin.com" + href

        return {
            "profile_url": normalize_url(profile_url),
            "full_name": name_el.inner_text().strip() if name_el else "Unknown",
            "headline": headline_el.inner_text().strip() if headline_el else "",
            "industry": None,
            "location": None,
            "connections_count": None,
            "mutual_connections": 0,
            "relevance_score": self._score_profile_headline(
                headline_el.inner_text() if headline_el else ""
            ),
        }

    def _extract_search_profile(self, element) -> Optional[Dict[str, Any]]:
        """Extract profile data from a search result card."""
        name_el = element.query_selector(
            ".entity-result__title-text, .actor-name"
        )
        headline_el = element.query_selector(
            ".entity-result__primary-subtitle"
        )
        location_el = element.query_selector(
            ".entity-result__secondary-subtitle"
        )
        link_el = element.query_selector("a[href*='/in/']")

        if not link_el:
            return None

        href = link_el.get_attribute("href") or ""
        profile_url = href if href.startswith("http") else "https://www.linkedin.com" + href

        headline = headline_el.inner_text().strip() if headline_el else ""

        return {
            "profile_url": normalize_url(profile_url),
            "full_name": name_el.inner_text().strip() if name_el else "Unknown",
            "headline": headline,
            "industry": None,
            "location": location_el.inner_text().strip() if location_el else None,
            "connections_count": None,
            "mutual_connections": 0,
            "relevance_score": self._score_profile_headline(
                " ".join([
                    headline,
                    location_el.inner_text() if location_el else "",
                    element.inner_text()[:300],
                ])
            ),
        }

    def _score_profile_headline(self, headline: str) -> float:
        """Score a profile based on how well their headline matches target roles."""
        if not headline:
            return 0.1
        headline_lower = headline.lower()
        matches = sum(1 for role in self.target_roles if role.lower() in headline_lower)
        location_matches = sum(
            1 for location in self.target_locations if location.lower() in headline_lower
        )
        keyword_matches = sum(1 for kw in self.keywords if kw.lower() in headline_lower)
        score = (
            matches / max(len(self.target_roles), 1) * 4.0
            + location_matches * 0.35
            + keyword_matches / max(len(self.keywords), 1) * 2.0
        )
        return min(score, 1.0)

    def _scroll_feed(self, scrolls: int = 3):
        """Scroll the page to load more content."""
        for _ in range(scrolls):
            self.page.evaluate("window.scrollBy(0, window.innerHeight * 0.8)")
            self._random_delay(1.5, 3.5)

    @staticmethod
    def _random_delay(min_s: float, max_s: float):
        time.sleep(random.uniform(min_s, max_s))
