"""Views for the Exam Referral Cash Reward system.

Student endpoints  — prefixed /api/exam-referrals/
Admin endpoints    — prefixed /api/exam-referrals/admin/
"""
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum, Count, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from users.permissions import IsMasterAdmin
from .models import (
    BankAccount,
    ExamReferralCampaign,
    ExamReferralPayout,
    ExamReferralPromoConfig,
    ExamReferralReward,
    ReferralRelationship,
)
from .exam_referral_serializers import (
    BankAccountSerializer,
    ExamReferralCampaignCreateSerializer,
    ExamReferralCampaignSerializer,
    ExamReferralPayoutSerializer,
    ExamReferralPromoConfigSerializer,
    ExamReferralRewardSerializer,
)
from .referral_utils import get_or_create_referral_profile


def _user_display(user):
    if not user:
        return None
    full = f"{user.first_name or ''} {user.last_name or ''}".strip()
    return full or user.username


# ═══════════════════════════════════════════════════════════════════════════
#  STUDENT ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════


class ExamReferralCampaignsListView(APIView):
    """GET — list active campaigns with user's referral link context."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        campaigns = ExamReferralCampaign.objects.select_related('exam').filter(
            is_active=True,
        ).order_by('-created_at')

        # Filter to currently valid only
        valid = [c for c in campaigns if c.is_valid()]

        profile = get_or_create_referral_profile(request.user)
        data = ExamReferralCampaignSerializer(valid, many=True).data

        # Annotate each campaign with user-specific referral count
        for item, campaign in zip(data, valid):
            item['referral_count'] = ExamReferralReward.objects.filter(
                campaign=campaign, referrer=request.user,
            ).exclude(status=ExamReferralReward.STATUS_CANCELLED).count()
            item['referral_code'] = profile.code

        return Response(data)


class StudentExamReferralDashboardView(APIView):
    """GET — student's complete exam referral dashboard data."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        profile = get_or_create_referral_profile(user)

        rewards = ExamReferralReward.objects.filter(
            referrer=user,
        ).select_related('campaign__exam', 'referee', 'payout')

        total_earned = rewards.filter(
            status__in=[ExamReferralReward.STATUS_EARNED, ExamReferralReward.STATUS_PAID],
        ).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

        total_paid = rewards.filter(
            status=ExamReferralReward.STATUS_PAID,
        ).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

        total_pending = rewards.filter(
            status=ExamReferralReward.STATUS_EARNED,
        ).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

        # Bank account
        try:
            bank = BankAccountSerializer(user.bank_account).data
        except BankAccount.DoesNotExist:
            bank = None

        # Payouts
        payouts = ExamReferralPayout.objects.filter(
            user=user,
        ).order_by('-created_at')[:20]

        # Active campaigns for referral links
        campaigns = ExamReferralCampaign.objects.select_related('exam').filter(
            is_active=True,
        )
        valid_campaigns = [c for c in campaigns if c.is_valid()]

        # Next payout date
        next_payout = None
        for c in valid_campaigns:
            if c.payout_date:
                if next_payout is None or c.payout_date < next_payout:
                    next_payout = c.payout_date

        return Response({
            'referral_code': profile.code,
            'points_balance': str(profile.points_balance),
            'total_earned': str(total_earned),
            'total_paid': str(total_paid),
            'total_pending': str(total_pending),
            'bank_account': bank,
            'next_payout_date': next_payout,
            'rewards': ExamReferralRewardSerializer(
                rewards.order_by('-created_at')[:50], many=True,
            ).data,
            'payouts': ExamReferralPayoutSerializer(payouts, many=True).data,
            'active_campaigns': ExamReferralCampaignSerializer(valid_campaigns, many=True).data,
        })


