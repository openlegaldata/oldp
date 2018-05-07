# Get an instance of a logger
import logging
import os

from PIL import Image, ImageDraw, ImageFont
from django.conf import settings
from django.core.management import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Render imprint image with values from settings'

    def __init__(self):
        super(Command, self).__init__()

    def handle(self, *args, **options):
        font_path = os.path.join(settings.BASE_DIR, 'oldp/assets/static-global/fonts/roboto-regular.ttf')
        image_path = os.path.join(settings.BASE_DIR, 'oldp/assets/static-global/images/imprint.png')
        line_height = 20

        img = Image.new('RGB', (250, line_height * 6 + 5), color=(255, 255, 255))
        d = ImageDraw.Draw(img)
        font_color = (0, 0, 0)
        font = ImageFont.truetype(font_path, 16)

        d.text((0, 0 * line_height), settings.IMPRINT_NAME, fill=font_color, font=font)
        d.text((0, 1 * line_height), settings.IMPRINT_STREET, fill=font_color, font=font)
        d.text((0, 2 * line_height), settings.IMPRINT_CITY, fill=font_color, font=font)
        d.text((0, 4 * line_height), 'Phone: ' + settings.IMPRINT_PHONE, fill=font_color, font=font)
        d.text((0, 5 * line_height), 'Email: ' + settings.IMPRINT_EMAIL, fill=font_color, font=font)

        img.save(image_path)

        logger.info('Image created: %s' % image_path)