"""
Prize allocation and selection service.
Handles weighted random selection of prizes based on available inventory.
"""
import random
from typing import Optional, Tuple
from app.models import PrizeInventory, Coupon, SpinResult
from app import db


class PrizeSelectionService:
    """
    Service for selecting prizes based on weighted probability and available inventory.
    """

    @staticmethod
    def get_available_prizes(campaign_id: int) -> list:
        """
        Get all active prizes with remaining coupons.
        
        Returns:
            List of PrizeInventory objects that are active and have remaining coupons
        """
        return PrizeInventory.query.filter(
            PrizeInventory.campaign_id == campaign_id,
            PrizeInventory.is_active == True,
            PrizeInventory.remaining_coupons > 0
        ).all()

    @staticmethod
    def select_prize_weighted(campaign_id: int) -> Optional[PrizeInventory]:
        """
        Select a prize using weighted random selection.
        Prizes with higher weight have higher probability of being selected.
        
        Returns:
            Selected PrizeInventory object or None if no prizes available
        """
        available_prizes = PrizeSelectionService.get_available_prizes(campaign_id)

        
        if not available_prizes:
            return None
        
        # Build weighted list
        prizes = []
        weights = []
        
        for prize in available_prizes:
            prizes.append(prize)
            weights.append(prize.weight)
        
        # Weighted random selection
        selected = random.choices(prizes, weights=weights, k=1)[0]
        return selected

    @staticmethod
    def get_prize_index(prize_id: int, campaign_id: int):
   
        """
        Get the visual index of a prize on the wheel (0-5 for 6 prizes).
        This is used by Flutter to animate the wheel to the correct position.
        
        Args:
            prize_id: The ID of the prize
        
        Returns:
            Index position (0-5) or None if prize not found
        """
        # Get all prizes ordered by SMS amount (ascending)
        all_prizes = (
                PrizeInventory.query
                .filter_by(campaign_id=campaign_id)
                .order_by(PrizeInventory.sms_amount.asc())
                .all()
            )        
        for index, prize in enumerate(all_prizes):
            if prize.id == prize_id:
                return index
        
        return None

    @staticmethod
    def check_phone_eligibility(phone_number: str, campaign_id: int): 
        """
        Check if a phone number is eligible to spin.
        Business rule: One spin per phone number.
        
        Args:
            phone_number: Normalized phone number
        
        Returns:
            Tuple of (is_eligible, message)
        """
        existing_spin = (
            SpinResult.query
            .filter(
                SpinResult.phone_number == phone_number,
                SpinResult.campaign_id == campaign_id,
                SpinResult.status.in_(["reserved", "claimed"])
            )
            .first()
        )
        if existing_spin:
            return False, None, "This phone number has already participated."
        
        return True, "Phone number is eligible"


