from datetime import datetime
from app import db


class PrizeInventory(db.Model):
    """
    Represents a prize tier with SMS amount and coupon inventory.
    """
    __tablename__ = 'prize_inventory'

    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey("campaigns.id"), nullable=False, index=True)
    prize_name = db.Column(db.String(255), nullable=False)
    sms_amount = db.Column(db.Integer, nullable=False)
    total_coupons = db.Column(db.Integer, nullable=False)
    remaining_coupons = db.Column(db.Integer, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    weight = db.Column(db.Integer, default=1, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    coupons = db.relationship('Coupon', backref='prize_tier', lazy=True, cascade='all, delete-orphan')
    spin_results = db.relationship('SpinResult', backref='prize_tier', lazy=True)
    __table_args__ = (
    db.UniqueConstraint("campaign_id", "sms_amount", name="uq_campaign_sms_amount"),
)   
    def __repr__(self):
        return f'<PrizeInventory {self.sms_amount}SMS - {self.remaining_coupons}/{self.total_coupons}>'

    def to_dict(self):
        return {
            'id': self.id,
            'prize_name': self.prize_name,
            'sms_amount': self.sms_amount,
            'total_coupons': self.total_coupons,
            'remaining_coupons': self.remaining_coupons,
            'is_active': self.is_active,
            'weight': self.weight,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }
