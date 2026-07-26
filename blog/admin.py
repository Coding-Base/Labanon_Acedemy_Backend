from django.contrib import admin
from .models import Blog, BlogAd


@admin.register(Blog)
class BlogAdmin(admin.ModelAdmin):
    list_display = ['title', 'author', 'is_published', 'is_featured', 'is_trending', 'is_popular', 'created_at', 'published_at']
    list_filter = ['is_published', 'is_featured', 'is_trending', 'is_popular', 'created_at']
    search_fields = ['title', 'content', 'meta_title', 'meta_description']
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        (None, {
            'fields': ('title', 'slug', 'author', 'content', 'excerpt', 'image', 'is_published', 'is_featured', 'is_trending', 'is_popular')
        }),
        ('SEO / Metadata', {
            'classes': ('collapse',),
            'fields': ('meta_title', 'meta_description', 'meta_keywords')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'published_at')
        })
    )


@admin.register(BlogAd)
class BlogAdAdmin(admin.ModelAdmin):
    list_display = ['title', 'badge_text', 'button_text', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['title', 'description', 'badge_text']
    readonly_fields = ['created_at', 'updated_at']

