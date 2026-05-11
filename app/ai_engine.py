"""app/ai_engine.py — GPT-4o-mini content generation engine"""

import json
import logging
import os
import re
from typing import Any

from openai import OpenAI

logger = logging.getLogger(__name__)
_client = None


def get_client():
    global _client
    if _client is None:
        key = os.environ.get("OPENAI_API_KEY", "")
        if not key:
            raise RuntimeError("OPENAI_API_KEY not set in .env")
        _client = OpenAI(api_key=key)
    return _client


MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

POST_TYPES = [
    "promo",
    "tip",
    "testimonial",
    "behind_the_scenes",
    "festival_offer",
    "reel_idea",
    "story_poll",
    "product_spotlight",
    "customer_love",
    "motivational",
]

PLATFORM_RULES = {
    "instagram": "Max 2200 chars caption. 20-30 hashtags. Use emojis. End with CTA.",
    "whatsapp":  "Max 500 chars. No hashtags. Conversational. Use bold (*text*) sparingly.",
    "facebook":  "Max 500 chars caption. 5-10 hashtags. Friendly and shareable.",
    "linkedin":  "Professional tone. 150-300 chars. 3-5 hashtags. No emojis.",
}

LANGUAGE_INSTRUCTIONS = {
    "hinglish": "Write in Hinglish — natural mix of Hindi and English like real Indian conversations. Use Devanagari sparingly for punch words only.",
    "english":  "Write in clear Indian English. Warm and relatable.",
    "hindi":    "Write primarily in Hindi using Roman script (not Devanagari). Easy to read on mobile.",
}

TONE_MAP = {
    "friendly":      "warm, approachable, like a trusted neighbour",
    "professional":  "polished, expert, authoritative but not stiff",
    "fun":           "playful, punchy, uses humour and wordplay",
    "luxury":        "premium, aspirational, exclusive feeling",
    "urgent":        "creates FOMO, urgency, limited time energy",
}


def _clean_json(text: str) -> str:
    """Strip markdown fences GPT sometimes wraps around JSON."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _build_system_prompt(biz: dict) -> str:
    lang_instr  = LANGUAGE_INSTRUCTIONS.get(biz.get("language", "hinglish"), LANGUAGE_INSTRUCTIONS["hinglish"])
    tone_desc   = TONE_MAP.get(biz.get("tone", "friendly"), TONE_MAP["friendly"])
    return f"""You are an expert Indian social media content creator and copywriter.
You create viral, engaging content for Indian businesses on Instagram, WhatsApp, and Facebook.

BUSINESS PROFILE:
- Name: {biz['name']}
- Category: {biz['category']}
- Location: {biz['location']}
- Description: {biz['description']}
- USP: {biz.get('usp', 'Quality and trust')}
- Target Audience: {biz.get('target_audience', 'Local customers')}

WRITING RULES:
- Language: {lang_instr}
- Tone: {tone_desc}
- Always mention the business name naturally
- Make it hyper-local — mention the city/area
- Include a clear call to action (DM us, call now, visit today, link in bio)
- Be specific — use real-feeling details, not generic fluff
- Indian context: UPI, local festivals, Indian slang where appropriate"""


def generate_month_content(biz: dict, num_posts: int = 30, platform: str = "instagram") -> list[dict]:
    """
    Generate a full month of social media posts for a business.
    Returns list of post dicts.
    """
    platform_rule = PLATFORM_RULES.get(platform, PLATFORM_RULES["instagram"])
    system_prompt = _build_system_prompt(biz)

    # Build a balanced content calendar
    type_rotation = (POST_TYPES * 4)[:num_posts]

    user_prompt = f"""Generate exactly {num_posts} social media posts for this business.

Platform: {platform.upper()}
Platform rules: {platform_rule}

Return ONLY a JSON array with exactly {num_posts} objects. Each object must have:
- "day": integer (1 to {num_posts})
- "post_type": one of {json.dumps(POST_TYPES)}
- "caption": the full post caption (follow platform rules)
- "hashtags": string of space-separated hashtags (empty string for WhatsApp)
- "image_prompt": a detailed prompt to generate the image in Canva/Midjourney (1-2 sentences)
- "best_time": best time to post e.g. "7:00 PM" or "12:30 PM"
- "day_label": label like "Day 1 - Monday" 

