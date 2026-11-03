import os
from datetime import timedelta

# --------------------------------
# CORE APP CONFIGURATION
# --------------------------------

# Base directory
basedir = os.path.abspath(os.path.dirname(__file__))

# Secret key for JWT signing & Flask sessions
# SQLAlchemy configuration
SQLALCHEMY_DATABASE_URI = os.environ.get(
    "DATABASE_URL", f"sqlite:///{os.path.join(basedir, 'app.db')}"
)
SQLALCHEMY_TRACK_MODIFICATIONS = False

# JWT configuration (if you use flask_jwt_extended)
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
JWT_ACCESS_TOKEN_EXPIRES = timedelta(days=1)

# Optional: CORS and debugging
DEBUG = True
CORS_ALLOWED_ORIGINS = "*"

# Optional: Email or SMS API credentials
JORMALL_SMS_USERNAME = os.environ.get("JORMALL_SMS_USERNAME")
JORMALL_SMS_PASSWORD = os.environ.get("JORMALL_SMS_PASSWORD")

# Example: Server URL for your API
SERVER_URL = os.environ.get("SERVER_URL")
