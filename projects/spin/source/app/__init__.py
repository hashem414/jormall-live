from flask import Flask
from flask_cors import CORS
import os

from app.database import db


def create_app():
    app = Flask(__name__)

    env = os.getenv("FLASK_ENV", "development")

    if env == "production":
        app.config.from_object("config.ProductionConfig")
    elif env == "testing":
        app.config.from_object("config.TestingConfig")
    else:
        app.config.from_object("config.DevelopmentConfig")

    db.init_app(app)

    # CORS(
    #     app,
    #     resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}},
    #     supports_credentials=False,
    #     allow_headers=["Content-Type", "Authorization", "Accept", "Origin", "X-Requested-With"],
    #     methods=["GET", "POST", "OPTIONS"],
    # )
    CORS(
        app,
        resources={
            r"/api/*": {"origins": app.config["CORS_ORIGINS"]},
            r"/spin/*": {"origins": app.config["CORS_ORIGINS"]},
        },
        supports_credentials=False,
        allow_headers=[
            "Content-Type",
            "Authorization",
            "Accept",
            "Origin",
            "X-Requested-With",
        ],
        methods=["GET", "POST", "OPTIONS"],
    )
    from app.models import campaign, prize_inventory, coupon, spin_result
    from app.routes.spin_routes import spin_bp
    app.register_blueprint(spin_bp)

    return app