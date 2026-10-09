"""Serializers for the Exam Referral Cash Reward system."""
from rest_framework import serializers
from .models import (
    BankAccount, ExamReferralCampaign, ExamReferralReward,
    ExamReferralPayout, ExamReferralPromoConfig,
)


def _user_display_name(user):
    if not user:
        return None
    full = f"{user.first_name or ''} {user.last_name or ''}".strip()
    return full or user.username or user.email


# ---------------------------------------------------------------------------
# Bank Account
# ---------------------------------------------------------------------------

class BankAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankAccount
        fields = [
            'id', 'bank_name', 'bank_code', 'account_number',
            'account_name', 'is_verified', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'is_verified', 'created_at', 'updated_at']


# ---------------------------------------------------------------------------
# Campaign
# ---------------------------------------------------------------------------

class ExamReferralCampaignSerializer(serializers.ModelSerializer):
    exam_title = serializers.CharField(source='exam.title', read_only=True)
    exam_slug = serializers.CharField(source='exam.slug', read_only=True)
    exam_id = serializers.IntegerField(source='exam.id', read_only=True)
    is_valid = serializers.SerializerMethodField()
    total_rewards_issued = serializers.SerializerMethodField()
    total_amount_accrued = serializers.SerializerMethodField()

    class Meta:
        model = ExamReferralCampaign
        fields = [
            'id', 'exam', 'exam_id', 'exam_title', 'exam_slug',
            'cash_reward', 'currency', 'is_active', 'is_valid',
            'payout_date', 'payout_day', 'payout_note',
            'start_date', 'end_date',
            'max_rewards_per_referrer', 'max_total_rewards',
            'total_rewards_issued', 'total_amount_accrued',
            'created_by', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'total_rewards_issued', 'total_amount_accrued',
            'created_by', 'created_at', 'updated_at',
        ]

    def get_is_valid(self, obj):
        return obj.is_valid()

    def get_total_rewards_issued(self, obj):
        return obj.rewards.filter(
            status__in=[ExamReferralReward.STATUS_EARNED, ExamReferralReward.STATUS_PAID]
        ).count()

    def get_total_amount_accrued(self, obj):
        from django.db.models import Sum
        val = obj.rewards.filter(
            status__in=[ExamReferralReward.STATUS_EARNED, ExamReferralReward.STATUS_PAID]
        ).aggregate(s=Sum('amount'))['s']
        return str(val or '0.00')


class ExamReferralCampaignCreateSerializer(serializers.ModelSerializer):
    """Thin serializer used when creating / updating campaigns."""
    class Meta:
        model = ExamReferralCampaign
        fields = [
            'exam', 'cash_reward', 'currency', 'is_active',
            'payout_date', 'payout_day', 'payout_note',
            'start_date', 'end_date',
            'max_rewards_per_referrer', 'max_total_rewards',
        ]


# ---------------------------------------------------------------------------
# Reward
# ---------------------------------------------------------------------------

class ExamReferralRewardSerializer(serializers.ModelSerializer):
    referrer_name = serializers.SerializerMethodField()
    referrer_email = serializers.EmailField(source='referrer.email', read_only=True)
    referee_name = serializers.SerializerMethodField()
    referee_email = serializers.EmailField(source='referee.email', read_only=True)
    exam_title = serializers.CharField(source='campaign.exam.title', read_only=True)
    campaign_id = serializers.IntegerField(source='campaign.id', read_only=True)
    bank_details = serializers.SerializerMethodField()

    class Meta:
        model = ExamReferralReward
        fields = [
            'id', 'campaign', 'campaign_id', 'exam_title',
            'referrer', 'referrer_name', 'referrer_email',
            'referee', 'referee_name', 'referee_email',
            'amount', 'currency', 'status',
            'activation_unlock', 'earned_at', 'paid_at', 'paid_by',
            'payout', 'created_at', 'updated_at',
            'bank_details',
        ]

    def get_referrer_name(self, obj):
        return _user_display_name(obj.referrer)

    def get_referee_name(self, obj):
        return _user_display_name(obj.referee)

    def get_bank_details(self, obj):
        """Only included when the serializer context has include_bank_details=True (admin views)."""
        if not self.context.get('include_bank_details'):
            return None
        try:
            ba = obj.referrer.bank_account
            return BankAccountSerializer(ba).data
        except BankAccount.DoesNotExist:
            return None


# ---------------------------------------------------------------------------
# Payout
# ---------------------------------------------------------------------------

class ExamReferralPayoutSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    user_email = serializers.EmailField(source='user.email', read_only=True)
    confirmed_by_name = serializers.SerializerMethodField()
    reward_ids = serializers.SerializerMethodField()

    class Meta:
        model = ExamReferralPayout
        fields = [
            'id', 'user', 'user_name', 'user_email',
            'amount', 'currency', 'status',
            'confirmed_by', 'confirmed_by_name', 'confirmed_at',
            'transaction_reference', 'admin_note',
            'reward_ids',
            'created_at', 'updated_at',
        ]

    def get_user_name(self, obj):
        return _user_display_name(obj.user)

    def get_confirmed_by_name(self, obj):
        return _user_display_name(obj.confirmed_by)

    def get_reward_ids(self, obj):
        return list(obj.rewards.values_list('id', flat=True))


# ---------------------------------------------------------------------------
# Promo Config
# ---------------------------------------------------------------------------

class ExamReferralPromoConfigSerializer(serializers.ModelSerializer):
    max_cash_reward = serializers.SerializerMethodField()
    active_campaigns_count = serializers.SerializerMethodField()
    featured_exam = serializers.SerializerMethodField()

    class Meta:
        model = ExamReferralPromoConfig
        fields = [
            'show_homepage_banner', 'show_dashboard_banner', 'show_popup_modal',
            'popup_frequency_hours',
            'banner_title', 'banner_description', 'banner_cta_text',
            'is_active', 'updated_at',
            'max_cash_reward', 'active_campaigns_count', 'featured_exam',
        ]
        read_only_fields = ['updated_at', 'max_cash_reward', 'active_campaigns_count', 'featured_exam']

    def get_max_cash_reward(self, obj):
        from courses.models import ExamReferralCampaign
        from django.db.models import Max
        val = ExamReferralCampaign.objects.filter(is_active=True).aggregate(m=Max('cash_reward'))['m']
        return str(val or '1000.00')

    def get_active_campaigns_count(self, obj):
        from courses.models import ExamReferralCampaign
        return ExamReferralCampaign.objects.filter(is_active=True).count()

    def get_featured_exam(self, obj):
        from courses.models import ExamReferralCampaign
        c = ExamReferralCampaign.objects.filter(is_active=True).order_by('-cash_reward').first()
        return c.exam.title if c and c.exam else 'CBT Exams'

