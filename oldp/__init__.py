try:
    import importlib.metadata

    __version__ = importlib.metadata.version("oldp")
except (importlib.metadata.PackageNotFoundError, ImportError):
    # Fallback version when package is not installed
    __version__ = "0.9.0"
#
# from configurations import importer

# # Enable django-configuration support for PyCharm
# importer.install(check_options=True)
