import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oldp.settings")
os.environ.setdefault("DJANGO_CONFIGURATION", "DevConfiguration")

from configurations.asgi import get_asgi_application

application = get_asgi_application()