class BankAccountView(APIView):
    """GET / POST / PUT — manage user's bank account for payouts."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            ba = request.user.bank_account
            return Response(BankAccountSerializer(ba).data)
        except BankAccount.DoesNotExist:
            return Response(None, status=status.HTTP_200_OK)

    def post(self, request):
        # Create
        if BankAccount.objects.filter(user=request.user).exists():
            return Response(
                {'detail': 'Bank account already exists. Use PUT to update.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = BankAccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(user=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def put(self, request):
        try:
            ba = request.user.bank_account
        except BankAccount.DoesNotExist:
            # Auto-create on PUT for convenience
            serializer = BankAccountSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.save(user=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        serializer = BankAccountSerializer(ba, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        # When account details change, reset verification
        if any(k in request.data for k in ('account_number', 'bank_name', 'bank_code')):
            serializer.save(is_verified=False)
        else:
            serializer.save()
        return Response(serializer.data)


class ExamReferralPromoConfigView(APIView):
    """GET — public-facing promo display config (for student dashboard and homepage)."""
    permission_classes = [AllowAny]

    def get(self, request):
        config = ExamReferralPromoConfig.get_solo()
        return Response(ExamReferralPromoConfigSerializer(config).data)


class ReferralRegistrationView(APIView):
    """POST — streamlined registration with auto email verification for
    students arriving via an exam referral link.

    Payload: { username, email, password, first_name, last_name,
               referral_code, exam_id }

    On success returns JWT tokens + target exam info so the frontend can
    auto-login and redirect.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        from users.models import User
        from users.serializers import RegisterSerializer
        from rest_framework_simplejwt.tokens import RefreshToken
        from .referral_utils import apply_referral_code

        data = request.data.copy()
        referral_code = data.pop('referral_code', '') or ''
        exam_id = data.pop('exam_id', '') or ''

        # Force student role
        data['role'] = 'student'
        # Strip the referral_code field from data to prevent RegisterSerializer
        # from applying it separately (we handle it ourselves below).
        data.pop('referral_code', None)

        serializer = RegisterSerializer(data=data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # Auto-verify email for referred students
        if referral_code:
            user.email_verified = True
            user.email_verified_at = timezone.now()
            user.email_verification_token = None
            user.save(update_fields=[
                'email_verified', 'email_verified_at', 'email_verification_token',
            ])
            apply_referral_code(user, referral_code)

            # Create pending exam-referral reward if campaign exists
            if exam_id:
                try:
                    campaign = ExamReferralCampaign.objects.filter(
                        Q(exam__id=int(exam_id)) | Q(exam__slug=str(exam_id)),
                        is_active=True,
                    ).first()
                    if campaign and campaign.is_valid():
                        rel = ReferralRelationship.objects.filter(referred=user).first()
                        if rel:
                            ExamReferralReward.objects.get_or_create(
                                campaign=campaign,
                                referrer=rel.referrer,
                                referee=user,
                                defaults={
                                    'amount': campaign.cash_reward,
                                    'currency': campaign.currency,
                                    'status': ExamReferralReward.STATUS_PENDING,
                                },
                            )
                except Exception:
                    pass

        # Issue JWT tokens for auto-login
        refresh = RefreshToken.for_user(user)

        # Build direct target route for CBT exam page (e.g. 1-jamb)
        exam_target_route = ''
        if exam_id:
            try:
                from cbt.models import Exam as CBTExam
                ex = CBTExam.objects.filter(
                    Q(id=int(exam_id)) if str(exam_id).isdigit() else Q(slug=str(exam_id))
                ).first()
                if ex:
                    exam_target_route = f"{ex.id}-{ex.slug}" if ex.slug else str(ex.id)
            except Exception:
                exam_target_route = str(exam_id)

        return Response({
            'detail': 'Account created successfully.',
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'exam_id': exam_id,
            'exam_target_route': exam_target_route,
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'role': user.role,
            },
        }, status=status.HTTP_201_CREATED)


# ═══════════════════════════════════════════════════════════════════════════
#  ADMIN ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════


class AdminExamReferralCampaignView(APIView):
    """GET / POST — list all campaigns or create a new one."""
    permission_classes = [IsAuthenticated, IsMasterAdmin]

    def get(self, request):
        qs = ExamReferralCampaign.objects.select_related('exam', 'created_by').all()
        return Response(ExamReferralCampaignSerializer(qs, many=True).data)

    def post(self, request):
        serializer = ExamReferralCampaignCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        campaign = serializer.save(created_by=request.user)
        return Response(
            ExamReferralCampaignSerializer(campaign).data,
            status=status.HTTP_201_CREATED,
        )


