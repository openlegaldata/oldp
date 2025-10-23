"""Version utilities for OLDP package."""

import importlib.metadata


def get_version() -> str:
    """Get the version of the oldp package dynamically.

    This function tries multiple methods to get the version:
    1. From package metadata (works when installed)
    2. From oldp.__version__ (fallback)

    Returns:
        str: The version string of the oldp package

    Raises:
        RuntimeError: If version cannot be determined
    """
    try:
        # Try to get version from installed package metadata
        return importlib.metadata.version("oldp")
    except importlib.metadata.PackageNotFoundError:
        # Fallback to __version__ in __init__.py
        try:
            from oldp import __version__

            return __version__
        except ImportError:
            raise RuntimeError("Could not determine oldp package version")


def get_version_info() -> dict:
    """Get detailed version information.

    Returns:
        dict: Dictionary containing version and metadata
    """
    version = get_version()

    try:
        metadata = importlib.metadata.metadata("oldp")
        return {
            "version": version,
            "name": metadata.get("Name", "oldp"),
            "summary": metadata.get("Summary", ""),
            "author": metadata.get("Author", ""),
            "license": metadata.get("License", ""),
        }
    except importlib.metadata.PackageNotFoundError:
        return {
            "version": version,
            "name": "oldp",
            "summary": "Open Legal Data Platform",
            "author": "Malte Ostendorff",
            "license": "MIT",
        }
