from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import ActivityLog, db

logs_bp = Blueprint("logs", __name__)

@logs_bp.route("/logs", methods=["GET"])
@jwt_required()
def get_logs():
    user_id = get_jwt_identity()

    # Only admins can see logs
    from app.models import User
    user = User.query.get(user_id)
    if not user or not user.is_admin:
        return jsonify({"msg": "Forbidden"}), 403

    logs = ActivityLog.query.order_by(ActivityLog.timestamp.desc()).limit(300).all()

    return jsonify([
        {
            "id": log.id,
            "user_id": log.user_id,
            "action": log.action,
            "endpoint": log.endpoint,
            "method": log.method,
            "details": log.details,
            "ip": log.ip,
            "timestamp": log.timestamp.isoformat()
        }
        for log in logs
    ]), 200