class AdminExamReferralCampaignDetailView(APIView):
    """GET / PUT / PATCH / DELETE — manage a single campaign."""
    permission_classes = [IsAuthenticated, IsMasterAdmin]

    def _get_campaign(self, campaign_id):
        try:
            return ExamReferralCampaign.objects.select_related('exam').get(id=campaign_id)
        except ExamReferralCampaign.DoesNotExist:
            return None

    def get(self, request, campaign_id):
        campaign = self._get_campaign(campaign_id)
        if not campaign:
            return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(ExamReferralCampaignSerializer(campaign).data)

    def put(self, request, campaign_id):
        return self._update(request, campaign_id, partial=False)

    def patch(self, request, campaign_id):
        return self._update(request, campaign_id, partial=True)

    def _update(self, request, campaign_id, partial):
        campaign = self._get_campaign(campaign_id)
        if not campaign:
            return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        serializer = ExamReferralCampaignCreateSerializer(
            campaign, data=request.data, partial=partial,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(ExamReferralCampaignSerializer(campaign).data)

    def delete(self, request, campaign_id):
        campaign = self._get_campaign(campaign_id)
        if not campaign:
            return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        campaign.delete()
        return Response({'detail': 'Campaign deleted successfully.'}, status=status.HTTP_200_OK)


class AdminExamReferralRewardsView(APIView):
    """GET — all rewards with referrer bank details for payout processing."""
    permission_classes = [IsAuthenticated, IsMasterAdmin]

    def get(self, request):
        qs = ExamReferralReward.objects.select_related(
            'campaign__exam', 'referrer__bank_account', 'referee', 'payout',
        ).all()

        # Optional filters
        status_filter = request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        campaign_id = request.query_params.get('campaign_id')
        if campaign_id:
            qs = qs.filter(campaign_id=campaign_id)

        limit = min(int(request.query_params.get('limit', 200)), 500)
        rewards = qs[:limit]

        serializer = ExamReferralRewardSerializer(
            rewards, many=True,
            context={'include_bank_details': True},
        )
        return Response(serializer.data)


class AdminExamReferralDashboardView(APIView):
    """GET — aggregate metrics for the entire exam referral programme."""
    permission_classes = [IsAuthenticated, IsMasterAdmin]

    def get(self, request):
        campaigns = ExamReferralCampaign.objects.select_related('exam').all()
        rewards = ExamReferralReward.objects.all()
        payouts = ExamReferralPayout.objects.all()

        total_accrued = rewards.filter(
            status__in=[ExamReferralReward.STATUS_EARNED, ExamReferralReward.STATUS_PAID],
        ).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

        total_paid = payouts.filter(
            status=ExamReferralPayout.STATUS_CONFIRMED,
        ).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

        # Real pending due is the sum of unlocked rewards ('earned') awaiting payout
        total_pending = rewards.filter(
            status=ExamReferralReward.STATUS_EARNED,
        ).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

        # Per-campaign breakdown
        breakdown = []
        for c in campaigns:
            r = rewards.filter(campaign=c)
            breakdown.append({
                'campaign_id': c.id,
                'exam_title': c.exam.title,
                'cash_reward': str(c.cash_reward),
                'currency': c.currency,
                'is_active': c.is_active,
                'payout_date': c.payout_date,
                'total_rewards': r.count(),
                'earned': r.filter(status=ExamReferralReward.STATUS_EARNED).count(),
                'paid': r.filter(status=ExamReferralReward.STATUS_PAID).count(),
                'pending_signups': r.filter(status=ExamReferralReward.STATUS_PENDING).count(),
                'amount_accrued': str(
                    r.filter(status__in=['earned', 'paid']).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
                ),
            })

        # Referrers with complete grouped referees & bank details
        distinct_referrer_ids = list(
            rewards.exclude(status=ExamReferralReward.STATUS_CANCELLED)
            .values_list('referrer__id', flat=True)
            .distinct()
        )

        from django.contrib.auth import get_user_model
        User = get_user_model()
        referrers_users = User.objects.filter(id__in=distinct_referrer_ids).select_related('bank_account')

        top_referrers = []
        for u in referrers_users:
            u_rewards = (
                rewards.filter(referrer=u)
                .select_related('referee', 'campaign__exam', 'payout')
                .order_by('-created_at')
            )

            accrued = u_rewards.filter(
                status__in=[ExamReferralReward.STATUS_EARNED, ExamReferralReward.STATUS_PAID]
            ).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

            paid = u_rewards.filter(
                status=ExamReferralReward.STATUS_PAID
            ).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

            pending = u_rewards.filter(
                status=ExamReferralReward.STATUS_EARNED
            ).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

            pending_count = u_rewards.filter(status=ExamReferralReward.STATUS_EARNED).count()

            # Bank details
            bank = None
            try:
                if hasattr(u, 'bank_account'):
                    bank = BankAccountSerializer(u.bank_account).data
            except Exception:
                pass

            referees_list = []
            for rew in u_rewards:
                ref_name = _user_display(rew.referee)
                referees_list.append({
                    'reward_id': rew.id,
                    'referee_id': rew.referee_id,
                    'referee_name': ref_name,
                    'referee_email': rew.referee.email if rew.referee else '',
                    'referee_username': rew.referee.username if rew.referee else '',
                    'campaign_id': rew.campaign_id,
                    'exam_id': rew.campaign.exam_id if rew.campaign else None,
                    'exam_title': rew.campaign.exam.title if rew.campaign and rew.campaign.exam else 'CBT Exam',
                    'amount': str(rew.amount),
                    'currency': rew.currency,
                    'status': rew.status,
                    'status_display': rew.get_status_display(),
                    'earned_at': rew.earned_at.isoformat() if rew.earned_at else None,
                    'paid_at': rew.paid_at.isoformat() if rew.paid_at else None,
                    'created_at': rew.created_at.isoformat() if rew.created_at else None,
                    'transaction_reference': rew.payout.transaction_reference if rew.payout else '',
                    'payout_id': rew.payout_id,
                    'is_payable': rew.status == ExamReferralReward.STATUS_EARNED,
                })

            full_name = f"{u.first_name or ''} {u.last_name or ''}".strip()
            top_referrers.append({
                'user_id': u.id,
                'name': full_name or u.username,
                'username': u.username,
                'email': u.email,
                'total_amount': str(accrued),
                'total_paid': str(paid),
                'pending_balance': str(pending),
                'pending_count': pending_count,
                'reward_count': u_rewards.count(),
                'bank_details': bank,
                'referees': referees_list,
            })

        # Sort referrers: pending balance first, then total accrued
        top_referrers.sort(
            key=lambda x: (Decimal(x['pending_balance']), Decimal(x['total_amount'])),
            reverse=True,
        )

        return Response({
            'total_campaigns': campaigns.count(),
            'active_campaigns': campaigns.filter(is_active=True).count(),
            'total_rewards_issued': rewards.count(),
            'total_amount_accrued': str(total_accrued),
            'total_amount_paid': str(total_paid),
            'total_amount_pending': str(total_pending),
            'campaigns_breakdown': breakdown,
            'top_referrers': top_referrers,
            'recent_rewards': ExamReferralRewardSerializer(
                rewards.select_related('campaign__exam', 'referrer', 'referee')
                .order_by('-created_at')[:50],
                many=True,
                context={'include_bank_details': True},
            ).data,
        })


class AdminConfirmPayoutView(APIView):
    """POST — confirm manual payment to a referrer.

    Payload:
        user_id: int                   – the referrer being paid
        reward_ids: list[int]          – specific rewards to mark as paid
        amount: decimal                – amount actually transferred
        transaction_reference: str     – bank transfer ref / receipt
        admin_note: str (optional)
    """
    permission_classes = [IsAuthenticated, IsMasterAdmin]

    def post(self, request):
        user_id = request.data.get('user_id')
        reward_ids = request.data.get('reward_ids', [])
        tx_ref = str(request.data.get('transaction_reference', '')).strip()
        admin_note = str(request.data.get('admin_note', '')).strip()

        if not user_id:
            return Response(
                {'detail': 'user_id is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not tx_ref:
            return Response(
                {'detail': 'Transaction reference is required for record keeping.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from django.contrib.auth import get_user_model
        User = get_user_model()
        try:
            target_user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({'detail': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

        with transaction.atomic():
            # Filter strictly by STATUS_EARNED (only unpaid earned rewards can ever be settled)
            if reward_ids:
                rewards_to_update = ExamReferralReward.objects.select_for_update().filter(
                    id__in=reward_ids,
                    referrer=target_user,
                    status=ExamReferralReward.STATUS_EARNED,
                )
            else:
                rewards_to_update = ExamReferralReward.objects.select_for_update().filter(
                    referrer=target_user,
                    status=ExamReferralReward.STATUS_EARNED,
                )

            # Strict guardrail: Prevent duplicate payout confirmations completely
            if not rewards_to_update.exists():
                return Response(
                    {
                        'detail': (
                            'This referrer has no unpaid earned rewards pending payout. '
                            'All eligible rewards have already been paid or are awaiting referee unlock.'
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Calculate exact payable sum from the actual rewards being settled
            actual_payable = rewards_to_update.aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
            currency = rewards_to_update.first().currency or 'NGN'

            # Create payout record for the exact payable sum
            payout = ExamReferralPayout.objects.create(
                user=target_user,
                amount=actual_payable,
                currency=currency,
                status=ExamReferralPayout.STATUS_CONFIRMED,
                confirmed_by=request.user,
                confirmed_at=timezone.now(),
                transaction_reference=tx_ref,
                admin_note=admin_note,
            )

            # Mark rewards as PAID and permanently link to this payout record
            rewards_to_update.update(
                status=ExamReferralReward.STATUS_PAID,
                paid_at=timezone.now(),
                paid_by=request.user,
                payout=payout,
            )

        # Send inbox notification to student
        _send_payout_notification(target_user, payout, request.user)

        return Response(
            ExamReferralPayoutSerializer(payout).data,
            status=status.HTTP_201_CREATED,
        )


class AdminPayoutHistoryView(APIView):
    """GET — full history of all confirmed payouts."""
    permission_classes = [IsAuthenticated, IsMasterAdmin]

    def get(self, request):
        qs = ExamReferralPayout.objects.select_related(
            'user', 'confirmed_by',
        ).all()

        status_filter = request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        limit = min(int(request.query_params.get('limit', 200)), 500)
        return Response(ExamReferralPayoutSerializer(qs[:limit], many=True).data)


class AdminExamReferralPromoConfigView(APIView):
    """GET / PATCH — manage promotional display settings."""
    permission_classes = [IsAuthenticated, IsMasterAdmin]

    def get(self, request):
        config = ExamReferralPromoConfig.get_solo()
        return Response(ExamReferralPromoConfigSerializer(config).data)

    def patch(self, request):
        config = ExamReferralPromoConfig.get_solo()
        serializer = ExamReferralPromoConfigSerializer(
            config, data=request.data, partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


# ═══════════════════════════════════════════════════════════════════════════
#  HELPER: Award exam referral on unlock
# ═══════════════════════════════════════════════════════════════════════════

def check_exam_referral_reward(user, exam_identifier, activation_unlock=None):
    """Called after a successful exam unlock to award cash referral if applicable.

    Returns the ExamReferralReward if one was created/promoted to 'earned', else None.
    """
    from cbt.models import Exam as CBTExam

    # Resolve exam ID
    exam_obj = None
    try:
        if str(exam_identifier).isdigit():
            exam_obj = CBTExam.objects.get(id=int(exam_identifier))
        else:
            exam_obj = CBTExam.objects.get(slug=exam_identifier)
    except CBTExam.DoesNotExist:
        return None

    # Find active campaign
    campaign = ExamReferralCampaign.objects.filter(
        exam=exam_obj, is_active=True,
    ).first()
    if not campaign or not campaign.is_valid():
        return None

    # Find referral relationship
    relationship = ReferralRelationship.objects.filter(referred=user).first()
    if not relationship:
        return None

    referrer = relationship.referrer

    # Prevent self-referral
    if referrer.id == user.id:
        return None

    # Check per-referrer cap
    if campaign.max_rewards_per_referrer > 0:
        existing = ExamReferralReward.objects.filter(
            campaign=campaign, referrer=referrer,
        ).exclude(status=ExamReferralReward.STATUS_CANCELLED).count()
        if existing >= campaign.max_rewards_per_referrer:
            return None

    with transaction.atomic():
        reward, created = ExamReferralReward.objects.update_or_create(
            campaign=campaign,
            referrer=referrer,
            referee=user,
            defaults={
                'amount': campaign.cash_reward,
                'currency': campaign.currency,
                'status': ExamReferralReward.STATUS_EARNED,
                'activation_unlock': activation_unlock,
                'earned_at': timezone.now(),
            },
        )

        rewards_qs = ExamReferralReward.objects.filter(
            campaign=campaign,
            status__in=[ExamReferralReward.STATUS_EARNED, ExamReferralReward.STATUS_PAID],
        )
        campaign.total_rewards_issued = rewards_qs.count()
        campaign.total_amount_accrued = rewards_qs.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        campaign.save(update_fields=['total_rewards_issued', 'total_amount_accrued'])

    return reward


# ═══════════════════════════════════════════════════════════════════════════
#  HELPER: Send payout inbox notification
# ═══════════════════════════════════════════════════════════════════════════

def _send_payout_notification(user, payout, admin_user):
    """Create a DirectMessage in the user's inbox confirming their payout."""
    try:
        from messaging.models import DirectMessage

        ids = sorted([admin_user.id, user.id])
        DirectMessage.objects.create(
            thread_id=f"direct_{ids[0]}_{ids[1]}",
            sender=admin_user,
            recipient=user,
            message=(
                f"💰 Referral Payout Confirmed!\n\n"
                f"We've processed your referral reward payment:\n"
                f"• Amount: {payout.currency} {payout.amount:,.2f}\n"
                f"• Reference: {payout.transaction_reference or 'N/A'}\n"
                f"• Date: {payout.confirmed_at.strftime('%B %d, %Y at %I:%M %p')}\n\n"
                f"Thank you for helping us grow! Keep referring friends to earn more.\n\n"
                f"— LightHub Academy Team"
            ),
        )
    except Exception as e:
        # Log but don't crash the payout flow
        print(f"[WARN] Failed to send payout notification to {user.username}: {e}")
