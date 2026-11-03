"""
Phone number validation and normalization utilities.
"""
import phonenumbers
from phonenumbers import NumberParseException


def normalize_phone_number(phone_str: str, default_region: str = 'JO') -> str:
    """
    Normalize a phone number to E.164 format.
    
    Args:
        phone_str: The phone number string to normalize
        default_region: Default region code (ISO 3166-1 alpha-2), default is 'JO' (Jordan)
    
    Returns:
        Normalized phone number in E.164 format (e.g., '+9627XXXXXXXX')
    
    Raises:
        ValueError: If phone number is invalid
    """
    try:
        # Parse the phone number
        parsed = phonenumbers.parse(phone_str, default_region)
        
        # Validate the number
        if not phonenumbers.is_valid_number(parsed):
            raise ValueError(f"Invalid phone number: {phone_str}")
        
        # Format to E.164
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except NumberParseException as e:
        raise ValueError(f"Failed to parse phone number: {phone_str}") from e


def validate_phone_number(phone_str: str, default_region: str = 'JO') -> bool:
    """
    Validate if a phone number is valid.
    
    Args:
        phone_str: The phone number string to validate
        default_region: Default region code
    
    Returns:
        True if valid, False otherwise
    """
    try:
        parsed = phonenumbers.parse(phone_str, default_region)
        return phonenumbers.is_valid_number(parsed)
    except NumberParseException:
        return False
