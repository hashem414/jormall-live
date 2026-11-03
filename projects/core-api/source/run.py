from flask import Flask
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from app.models import db
from app.routes.push import push_bp
from app.routes.auth import auth_bp
from app.routes.admin.admin_routes import admin_bp
from flask_cors import CORS
from app.routes.admin.admin_push_routes import admin_push_bp
from app.routes.admin.admin_stats import admin_stats_bp
from app.routes.logs import logs_bp
from app.routes.email import email_bp
from app.routes.campaign_generation import campaign_bp

import os

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///data.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY")

db.init_app(app)
jwt = JWTManager(app)

# register blueprints
app.register_blueprint(push_bp, url_prefix="/api/push")
app.register_blueprint(auth_bp, url_prefix="/api/auth")
app.register_blueprint(admin_bp, url_prefix="/api/admin")
app.register_blueprint(admin_push_bp, url_prefix="/api/admin")
app.register_blueprint(admin_stats_bp, url_prefix="/api/admin")
app.register_blueprint(logs_bp, url_prefix="/api")
app.register_blueprint(email_bp, url_prefix="/api")
app.register_blueprint(campaign_bp, url_prefix="/api")

@app.route("/api/health")
def health():
    return {"status": "ok"}, 200

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    
    app.run(debug=True)
