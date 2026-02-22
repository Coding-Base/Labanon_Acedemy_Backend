from django.contrib import admin
from .models import PromoCode


@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    list_display = ('code', 'amount', 'is_percentage', 'uses', 'max_uses', 'expires_at', 'active', 'created_by', 'created_at')
    list_filter = ('is_percentage', 'active', 'expires_at')
    search_fields = ('code', 'created_by__username')
