from app.database import db
from datetime import datetime, timedelta

class SpinResult(db.Model):
    """
    Represents the result of a spin: phone number, assigned prize, coupon, and status.
    Status: 'reserved', 'claimed', 'cancelled'
    """
    __tablename__ = 'spin_results'

    id = db.Column(db.Integer, primary_key=True)
    phone_number = db.Column(db.String(20), nullable=False, index=True)
    prize_inventory_id = db.Column(db.Integer, db.ForeignKey('prize_inventory.id'), nullable=True)
    coupon_id = db.Column(db.Integer, db.ForeignKey('coupons.id'), nullable=True)
    sms_amount = db.Column(db.Integer, nullable=False)
    spin_time = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    otp_verified = db.Column(db.Boolean, default=False, nullable=False)
    otp_code = db.Column(db.String(6), nullable=True)
    otp_expires_at = db.Column(db.DateTime, nullable=True)
    otp_attempts = db.Column(db.Integer, default=0)
    campaign_id = db.Column(db.Integer, db.ForeignKey("campaigns.id"), nullable=False, index=True)
    sender_id = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(50), default='reserved', nullable=False)  # reserved, claimed, cancelled
    spin_token = db.Column(db.String(255), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    coupon = db.relationship('Coupon', backref='spin_results')

    def __repr__(self):
        return f'<SpinResult {self.phone_number} - {self.sms_amount}SMS - {self.status}>'

    def to_dict(self):
        return {
            'id': self.id,
            'phone_number': self.phone_number,
            'prize_inventory_id': self.prize_inventory_id,
            'coupon_id': self.coupon_id,
            'sms_amount': self.sms_amount,
            'spin_time': self.spin_time.isoformat(),
            'otp_verified': self.otp_verified,
            'otp_code': self.otp_code,
            'otp_expires_at': self.otp_expires_at.isoformat() if self.otp_expires_at else None,
            'otp_attempts': self.otp_attempts,
            'campaign_id': self.campaign_id,
            'sender_id': self.sender_id,
            'status': self.status,
            'spin_token': self.spin_token,
            'created_at': self.created_at.isoformat(),
        }
