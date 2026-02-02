from django.contrib.sitemaps import Sitemap
from django.urls import reverse


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
        """Generate the URL for each item"""
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
