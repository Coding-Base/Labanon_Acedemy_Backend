# backend/materials/admin.py

from django.contrib import admin
from .models import Material, MaterialPurchase, MaterialDownload


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'area', 'topic_category', 'price', 'is_published', 
        'total_downloads', 'total_revenue', 'created_at'
    ]
    list_filter = ['is_published', 'area', 'created_at', 'file_source']
    search_fields = ['name', 'topic_category', 'creator_name', 'description']
    readonly_fields = ['id', 'total_revenue', 'created_at', 'updated_at', 'created_by']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'name', 'description', 'area', 'topic_category')
        }),
        ('Creator Details', {
            'fields': ('creator_name', 'licenses', 'created_by')
        }),
        ('File Storage', {
            'fields': ('file_source', 'file_url', 'gdrive_link', 'file_size', 'file_name')
        }),
        ('Pricing', {
            'fields': ('price', 'currency', 'total_revenue')
        }),
        ('Publication', {
            'fields': ('is_published',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if not change:  # Creating new material
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(MaterialPurchase)
class MaterialPurchaseAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'material', 'download_count', 'accessed_at', 'last_downloaded_at'
    ]
    list_filter = ['accessed_at', 'material']
    search_fields = ['user__email', 'material__name']
    readonly_fields = ['id', 'accessed_at', 'last_downloaded_at']
    
    fieldsets = (
        ('Purchase Information', {
            'fields': ('id', 'user', 'material')
        }),
        ('Access Tracking', {
            'fields': ('download_count', 'accessed_at', 'last_downloaded_at')
        }),
        ('Payment', {
            'fields': ('payment',),
            'classes': ('collapse',)
        }),
    )


@admin.register(MaterialDownload)
class MaterialDownloadAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'material', 'link_expires_at', 'is_expired', 'downloaded_at', 'created_at'
    ]
    list_filter = ['created_at', 'link_expires_at', 'material']
    search_fields = ['user__email', 'material__name', 'download_token']
    readonly_fields = ['id', 'download_token', 'created_at']
    
    fieldsets = (
        ('Download Record', {
            'fields': ('id', 'user', 'material', 'download_token')
        }),
        ('Link Expiration', {
            'fields': ('link_expires_at', 'is_expired', 'downloaded_at')
        }),
        ('User Information', {
            'fields': ('ip_address', 'user_agent'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    def is_expired(self, obj):
        return obj.is_expired
    is_expired.boolean = True
    is_expired.short_description = "Link Expired?"
