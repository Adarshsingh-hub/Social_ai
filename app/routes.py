"""app/routes.py — All Flask routes"""

import json
import logging

from flask import (Blueprint, Response, flash, jsonify, redirect,
                   render_template, request, url_for)

from app.ai_engine import (POST_TYPES, generate_caption_variants,
                            generate_festival_posts, generate_month_content,
                            generate_single_post, suggest_content_strategy)
from app.exporter import export_to_csv, export_to_txt
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


# ─── Home ─────────────────────────────────────────────────────────────────────

@bp.route("/")
def index():
    businesses = Business.query.order_by(Business.created_at.desc()).all()
    return render_template("index.html", businesses=businesses)


# ─── Business CRUD ───────────────────────────────────────────────────────────

@bp.route("/business/new", methods=["GET", "POST"])
def new_business():
    if request.method == "POST":
        biz = Business(
            name=request.form["name"].strip(),
            category=request.form["category"].strip(),
            location=request.form["location"].strip(),
            description=request.form["description"].strip(),
            tone=request.form.get("tone", "friendly"),
            language=request.form.get("language", "hinglish"),
            usp=request.form.get("usp", "").strip(),
            target_audience=request.form.get("target_audience", "").strip(),
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
        "total":      len(posts),
        "used":       sum(1 for p in posts if p.is_used),
        "remaining":  sum(1 for p in posts if not p.is_used),
        "by_type":    {},
    }
    for p in posts:
        stats["by_type"][p.post_type] = stats["by_type"].get(p.post_type, 0) + 1
    return render_template("dashboard.html", biz=biz, posts=posts,
                           stats=stats, post_types=POST_TYPES, festivals=FESTIVALS)


# ─── Generate Full Month ──────────────────────────────────────────────────────

@bp.route("/business/<int:biz_id>/generate", methods=["POST"])
def generate_content(biz_id):
    biz      = Business.query.get_or_404(biz_id)
    num      = int(request.form.get("num_posts", 30))
    platform = request.form.get("platform", "instagram")
    replace  = request.form.get("replace_existing") == "on"

    if replace:
        Post.query.filter_by(business_id=biz_id).delete()
        db.session.commit()

    biz_dict = {
        "name": biz.name, "category": biz.category,
        "location": biz.location, "description": biz.description,
        "tone": biz.tone, "language": biz.language,
        "usp": biz.usp, "target_audience": biz.target_audience,
    }

    posts_data = generate_month_content(biz_dict, num_posts=num, platform=platform)

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
        )
        db.session.add(post)
    db.session.commit()

    flash(f"✅ {len(posts_data)} posts generated successfully!", "success")
    return redirect(url_for("main.dashboard", biz_id=biz_id))


# ─── Single Post Generator ────────────────────────────────────────────────────

@bp.route("/business/<int:biz_id>/single", methods=["POST"])
def generate_single(biz_id):
    biz       = Business.query.get_or_404(biz_id)
    post_type = request.form.get("post_type", "promo")
    platform  = request.form.get("platform", "instagram")
    context   = request.form.get("context", "")

    biz_dict = {
        "name": biz.name, "category": biz.category,
        "location": biz.location, "description": biz.description,
        "tone": biz.tone, "language": biz.language,
        "usp": biz.usp, "target_audience": biz.target_audience,
    }

    data = generate_single_post(biz_dict, post_type, platform, context)
    if not data:
        return jsonify({"error": "Generation failed"}), 500

    post = Post(
        business_id  = biz_id,
        post_type    = post_type,
        platform     = platform,
        caption      = data.get("caption", ""),
        hashtags     = data.get("hashtags", ""),
        image_prompt = data.get("image_prompt", ""),
        best_time    = data.get("best_time", "7:00 PM"),
        day_number   = Post.query.filter_by(business_id=biz_id).count() + 1,
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


# ─── Caption Variants (A/B) ───────────────────────────────────────────────────

@bp.route("/business/<int:biz_id>/variants", methods=["POST"])
def caption_variants(biz_id):
    biz     = Business.query.get_or_404(biz_id)
    topic   = request.form.get("topic", "")
    platform = request.form.get("platform", "instagram")

    biz_dict = {
        "name": biz.name, "category": biz.category,
        "location": biz.location, "description": biz.description,
        "tone": biz.tone, "language": biz.language,
        "usp": biz.usp, "target_audience": biz.target_audience,
    }

    variants = generate_caption_variants(biz_dict, topic, platform)
    return jsonify({"variants": variants})


# ─── Festival Post ────────────────────────────────────────────────────────────

@bp.route("/business/<int:biz_id>/festival", methods=["POST"])
def festival_post(biz_id):
    biz      = Business.query.get_or_404(biz_id)
    festival = request.form.get("festival", "Diwali")

    biz_dict = {
        "name": biz.name, "category": biz.category,
        "location": biz.location, "description": biz.description,
        "tone": biz.tone, "language": biz.language,
        "usp": biz.usp, "target_audience": biz.target_audience,
    }

    data = generate_festival_posts(biz_dict, festival)
    if not data:
        return jsonify({"error": "Generation failed"}), 500

    post = Post(
        business_id  = biz_id,
        post_type    = "festival_offer",
        platform     = "instagram",
        caption      = data.get("caption", ""),
        hashtags     = data.get("hashtags", ""),
        image_prompt = data.get("image_prompt", ""),
        best_time    = data.get("best_time", "9:00 AM"),
        day_number   = Post.query.filter_by(business_id=biz_id).count() + 1,
    )
    db.session.add(post)
    db.session.commit()

    return jsonify({
        "id": post.id, "caption": post.caption,
        "hashtags": post.hashtags, "image_prompt": post.image_prompt,
    })


# ─── Strategy ─────────────────────────────────────────────────────────────────

@bp.route("/business/<int:biz_id>/strategy")
def strategy(biz_id):
    biz = Business.query.get_or_404(biz_id)
    biz_dict = {
        "name": biz.name, "category": biz.category,
        "location": biz.location, "description": biz.description,
        "tone": biz.tone, "language": biz.language,
        "usp": biz.usp, "target_audience": biz.target_audience,
    }
    data = suggest_content_strategy(biz_dict)
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
    biz_id = post.business_id
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
    return Response(
        data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={biz.name}_content.csv"},
    )


@bp.route("/business/<int:biz_id>/export/txt")
def export_txt(biz_id):
    biz   = Business.query.get_or_404(biz_id)
    posts = Post.query.filter_by(business_id=biz_id).order_by(Post.day_number).all()
    data  = export_to_txt(posts, biz.name)
    return Response(
        data,
        mimetype="text/plain",
        headers={"Content-Disposition": f"attachment; filename={biz.name}_captions.txt"},
    )


# ─── Health ───────────────────────────────────────────────────────────────────

@bp.route("/health")
def health():
    return jsonify({"status": "ok"})