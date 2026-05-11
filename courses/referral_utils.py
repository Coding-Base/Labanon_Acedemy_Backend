import json
import uuid
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import (
    Course,
    Enrollment,
    Payment,
    ReferralEvent,
    ReferralProfile,
    ReferralRelationship,
    ReferralSettings,
)
from .models import PaymentSplitConfig


def _user_label(user):
    if not user:
        return ''
    full_name = f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip()
    return full_name or getattr(user, 'username', '') or getattr(user, 'email', '')


def generate_referral_code(user):
    base = ''.join(ch for ch in (getattr(user, 'username', '') or getattr(user, 'email', '') or 'USER') if ch.isalnum())
    base = (base[:6] or 'USER').upper()
    return f"{base}{uuid.uuid4().hex[:6].upper()}"


def get_or_create_referral_profile(user):
    profile = getattr(user, 'referral_profile', None)
    if profile:
        return profile

    for _ in range(8):
        try:
            return ReferralProfile.objects.create(user=user, code=generate_referral_code(user))
        except IntegrityError:
            continue
    return ReferralProfile.objects.create(user=user, code=uuid.uuid4().hex[:12].upper())


def apply_referral_code(referred_user, code):
    code = (code or '').strip().upper()
    if not code or not referred_user or not getattr(referred_user, 'is_authenticated', True):
        return None
    if ReferralRelationship.objects.filter(referred=referred_user).exists():
        return ReferralRelationship.objects.filter(referred=referred_user).first()

    try:
        profile = ReferralProfile.objects.select_related('user').get(code__iexact=code)
    except ReferralProfile.DoesNotExist:
        return None

    if profile.user_id == referred_user.id:
        return None

    try:
        return ReferralRelationship.objects.create(
            referrer=profile.user,
            referred=referred_user,
            code_used=profile.code,
        )
    except IntegrityError:
        return ReferralRelationship.objects.filter(referred=referred_user).first()


def award_signup_verified(referred_user):
    relationship = ReferralRelationship.objects.filter(referred=referred_user).select_related('referrer').first()
    if not relationship:
        return None
    # Per new policy: track signup but do not award points for signups (award 0 points)
    return _award_referral_event(
        referrer=relationship.referrer,
        referred=referred_user,
        event_type=ReferralEvent.SIGNUP_VERIFIED,
        metadata={'referred_name': _user_label(referred_user)},
        force_zero_points=True,  # Track but don't award
    )


def award_course_purchase(payment):
    if not payment or payment.kind != Payment.KIND_COURSE or not payment.course or Decimal(payment.amount or 0) <= 0:
        return None
    relationship = ReferralRelationship.objects.filter(referred=payment.user).select_related('referrer').first()
    if not relationship:
        return None
    return _award_referral_event(
        referrer=relationship.referrer,
        referred=payment.user,
        event_type=ReferralEvent.COURSE_PURCHASE,
        course=payment.course,
        payment=payment,
        metadata={'item_title': payment.course.title, 'referred_name': _user_label(payment.user)},
    )


def award_material_purchase(payment, material):
    if not payment or not material or payment.kind != Payment.KIND_MATERIAL or Decimal(payment.amount or 0) <= 0:
        return None
    relationship = ReferralRelationship.objects.filter(referred=payment.user).select_related('referrer').first()
    if not relationship:
        return None
    return _award_referral_event(
        referrer=relationship.referrer,
        referred=payment.user,
        event_type=ReferralEvent.MATERIAL_PURCHASE,
        material_id=material.id,
        payment=payment,
        metadata={'item_title': material.name, 'referred_name': _user_label(payment.user)},
    )


