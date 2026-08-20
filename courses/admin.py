from django.contrib import admin
from .models import (
    ActivationFee, ActivationUnlock, ReferralEvent, ReferralProfile,
    ReferralRelationship, ReferralSettings, ProPlan, UserSubscription, SubscriptionResetLog
)


@admin.register(ProPlan)
class ProPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'price_ngn', 'price_usd', 'billing_interval_days', 'all_exams_unlocked', 'is_active', 'order')
    list_filter = ('is_active', 'all_exams_unlocked')
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(UserSubscription)
class UserSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan', 'status', 'start_date', 'end_date', 'auto_renew', 'created_at')
    list_filter = ('status', 'auto_renew', 'plan')
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(SubscriptionResetLog)
class SubscriptionResetLogAdmin(admin.ModelAdmin):
    list_display = ('admin_user', 'exam_title', 'months_threshold', 'cutoff_date', 'affected_users_count', 'created_at')
    readonly_fields = ('created_at',)


@admin.register(ActivationFee)
class ActivationFeeAdmin(admin.ModelAdmin):
    list_display = ('type', 'exam_identifier', 'subject_id', 'currency', 'amount', 'updated_by', 'updated_at')
    list_filter = ('type', 'currency')
    search_fields = ('exam_identifier',)


@admin.register(ActivationUnlock)
class ActivationUnlockAdmin(admin.ModelAdmin):
    list_display = ('user', 'exam_identifier', 'subject_id', 'is_active', 'payment', 'activated_at', 'revoked_at')
    list_filter = ('is_active',)
    search_fields = ('user__username', 'exam_identifier')
    readonly_fields = ('activated_at',)


@admin.register(ReferralSettings)
class ReferralSettingsAdmin(admin.ModelAdmin):
    list_display = ('points_per_success', 'updated_at', 'updated_by')


@admin.register(ReferralProfile)
class ReferralProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'code', 'points_balance', 'created_at')
    search_fields = ('user__username', 'user__email', 'code')


@admin.register(ReferralRelationship)
class ReferralRelationshipAdmin(admin.ModelAdmin):
    list_display = ('referrer', 'referred', 'code_used', 'created_at')
    search_fields = ('referrer__username', 'referred__username', 'code_used')


@admin.register(ReferralEvent)
class ReferralEventAdmin(admin.ModelAdmin):
    list_display = ('event_type', 'referrer', 'referred', 'points', 'course', 'material_id', 'created_at')
    list_filter = ('event_type', 'created_at')
    search_fields = ('referrer__username', 'referred__username', 'course__title')
