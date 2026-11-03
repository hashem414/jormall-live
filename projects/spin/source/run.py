"""
JorMall Spin & Win Backend - Entry Point
"""
import os
from dotenv import load_dotenv

from app import create_app
from app.database import db

# Load environment variables from .env file
load_dotenv()

# Create Flask app
app = create_app()


@app.shell_context_processor
def make_shell_context():
    """Make database and models available in Flask shell."""
    from app.models import PrizeInventory, Coupon, SpinResult, Campaign
    return {
        'db': db,
        'PrizeInventory': PrizeInventory,
        'Coupon': Coupon,
        'SpinResult': SpinResult,
    }


if __name__ == '__main__':
    app.run(
        host=os.getenv('FLASK_HOST', '127.0.0.1'),
        port=int(os.getenv('FLASK_PORT', 5000)),
        debug=os.getenv('FLASK_DEBUG', 'true').lower() == 'true'
    )