def _award_referral_event(referrer, referred, event_type, course=None, material_id=None, payment=None, metadata=None, force_zero_points=False):
    settings = ReferralSettings.get_solo()

    # Handle force_zero_points for signup tracking (no points awarded)
    if force_zero_points:
        points = Decimal('0.00')
    else:
        # Prefer configured fractional percent (e.g., 0.05 => 5%).
        referral_percent = Decimal(settings.referral_percent or 0)

        # Fallback mode: if referral_percent is not positive, use legacy points_per_success
        use_legacy_points = referral_percent <= 0

        if use_legacy_points:
            points = Decimal(int(settings.points_per_success or 0))
        else:
            # Compute base: prefer payment.platform_fee when available, else compute platform share from amount
            base = Decimal('0.00')
            if payment is not None:
                try:
                    p_platform = Decimal(payment.platform_fee or 0)
                except Exception:
                    p_platform = Decimal('0.00')
                if p_platform > 0:
                    base = p_platform
                else:
                    # compute platform share from configured splits
                    split = PaymentSplitConfig.get_solo()
                    if getattr(payment, 'course', None) and getattr(payment.course, 'institution', None):
                        inst = payment.course.institution
                        creator_share = Decimal(inst.custom_share_percentage) if getattr(inst, 'custom_share_percentage', None) else Decimal(split.institution_share)
                    else:
                        creator_share = Decimal(split.tutor_share)
                    platform_share_percent = (Decimal('100') - creator_share)
                    try:
                        base = (Decimal(payment.amount or 0) * platform_share_percent) / Decimal('100')
                    except Exception:
                        base = Decimal('0.00')

            # referral amount = base * referral_percent
            points = (base * referral_percent).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    # Create event even with 0 points (for signup tracking)
    with transaction.atomic():
        profile = get_or_create_referral_profile(referrer)

        event, created = ReferralEvent.objects.get_or_create(
            referrer=referrer,
            referred=referred,
            event_type=event_type,
            course=course,
            material_id=material_id,
            defaults={
                'points': points,
                'payment': payment,
                'metadata': metadata or {},
            },
        )
        if created and points > 0:
            # Only increment balance if points > 0 (don't increment for signup tracking)
            profile.points_balance = (Decimal(profile.points_balance or 0) + points).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            profile.save(update_fields=['points_balance', 'updated_at'])
        return event


def redeem_points_for_item(user, item_type, item_id):
    item_type = (item_type or '').strip().lower()
    if item_type not in ('course', 'material'):
        raise ValueError('Referral points can only be used for courses and materials.')

    with transaction.atomic():
        profile = ReferralProfile.objects.select_for_update().get(user=user)

        if item_type == 'course':
            item = Course.objects.get(id=item_id)
            price = Decimal(item.price or 0)
            kind = Payment.KIND_COURSE
        else:
            from materials.models import Material
            item = Material.objects.get(id=item_id)
            price = Decimal(item.price or 0)
            kind = Payment.KIND_MATERIAL

        if price <= 0:
            raise ValueError('This item is free and does not require referral points.')

        # Treat points_balance as currency-credit; require two-decimal comparison
        points_needed = price.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        if Decimal(profile.points_balance or 0) < points_needed:
            raise ValueError('Insufficient referral points for this purchase.')

        payment = Payment.objects.create(
            user=user,
            course=item if item_type == 'course' else None,
            amount=0,
            currency=getattr(item, 'currency', 'NGN') or 'NGN',
            kind=kind,
            platform_fee=0,
            creator_amount=0,
            status=Payment.SUCCESS,
            verified_at=timezone.now(),
            provider_reference=json.dumps({
                'item_type': item_type,
                'item_id': str(getattr(item, 'id')),
                'points_redeemed': str(points_needed),
                'source': 'referral_points',
            }),
        )

        if item_type == 'course':
            Enrollment.objects.update_or_create(
                user=user,
                course=item,
                defaults={'purchased': True, 'purchased_at': timezone.now()},
            )
            metadata = {'item_title': item.title, 'item_type': 'course'}
        else:
            from materials.models import MaterialPurchase
            MaterialPurchase.objects.update_or_create(
                user=user,
                material=item,
                defaults={'payment': payment, 'accessed_at': timezone.now()},
            )
            metadata = {'item_title': item.name, 'item_type': 'material', 'material_id': str(item.id)}

        profile.points_balance = (Decimal(profile.points_balance or 0) - points_needed).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        profile.save(update_fields=['points_balance', 'updated_at'])

        event = ReferralEvent.objects.create(
            referrer=user,
            referred=None,
            event_type=ReferralEvent.POINTS_REDEEMED,
            points=(Decimal('-1') * points_needed).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            course=item if item_type == 'course' else None,
            material_id=item.id if item_type == 'material' else None,
            payment=payment,
            metadata=metadata,
        )

        return payment, event, profile
