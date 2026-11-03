# app/routes/admin/admin_routes.py
import os
from flask import Blueprint, request, jsonify
from app.models import db, User
from flask_jwt_extended import jwt_required
from app.routes.auth import token_required  # uses token_required that returns current_user
from sqlalchemy.exc import SQLAlchemyError
from utils.logger import log_action

# from fcm_django.models import FCMDevice

admin_bp = Blueprint("admin", __name__)

# helper to verify admin_secret
def _check_admin_secret(payload):
    admin_secret = os.getenv("ADMIN_SECRET")
    if not admin_secret:
        return False, "ADMIN_SECRET not configured on server"
    provided = payload.get("admin_secret")
    if not provided:
        return False, "Missing admin_secret"
    if provided != admin_secret:
        return False, "Invalid admin_secret"
    return True, None

# List all users (admin only)
@admin_bp.route("/users", methods=["GET"])
@token_required
def list_users(current_user):
    if not current_user.is_admin:
        return jsonify({"msg": "Forbidden"}), 403
    users = User.query.order_by(User.id.desc()).all()
    out = []
    for u in users:
        out.append({
            "id": u.id,
            "email": u.email,
            "mobile": u.mobile,
            "company": u.company,
            "is_active": bool(u.is_active),
            "is_admin": bool(u.is_admin),
            "created_at": getattr(u, "created_at", None)
        })
    return jsonify(out), 200

# Make admin (requires admin_secret)
@admin_bp.route("/users/<int:user_id>/make-admin", methods=["POST"])
@token_required
def make_admin(current_user, user_id):
    if not current_user.is_admin:
        return jsonify({"msg": "Forbidden"}), 403

    payload = request.get_json() or {}
    ok, err = _check_admin_secret(payload)
    if not ok:
        return jsonify({"msg": err}), 403

    u = User.query.get(user_id)
    if not u:
        return jsonify({"msg": "User not found"}), 404
    u.is_admin = True
    db.session.commit()
    log_action("make admin", f"user {user_id} made admin by admin {current_user.id}")
    return jsonify({"msg": f"{u.email} is now admin"}), 200

# Remove admin (requires admin_secret)
@admin_bp.route("/users/<int:user_id>/remove-admin", methods=["POST"])
@token_required
def remove_admin(current_user, user_id):
    if not current_user.is_admin:
        return jsonify({"msg": "Forbidden"}), 403

    payload = request.get_json() or {}
    ok, err = _check_admin_secret(payload)
    if not ok:
        return jsonify({"msg": err}), 403

    u = User.query.get(user_id)
    if not u:
        return jsonify({"msg": "User not found"}), 404
    u.is_admin = False
    db.session.commit()
    log_action("remove admin", f"user {user_id} removed admin by admin {current_user.id}")
    return jsonify({"msg": f"{u.email} admin removed"}), 200

# Activate / Deactivate user (admin only)
@admin_bp.route("/users/<int:user_id>/activate", methods=["POST"])
@token_required
def activate_user(current_user, user_id):
    if not current_user.is_admin:
        return jsonify({"msg": "Forbidden"}), 403
    u = User.query.get(user_id)
    if not u:
        return jsonify({"msg": "User not found"}), 404
    u.is_active = True
    db.session.commit()
    log_action("activate user", f"user {user_id} activated by admin {current_user.id}")
    return jsonify({"msg": f"{u.email} activated"}), 200

@admin_bp.route("/users/<int:user_id>/deactivate", methods=["POST"])
@token_required
def deactivate_user(current_user, user_id):
    if not current_user.is_admin:
        return jsonify({"msg": "Forbidden"}), 403
    u = User.query.get(user_id)
    if not u:
        return jsonify({"msg": "User not found"}), 404
    u.is_active = False
    db.session.commit()
    log_action("deactivate user", f"user {user_id} deactivated by admin {current_user.id}")
    return jsonify({"msg": f"{u.email} deactivated"}), 200

# Delete user
@admin_bp.route("/users/<int:user_id>", methods=["DELETE"])
@token_required
def delete_user(current_user, user_id):
    if not current_user.is_admin:
        return jsonify({"msg": "Forbidden"}), 403
    u = User.query.get(user_id)
    if not u:
        return jsonify({"msg": "User not found"}), 404
    db.session.delete(u)
    db.session.commit()
    log_action("delete user", f"user {user_id} deleted by admin {current_user.id}")
    return jsonify({"msg": f"{u.email} deleted"}), 200

# Reset DB (dangerous) — require admin_secret as body parameter
@admin_bp.route("/reset", methods=["POST"])
@token_required
def reset_db(current_user):
    if not current_user.is_admin:
        return jsonify({"msg": "Forbidden"}), 403
    payload = request.get_json() or {}
    ok, err = _check_admin_secret(payload)
    if not ok:
        return jsonify({"msg": err}), 403
    try:
        # drop all and create
        db.drop_all()
        db.create_all()
        log_action("reset db", f"Database reset by admin {current_user.id}")
        return jsonify({"msg": "Database reset successfully"}), 200
    except SQLAlchemyError as e:
        log_action("reset db failed", f"Database reset failed by admin {current_user.id}: {str(e)}")
        return jsonify({"msg": f"Error resetting DB: {str(e)}"}), 500
# -------------------------
# Admin: Update Offer Text
# -------------------------

@admin_bp.route('/offers/update', methods=['POST'])
@jwt_required()
def update_offers(current_user):
    if not current_user.is_admin:
        log_action("unauthorized offer update attempt", f"by user {current_user.id}")
        return jsonify({"error": "Not authorized"}), 403
