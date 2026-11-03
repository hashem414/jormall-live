import os
from flask import Blueprint, request, jsonify
from app.models import db, User, PushToken
from app.routes.auth import token_required
from firebase_admin import messaging
from utils.logger import log_action

admin_push_bp = Blueprint("admin_push", __name__)

# -------------------------------------------
# ✅ Send push notification to a single user
# -------------------------------------------
@admin_push_bp.route("/notify/<int:user_id>", methods=["POST"])
@token_required
def notify_user(current_user, user_id):
    if not current_user.is_admin:
        return jsonify({"msg": "Forbidden"}), 403

    body = request.get_json() or {}
    title = body.get("title")
    message_body = body.get("body")

    if not title or not message_body:
        return jsonify({"msg": "Missing title/body"}), 400

    # Fetch FCM token(s)
    tokens = PushToken.query.filter_by(user_id=user_id).all()
    if not tokens:
        return jsonify({"msg": "User does not have FCM tokens"}), 404

    responses = []
    for token in tokens:
        try:
            message = messaging.Message(
                notification=messaging.Notification(title=title, body=message_body),
                token=token.fcm_token,
            )
            response = messaging.send(message)
            responses.append(response)
        except Exception as e:
            responses.append(str(e))
    log_action("send push", f"to user {user_id} title: {title}, body: {message_body} from admin {current_user.id}")
    return jsonify({"msg": "Notification sent", "responses": responses}), 200


# -------------------------------------------
# ✅ Send push notification to ALL users
# -------------------------------------------
@admin_push_bp.route("/notify-all", methods=["POST"])
@token_required
def notify_all(current_user):
    if not current_user.is_admin:
        return jsonify({"msg": "Forbidden"}), 403

    body = request.get_json() or {}
    title = body.get("title")
    message_body = body.get("body")

    if not title or not message_body:
        return jsonify({"msg": "Missing title/body"}), 400

    tokens = PushToken.query.all()

    if not tokens:
        return jsonify({"msg": "No users have registered tokens"}), 404

    responses = []
    errors = []

    for token in tokens:
        print("📡 Sending to:", token.fcm_token)

        if not token.fcm_token:
            errors.append("❌ Empty token entry")
            continue

        try:
            message = messaging.Message(
                notification=messaging.Notification(title=title, body=message_body),
                token=token.fcm_token,
            )

            response = messaging.send(message)
            responses.append({"token": token.fcm_token, "response": response})

        except Exception as e:
            errors.append({"token": token.fcm_token, "error": str(e)})
            # Optional: delete invalid tokens from DB
            if "not registered" in str(e).lower():
                db.session.delete(token)
                db.session.commit()
    log_action("broadcast push", f"title: {title}, body: {message_body} from admin {current_user.id}")
    return jsonify({
        "msg": "Broadcast complete",
        "sent": responses,
        "failed": errors
    }), 200


# -------------------------------------------
# ✅ List all FCM tokens (admin only)
# -------------------------------------------
@admin_push_bp.route("/tokens", methods=["GET"])
@token_required
def list_tokens(current_user):
    if not current_user.is_admin:
        return jsonify({"msg": "Forbidden"}), 403
    data = [
        {"user_id": t.user_id, "token": t.fcm_token[:20] + "..."}
        for t in PushToken.query.all()
    ]
    return jsonify({"count": len(data), "tokens": data}), 200