Use this content type rotation: {json.dumps(type_rotation)}

Make every post feel real, specific to {biz['name']} in {biz['location']}, and genuinely useful or interesting to their audience.
No two posts should feel the same. Vary hooks, formats, and angles.
Return ONLY the JSON array. No explanation, no markdown."""

    try:
        resp = get_client().chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            max_tokens=6000,
            temperature=0.85,
        )
        raw  = resp.choices[0].message.content
        data = json.loads(_clean_json(raw))
        if isinstance(data, list):
            return data
        logger.error("Expected list, got: %s", type(data))
        return []
    except json.JSONDecodeError as exc:
        logger.error("JSON parse failed: %s", exc)
        return []
    except Exception as exc:
        logger.error("Content generation failed: %s", exc)
        return []


def generate_single_post(biz: dict, post_type: str, platform: str = "instagram",
                          extra_context: str = "") -> dict:
    """Generate one post on demand."""
    platform_rule = PLATFORM_RULES.get(platform, PLATFORM_RULES["instagram"])
    system_prompt = _build_system_prompt(biz)

    user_prompt = f"""Write ONE {post_type} social media post.
Platform: {platform.upper()} — {platform_rule}
{f'Extra context: {extra_context}' if extra_context else ''}

Return ONLY a JSON object with:
- "caption": full post caption
- "hashtags": space-separated hashtags
- "image_prompt": Canva/Midjourney image prompt
- "best_time": recommended posting time

Return ONLY valid JSON."""

    try:
        resp = get_client().chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            max_tokens=800,
            temperature=0.85,
        )
        raw = resp.choices[0].message.content
        return json.loads(_clean_json(raw))
    except Exception as exc:
        logger.error("Single post generation failed: %s", exc)
        return {}


def generate_caption_variants(biz: dict, topic: str, platform: str = "instagram") -> list[dict]:
    """Generate 3 caption variants for A/B testing."""
    system_prompt = _build_system_prompt(biz)
    user_prompt = f"""Write 3 different caption variants for this topic: "{topic}"
Platform: {platform.upper()} — {PLATFORM_RULES.get(platform, '')}

Each variant should have a completely different hook and angle.
Return ONLY a JSON array of 3 objects, each with:
- "variant": "A", "B", or "C"
- "hook_style": e.g. "Question", "Bold claim", "Story"
- "caption": full caption
- "hashtags": hashtags string
Return ONLY valid JSON array."""

    try:
        resp = get_client().chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            max_tokens=1500,
            temperature=0.9,
        )
        raw = resp.choices[0].message.content
        return json.loads(_clean_json(raw))
    except Exception as exc:
        logger.error("Variants generation failed: %s", exc)
        return []


def generate_festival_posts(biz: dict, festival: str) -> dict:
    """Generate a festival-specific promotional post."""
    system_prompt = _build_system_prompt(biz)
    user_prompt = f"""Create a {festival} special post for this business.
Make it festive, warm, and include a special offer or greeting.
Return ONLY a JSON object with: caption, hashtags, image_prompt, best_time.
Return ONLY valid JSON."""

    try:
        resp = get_client().chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            max_tokens=600,
            temperature=0.85,
        )
        return json.loads(_clean_json(resp.choices[0].message.content))
    except Exception as exc:
        logger.error("Festival post failed: %s", exc)
        return {}


def suggest_content_strategy(biz: dict) -> dict:
    """Generate a complete content strategy recommendation."""
    user_prompt = f"""As a social media strategist, create a content strategy for:
Business: {biz['name']} ({biz['category']}) in {biz['location']}
Description: {biz['description']}

Return ONLY a JSON object with:
- "posting_frequency": recommended posts per week
- "best_days": list of best days to post
- "best_times": list of best times
- "content_pillars": list of 5 content themes with description
- "hashtag_strategy": object with "niche" (5 tags), "local" (5 tags), "broad" (5 tags)
- "growth_tips": list of 5 actionable tips specific to this business
- "competitor_angles": list of 3 unique angles competitors are NOT doing
Return ONLY valid JSON."""

    try:
        resp = get_client().chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": user_prompt}],
            max_tokens=1200,
            temperature=0.7,
        )
        return json.loads(_clean_json(resp.choices[0].message.content))
    except Exception as exc:
        logger.error("Strategy generation failed: %s", exc)
        return {}