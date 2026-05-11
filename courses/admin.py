from django.contrib import admin
from .models import (
    ActivationFee, ActivationUnlock, ReferralEvent, ReferralProfile,
    ReferralRelationship, ReferralSettings
)


@admin.register(ActivationFee)
class ActivationFeeAdmin(admin.ModelAdmin):
    list_display = ('type', 'exam_identifier', 'subject_id', 'currency', 'amount', 'updated_by', 'updated_at')
    list_filter = ('type', 'currency')
    search_fields = ('exam_identifier',)


@admin.register(ActivationUnlock)
class ActivationUnlockAdmin(admin.ModelAdmin):
    list_display = ('user', 'exam_identifier', 'subject_id', 'payment', 'activated_at')
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
