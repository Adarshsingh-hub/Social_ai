"""app/routes.py — All Flask routes"""

import json
import logging
import os
from datetime import datetime, timezone

from flask import (Blueprint, Response, flash, jsonify, redirect,
                   render_template, request, send_from_directory, url_for)

from app.ai_engine import (POST_TYPES, generate_caption_variants,
                            generate_festival_posts, generate_month_content,
                            generate_single_post, suggest_content_strategy)
from app.exporter import export_to_csv, export_to_txt
from app.image_engine import generate_image
from app.instagram_publisher import get_publisher
from app.models import Business, Post, db

logger = logging.getLogger(__name__)
bp = Blueprint("main", __name__)

FESTIVALS = [
    "Diwali", "Holi", "Eid", "Navratri", "Dussehra",
    "Christmas", "New Year", "Independence Day", "Republic Day",
    "Raksha Bandhan", "Valentine's Day", "Mother's Day",
]

CATEGORIES = [
    "Restaurant / Food", "Clothing / Fashion", "Electronics",
    "Salon / Beauty", "Gym / Fitness", "Medical / Clinic",
    "Real Estate", "Education / Coaching", "Jewellery",
    "Grocery / Kirana", "Travel / Tours", "Photography",
    "Interior Design", "Automobile", "Other",
]


def _biz_dict(biz):
    return {
        "name": biz.name, "category": biz.category,
        "location": biz.location, "description": biz.description,
        "tone": biz.tone, "language": biz.language,
        "usp": biz.usp or "", "target_audience": biz.target_audience or "",
    }


# ─── Home ─────────────────────────────────────────────────────────────────────

@bp.route("/")
def index():
    businesses = Business.query.order_by(Business.created_at.desc()).all()
    return render_template("index.html", businesses=businesses)


# ─── Business CRUD ────────────────────────────────────────────────────────────

@bp.route("/business/new", methods=["GET", "POST"])
def new_business():
    if request.method == "POST":
        biz = Business(
            name            = request.form["name"].strip(),
            category        = request.form["category"].strip(),
            location        = request.form["location"].strip(),
            description     = request.form["description"].strip(),
            tone            = request.form.get("tone", "friendly"),
            language        = request.form.get("language", "hinglish"),
            usp             = request.form.get("usp", "").strip(),
            target_audience = request.form.get("target_audience", "").strip(),
        )
        db.session.add(biz)
        db.session.commit()
        flash(f"Business '{biz.name}' created!", "success")
        return redirect(url_for("main.dashboard", biz_id=biz.id))
    return render_template("new_business.html", categories=CATEGORIES)


@bp.route("/business/<int:biz_id>/edit", methods=["GET", "POST"])
def edit_business(biz_id):
    biz = Business.query.get_or_404(biz_id)
    if request.method == "POST":
        biz.name            = request.form["name"].strip()
        biz.category        = request.form["category"].strip()
        biz.location        = request.form["location"].strip()
        biz.description     = request.form["description"].strip()
        biz.tone            = request.form.get("tone", "friendly")
        biz.language        = request.form.get("language", "hinglish")
        biz.usp             = request.form.get("usp", "").strip()
        biz.target_audience = request.form.get("target_audience", "").strip()
        db.session.commit()
        flash("Business updated!", "success")
        return redirect(url_for("main.dashboard", biz_id=biz.id))
    return render_template("new_business.html", biz=biz, categories=CATEGORIES)


@bp.route("/business/<int:biz_id>/delete", methods=["POST"])
def delete_business(biz_id):
    biz = Business.query.get_or_404(biz_id)
    db.session.delete(biz)
    db.session.commit()
    flash("Business deleted.", "info")
    return redirect(url_for("main.index"))


# ─── Dashboard ────────────────────────────────────────────────────────────────

