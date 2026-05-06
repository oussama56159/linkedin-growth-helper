"""
Scores and ranks scraped posts to determine which are worth engaging with.
Uses engagement metrics + relevance score + recency.
No external API required.
"""

import logging
import math
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

NEWS_SIGNALS = (
    "news",
    "article",
    "report",
    "analysis",
    "research",
    "announced",
    "launches",
    "released",
    "technology",
    "cybersecurity",
    "semiconductor",
    "cloud",
)


def score_post(post: Dict[str, Any], config: Dict[str, Any]) -> float:
    """
    Compute a composite engagement score for a post.
    Returns a float 0.0–100.0 (higher = better candidate for engagement).
    """
    if post.get("is_spam"):
        return 0.0

    scoring_cfg = config.get("scoring", {})
    min_likes = scoring_cfg.get("min_post_likes", 5)
    min_comments = scoring_cfg.get("min_post_comments", 1)

    likes = post.get("likes_count", 0) or 0
    comments = post.get("comments_count", 0) or 0
    reposts = post.get("reposts_count", 0) or 0
    relevance = post.get("relevance_score", 0.0) or 0.0
    age_hours = post.get("post_age_hours")
    source_bonus = _source_quality_bonus(post, config)

    # Hard filters
    if likes < min_likes and comments < min_comments:
        # LinkedIn search cards often hide engagement counts. If the scraper still
        # found a concrete post URL and the content is relevant, keep it as a
        # low-priority like candidate instead of dropping it entirely.
        post_url = post.get("post_url", "") or ""
        has_real_post_url = "/feed/update/" in post_url or "/posts/" in post_url
        if not has_real_post_url or relevance < 0.2:
            logger.debug(
                "Filtered post below engagement threshold: likes=%s comments=%s relevance=%.3f url=%s",
                likes,
                comments,
                relevance,
                post_url,
            )
            return 0.0
        engagement = 1.0
    else:
        # Engagement score: log-scale to avoid huge viral posts dominating
        engagement = (
            math.log1p(likes) * 1.0
            + math.log1p(comments) * 2.0   # Comments weighted higher
            + math.log1p(reposts) * 1.5
        )


    # Recency bonus: newer posts score higher
    recency_factor = 1.0
    if age_hours is not None:
        if age_hours <= 6:
            recency_factor = 1.5
        elif age_hours <= 24:
            recency_factor = 1.2
        elif age_hours <= 48:
            recency_factor = 1.0
        else:
            recency_factor = 0.6

    # Relevance multiplier (0.0–1.0 → 0.5–1.5 range to avoid zeroing out)
    relevance_multiplier = 0.5 + relevance + source_bonus

    final_score = engagement * recency_factor * relevance_multiplier
    return round(final_score, 3)


def _source_quality_bonus(post: Dict[str, Any], config: Dict[str, Any]) -> float:
    """Boost posts from configured tech/news pages and article-like content."""
    author = (post.get("author_name") or "").lower()
    author_url = (post.get("author_profile_url") or "").lower()
    content = (post.get("content") or "").lower()
    bonus = 0.0

    for page in config.get("targeting", {}).get("target_company_pages", []):
        page_name = (page.get("name") or "").lower()
        page_url = (page.get("url") or "").lower().rstrip("/")
        if page_name and page_name in author:
            bonus += 0.5
        if page_url and page_url in author_url.rstrip("/"):
            bonus += 0.5

    if any(signal in content for signal in NEWS_SIGNALS):
        bonus += 0.25
    if "/company/" in author_url:
        bonus += 0.15

    return min(bonus, 0.8)


def rank_posts(posts: List[Dict[str, Any]], config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Score and rank all posts. Returns sorted list (best first).
    Filters out spam and below-threshold posts.
    """
    scored = []
    for post in posts:
        score = score_post(post, config)
        if score > 0:
            post["final_score"] = score
            scored.append(post)

    scored.sort(key=lambda p: p["final_score"], reverse=True)
    logger.info("Ranked %d posts (from %d total)", len(scored), len(posts))
    return scored


def suggest_action(post: Dict[str, Any]) -> str:
    """
    Suggest the most appropriate action for a post based on its metrics.
    Returns: 'like', 'comment', or 'repost'
    """
    likes = post.get("likes_count", 0) or 0
    comments = post.get("comments_count", 0) or 0
    score = post.get("final_score", 0)
    author_url = post.get("author_profile_url", "") or ""
    content = (post.get("content") or "").lower()

    # High engagement + high relevance → comment (most valuable)
    if score > 5.0 and comments > 5:
        return "comment"

    # Moderate engagement → repost if very relevant
    if ("/company/" in author_url or any(signal in content for signal in NEWS_SIGNALS)) and post.get("relevance_score", 0) >= 0.2:
        return "repost"

    if score > 3.0 and post.get("relevance_score", 0) > 0.6:
        return "repost"

    # Default: like
    return "like"
