"""
Seed gifts for spin-win-test2-2026 campaign.
Run:
    python3 seed_test2_campaign.py
"""

from dotenv import load_dotenv
from app import create_app, db
from app.models import Campaign, PrizeInventory, Coupon
from app.utils import generate_coupon_code

load_dotenv()

app = create_app()

CAMPAIGN = {
    "campaign_slug": "spin-win-test2-2026",
    "campaign_name": "Spin Win Test 2 2026",
    "is_active": True,
}

PRIZES_DATA = [
    {"prize_name": "25K SMS Bundle", "sms_amount": 25000, "total_coupons": 100, "weight": 40},
    {"prize_name": "50K SMS Bundle", "sms_amount": 50000, "total_coupons": 80, "weight": 25},
    {"prize_name": "100K SMS Bundle", "sms_amount": 100000, "total_coupons": 60, "weight": 18},
    {"prize_name": "250K SMS Bundle", "sms_amount": 250000, "total_coupons": 40, "weight": 10},
    {"prize_name": "500K SMS Bundle", "sms_amount": 500000, "total_coupons": 20, "weight": 5},
    {"prize_name": "1M SMS Bundle (Grand Prize)", "sms_amount": 1000000, "total_coupons": 10, "weight": 2},
]


def get_or_create_campaign():
    campaign = Campaign.query.filter_by(
        campaign_slug=CAMPAIGN["campaign_slug"]
    ).first()

    if campaign:
        campaign.campaign_name = CAMPAIGN["campaign_name"]
        campaign.is_active = True
        print(f"✓ Campaign exists: {campaign.campaign_slug}")
        return campaign

    campaign = Campaign(**CAMPAIGN)
    db.session.add(campaign)
    db.session.flush()

    print(f"✓ Created campaign: {campaign.campaign_slug}")
    return campaign


def unique_coupon_code(campaign_id, prefix):
    code = generate_coupon_code(prefix=prefix, length=16)

    while Coupon.query.filter_by(
        campaign_id=campaign_id,
        coupon_code=code
    ).first():
        code = generate_coupon_code(prefix=prefix, length=16)

    return code


def seed():
    with app.app_context():
        campaign = get_or_create_campaign()

        for prize_data in PRIZES_DATA:
            prize = PrizeInventory.query.filter_by(
                campaign_id=campaign.id,
                sms_amount=prize_data["sms_amount"]
            ).first()

            if not prize:
                prize = PrizeInventory(
                    campaign_id=campaign.id,
                    prize_name=prize_data["prize_name"],
                    sms_amount=prize_data["sms_amount"],
                    total_coupons=prize_data["total_coupons"],
                    remaining_coupons=prize_data["total_coupons"],
                    is_active=True,
                    weight=prize_data["weight"],
                )
                db.session.add(prize)
                db.session.flush()
                print(f"✓ Created prize: {prize.prize_name}")
            else:
                prize.prize_name = prize_data["prize_name"]
                prize.total_coupons = prize_data["total_coupons"]
                prize.weight = prize_data["weight"]
                prize.is_active = True
                print(f"✓ Updated prize: {prize.prize_name}")

            existing = Coupon.query.filter_by(
                campaign_id=campaign.id,
                prize_inventory_id=prize.id
            ).count()

            missing = prize_data["total_coupons"] - existing

            prefix = f"JM{prize_data['sms_amount'] // 1000}K"

            for _ in range(max(missing, 0)):
                coupon = Coupon(
                    campaign_id=campaign.id,
                    prize_inventory_id=prize.id,
                    coupon_code=unique_coupon_code(campaign.id, prefix),
                    status="available",
                )
                db.session.add(coupon)

            available = Coupon.query.filter_by(
                campaign_id=campaign.id,
                prize_inventory_id=prize.id,
                status="available"
            ).count()

            prize.remaining_coupons = available
            print(f"  Coupons: {available}/{prize_data['total_coupons']} available")

        db.session.commit()
        print("✅ Test2 campaign seeded successfully.")


if __name__ == "__main__":
    seed()
