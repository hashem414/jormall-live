# app/routes/push.py
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import db, User
from firebase_admin import messaging, credentials, initialize_app, get_app, _apps
import requests, os
from utils.logger import log_action
# --- Firebase initialization (safe singleton) ---
cred_path = os.path.join(os.path.dirname(__file__), "..", "..", "firebase-service-account.json")

if not _apps:
    cred = credentials.Certificate(cred_path)
    firebase_app = initialize_app(cred)
else:
    firebase_app = get_app()

# --- Flask Blueprint ---
push_bp = Blueprint('push', __name__)

# --- Model ---
class PushToken(db.Model):
    __tablename__ = 'push_token'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    fcm_token = db.Column(db.String(255), unique=True, nullable=False)


# --- Routes ---
@push_bp.route('/token', methods=['POST'])
@jwt_required()
def save_token():
    uid = get_jwt_identity()
    data = request.get_json()
    token_value = data.get('fcm_token')

    if not token_value:
        return jsonify({'msg': 'Missing fcm_token'}), 400

    token = PushToken.query.filter_by(fcm_token=token_value).first()
    if not token:
        token = PushToken(user_id=uid, fcm_token=token_value)
        db.session.add(token)
        db.session.commit()
    log_action("save fcm token", f"user {uid} saved FCM token")
    return jsonify({'msg': 'Token saved'}), 200


@push_bp.route('/send', methods=['POST'])
@jwt_required()
def send_push():
    data = request.get_json()
    title = data.get('title')
    body = data.get('body')
    token = data.get('token')

    if not all([title, body, token]):
        return jsonify({'msg': 'Missing title/body/token'}), 400

    message = messaging.Message(
        notification=messaging.Notification(title=title, body=body),
        token=token,
    )

    response = messaging.send(message)
    log_action("send push", f"Push sent to token {token} with title: {title}")
    return jsonify({'msg': 'Push sent', 'response': response}), 200

notifications_bp = Blueprint("notifications", __name__)

FCM_SERVER_KEY = os.getenv("FCM_SERVER_KEY")  # from Firebase console

@notifications_bp.route("/test", methods=["POST"])
def send_test_push():
    data = request.get_json()
    fcm_token = data.get("fcm_token")
    if not fcm_token:
        return jsonify({"msg": "Missing fcm_token"}), 400

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"key={FCM_SERVER_KEY}"
    }
    payload = {
        "to": fcm_token,
        "notification": {
            "title": "JorMall SMS",
            "body": "🔥 Test push notification works!",
        }
    }

    response = requests.post("https://fcm.googleapis.com/fcm/send", json=payload, headers=headers)
    return jsonify(response.json()), response.status_code
