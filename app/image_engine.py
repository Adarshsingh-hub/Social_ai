"""
app/image_engine.py
────────────────────
DALL-E 3 image generation + Cloudinary upload.
Cloudinary gives a public URL that Instagram's API can pull from.
"""

import logging
import os
import re
import time
import uuid
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

GENERATED_DIR = Path(__file__).parent / "static" / "generated"
GENERATED_DIR.mkdir(parents=True, exist_ok=True)


# ─── Lazy OpenAI client ───────────────────────────────────────────────────────

_openai_client = None


def _get_openai():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        _openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _openai_client


# ─── Cloudinary setup ─────────────────────────────────────────────────────────

_cloudinary_configured = False


def _setup_cloudinary():
    global _cloudinary_configured
    if _cloudinary_configured:
        return True
    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME", "")
    api_key    = os.getenv("CLOUDINARY_API_KEY", "")
    api_secret = os.getenv("CLOUDINARY_API_SECRET", "")
    if not all([cloud_name, api_key, api_secret]):
        logger.warning("Cloudinary not configured — images won't be auto-posted to Instagram.")
        return False
    import cloudinary
    cloudinary.config(cloud_name=cloud_name, api_key=api_key, api_secret=api_secret)
    _cloudinary_configured = True
    return True


# ─── Prompt builder ───────────────────────────────────────────────────────────

def build_dalle_prompt(
    image_prompt: str,
    business_name: str,
    category: str,
    post_type: str,
) -> str:
    """
    Turn a short image idea into a detailed DALL-E 3 prompt.
    Enforces: no text/watermarks, professional photography style.
    """
    style_map = {
        "promo":             "vibrant product photography, bright studio lighting",
        "tip":               "clean infographic style, minimal flat design",
        "testimonial":       "warm lifestyle photography, natural light",
        "behind_the_scenes": "authentic candid photography, warm tones",
        "festival_offer":    "festive Indian celebration, colorful and joyful",
        "reel_idea":         "dynamic motion blur, energetic composition",
        "story_poll":        "bold graphic design, high contrast colors",
        "product_spotlight": "luxury product photography, dark background with spotlighting",
        "customer_love":     "happy customer lifestyle photography, genuine smiles",
        "motivational":      "inspiring sunrise/nature, uplifting atmosphere",
    }
    style = style_map.get(post_type, "professional commercial photography")

    # Strip any mention of text/logos from the original prompt
    clean_prompt = re.sub(
        r"\b(text|logo|watermark|caption|words|write|label|sign|banner)\b",
        "", image_prompt, flags=re.IGNORECASE
    ).strip()

    return (
        f"{clean_prompt}. "
        f"Style: {style}. "
        f"Category: {category} business. "
        f"High quality, professional Instagram post image. "
        f"No text, no words, no watermarks, no logos anywhere in the image. "
        f"Square 1:1 aspect ratio composition."
    )


# ─── DALL-E 3 Generation ──────────────────────────────────────────────────────

def generate_image(
    image_prompt: str,
    business_name: str,
    category: str,
    post_type: str,
) -> dict:
    """
    Generate an image with DALL-E 3.
    Returns: { "local_path": str, "public_url": str|None, "dalle_url": str }
    """
    prompt = build_dalle_prompt(image_prompt, business_name, category, post_type)
    logger.info("Generating image for post_type=%s", post_type)

    try:
        client = _get_openai()
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            quality="standard",
            n=1,
        )
        dalle_url = response.data[0].url
        logger.info("DALL-E 3 image generated: %s", dalle_url[:60])
    except Exception as exc:
        logger.error("DALL-E 3 generation failed: %s", exc)
        return {"error": str(exc), "local_path": None, "public_url": None, "dalle_url": None}

    # ── Download to local disk ────────────────────────────────────────────────
    filename    = f"{uuid.uuid4().hex}.png"
    local_path  = GENERATED_DIR / filename
    try:
        img_data = requests.get(dalle_url, timeout=30)
        img_data.raise_for_status()
        with open(local_path, "wb") as f:
            f.write(img_data.content)
        logger.info("Image saved locally: %s", local_path)
    except Exception as exc:
        logger.error("Failed to download DALL-E image: %s", exc)
        return {"error": str(exc), "local_path": None, "public_url": None, "dalle_url": dalle_url}

    # ── Upload to Cloudinary for a permanent public URL ────────────────────────
    public_url = None
    if _setup_cloudinary():
        try:
            import cloudinary.uploader
            result = cloudinary.uploader.upload(
                str(local_path),
                folder="social_ai",
                resource_type="image",
                transformation=[
                    {"width": 1080, "height": 1080, "crop": "fill", "gravity": "center"},
                    {"quality": "auto", "fetch_format": "auto"},
                ],
            )
            public_url = result.get("secure_url")
            logger.info("Uploaded to Cloudinary: %s", public_url)
        except Exception as exc:
            logger.error("Cloudinary upload failed: %s", exc)

    return {
        "local_path":  str(local_path),
        "filename":    filename,
        "public_url":  public_url,
        "dalle_url":   dalle_url,
        "error":       None,
    }