@bp.route("/business/<int:biz_id>")
def dashboard(biz_id):
    biz   = Business.query.get_or_404(biz_id)
    posts = Post.query.filter_by(business_id=biz_id).order_by(Post.day_number).all()
    stats = {
        "total":     len(posts),
        "used":      sum(1 for p in posts if p.is_used),
        "remaining": sum(1 for p in posts if not p.is_used),
        "with_image":sum(1 for p in posts if p.image_status == "ready"),
        "scheduled": sum(1 for p in posts if p.publish_status == "scheduled"),
        "published": sum(1 for p in posts if p.publish_status == "published"),
    }
    ig_configured = bool(os.getenv("INSTAGRAM_ACCESS_TOKEN") and os.getenv("INSTAGRAM_ACCOUNT_ID"))
    return render_template("dashboard.html", biz=biz, posts=posts,
                           stats=stats, post_types=POST_TYPES, festivals=FESTIVALS,
                           ig_configured=ig_configured)


# ─── Generate Full Month (text only) ──────────────────────────────────────────

@bp.route("/business/<int:biz_id>/generate", methods=["POST"])
def generate_content(biz_id):
    biz      = Business.query.get_or_404(biz_id)
    num      = int(request.form.get("num_posts", 30))
    platform = request.form.get("platform", "instagram")
    replace  = request.form.get("replace_existing") == "on"

    if replace:
        Post.query.filter_by(business_id=biz_id).delete()
        db.session.commit()

    posts_data = generate_month_content(_biz_dict(biz), num_posts=num, platform=platform)
    if not posts_data:
        flash("AI generation failed. Check your OPENAI_API_KEY.", "danger")
        return redirect(url_for("main.dashboard", biz_id=biz_id))

    for item in posts_data:
        post = Post(
            business_id  = biz_id,
            post_type    = item.get("post_type", "promo"),
            platform     = platform,
            caption      = item.get("caption", ""),
            hashtags     = item.get("hashtags", ""),
            image_prompt = item.get("image_prompt", ""),
            best_time    = item.get("best_time", "7:00 PM"),
            day_number   = int(item.get("day", 1)),
            image_status = "none",
            publish_status = "draft",
        )
        db.session.add(post)
    db.session.commit()

    flash(f"{len(posts_data)} posts generated! Now generate images for each post.", "success")
    return redirect(url_for("main.dashboard", biz_id=biz_id))


# ─── Generate Image for ONE post ──────────────────────────────────────────────

@bp.route("/post/<int:post_id>/generate-image", methods=["POST"])
def generate_post_image(post_id):
    post = Post.query.get_or_404(post_id)
    biz  = post.business

    post.image_status = "generating"
    db.session.commit()

    result = generate_image(
        image_prompt  = post.image_prompt or post.caption[:100],
        business_name = biz.name,
        category      = biz.category,
        post_type     = post.post_type,
    )

    if result.get("error"):
        post.image_status = "failed"
        db.session.commit()
        return jsonify({"success": False, "error": result["error"]}), 500

    post.image_local      = result.get("filename")
    post.image_public_url = result.get("public_url") or result.get("dalle_url")
    post.image_status     = "ready"
    db.session.commit()

    return jsonify({
        "success":    True,
        "filename":   post.image_local,
        "public_url": post.image_public_url,
        "local_url":  f"/images/{post.image_local}" if post.image_local else None,
    })


# ─── Generate images for ALL posts in batch ───────────────────────────────────

@bp.route("/business/<int:biz_id>/generate-all-images", methods=["POST"])
def generate_all_images(biz_id):
    """Generate DALL-E images for all posts that don't have one yet."""
    biz   = Business.query.get_or_404(biz_id)
    posts = Post.query.filter_by(
        business_id=biz_id, image_status="none"
    ).order_by(Post.day_number).limit(10).all()  # limit 10 at once (cost control)

    if not posts:
        return jsonify({"success": False, "message": "No posts need images."})

    results = []
    for post in posts:
        post.image_status = "generating"
        db.session.commit()

        result = generate_image(
            image_prompt  = post.image_prompt or post.caption[:100],
            business_name = biz.name,
            category      = biz.category,
            post_type     = post.post_type,
        )
        if result.get("error"):
            post.image_status = "failed"
        else:
            post.image_local      = result.get("filename")
            post.image_public_url = result.get("public_url") or result.get("dalle_url")
            post.image_status     = "ready"

        db.session.commit()
        results.append({"post_id": post.id, "success": post.image_status == "ready"})

    success_count = sum(1 for r in results if r["success"])
    return jsonify({
        "success": True,
        "generated": success_count,
        "failed": len(results) - success_count,
        "results": results,
    })


