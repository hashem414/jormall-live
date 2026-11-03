# app/routes/admin_stats.py
from flask import Blueprint, jsonify
from app.models import User, PushToken
from flask_jwt_extended import jwt_required

admin_stats_bp = Blueprint("admin_stats", __name__)

@admin_stats_bp.route("/stats", methods=["GET"])
@jwt_required()
def get_stats():
    total_users = User.query.count()
    total_admins = User.query.filter_by(is_admin=True).count()
    total_tokens = PushToken.query.count()  # number of registered devices for push

    return jsonify({
        "total_users": total_users,
        "admins": total_admins,
        "push_tokens": total_tokens
    }), 200


