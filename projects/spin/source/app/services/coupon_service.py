"""
Coupon reservation and management service.
Handles atomic coupon reservation with proper transaction handling.
"""

from datetime import datetime
from typing import Optional, Tuple

from app import db
from app.models import Coupon, PrizeInventory, SpinResult


class CouponReservationService:
    """
    Service for reserving coupons with atomic transactions.
    Ensures no race conditions or double-reservation.
    """

    @staticmethod
    def reserve_coupon_for_prize(
        prize_id: int,
        phone_number: str,
        campaign_id: int
    ) -> Tuple[bool, Optional[Coupon], str]:
        """
        Reserve one available coupon for a selected prize and attach it
        to the verified otp_pending spin record for this phone number.

        Args:
            prize_id: ID of the selected prize tier
            phone_number: normalized phone number

        Returns:
            Tuple[success, coupon, message]
        """
        try:
            existing_completed_result = (
                SpinResult.query
                .filter(
                    SpinResult.phone_number == phone_number,
                    SpinResult.campaign_id == campaign_id,
                    SpinResult.status.in_(["reserved", "claimed"])
                )
                .first()
            )
            if existing_completed_result:
                return False, None, "This phone number has already participated."

            pending_spin = (
                SpinResult.query
                .filter(
                    SpinResult.phone_number == phone_number,
                    SpinResult.campaign_id == campaign_id,
                    SpinResult.status == "otp_pending"
                )
                .order_by(SpinResult.id.desc())
                .with_for_update()
                .first()
            )

            if not pending_spin:
                return False, None, "No pending verified OTP session found."

            if not pending_spin.otp_verified:
                return False, None, "Phone number is not OTP verified."

            prize = (
                db.session.query(PrizeInventory)
                .filter_by(id=prize_id, campaign_id=campaign_id, is_active=True)
                .with_for_update()
                .first()
            )

            if not prize:
                return False, None, f"Prize with ID {prize_id} not found"

            if prize.remaining_coupons <= 0:
                return False, None, f"No coupons remaining for prize {prize.sms_amount}SMS"

            coupon = (
                db.session.query(Coupon)
                .filter_by(
                    campaign_id=campaign_id,
                    prize_inventory_id=prize_id,
                    status='available',
                )
                .with_for_update()
                .first()
            )

            if not coupon:
                return False, None, f"No available coupons for prize {prize.sms_amount}SMS"

            now = datetime.utcnow()

            coupon.status = 'reserved'
            coupon.reserved_by_phone = phone_number
            coupon.reserved_at = now

            prize.remaining_coupons -= 1
            if hasattr(prize, 'updated_at'):
                prize.updated_at = now

            pending_spin.prize_inventory_id = prize_id
            pending_spin.coupon_id = coupon.id
            pending_spin.sms_amount = prize.sms_amount
            pending_spin.spin_time = now
            pending_spin.status = 'reserved'

            db.session.commit()

            return True, coupon, "Coupon reserved successfully"

        except Exception as e:
            db.session.rollback()
            return False, None, f"Error reserving coupon: {str(e)}"

    @staticmethod
    def has_phone_already_participated(phone_number: str) -> bool:
        return (
            SpinResult.query
            .filter(
                SpinResult.phone_number == phone_number,
                SpinResult.status.in_(["reserved", "claimed"])
            )
            .first()
            is not None
        )

    @staticmethod
    def get_result_by_phone(phone_number: str) -> Optional[SpinResult]:
        return (
            SpinResult.query
            .filter(
                SpinResult.phone_number == phone_number,
                SpinResult.status.in_(["reserved", "claimed", "otp_pending"])
            )
            .order_by(SpinResult.id.desc())
            .first()
        )

    @staticmethod
    def get_coupon_by_id(coupon_id: int) -> Optional[Coupon]:
        return Coupon.query.get(coupon_id)

    @staticmethod
    def claim_coupon(spin_token: str) -> Tuple[bool, str]:
        """
        Optional legacy support.
        """
        try:
            spin_result = SpinResult.query.filter_by(spin_token=spin_token).first()

            if not spin_result:
                return False, "Spin token not found"
            
            if spin_result.status != 'reserved':
                return False, f"Spin result status is {spin_result.status}, cannot claim"

            coupon = Coupon.query.get(spin_result.coupon_id)

            if not coupon:
                return False, "Coupon not found"

            coupon.status = 'claimed'
            coupon.claimed_at = datetime.utcnow()
            spin_result.status = 'claimed'

            db.session.commit()
            return True, "Coupon claimed successfully"

        except Exception as e:
            db.session.rollback()
            return False, f"Error claiming coupon: {str(e)}"