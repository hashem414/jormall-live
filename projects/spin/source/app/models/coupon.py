from datetime import datetime
from app.database import db


class Coupon(db.Model):
    """
    Represents a coupon code tied to a prize tier.
    Status: 'available', 'reserved', 'claimed', 'expired'
    """
    __tablename__ = 'coupons'

    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey("campaigns.id"), nullable=False, index=True)
    prize_inventory_id = db.Column(db.Integer, db.ForeignKey('prize_inventory.id'), nullable=False)
    coupon_code = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(50), default='available', nullable=False)  # available, reserved, claimed, expired
    reserved_by_phone = db.Column(db.String(20), nullable=True)
    reserved_at = db.Column(db.DateTime, nullable=True)
    claimed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    __table_args__ = (db.UniqueConstraint("campaign_id", "coupon_code", name="uq_campaign_coupon_code"),)
    def __repr__(self):
        return f'<Coupon {self.coupon_code} - {self.status}>'

    def to_dict(self):
        return {
            'id': self.id,
            'prize_inventory_id': self.prize_inventory_id,
            'coupon_code': self.coupon_code,
            'status': self.status,
            'reserved_by_phone': self.reserved_by_phone,
            'reserved_at': self.reserved_at.isoformat() if self.reserved_at else None,
            'claimed_at': self.claimed_at.isoformat() if self.claimed_at else None,
            'created_at': self.created_at.isoformat(),
        }