# ─── Serve generated images ───────────────────────────────────────────────────

@bp.route("/images/<path:filename>")
def serve_image(filename):
    from app.image_engine import GENERATED_DIR
    return send_from_directory(str(GENERATED_DIR), filename)


# ─── Schedule a post ──────────────────────────────────────────────────────────

@bp.route("/post/<int:post_id>/schedule", methods=["POST"])
def schedule_post(post_id):
    post = Post.query.get_or_404(post_id)

    if not post.image_public_url:
        return jsonify({"success": False, "error": "Generate an image first before scheduling."}), 400

    scheduled_str = request.form.get("scheduled_at", "")
    if not scheduled_str:
        return jsonify({"success": False, "error": "No schedule time provided."}), 400

    try:
        # Expect ISO format: "2025-06-15T19:00"
        naive_dt = datetime.fromisoformat(scheduled_str)
        aware_dt = naive_dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return jsonify({"success": False, "error": "Invalid date format."}), 400

    post.scheduled_at   = aware_dt
    post.publish_status = "scheduled"
    db.session.commit()

    return jsonify({
        "success":      True,
        "scheduled_at": aware_dt.isoformat(),
        "message":      f"Post scheduled for {aware_dt.strftime('%d %b %Y at %H:%M UTC')}",
    })


# ─── Publish a post NOW ───────────────────────────────────────────────────────

@bp.route("/post/<int:post_id>/publish-now", methods=["POST"])
def publish_now(post_id):
    post = Post.query.get_or_404(post_id)

    if not post.image_public_url:
        return jsonify({"success": False, "error": "Generate an image first."}), 400

    publisher = get_publisher()
    if not publisher:
        return jsonify({
            "success": False,
            "error": "Instagram not configured. Add INSTAGRAM_ACCESS_TOKEN and INSTAGRAM_ACCOUNT_ID to .env"
        }), 400

    result = publisher.publish_image_post(
        image_url = post.image_public_url,
        caption   = post.full_caption(),
    )

    if result.get("success"):
        post.publish_status = "published"
        post.published_at   = datetime.now(timezone.utc)
        post.ig_media_id    = result.get("media_id", "")
        post.is_used        = True
        db.session.commit()
        return jsonify({"success": True, "media_id": post.ig_media_id})
    else:
        post.publish_status = "failed"
        post.publish_error  = str(result.get("error", ""))
        db.session.commit()
        return jsonify({"success": False, "error": post.publish_error}), 500


# ─── Cancel schedule ──────────────────────────────────────────────────────────

@bp.route("/post/<int:post_id>/unschedule", methods=["POST"])
def unschedule_post(post_id):
    post = Post.query.get_or_404(post_id)
    post.scheduled_at   = None
    post.publish_status = "draft"
    db.session.commit()
    return jsonify({"success": True})


# ─── Single Post Generator ────────────────────────────────────────────────────

@bp.route("/business/<int:biz_id>/single", methods=["POST"])
def generate_single(biz_id):
    biz       = Business.query.get_or_404(biz_id)
    post_type = request.form.get("post_type", "promo")
    platform  = request.form.get("platform", "instagram")
    context   = request.form.get("context", "")

    data = generate_single_post(_biz_dict(biz), post_type, platform, context)
    if not data:
        return jsonify({"error": "Generation failed"}), 500

    post = Post(
        business_id    = biz_id,
        post_type      = post_type,
        platform       = platform,
        caption        = data.get("caption", ""),
        hashtags       = data.get("hashtags", ""),
        image_prompt   = data.get("image_prompt", ""),
        best_time      = data.get("best_time", "7:00 PM"),
        day_number     = Post.query.filter_by(business_id=biz_id).count() + 1,
        image_status   = "none",
        publish_status = "draft",
    )
    db.session.add(post)
    db.session.commit()

    return jsonify({
        "id":           post.id,
        "post_type":    post.post_type,
        "caption":      post.caption,
        "hashtags":     post.hashtags,
        "image_prompt": post.image_prompt,
        "best_time":    post.best_time,
    })


