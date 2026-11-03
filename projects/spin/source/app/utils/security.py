"""
Security utilities for token generation and validation.
"""
import secrets
import hashlib
import hmac
from datetime import datetime, timedelta
from typing import Optional


def generate_spin_token(length: int = 32) -> str:
    """
    Generate a secure random token for spin results.
    
    Args:
        length: Length of the token in bytes
    
    Returns:
        Hex-encoded secure random token
    """
    return secrets.token_hex(length)


def generate_coupon_code(prefix: str = 'JM', length: int = 12) -> str:
    """
    Generate a unique coupon code.
    
    Args:
        prefix: Prefix for the coupon code
        length: Total length of the code
    
    Returns:
        Generated coupon code
    """
    random_part = secrets.token_hex((length - len(prefix)) // 2).upper()
    return f"{prefix}{random_part}"[:length]


def hash_token(token: str, salt: Optional[str] = None) -> str:
    """
    Hash a token using SHA-256.
    
    Args:
        token: Token to hash
        salt: Optional salt for hashing
    
    Returns:
        Hex-encoded hash
    """
    if salt:
        return hmac.new(salt.encode(), token.encode(), hashlib.sha256).hexdigest()
    return hashlib.sha256(token.encode()).hexdigest()
