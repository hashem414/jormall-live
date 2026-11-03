# app/models.py
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
db = SQLAlchemy()
class PushToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    fcm_token = db.Column(db.String(255), unique=True, nullable=False)

class User(db.Model):
    __tablename__ = "users"
    id         = db.Column(db.Integer, primary_key=True)
    mobile     = db.Column(db.String(32), nullable=False)
    email      = db.Column(db.String(255), unique=True, nullable=False)
    company    = db.Column(db.String(255), nullable=False)
    password   = db.Column(db.String(255), nullable=False)
    is_active  = db.Column(db.Boolean, default=False, nullable=False)
    is_admin   = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

class Offers(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    monthly_offer_header = db.Column(db.String(255), default="Exclusive Monthly Offers")


class ActivityLog(db.Model):
    __tablename__ = "activity_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=True)  # null if system event
    action = db.Column(db.String(255), nullable=False)
    endpoint = db.Column(db.String(255), nullable=True)
    method = db.Column(db.String(10), nullable=True)
    details = db.Column(db.Text, nullable=True)
    ip = db.Column(db.String(64), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
