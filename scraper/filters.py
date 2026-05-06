"""
Spam detection and duplicate filtering for scraped LinkedIn content.
"""

import re
import hashlib
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

# Patterns that indicate low-quality or spam content
SPAM_PATTERNS = [
    r"\b(follow me|follow back|f4f|like4like|l4l)\b",
    r"\b(buy now|limited offer|discount|promo code|coupon)\b",
    r"\b(make money|earn \$|passive income|financial freedom)\b",
    r"\b(click the link|link in bio|swipe up)\b",
    r"(🔥){3,}",          # Excessive fire emojis
    r"(!!!){2,}",          # Excessive exclamation marks
    r"(https?://\S+){3,}", # More than 2 URLs in a post
    r"\b(MLM|pyramid|network marketing)\b",
    r"\b(crypto|NFT|token|blockchain)\b.*\b(invest|profit|gain)\b",
]

SPAM_REGEX = re.compile("|".join(SPAM_PATTERNS), re.IGNORECASE)

# Minimum meaningful content length (characters)
MIN_CONTENT_LENGTH = 50


def is_spam(post: Dict[str, Any]) -> bool:
    """Return True if the post appears to be spam or low quality."""
    content = post.get("content", "") or ""

    # Too short
    if len(content.strip()) < MIN_CONTENT_LENGTH:
        logger.debug("Post too short: %s chars", len(content))
        return True

    # Matches spam patterns
    if SPAM_REGEX.search(content):
        logger.debug("Post matches spam pattern")
        return True

    # Suspiciously high hashtag density (>10 hashtags = likely spam)
    hashtag_count = len(re.findall(r"#\w+", content))
    if hashtag_count > 10:
        logger.debug("Too many hashtags: %d", hashtag_count)
        return True

    return False


def extract_hashtags(content: str) -> List[str]:
    """Extract all hashtags from post content."""
    return re.findall(r"#(\w+)", content)


def normalize_url(url: str) -> str:
    """Strip tracking parameters from LinkedIn URLs."""
    # Remove query params that are just tracking
    url = re.sub(r"\?.*$", "", url)
    # Normalize trailing slash
    url = url.rstrip("/")
    return url


def content_hash(url: str) -> str:
    """Generate a stable hash for deduplication."""
    return hashlib.md5(normalize_url(url).encode()).hexdigest()


def is_relevant(content: str, keywords: List[str], hashtags: List[str]) -> float:
    """
    Return a relevance score 0.0–1.0 based on keyword/hashtag matches.
    Higher = more relevant.
    """
    if not content:
        return 0.0

    content_lower = content.lower()
    score = 0.0
    total_signals = len(keywords) + len(hashtags)

    if total_signals == 0:
        return 0.5  # No filter configured, treat everything as neutral

    matched = 0
    for kw in keywords:
        if kw.lower() in content_lower:
            matched += 1

    post_hashtags = [h.lower() for h in extract_hashtags(content)]
    for ht in hashtags:
        clean_ht = ht.lstrip("#").lower()
        if clean_ht in post_hashtags:
            matched += 1

    score = matched / total_signals
    return min(score * 3.0, 1.0)  # Amplify small matches, cap at 1.0
