"""
Spin & Win API routes.
Handles DB-driven spin requests for the Flutter web app.
"""

from datetime import datetime, timedelta
import os
import random
import secrets

import requests
from flask import Blueprint, request, jsonify
import traceback

from app.database import db
from app.utils import normalize_phone_number, validate_phone_number
from app.services import PrizeSelectionService, CouponReservationService
from app.models import SpinResult, Campaign


spin_bp = Blueprint('spin', __name__, url_prefix='/api/spin')


def _latest_pending_spin(phone_number: str, campaign_id: int) -> SpinResult:
    return (
        SpinResult.query
        .filter_by(phone_number=phone_number, campaign_id=campaign_id, status='otp_pending')
        .order_by(SpinResult.id.desc())
        .first()
    )


def _completed_spin_exists(phone_number: str, campaign_id: int) -> bool:
    existing = (
        SpinResult.query
        .filter(
            SpinResult.phone_number == phone_number,
            SpinResult.campaign_id == campaign_id,  
            SpinResult.status.in_(['reserved', 'claimed'])
        )
        .first()
    )
    return existing is not None

def _get_campaign_from_request(data):
    campaign_slug = str(data.get("campaign_slug", "spin-win-test-2026")).strip()

    campaign = Campaign.query.filter_by(
        campaign_slug=campaign_slug,
        is_active=True
    ).first()

    return campaign

def _send_otp_sms(phone_number: str, otp: str):
    sender_id = os.getenv('SMS_SENDER_ID')
    accname = os.getenv('SMS_ACCNAME')
    accpass = os.getenv('SMS_ACCPASS')
    sms_url = os.getenv(
        'SMS_API_URL',
        'https://www.josms.net/SMSServices/Clients/Prof/SingleSMS/SMSService.asmx/SendSMS'
    )

    if not sender_id or not accname or not accpass:
        raise ValueError('Missing SMS environment variables.')

    message = f'Your OTP code is {otp}. Do not share it with anyone.'

    params = {
        'senderid': sender_id,
        'numbers': phone_number,
        'accname': accname,
        'AccPass': accpass,
        'msg': message,
        'id': '',
    }

    response = requests.get(sms_url, params=params, timeout=30)
    response.raise_for_status()

    response_text = response.text.strip()

    # Keep this for debugging provider responses
    print(f'[JOSMS RESPONSE] {response_text}')

    return response_text


@spin_bp.route('/request', methods=['POST'])
def spin():
    try:
        data = request.get_json(silent=True) or {}

        phone_input = str(data.get('phone_number', '')).strip()
        campaign_id = str(data.get('campaign_id', '')).strip()
        spin_token_input = str(data.get('spin_token', '')).strip()
        campaign = _get_campaign_from_request(data)
        if not campaign:
            return jsonify({
                'status': 'error',
                'message': 'Invalid or inactive campaign.'
            }), 404
        if not phone_input:
            return jsonify({
                'status': 'error',
                'message': 'Missing phone_number in request',
            }), 400

        if not spin_token_input:
            return jsonify({
                'status': 'error',
                'message': 'Missing spin_token in request',
            }), 400

        if not validate_phone_number(phone_input):
            return jsonify({
                'status': 'error',
                'message': 'Invalid phone number format',
            }), 400

        try:
            phone_number = normalize_phone_number(phone_input)
        except ValueError as exc:
            return jsonify({
                'status': 'error',
                'message': str(exc),
            }), 400

        pending_spin = (
            SpinResult.query
            .filter_by(
                phone_number=phone_number,
                campaign_id=campaign.id,
                status='otp_pending',
                spin_token=spin_token_input,
            )
            .order_by(SpinResult.id.desc())
            .first()
        )

        if not pending_spin:
            return jsonify({
                'status': 'error',
                'message': 'No valid OTP session found. Please request a new OTP first.',
            }), 403

        if pending_spin.otp_expires_at and pending_spin.otp_expires_at < datetime.utcnow():
            return jsonify({
                'status': 'error',
                'message': 'OTP session expired. Please request a new OTP.',
            }), 403

        if not pending_spin.otp_verified:
            return jsonify({
                'status': 'error',
                'message': 'Phone not verified. Please verify OTP first.',
            }), 403

        if _completed_spin_exists(phone_number, campaign.id):
            return jsonify({
                'status': 'error',
                'message': 'This phone number has already participated.',
            }), 409

        selected_prize = PrizeSelectionService.select_prize_weighted(campaign.id)
        if not selected_prize:
            return jsonify({
                'status': 'error',
                'message': 'No prizes available at this time',
            }), 503

        success, coupon, message = CouponReservationService.reserve_coupon_for_prize(
            selected_prize.id,
            phone_number,
            campaign.id,
        )

        if not success or coupon is None:
            status_code = 409 if 'already participated' in (message or '').lower() else 500
            return jsonify({
                'status': 'error',
                'message': message or 'Failed to reserve coupon.',
            }), status_code

        pending_spin.prize_inventory_id = selected_prize.id
        pending_spin.coupon_id = coupon.id
        pending_spin.sms_amount = int(selected_prize.sms_amount)
        pending_spin.status = 'reserved'
        pending_spin.spin_time = datetime.utcnow()

        pending_spin.otp_code = None
        pending_spin.otp_expires_at = None

        db.session.commit()

        return jsonify({
            'status': 'success',
            'message': 'Prize assigned successfully',
            'data': {
                'smsAmount': int(selected_prize.sms_amount),
                'isGrandPrize': bool(int(selected_prize.sms_amount) >= 1000000),
                'couponCode': str(coupon.coupon_code),
                'prizeId': int(selected_prize.id),
                'spinToken': str(pending_spin.spin_token),
            }
        }), 200

    except Exception as exc:
        db.session.rollback()
        traceback.print_exc()
        return jsonify({
            'status': 'error',
            'message': f'Server error: {str(exc)}',
        }), 500


