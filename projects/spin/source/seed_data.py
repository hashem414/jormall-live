"""
Seed data script for JorMall Spin & Win.
Creates default campaign, prize inventory, and coupon codes.

Usage:
    python seed_data.py
"""

import os
from dotenv import load_dotenv

from app import create_app, db
from app.models import Campaign, PrizeInventory, Coupon
from app.utils import generate_coupon_code


load_dotenv()

app = create_app()


DEFAULT_CAMPAIGN = {
    "campaign_slug": "spin-win-test-2026",
    "campaign_name": "Spin Win Test 2026",
    "is_active": True,
}


PRIZES_DATA = [
    {
        "prize_name": "25K SMS Bundle",
        "sms_amount": 25000,
        "total_coupons": 100,
        "weight": 40,
    },
    {
        "prize_name": "50K SMS Bundle",
        "sms_amount": 50000,
        "total_coupons": 80,
        "weight": 25,
    },
    {
        "prize_name": "100K SMS Bundle",
        "sms_amount": 100000,
        "total_coupons": 60,
        "weight": 18,
    },
    {
        "prize_name": "250K SMS Bundle",
        "sms_amount": 250000,
        "total_coupons": 40,
        "weight": 10,
    },
    {
        "prize_name": "500K SMS Bundle",
        "sms_amount": 500000,
        "total_coupons": 20,
        "weight": 5,
    },
    {
        "prize_name": "1M SMS Bundle (Grand Prize)",
        "sms_amount": 1000000,
        "total_coupons": 10,
        "weight": 2,
    },
]


def get_or_create_default_campaign():
    campaign = Campaign.query.filter_by(
        campaign_slug=DEFAULT_CAMPAIGN["campaign_slug"]
    ).first()

    if campaign:
        campaign.campaign_name = DEFAULT_CAMPAIGN["campaign_name"]
        campaign.is_active = DEFAULT_CAMPAIGN["is_active"]
        print(f"✓ Campaign already exists: {campaign.campaign_slug}")
        return campaign

    campaign = Campaign(
        campaign_slug=DEFAULT_CAMPAIGN["campaign_slug"],
        campaign_name=DEFAULT_CAMPAIGN["campaign_name"],
        is_active=DEFAULT_CAMPAIGN["is_active"],
    )

    db.session.add(campaign)
    db.session.flush()

    print(f"✓ Created campaign: {campaign.campaign_slug}")
    return campaign


def generate_unique_coupon_code_for_campaign(campaign_id, prefix):
    coupon_code = generate_coupon_code(prefix=prefix, length=16)

    while Coupon.query.filter_by(
        campaign_id=campaign_id,
        coupon_code=coupon_code,
    ).first():
        coupon_code = generate_coupon_code(prefix=prefix, length=16)

    return coupon_code


def seed_prizes_and_coupons():
    with app.app_context():
        print("DB URI:", app.config.get("SQLALCHEMY_DATABASE_URI"))

        db.create_all()

        campaign = get_or_create_default_campaign()

        print("\nSeeding prize inventory...")

        for prize_data in PRIZES_DATA:
            prize = PrizeInventory.query.filter_by(
                campaign_id=campaign.id,
                sms_amount=prize_data["sms_amount"],
            ).first()

            if prize:
                print(
                    f"⚠️ Prize already exists for campaign "
                    f"{campaign.campaign_slug}: {prize.prize_name}"
                )

                prize.prize_name = prize_data["prize_name"]
                prize.total_coupons = prize_data["total_coupons"]
                prize.weight = prize_data["weight"]
                prize.is_active = True

            else:
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

                print(
                    f"✓ Created prize: {prize.prize_name} "
                    f"({prize.total_coupons} coupons)"
                )

            existing_coupon_count = Coupon.query.filter_by(
                campaign_id=campaign.id,
                prize_inventory_id=prize.id,
            ).count()

            coupons_to_create = prize_data["total_coupons"] - existing_coupon_count

            if coupons_to_create <= 0:
                print(
                    f"  ✓ Coupons already complete: "
                    f"{existing_coupon_count}/{prize_data['total_coupons']}"
                )
                continue

            print(
                f"  Generating {coupons_to_create} missing coupons "
                f"for {prize.prize_name}..."
            )

            prefix = f"JM{prize_data['sms_amount'] // 1000}K"

            for i in range(coupons_to_create):
                coupon_code = generate_unique_coupon_code_for_campaign(
                    campaign_id=campaign.id,
                    prefix=prefix,
                )

                coupon = Coupon(
                    campaign_id=campaign.id,
                    prize_inventory_id=prize.id,
                    coupon_code=coupon_code,
                    status="available",
                )

                db.session.add(coupon)

                if (i + 1) % 10 == 0:
                    print(f"    Generated {i + 1}/{coupons_to_create}")

            print(f"  ✓ Added {coupons_to_create} coupons")

        db.session.commit()

        refresh_remaining_coupons(campaign.id)

        print_summary(campaign.id)

        print("\n✅ Database seeding completed successfully!")


def refresh_remaining_coupons(campaign_id):
    prizes = PrizeInventory.query.filter_by(campaign_id=campaign_id).all()

    for prize in prizes:
        available_count = Coupon.query.filter_by(
            campaign_id=campaign_id,
            prize_inventory_id=prize.id,
            status="available",
        ).count()

        prize.remaining_coupons = available_count

    db.session.commit()


def print_summary(campaign_id):
    campaign = Campaign.query.get(campaign_id)

    print("\n📊 Summary:")
    print(f"Campaign: {campaign.campaign_name} ({campaign.campaign_slug})")

    prizes = PrizeInventory.query.filter_by(
        campaign_id=campaign_id
    ).order_by(PrizeInventory.sms_amount.asc()).all()

    for prize in prizes:
        total_coupon_count = Coupon.query.filter_by(
            campaign_id=campaign_id,
            prize_inventory_id=prize.id,
        ).count()

        available_coupon_count = Coupon.query.filter_by(
            campaign_id=campaign_id,
            prize_inventory_id=prize.id,
            status="available",
        ).count()

        print(
            f"  {prize.prize_name}: "
            f"{available_coupon_count}/{total_coupon_count} available "
            f"(weight: {prize.weight})"
        )


if __name__ == "__main__":
    seed_prizes_and_coupons()