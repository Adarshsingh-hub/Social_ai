"""
app/instagram_publisher.py
───────────────────────────
Publishes images + captions to Instagram via the official Graph API.

REQUIREMENTS (one-time setup per client):
  1. Instagram Business or Creator account
  2. Connected to a Facebook Page
  3. Meta Developer App with instagram_content_publish permission approved
  4. Long-lived User Access Token (60-day, auto-refreshed here)

Flow: Upload media container → Publish container → Done.
"""

import logging
import os
import time
from datetime import datetime, timezone

import requests

logger = logging.getLogger(__name__)

GRAPH_URL = "https://graph.facebook.com/v21.0"


class InstagramPublisher:
    """Wraps Meta Graph API for Instagram content publishing."""

    def __init__(
        self,
        access_token: str,
        instagram_account_id: str,
        app_id: str = "",
        app_secret: str = "",
    ):
        self.access_token         = access_token
        self.instagram_account_id = instagram_account_id
        self.app_id               = app_id
        self.app_secret           = app_secret

    # ── Token management ──────────────────────────────────────────────────────

    def refresh_token(self) -> str | None:
        """Exchange current token for a fresh long-lived token (call monthly)."""
        if not self.app_id or not self.app_secret:
            logger.warning("Cannot refresh token — app_id/app_secret not set.")
            return None
        url = f"{GRAPH_URL}/oauth/access_token"
        params = {
            "grant_type":       "fb_exchange_token",
            "client_id":        self.app_id,
            "client_secret":    self.app_secret,
            "fb_exchange_token": self.access_token,
        }
        try:
            resp = requests.get(url, params=params, timeout=15)
            data = resp.json()
            if "access_token" in data:
                self.access_token = data["access_token"]
                logger.info("Access token refreshed successfully.")
                return self.access_token
            logger.error("Token refresh failed: %s", data)
            return None
        except Exception as exc:
            logger.error("Token refresh exception: %s", exc)
            return None

    def validate_token(self) -> dict:
        """Check if current token is valid. Returns token info dict."""
        url    = f"{GRAPH_URL}/me"
        params = {"access_token": self.access_token, "fields": "id,name"}
        try:
            resp = requests.get(url, params=params, timeout=10)
            return resp.json()
        except Exception as exc:
            return {"error": str(exc)}

    # ── Publishing ────────────────────────────────────────────────────────────

    def _create_media_container(self, image_url: str, caption: str) -> str | None:
        """
        Step 1: Create a media container on Instagram.
        Returns creation_id or None on failure.
        """
        url  = f"{GRAPH_URL}/{self.instagram_account_id}/media"
        data = {
            "image_url":    image_url,
            "caption":      caption,
            "access_token": self.access_token,
        }
        try:
            resp = requests.post(url, data=data, timeout=30)
            result = resp.json()
            if "id" in result:
                logger.info("Media container created: %s", result["id"])
                return result["id"]
            logger.error("Container creation failed: %s", result)
            return None
        except Exception as exc:
            logger.error("Container creation exception: %s", exc)
            return None

    def _check_container_status(self, container_id: str) -> str:
        """Poll container status until FINISHED or error."""
        url    = f"{GRAPH_URL}/{container_id}"
        params = {
            "fields":       "status_code,status",
            "access_token": self.access_token,
        }
        for attempt in range(10):
            try:
                resp   = requests.get(url, params=params, timeout=10)
                data   = resp.json()
                status = data.get("status_code", "")
                logger.info("Container status (attempt %d): %s", attempt + 1, status)
                if status == "FINISHED":
                    return "FINISHED"
                if status in ("ERROR", "EXPIRED"):
                    logger.error("Container status error: %s", data)
                    return status
                time.sleep(3)
            except Exception as exc:
                logger.error("Status check error: %s", exc)
                time.sleep(3)
        return "TIMEOUT"

    def _publish_container(self, container_id: str) -> dict:
        """
        Step 2: Publish the media container to Instagram Feed.
        Returns the published media response dict.
        """
        url  = f"{GRAPH_URL}/{self.instagram_account_id}/media_publish"
        data = {
            "creation_id":  container_id,
            "access_token": self.access_token,
        }
        try:
            resp   = requests.post(url, data=data, timeout=30)
            result = resp.json()
            if "id" in result:
                logger.info("Published to Instagram! Media ID: %s", result["id"])
                return {"success": True, "media_id": result["id"]}
            logger.error("Publish failed: %s", result)
            return {"success": False, "error": result}
        except Exception as exc:
            logger.error("Publish exception: %s", exc)
            return {"success": False, "error": str(exc)}

    def publish_image_post(self, image_url: str, caption: str) -> dict:
        """
        Full publish flow: container → status check → publish.
        image_url MUST be a publicly accessible HTTPS URL.
        Returns { success, media_id, error }.
        """
        if not image_url.startswith("https://"):
            return {"success": False, "error": "image_url must be a public HTTPS URL"}

        # Step 1 — create container
        container_id = self._create_media_container(image_url, caption)
        if not container_id:
            return {"success": False, "error": "Failed to create media container"}

        # Step 2 — wait for container to be ready
        time.sleep(5)
        status = self._check_container_status(container_id)
        if status != "FINISHED":
            return {"success": False, "error": f"Container not ready: {status}"}

        # Step 3 — publish
        return self._publish_container(container_id)

    def get_recent_posts(self, limit: int = 10) -> list:
        """Fetch recent Instagram posts for analytics."""
        url    = f"{GRAPH_URL}/{self.instagram_account_id}/media"
        params = {
            "fields":       "id,caption,media_type,timestamp,like_count,comments_count,permalink",
            "limit":        limit,
            "access_token": self.access_token,
        }
        try:
            resp = requests.get(url, params=params, timeout=15)
            data = resp.json()
            return data.get("data", [])
        except Exception as exc:
            logger.error("get_recent_posts failed: %s", exc)
            return []

    def get_account_insights(self) -> dict:
        """Get basic account metrics."""
        url    = f"{GRAPH_URL}/{self.instagram_account_id}"
        params = {
            "fields":       "name,username,followers_count,media_count,profile_picture_url",
            "access_token": self.access_token,
        }
        try:
            resp = requests.get(url, params=params, timeout=10)
            return resp.json()
        except Exception as exc:
            return {"error": str(exc)}


def get_publisher() -> InstagramPublisher | None:
    """
    Build an InstagramPublisher from environment variables.
    Returns None if not configured.
    """
    token      = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
    account_id = os.getenv("INSTAGRAM_ACCOUNT_ID", "")
    if not token or not account_id:
        return None
    return InstagramPublisher(
        access_token         = token,
        instagram_account_id = account_id,
        app_id               = os.getenv("META_APP_ID", ""),
        app_secret           = os.getenv("META_APP_SECRET", ""),
    )