@spin_bp.route('/send-otp', methods=['POST'])
def send_otp():
    try:
        data = request.get_json(silent=True) or {}
        campaign = _get_campaign_from_request(data)
        if not campaign:
            return jsonify({
                'success': False,
                'message': 'Invalid or inactive campaign.'
            }), 404
        phone_input = str(data.get('phone_number', '')).strip()
        if not phone_input:
            return jsonify({
                'success': False,
                'message': 'Missing phone_number in request'
            }), 400

        if not validate_phone_number(phone_input):
            return jsonify({
                'success': False,
                'message': 'Invalid phone number'
            }), 400

        try:
            phone_number = normalize_phone_number(phone_input)
        except ValueError as exc:
            return jsonify({
                'success': False,
                'message': str(exc)
            }), 400

        if _completed_spin_exists(phone_number, campaign.id):
            return jsonify({
                'success': False,
                'message': 'This phone number has already participated.'
            }), 409

        otp = str(random.randint(100000, 999999))
        expires_at = datetime.utcnow() + timedelta(minutes=5)

        pending_spin = _latest_pending_spin(phone_number, campaign.id)
        completed_spin_exists = _completed_spin_exists(phone_number, campaign.id)

        if pending_spin:
            pending_spin.otp_code = otp
            pending_spin.otp_expires_at = expires_at
            pending_spin.otp_verified = False
            pending_spin.otp_attempts = 0
            pending_spin.spin_token = secrets.token_urlsafe(32)
        else:
            pending_spin = SpinResult(
                phone_number=phone_number,
                prize_inventory_id=None,
                coupon_id=None,
                sms_amount=0,
                otp_verified=False,
                otp_code=otp,
                otp_expires_at=expires_at,
                otp_attempts=0,
                campaign_id=campaign.id,
                sender_id=os.getenv('SMS_SENDER_ID'),
                status='otp_pending',
                spin_token=secrets.token_urlsafe(32),
            )
            db.session.add(pending_spin)

        db.session.flush()

        sms_response = _send_otp_sms(phone_number, otp)

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'OTP sent successfully',
            'provider_response': sms_response,
        }), 200

    except requests.RequestException as exc:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Failed to send OTP SMS: {str(exc)}'
        }), 502

    except Exception as exc:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Server error: {str(exc)}'
        }), 500


@spin_bp.route('/verify-otp', methods=['POST'])
def verify_otp():
    try:
        data = request.get_json(silent=True) or {}

        phone_input = str(data.get('phone_number', '')).strip()
        otp_input = str(data.get('otp', '')).strip()

        if not phone_input or not otp_input:
            return jsonify({
                'success': False,
                'message': 'Missing phone or OTP'
            }), 400

        if not validate_phone_number(phone_input):
            return jsonify({
                'success': False,
                'message': 'Invalid phone number'
            }), 400

        try:
            phone_number = normalize_phone_number(phone_input)
        except ValueError as exc:
            return jsonify({
                'success': False,
                'message': str(exc)
            }), 400

        campaign = _get_campaign_from_request(data)
        if not campaign:
            return jsonify({
                'success': False,
                'message': 'Invalid or inactive campaign.'
            }), 404

        pending_spin = _latest_pending_spin(phone_number, campaign.id)

        if _completed_spin_exists(phone_number, campaign.id):
            return jsonify({
                'success': False,
                'message': 'This phone number has already participated.'
            }), 409

        if not pending_spin:
            return jsonify({
                'success': False,
                'message': 'OTP not found. Please request a new OTP.'
            }), 400

        if pending_spin.otp_expires_at and pending_spin.otp_expires_at < datetime.utcnow():
            return jsonify({
                'success': False,
                'message': 'OTP expired. Please request a new OTP.'
            }), 400

        if pending_spin.otp_attempts is None:
            pending_spin.otp_attempts = 0

        if pending_spin.otp_attempts >= 5:
            return jsonify({
                'success': False,
                'message': 'Too many invalid attempts. Please request a new OTP.'
            }), 429

        if pending_spin.otp_code != otp_input:
            pending_spin.otp_attempts += 1
            db.session.commit()
            return jsonify({
                'success': False,
                'message': 'Invalid OTP'
            }), 400

        pending_spin.otp_verified = True
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'OTP verified successfully',
            'spin_token': pending_spin.spin_token,
        }), 200

    except Exception as exc:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Server error: {str(exc)}'
        }), 500