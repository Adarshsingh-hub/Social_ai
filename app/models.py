"""app/models.py — Database models"""

from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def utcnow():
    return datetime.now(timezone.utc)


class Business(db.Model):
    __tablename__ = "businesses"
    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(120), nullable=False)
    category      = db.Column(db.String(80), nullable=False)
    location      = db.Column(db.String(120), nullable=False)
    description   = db.Column(db.Text, nullable=False)
    tone          = db.Column(db.String(30), default="friendly")
    language      = db.Column(db.String(20), default="hinglish")
    usp           = db.Column(db.Text, nullable=True)
    target_audience = db.Column(db.String(200), nullable=True)
    created_at    = db.Column(db.DateTime(timezone=True), default=utcnow)
    posts         = db.relationship("Post", back_populates="business",
                                    cascade="all, delete-orphan", lazy="dynamic")


class Post(db.Model):
    __tablename__ = "posts"
    id            = db.Column(db.Integer, primary_key=True)
    business_id   = db.Column(db.Integer, db.ForeignKey("businesses.id"), nullable=False)
    post_type     = db.Column(db.String(40), nullable=False)   # promo|tip|testimonial|festival|reel_idea|story
    platform      = db.Column(db.String(20), default="instagram")
    caption       = db.Column(db.Text, nullable=False)
    hashtags      = db.Column(db.Text, nullable=False)
    image_prompt  = db.Column(db.Text, nullable=True)
    best_time     = db.Column(db.String(50), nullable=True)
    day_number    = db.Column(db.Integer, default=1)
    is_used       = db.Column(db.Boolean, default=False)
    created_at    = db.Column(db.DateTime(timezone=True), default=utcnow)
    business      = db.relationship("Business", back_populates="posts")