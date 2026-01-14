from django.contrib import admin
from .models import ActivationFee, ActivationUnlock


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
