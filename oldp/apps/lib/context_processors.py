from django.conf import settings
from django.urls import reverse

from oldp.apps.lib.apps import DEBUG_CONTENT


def global_context_processor(request):
    """Global template variables"""
    # print(request.user.is_authenticated())

    # if 'user' in request:
    #     user = request.user
    # else:
    #     user = None

    return {
        'title': None,  # replace with views or use title from templates
        'site_title': settings.SITE_TITLE,
        'site_domain': None,
        'site_icon': settings.SITE_ICON,
        'site_twitter_url': settings.SITE_TWITTER_URL,
        'site_github_url': settings.SITE_GITHUB_URL,
        'site_blog_url': settings.SITE_BLOG_URL,
        'canonical': '',
        'nav': '',
        'searchQuery': '',
        'api_info_url': reverse('flatpages', kwargs={'url':'/api/'}),
        # 'user': user,
        'debug': settings.DEBUG,
        'debug_content': DEBUG_CONTENT
    }