# ─── Caption Variants ─────────────────────────────────────────────────────────

@bp.route("/business/<int:biz_id>/variants", methods=["POST"])
def caption_variants(biz_id):
    biz      = Business.query.get_or_404(biz_id)
    topic    = request.form.get("topic", "")
    platform = request.form.get("platform", "instagram")
    variants = generate_caption_variants(_biz_dict(biz), topic, platform)
    return jsonify({"variants": variants})


# ─── Festival Post ────────────────────────────────────────────────────────────

@bp.route("/business/<int:biz_id>/festival", methods=["POST"])
def festival_post(biz_id):
    biz      = Business.query.get_or_404(biz_id)
    festival = request.form.get("festival", "Diwali")
    data     = generate_festival_posts(_biz_dict(biz), festival)
    if not data:
        return jsonify({"error": "Generation failed"}), 500

    post = Post(
        business_id    = biz_id,
        post_type      = "festival_offer",
        platform       = "instagram",
        caption        = data.get("caption", ""),
        hashtags       = data.get("hashtags", ""),
        image_prompt   = data.get("image_prompt", ""),
        best_time      = data.get("best_time", "9:00 AM"),
        day_number     = Post.query.filter_by(business_id=biz_id).count() + 1,
        image_status   = "none",
        publish_status = "draft",
    )
    db.session.add(post)
    db.session.commit()
    return jsonify({"id": post.id, "caption": post.caption,
                    "hashtags": post.hashtags, "image_prompt": post.image_prompt})


# ─── Strategy ─────────────────────────────────────────────────────────────────

@bp.route("/business/<int:biz_id>/strategy")
def strategy(biz_id):
    biz  = Business.query.get_or_404(biz_id)
    data = suggest_content_strategy(_biz_dict(biz))
    return render_template("strategy.html", biz=biz, strategy=data)


# ─── Post Actions ─────────────────────────────────────────────────────────────

@bp.route("/post/<int:post_id>/toggle", methods=["POST"])
def toggle_used(post_id):
    post = Post.query.get_or_404(post_id)
    post.is_used = not post.is_used
    db.session.commit()
    return jsonify({"is_used": post.is_used})


@bp.route("/post/<int:post_id>/delete", methods=["POST"])
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    db.session.delete(post)
    db.session.commit()
    return jsonify({"status": "deleted"})


@bp.route("/post/<int:post_id>/edit", methods=["POST"])
def edit_post(post_id):
    post = Post.query.get_or_404(post_id)
    data = request.get_json()
    if "caption"  in data: post.caption  = data["caption"]
    if "hashtags" in data: post.hashtags = data["hashtags"]
    db.session.commit()
    return jsonify({"status": "updated"})


# ─── Exports ──────────────────────────────────────────────────────────────────

@bp.route("/business/<int:biz_id>/export/csv")
def export_csv(biz_id):
    biz   = Business.query.get_or_404(biz_id)
    posts = Post.query.filter_by(business_id=biz_id).order_by(Post.day_number).all()
    data  = export_to_csv(posts, biz.name)
    return Response(data, mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={biz.name}_content.csv"})


@bp.route("/business/<int:biz_id>/export/txt")
def export_txt(biz_id):
    biz   = Business.query.get_or_404(biz_id)
    posts = Post.query.filter_by(business_id=biz_id).order_by(Post.day_number).all()
    data  = export_to_txt(posts, biz.name)
    return Response(data, mimetype="text/plain",
                    headers={"Content-Disposition": f"attachment; filename={biz.name}_captions.txt"})


# ─── Instagram status check ───────────────────────────────────────────────────

@bp.route("/ig-status")
def ig_status():
    publisher = get_publisher()
    if not publisher:
        return jsonify({"configured": False, "message": "Instagram credentials not set in .env"})
    info = publisher.validate_token()
    if "error" in info:
        return jsonify({"configured": True, "valid": False, "error": info})
    account = publisher.get_account_insights()
    return jsonify({"configured": True, "valid": True, "account": account})


# ─── Health ───────────────────────────────────────────────────────────────────

@bp.route("/health")
def health():
    return jsonify({"status": "ok"})