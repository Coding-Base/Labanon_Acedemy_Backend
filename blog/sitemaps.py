from django.contrib.sitemaps import Sitemap
from django.conf import settings
from urllib.parse import urljoin
from .models import Blog

class BlogSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.6

    def items(self):
        return Blog.objects.filter(is_published=True)

    def lastmod(self, obj):
        return obj.published_at or obj.updated_at or obj.created_at

    def location(self, obj):
        """Generate relative URL path only; domain is added by get_urls()"""
        return f"/blog/{obj.slug}/"

    def get_urls(self, page=1, site=None, protocol=None):
        """Override to use frontend domain instead of Django Sites framework"""
        frontend_url = getattr(settings, 'FRONTEND_URL', 'https://lighthubacademy.org').rstrip('/')
        urls = []
        for item in self.paginator.page(page).object_list:
            loc = urljoin(frontend_url + '/', self.location(item).lstrip('/'))
            url_info = {
                'item': item,
                'location': loc,
                'lastmod': self.lastmod(item),
                'changefreq': self.changefreq,
                'priority': self.priority,
            }
            urls.append(url_info)
        return urls
