"""
Scores LinkedIn profiles to identify high-value networking targets.
"""

import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def score_profile(profile: Dict[str, Any], config: Dict[str, Any]) -> float:
    """
    Score a profile 0.0–100.0 for connection worthiness.
    """
    scoring_cfg = config.get("scoring", {})
    min_connections = scoring_cfg.get("min_profile_connections", 50)
    target_roles = config.get("targeting", {}).get("target_roles", [])
    target_industries = config.get("targeting", {}).get("target_industries", [])
    target_locations = config.get("targeting", {}).get("target_locations", [])

    headline = (profile.get("headline") or "").lower()
    industry = (profile.get("industry") or "").lower()
    location = (profile.get("location") or "").lower()
    search_query = (profile.get("search_query") or "").lower()
    connections = profile.get("connections_count") or 0
    mutual = profile.get("mutual_connections", 0) or 0
    base_relevance = profile.get("relevance_score", 0.0) or 0.0

    score = base_relevance * 40.0  # Up to 40 points from headline relevance

    # Role match bonus
    role_matches = sum(1 for r in target_roles if r.lower() in headline)
    score += min(role_matches * 10.0, 30.0)  # Up to 30 points

    # Industry match bonus
    industry_matches = sum(1 for i in target_industries if i.lower() in industry)
    score += min(industry_matches * 5.0, 15.0)  # Up to 15 points

    # Tunisia/local tech bonus
    location_matches = sum(
        1
        for loc in target_locations
        if loc.lower() in location or loc.lower() in headline or loc.lower() in search_query
    )
    score += min(location_matches * 12.0, 20.0)

    if any(term in f"{headline} {search_query}" for term in ["startup", "founder", "cto", "engineering manager"]):
        score += 8.0

    # Mutual connections bonus (social proof)
    score += min(mutual * 3.0, 15.0)  # Up to 15 points

    # Penalize profiles with very few connections (likely inactive/fake)
    if connections > 0 and connections < min_connections:
        score *= 0.5

    return round(min(score, 100.0), 3)


def rank_profiles(
    profiles: List[Dict[str, Any]], config: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Score and rank profiles. Returns sorted list (best first)."""
    scored = []
    for profile in profiles:
        s = score_profile(profile, config)
        if s > 5.0:  # Minimum threshold
            profile["final_score"] = s
            scored.append(profile)

    scored.sort(key=lambda p: p["final_score"], reverse=True)
    logger.info("Ranked %d profiles (from %d total)", len(scored), len(profiles))
    return scored


def build_connection_reason(profile: Dict[str, Any], config: Dict[str, Any]) -> str:
    """Generate a human-readable reason for connecting with this profile."""
    if profile.get("suggestion_type") == "follow" or profile.get("profile_type") == "company":
        headline = profile.get("headline", "")
        if headline:
            return f"High-signal technology/news source: {headline}"
        return "High-signal technology/news page to follow"

    headline = profile.get("headline", "")
    target_roles = config.get("targeting", {}).get("target_roles", [])
    mutual = profile.get("mutual_connections", 0) or 0

    matched_roles = [r for r in target_roles if r.lower() in headline.lower()]

    parts = []
    if matched_roles:
        parts.append(f"works as {matched_roles[0]}")
    if profile.get("location"):
        parts.append(f"based in {profile['location']}")
    elif any(loc.lower() in (profile.get("search_query") or "").lower() for loc in config.get("targeting", {}).get("target_locations", [])):
        parts.append("matched a Tunisia-focused tech search")
    if mutual > 0:
        parts.append(f"{mutual} mutual connection{'s' if mutual > 1 else ''}")
    if profile.get("industry"):
        parts.append(f"in {profile['industry']}")

    if parts:
        return "Relevant profile: " + ", ".join(parts)
    return "Matches your target network criteria"
