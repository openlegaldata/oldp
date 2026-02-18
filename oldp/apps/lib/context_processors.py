from django.conf import settings
from django.urls import reverse

from oldp.apps.lib.apps import DEBUG_CONTENT
from oldp.utils.version import get_version


def global_context_processor(request):
    """Global template variables"""
    # print(request.user.is_authenticated())

    # if 'user' in request:
    #     user = request.user
    # else:
    #     user = None

    return {
        "title": None,  # replace with views or use title from templates
        "site_title": settings.SITE_TITLE,
        "site_domain": None,
        "site_icon": settings.SITE_ICON,
        "site_twitter_url": settings.SITE_TWITTER_URL,
        "site_github_url": settings.SITE_GITHUB_URL,
        "site_blog_url": settings.SITE_BLOG_URL,
        "site_linkedin_url": settings.SITE_LINKEDIN_URL,
        "site_discord_url": settings.SITE_DISCORD_URL,
        "site_api_docs_url": settings.SITE_API_DOCS_URL,
        "canonical": "",
        "nav": "",
        "searchQuery": "",
        "api_info_url": reverse("flatpages", kwargs={"url": "/api/"}),
        # 'user': user,
        "debug": settings.DEBUG,
        "debug_content": DEBUG_CONTENT,
        "app_version": get_version(),
    }
