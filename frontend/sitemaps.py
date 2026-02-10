from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from django.conf import settings


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
            {'name': 'tutor-application', 'priority': 0.8, 'changefreq': 'monthly'},
            {'name': 'login', 'priority': 0.6, 'changefreq': 'monthly'},
            {'name': 'register', 'priority': 0.6, 'changefreq': 'monthly'},
        ]

    def location(self, item):
        """Generate absolute URL for each item with the frontend domain"""
        frontend_url = getattr(settings, 'FRONTEND_URL', 'https://lighthubacademy.org').rstrip('/')
        path = f"/{item['name']}/" if item['name'] != 'home' else "/"
        return f"{frontend_url}{path}"

    def lastmod(self, item):
        """Return the last modification date - not used for frontend static pages"""
        return None

    def priority(self, item):
        """Return the priority for each item"""
        return item.get('priority', self.priority)

    def changefreq(self, item):
        """Return the change frequency for each item"""
        return item.get('changefreq', self.changefreq)
