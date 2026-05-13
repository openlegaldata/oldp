"""Custom logging handlers for OLDP."""

import os
from logging.handlers import RotatingFileHandler


class ModeAwareRotatingFileHandler(RotatingFileHandler):
    """RotatingFileHandler that enforces a fixed file mode on every rollover.

    The stdlib RotatingFileHandler opens new log files with ``open(...)``, so
    the resulting permissions are ``0o666 & ~umask`` of whichever worker
    happens to create the file. Under multi-worker gunicorn this is racy:
    workers that inherit a tighter umask (e.g. 0o077) produce 0600 files,
    which then become unreadable to external log-analysis scripts and to
    non-root users on the host.

    This subclass chmods the file to a fixed mode (default 0o644) after every
    open and after every rollover, so external readers can always access the
    rotated history regardless of which worker performed the rotation.
    """

    def __init__(self, *args, file_mode: int = 0o644, **kwargs):
        self.file_mode = file_mode
        super().__init__(*args, **kwargs)
        self._ensure_mode(self.baseFilename)

    def _open(self):
        stream = super()._open()
        self._ensure_mode(self.baseFilename)
        return stream

    def doRollover(self):
        super().doRollover()
        for i in range(1, self.backupCount + 1):
            self._ensure_mode(f"{self.baseFilename}.{i}")
        self._ensure_mode(self.baseFilename)

    def _ensure_mode(self, path: str) -> None:
        try:
            os.chmod(path, self.file_mode)
        except FileNotFoundError:
            pass
        except OSError:
            pass
