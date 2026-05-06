"""
Generates contextual comment drafts for LinkedIn posts.
Uses template-based generation — no external API required.
Templates are designed to sound natural and professional.
"""

import random
import re
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

# ── Comment templates by topic ─────────────────────────────────────────────────

TEMPLATES = {
    "ai": [
        "Really insightful perspective on {topic}. The shift toward {keyword} is something I've been following closely — curious how you see it evolving over the next 12 months?",
        "Great point about {topic}. In my experience working with {keyword}, the biggest challenge is still {challenge}. Would love to hear your take.",
        "This resonates a lot. {topic} is moving faster than most people realize. Thanks for sharing this.",
        "Solid breakdown of {topic}. The {keyword} angle is often overlooked — glad someone's talking about it.",
    ],
    "embedded": [
        "Interesting work on {topic}. Have you considered using {keyword} for the real-time constraints? Always curious about the tradeoffs.",
        "Great insight on {topic}. The hardware-software co-design challenge in {keyword} is something I deal with regularly.",
        "This is a great overview of {topic}. The {keyword} ecosystem has matured a lot — what's your preferred toolchain?",
        "Solid post on {topic}. Debugging {keyword} systems is always an adventure — any tips you'd share?",
    ],
    "software": [
        "Good points on {topic}. The {keyword} pattern has been a game-changer for maintainability in my projects.",
        "Interesting take on {topic}. I've been exploring {keyword} recently and the developer experience has improved significantly.",
        "This is a great summary of {topic}. The {keyword} ecosystem keeps evolving — what's your go-to stack right now?",
        "Appreciate the breakdown of {topic}. {keyword} is often underestimated in production environments.",
    ],
    "general": [
        "Really valuable perspective here. Thanks for sharing your experience with {topic}.",
        "This is exactly the kind of content I come to LinkedIn for. Great insights on {topic}.",
        "Thoughtful post. The point about {topic} is something more people in the industry should be discussing.",
        "Well said. {topic} is a space worth watching closely — appreciate the analysis.",
    ],
}

CHALLENGES = [
    "latency optimization",
    "cross-team alignment",
    "scaling reliably",
    "keeping up with the pace of change",
    "balancing innovation with stability",
]

TOPIC_KEYWORDS = {
    "agentic ai": ("ai", "autonomous agents"),
    "llm": ("ai", "large language models"),
    "drone": ("embedded", "drone systems"),
    "embedded": ("embedded", "embedded development"),
    "stm32": ("embedded", "STM32"),
    "rtos": ("embedded", "real-time systems"),
    "full stack": ("software", "full-stack architecture"),
    "react": ("software", "React"),
    "python": ("software", "Python"),
    "electrical": ("general", "electrical engineering"),
    "pcb": ("general", "PCB design"),
}


def detect_topic(content: str) -> tuple:
    """Detect the main topic category and a relevant keyword from post content."""
    content_lower = content.lower()
    for trigger, (category, keyword) in TOPIC_KEYWORDS.items():
        if trigger in content_lower:
            return category, keyword
    return "general", _extract_first_noun(content)


def _extract_first_noun(content: str) -> str:
    """Naive extraction of a meaningful word from content for template filling."""
    # Remove hashtags and URLs
    clean = re.sub(r"#\w+|https?://\S+", "", content)
    words = [w for w in clean.split() if len(w) > 4 and w[0].isupper()]
    return words[0] if words else "this topic"


def generate_comment_draft(post: Dict[str, Any]) -> str:
    """
    Generate a contextual comment draft for a post.
    Returns a string comment suggestion.
    """
    content = post.get("content", "")
    author = post.get("author_name", "")

    category, keyword = detect_topic(content)
    templates = TEMPLATES.get(category, TEMPLATES["general"])
    template = random.choice(templates)

    # Extract a short topic phrase from the post
    topic = _extract_topic_phrase(content)
    challenge = random.choice(CHALLENGES)

    comment = template.format(
        topic=topic,
        keyword=keyword,
        challenge=challenge,
        author=author,
    )

    return comment


def _extract_topic_phrase(content: str) -> str:
    """Extract a short representative phrase from post content."""
    # Take first sentence or first 60 chars
    sentences = re.split(r"[.!?\n]", content)
    for s in sentences:
        s = s.strip()
        if 10 < len(s) < 80:
            return s.lower()
    return content[:60].lower().strip()


def generate_multiple_drafts(post: Dict[str, Any], count: int = 3) -> List[str]:
    """Generate multiple comment options for the user to choose from."""
    drafts = set()
    attempts = 0
    while len(drafts) < count and attempts < 10:
        drafts.add(generate_comment_draft(post))
        attempts += 1
    return list(drafts)
