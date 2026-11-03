from flask import request
from flask_jwt_extended import get_jwt_identity
from app.models import db, ActivityLog

def log_action(action, details=None):
    """Save backend activity to DB."""
    try:
        try:
            user_id = get_jwt_identity()  # May fail if anonymous
        except:
            user_id = None

        entry = ActivityLog(
            user_id=user_id,
            action=action,
            endpoint=request.path,
            method=request.method,
            ip=request.remote_addr,
            details=str(details) if details else None
        )

        db.session.add(entry)
        db.session.commit()

    except Exception as e:
        print("⚠️ Logging failed:", e)
        db.session.rollback()
