from flask import Blueprint, request, jsonify, current_app as app
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import requests
import jwt
from datetime import datetime, timedelta
from app.models import db, User
from app.routes.config import JWT_SECRET_KEY  
from utils.logger import log_action

auth_bp = Blueprint("auth", __name__)

# -------------------------------
# REGISTER USER
# -------------------------------
@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    required_fields = ["mobile", "email", "company", "password"]
    if not all(field in data for field in required_fields):
        return jsonify({"msg": "Missing fields"}), 400

    if User.query.filter_by(email=data["email"]).first():
        return jsonify({"msg": "User already registered"}), 409

    # Create user (inactive until admin approval)
    user = User(
        mobile=data["mobile"],
        email=data["email"],
        company=data["company"],
        password=generate_password_hash(data["password"]),
        is_active=False
    )
    db.session.add(user)
    db.session.commit()

    # Send study SMS
    try:
        sms_api_url = "https://sms.jormall.com/api/send"
        payload = {
            "username": "YOUR_JORMALL_USERNAME",
            "password": "YOUR_JORMALL_PASSWORD",
            "sender": "JorMall",
            "to": data["mobile"],
            "message": f"Welcome {data['company']}! Your JorMall SMS app account is now under study. You’ll be notified once approved."
        }
        response = requests.post(sms_api_url, data=payload, timeout=10)
        if response.status_code == 200:
            print(f"✅ Study SMS sent to {data['mobile']}")
        else:
            print(f"❌ Failed to send SMS: {response.text}")
    except Exception as e:
        print("⚠️ SMS sending error:", e)
    log_action("register", f"New user registered: {data['email']} from {data['company']}")
    return jsonify({"msg": "Registration submitted. Await admin approval."}), 201


# -------------------------------
# LOGIN USER
# -------------------------------
@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({"msg": "Email and password required"}), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"msg": "Account not found"}), 404

    if not user.is_active:
        return jsonify({"msg": "Your account is not yet activated"}), 403

    if not check_password_hash(user.password, password):
        return jsonify({"msg": "Invalid password"}), 401

    token = jwt.encode(
        {"sub": str(user.id), "exp": datetime.utcnow() + timedelta(days=1)},
        JWT_SECRET_KEY,
        algorithm="HS256",
    )
    log_action("login", f"User {user.id} logged in")
    return jsonify({
        "access_token": token,
        "is_admin": bool(user.is_admin),
        "msg": "Login successful"
    }), 200

# -------------------------------
# JWT DECORATOR
# -------------------------------
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if "Authorization" in request.headers:
            token = request.headers["Authorization"].split(" ")[1]
        if not token:
            return jsonify({"msg": "Token missing"}), 401

        try:
            decoded = jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"])
            current_user = User.query.get(decoded["sub"])
        except jwt.ExpiredSignatureError:
            return jsonify({"msg": "Token expired"}), 401
        except jwt.InvalidTokenError as e:
            return jsonify({"msg": str(e)}), 401

        return f(current_user, *args, **kwargs)
    return decorated


# -------------------------------
# GET CURRENT USER
# -------------------------------
@auth_bp.route("/me", methods=["GET"])
@token_required
def me(current_user):
    if not current_user:
        return jsonify({"msg": "User not found"}), 404

    return jsonify({
        "id": current_user.id,
        "mobile": current_user.mobile,
        "email": current_user.email,
        "company": current_user.company,
        "is_active": current_user.is_active,
    }), 200

# -------------------------------
# ACTIVATE USER (for admin use)
# -------------------------------
@auth_bp.route("/activate", methods=["POST"])
def activate_user():
    data = request.get_json()
    email = data.get("email")

    if not email:
        return jsonify({"msg": "Email is required"}), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"msg": "User not found"}), 404

    user.is_active = True
    db.session.commit()
    log_action("activate user", f"user {user.id} activated")
    return jsonify({"msg": f"User {email} activated successfully."}), 200

# -------------------------------
# Admin REQUIRED DECORATOR
# -------------------------------

def admin_required(f):
    @wraps(f)
    def decorated(current_user, *args, **kwargs):
        if not current_user.is_admin:
            return jsonify({"msg": "Admin access required"}), 403
        return f(current_user, *args, **kwargs)
    return decorated

# -------------------------------
# GET ALL USERS (admin only)
# -------------------------------
@auth_bp.route("/admin/users", methods=["GET"])
@token_required
@admin_required
def get_all_users(current_user):
    users = User.query.all()
    output = [
        {
            "id": u.id,
            "email": u.email,
            "mobile": u.mobile,
            "company": u.company,
            "is_active": u.is_active,
            "is_admin": u.is_admin
        } for u in users
    ]
    return jsonify(output), 200

# -------------------------------
# ACTIVATE/DEACTIVATE USER (admin only)
# -------------------------------
@auth_bp.route("/admin/activate/<int:user_id>", methods=["POST"])
@token_required
@admin_required
def admin_activate_user(current_user, user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"msg": "User not found"}), 404

    user.is_active = True
    db.session.commit()
    log_action("activate user", f"user {user_id} activated by admin {current_user.id}")
    return jsonify({"msg": "User activated"}), 200


@auth_bp.route("/admin/deactivate/<int:user_id>", methods=["POST"])
@token_required
@admin_required
def admin_deactivate_user(current_user, user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"msg": "User not found"}), 404

    user.is_active = False
    db.session.commit()
    log_action("deactivate user", f"user {user_id} deactivated by admin {current_user.id}")
    return jsonify({"msg": "User deactivated"}), 200


# ------------------------------
# SAVE FCM TOKEN
# ------------------------------

@auth_bp.route("/save-token", methods=["POST"])
@token_required
def save_token(current_user):
    data = request.get_json()
    token = data.get("fcm_token")

    if not token:
        return {"msg": "Missing token"}, 400

    current_user.fcm_token = token
    db.session.commit()
    log_action("save fcm token", f"user {current_user.id} saved FCM token")
    return {"msg": "Token saved"}, 200

