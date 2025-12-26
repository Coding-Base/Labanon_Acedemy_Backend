from django.contrib import admin
from .models import Message


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'sender', 'subject', 'message_type', 'is_read', 'created_at')
    list_filter = ('message_type', 'is_read', 'created_at')
    search_fields = ('subject', 'message', 'sender__username', 'recipient__username')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Message Info', {
            'fields': ('sender', 'recipient', 'subject', 'message_type', 'message')
        }),
        ('Status', {
            'fields': ('is_read', 'is_replied')
        }),
        ('Reply', {
            'fields': ('reply_message', 'replied_at')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
