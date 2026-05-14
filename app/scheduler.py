"""
app/scheduler.py
─────────────────
APScheduler background job that auto-publishes scheduled posts.
Runs every minute, checks for posts due to publish.
"""

import logging
import os
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)
_scheduler = None


def _publish_due_posts():
    """Called every minute by APScheduler."""
    # Import inside function to use app context
    try:
        from app.models import Post, db
        from app.instagram_publisher import get_publisher

        publisher = get_publisher()
        if not publisher:
            return  # Instagram not configured — skip silently

        now = datetime.now(timezone.utc)
        due_posts = Post.query.filter(
            Post.publish_status == "scheduled",
            Post.scheduled_at <= now,
            Post.image_public_url.isnot(None),
        ).all()

        for post in due_posts:
            logger.info("Auto-publishing post id=%d", post.id)
            result = publisher.publish_image_post(
                image_url=post.image_public_url,
                caption=post.full_caption(),
            )
            if result.get("success"):
                post.publish_status = "published"
                post.published_at   = now
                post.ig_media_id    = result.get("media_id", "")
                post.is_used        = True
                logger.info("Post %d published. IG media_id=%s", post.id, post.ig_media_id)
            else:
                post.publish_status = "failed"
                post.publish_error  = str(result.get("error", "Unknown error"))
                logger.error("Post %d publish failed: %s", post.id, post.publish_error)
            db.session.commit()

    except Exception as exc:
        logger.error("Scheduler job error: %s", exc, exc_info=True)


def start_scheduler(app):
    """Start background scheduler attached to Flask app context."""
    global _scheduler
    if _scheduler and _scheduler.running:
        return

    _scheduler = BackgroundScheduler(timezone="UTC")

    def job_with_context():
        with app.app_context():
            _publish_due_posts()

    _scheduler.add_job(
        func=job_with_context,
        trigger="interval",
        minutes=1,
        id="auto_publisher",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Background scheduler started — checking for due posts every minute.")


def stop_scheduler():
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")