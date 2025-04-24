import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oldp.settings")
os.environ.setdefault("DJANGO_CONFIGURATION", "DevConfiguration")

from configurations.wsgi import get_wsgi_application

application = get_wsgi_application()
