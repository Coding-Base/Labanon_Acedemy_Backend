from django.contrib.sitemaps import Sitemap
from .models import Blog

class BlogSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.6

    def items(self):
        return Blog.objects.filter(is_published=True)

    def lastmod(self, obj):
        return obj.published_at or obj.updated_at or obj.created_at

    def location(self, obj):
        return f"/blog/{obj.slug}/"
