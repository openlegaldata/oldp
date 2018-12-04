import logging
import os
import re

from django.core.management import BaseCommand
from django.http import HttpRequest

from oldp.apps.homepage.views import *

logger = logging.getLogger(__name__)

render_dir = os.path.join(settings.ASSETS_DIR, 'html_pages')

views_to_render = {
    'error404.html': error404_view,
    'error500.html': error500_view,
    'index.html': landing_page_view,
}


class Command(BaseCommand):
    """
    pre-render html pages (for non-django content/display directly with web server/nginx)

    landing page
    error pages
        - use homepage error views

    """

    help = 'Render static html pages'

    def __init__(self):
        super(Command, self).__init__()

    def handle(self, *args, **options):

        if not os.path.isdir(render_dir):
            os.mkdir(render_dir)
            logger.error('Output directory created: %s' % render_dir)

        # Compile SASS
        css_str = ''

        # Init request
        # TODO handle locale
        request = HttpRequest()

        for file_name in views_to_render:
            view_func = views_to_render[file_name]
            view_content = view_func(request).content.decode('utf-8')

            # Write view content to file
            with open(os.path.join(render_dir, file_name), 'w') as f:
                logger.info('Writing view to: %s' % file_name)

                # Replace CSS link with string (re.sub does not work with complex replace string)
                match = re.search(r'<link rel="stylesheet" href="(.*?)">', view_content)
                if match:
                    view_content = view_content[:match.start(0)] + '<style>' + css_str + '</style>' + view_content[match.end(0):]

                f.write(view_content)

        logger.info('done')



