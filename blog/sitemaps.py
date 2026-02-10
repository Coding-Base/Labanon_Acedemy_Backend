from django.contrib.sitemaps import Sitemap
from django.conf import settings
from .models import Blog

class BlogSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.6

    def items(self):
        return Blog.objects.filter(is_published=True)

    def lastmod(self, obj):
        return obj.published_at or obj.updated_at or obj.created_at

    def location(self, obj):
        """Generate absolute URL for blog post with the frontend domain"""
        frontend_url = getattr(settings, 'FRONTEND_URL', 'https://lighthubacademy.org').rstrip('/')
        return f"{frontend_url}/blog/{obj.slug}/"
