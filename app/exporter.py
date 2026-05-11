"""app/exporter.py — Export content calendar to CSV and PDF"""

import csv
import io
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)


def export_to_csv(posts: list, business_name: str) -> bytes:
    """Export posts to CSV. Returns bytes."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Day", "Post Type", "Platform", "Caption",
        "Hashtags", "Image Prompt", "Best Time", "Used"
    ])
    for p in posts:
        writer.writerow([
            getattr(p, "day_number", ""),
            getattr(p, "post_type", ""),
            getattr(p, "platform", ""),
            getattr(p, "caption", ""),
            getattr(p, "hashtags", ""),
            getattr(p, "image_prompt", ""),
            getattr(p, "best_time", ""),
            "Yes" if getattr(p, "is_used", False) else "No",
        ])
    return output.getvalue().encode("utf-8-sig")  # utf-8-sig for Excel compatibility


def export_to_txt(posts: list, business_name: str) -> bytes:
    """Export posts to plain text file for easy WhatsApp copy-paste."""
    lines = []
    lines.append(f"CONTENT CALENDAR — {business_name.upper()}")
    lines.append(f"Generated: {datetime.now().strftime('%d %B %Y')}")
    lines.append("=" * 60)
    lines.append("")

    for p in posts:
        lines.append(f"📅 DAY {getattr(p, 'day_number', '')} | {getattr(p, 'post_type', '').upper().replace('_', ' ')}")
        lines.append(f"⏰ Best Time: {getattr(p, 'best_time', '')}")
        lines.append("")
        lines.append("CAPTION:")
        lines.append(getattr(p, "caption", ""))
        lines.append("")
        lines.append("HASHTAGS:")
        lines.append(getattr(p, "hashtags", ""))
        lines.append("")
        lines.append("IMAGE IDEA:")
        lines.append(getattr(p, "image_prompt", ""))
        lines.append("")
        lines.append("-" * 60)
        lines.append("")

    return "\n".join(lines).encode("utf-8")