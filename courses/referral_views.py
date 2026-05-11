from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from decimal import Decimal

from users.permissions import IsMasterAdmin

from .models import ReferralEvent, ReferralRelationship, ReferralSettings
from .referral_utils import (
    apply_referral_code,
    get_or_create_referral_profile,
    redeem_points_for_item,
)
from .serializers import PaymentSerializer


def user_name(user):
    if not user:
        return None
    full = f"{user.first_name or ''} {user.last_name or ''}".strip()
    return full or user.username or user.email


class ReferralEventSerializer(serializers.ModelSerializer):
    referrer_name = serializers.SerializerMethodField()
    referrer_email = serializers.EmailField(source='referrer.email', read_only=True)
    referred_name = serializers.SerializerMethodField()
    referred_email = serializers.EmailField(source='referred.email', read_only=True, allow_null=True)
    item_title = serializers.SerializerMethodField()

    class Meta:
        model = ReferralEvent
        fields = [
            'id', 'event_type', 'points', 'referrer', 'referrer_name', 'referrer_email',
            'referred', 'referred_name', 'referred_email', 'course', 'material_id',
            'item_title', 'payment', 'metadata', 'created_at'
        ]

    def get_referrer_name(self, obj):
        return user_name(obj.referrer)

    def get_referred_name(self, obj):
        return user_name(obj.referred)

    def get_item_title(self, obj):
        if obj.course:
            return obj.course.title
        if obj.metadata:
            return obj.metadata.get('item_title')
        return None


class MyReferralView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile = get_or_create_referral_profile(request.user)
        events = ReferralEvent.objects.filter(referrer=request.user).select_related('referred', 'course', 'payment')[:20]
        relationships = ReferralRelationship.objects.filter(referrer=request.user)
        
        # Keep as querysets for filtering
        awarded_qs = ReferralEvent.objects.filter(referrer=request.user, points__gt=0)
        redeemed_qs = ReferralEvent.objects.filter(referrer=request.user, event_type=ReferralEvent.POINTS_REDEEMED)
        
        # Calculate sums from querysets
        awarded_list = list(awarded_qs)
        redeemed_list = list(redeemed_qs)
        
        settings = ReferralSettings.get_solo()
        return Response({
            'code': profile.code,
            'points_balance': profile.points_balance,
            'total_referrals': relationships.count(),
            'verified_signups': awarded_qs.filter(event_type=ReferralEvent.SIGNUP_VERIFIED).count(),
            'course_purchases': awarded_qs.filter(event_type=ReferralEvent.COURSE_PURCHASE).count(),
            'material_purchases': awarded_qs.filter(event_type=ReferralEvent.MATERIAL_PURCHASE).count(),
            'points_awarded': sum(Decimal(e.points) for e in awarded_list) if awarded_list else Decimal('0.00'),
            'points_redeemed': abs(sum(Decimal(e.points) for e in redeemed_list)) if redeemed_list else Decimal('0.00'),
            'recent_events': ReferralEventSerializer(events, many=True).data,
            'settings': {
                'points_per_success': settings.points_per_success,
                'referral_percent': settings.referral_percent,
            },
        })


class ApplyReferralCodeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        code = request.data.get('code') or request.data.get('referral_code')
        relationship = apply_referral_code(request.user, code)
        if not relationship:
            return Response({'detail': 'Referral code could not be applied.'}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'detail': 'Referral code applied.', 'code': relationship.code_used})


class RedeemReferralPointsView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        item_type = request.data.get('item_type')
        item_id = request.data.get('item_id')
        if not item_type or not item_id:
            return Response({'detail': 'item_type and item_id are required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            payment, event, profile = redeem_points_for_item(request.user, item_type, item_id)
            return Response({
                'detail': 'Referral points redeemed successfully.',
                'points_balance': profile.points_balance,
                'points_redeemed': abs(event.points),
                'payment': PaymentSerializer(payment).data,
            })
        except Exception as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class AdminReferralSettingsView(APIView):
    permission_classes = [IsAuthenticated, IsMasterAdmin]

    def get(self, request):
        settings = ReferralSettings.get_solo()
        return Response({'points_per_success': settings.points_per_success, 'referral_percent': settings.referral_percent, 'updated_at': settings.updated_at})

    def patch(self, request):
        settings = ReferralSettings.get_solo()
        # Allow updating both legacy points and the new referral_percent (decimal fraction such as 0.05 for 5%)
        updated = {}
        if 'points_per_success' in request.data:
            try:
                points = int(request.data.get('points_per_success'))
                if points < 0:
                    raise ValueError()
            except Exception:
                return Response({'detail': 'points_per_success must be a non-negative integer.'}, status=status.HTTP_400_BAD_REQUEST)
            settings.points_per_success = points
            updated['points_per_success'] = settings.points_per_success

        if 'referral_percent' in request.data:
            try:
                rp = Decimal(str(request.data.get('referral_percent')))
                if rp < 0:
                    raise ValueError()
            except Exception:
                return Response({'detail': 'referral_percent must be a non-negative decimal (e.g., 0.05 for 5%).'}, status=status.HTTP_400_BAD_REQUEST)
            settings.referral_percent = rp
            updated['referral_percent'] = settings.referral_percent

        settings.updated_by = request.user
        settings.save()
        return Response({'detail': 'Updated', **updated})


class AdminReferralEventsView(APIView):
    permission_classes = [IsAuthenticated, IsMasterAdmin]

    def get(self, request):
        qs = ReferralEvent.objects.select_related('referrer', 'referred', 'course', 'payment').all()
        event_type = request.query_params.get('event_type')
        if event_type:
            qs = qs.filter(event_type=event_type)

        limit = min(int(request.query_params.get('limit', 100)), 500)
        events = list(qs[:limit])
        
        # Keep querysets for aggregations
        awarded_qs = ReferralEvent.objects.filter(points__gt=0)
        redeemed_qs = ReferralEvent.objects.filter(event_type=ReferralEvent.POINTS_REDEEMED)
        
        awarded_list = list(awarded_qs)
        redeemed_list = list(redeemed_qs)
        
        return Response({
            'summary': {
                'total_events': ReferralEvent.objects.count(),
                'awarded_points': sum(Decimal(e.points) for e in awarded_list) if awarded_list else Decimal('0.00'),
                'redeemed_points': abs(sum(Decimal(e.points) for e in redeemed_list)) if redeemed_list else Decimal('0.00'),
                'active_referrers': ReferralEvent.objects.values('referrer').distinct().count(),
                'successful_referrals': len(awarded_list),
            },
            'results': ReferralEventSerializer(events, many=True).data,
        })
