from app import create_app, db
from app.models import Campaign, PrizeInventory, Coupon

app = create_app()

with app.app_context():
    print("Campaigns:", Campaign.query.count())
    print("Prizes:", PrizeInventory.query.count())
    print("Coupons:", Coupon.query.count())

    campaign = Campaign.query.filter_by(campaign_slug="spin-win-test-2026").first()
    print("Campaign:", campaign.id, campaign.campaign_slug)

    for prize in PrizeInventory.query.filter_by(campaign_id=campaign.id).all():
        coupons = Coupon.query.filter_by(
            campaign_id=campaign.id,
            prize_inventory_id=prize.id
        ).count()

        print(prize.id, prize.prize_name, prize.sms_amount, prize.remaining_coupons, coupons)