from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from django.conf import settings
from urllib.parse import urljoin


class FrontendSitemap(Sitemap):
    """
    Sitemap for frontend pages including Home and other key pages.
    These are static frontend routes that should be indexed by search engines.
    """
    changefreq = "weekly"
    priority = 0.8

    def items(self):
        """
        Define all frontend URLs that should be included in the sitemap.
        These correspond to routes defined in the Home.tsx navigation and other frontend pages.
        """
        return [
            {'name': 'home', 'priority': 1.0, 'changefreq': 'daily'},
            {'name': 'marketplace', 'priority': 0.9, 'changefreq': 'daily'},
            {'name': 'blog', 'priority': 0.8, 'changefreq': 'daily'},
            {'name': 'about', 'priority': 0.7, 'changefreq': 'monthly'},
            {'name': 'documentation', 'priority': 0.7, 'changefreq': 'weekly'},
            {'name': 'online-tutorial-for-student-application', 'priority': 0.8, 'changefreq': 'monthly'},
            {'name': 'login', 'priority': 0.6, 'changefreq': 'monthly'},
            {'name': 'register', 'priority': 0.6, 'changefreq': 'monthly'},
        ]

    def location(self, item):
        """Generate relative URL path only; domain is added by get_urls()"""
        return f"/{item['name']}/" if item['name'] != 'home' else "/"

    def lastmod(self, item):
        """Return the last modification date - not used for frontend static pages"""
        return None

    def priority(self, item):
        """Return the priority for each item"""
        return item.get('priority', self.priority)

    def changefreq(self, item):
        """Return the change frequency for each item"""
        return item.get('changefreq', self.changefreq)

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
                'changefreq': self.changefreq(item),
                'priority': self.priority(item),
            }
            urls.append(url_info)
        return urls
