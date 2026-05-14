"""app/models.py — Database models"""

from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def utcnow():
    return datetime.now(timezone.utc)


class Business(db.Model):
    __tablename__ = "businesses"
    id              = db.Column(db.Integer, primary_key=True)
    name            = db.Column(db.String(120), nullable=False)
    category        = db.Column(db.String(80),  nullable=False)
    location        = db.Column(db.String(120), nullable=False)
    description     = db.Column(db.Text, nullable=False)
    tone            = db.Column(db.String(30),  default="friendly")
    language        = db.Column(db.String(20),  default="hinglish")
    usp             = db.Column(db.Text, nullable=True)
    target_audience = db.Column(db.String(200), nullable=True)
    created_at      = db.Column(db.DateTime(timezone=True), default=utcnow)
    posts           = db.relationship("Post", back_populates="business",
                                      cascade="all, delete-orphan", lazy="dynamic")


class Post(db.Model):
    __tablename__ = "posts"
    id              = db.Column(db.Integer, primary_key=True)
    business_id     = db.Column(db.Integer, db.ForeignKey("businesses.id"), nullable=False)
    post_type       = db.Column(db.String(40), nullable=False)
    platform        = db.Column(db.String(20), default="instagram")
    caption         = db.Column(db.Text, nullable=False)
    hashtags        = db.Column(db.Text, nullable=False, default="")
    image_prompt    = db.Column(db.Text, nullable=True)
    # image fields
    image_local     = db.Column(db.String(300), nullable=True)   # filename in static/generated/
    image_public_url= db.Column(db.String(500), nullable=True)   # Cloudinary URL
    image_status    = db.Column(db.String(20),  default="none")  # none|generating|ready|failed
    # scheduling / publishing
    best_time       = db.Column(db.String(50),  nullable=True)
    scheduled_at    = db.Column(db.DateTime(timezone=True), nullable=True)
    published_at    = db.Column(db.DateTime(timezone=True), nullable=True)
    ig_media_id     = db.Column(db.String(100), nullable=True)
    publish_status  = db.Column(db.String(20),  default="draft")  # draft|scheduled|published|failed
    publish_error   = db.Column(db.Text, nullable=True)
    day_number      = db.Column(db.Integer, default=1)
    is_used         = db.Column(db.Boolean, default=False)
    created_at      = db.Column(db.DateTime(timezone=True), default=utcnow)
    business        = db.relationship("Business", back_populates="posts")

    def full_caption(self):
        """Caption + hashtags combined for posting."""
        parts = [self.caption]
        if self.hashtags:
            parts.append(self.hashtags)
        return "\n\n".join(parts)