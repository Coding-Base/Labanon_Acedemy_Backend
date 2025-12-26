from django.contrib import admin
from .models import SubAdmin


@admin.register(SubAdmin)
class SubAdminAdmin(admin.ModelAdmin):
    list_display = ['user', 'created_by', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['user__username', 'user__email']
    fieldsets = (
        ('User', {'fields': ('user', 'created_by', 'is_active')}),
        ('Permissions', {
            'fields': ('can_manage_users', 'can_manage_institutions', 'can_manage_courses', 
                      'can_manage_cbt', 'can_view_payments', 'can_manage_blog', 'can_manage_subadmins')
        }),
        ('Dates', {'fields': ('created_at', 'updated_at')}),
    )
    readonly_fields = ['created_at', 'updated_at']
