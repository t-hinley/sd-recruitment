from django.contrib.sitemaps import Sitemap
from django.urls import reverse


class StaticViewSitemap(Sitemap):
    changefreq = "monthly"

    def items(self):
        return ["core:home", "core:employers", "core:candidates", "core:about", "core:contact", "core:privacy"]

    def priority(self, item):
        return {"core:home": 1.0, "core:privacy": 0.3}.get(item, 0.8)

    def location(self, item):
        return reverse(item)
