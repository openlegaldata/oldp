import logging.config
import os
import re

from django.conf import settings

logger = logging.getLogger(__name__)


@DeprecationWarning
class Logger(object):
    logger = logging.getLogger()

    def __init__(self):
        super(Logger, self).__init__()

        # Logging settings
        # TODO Update path
        # os.path.dirname(
        logging.config.fileConfig(os.path.join(settings.BASE_DIR, 'utils', 'logging.conf'))


def find_from_mapping(haystack, mapping, mapping_list=False, default=None):
    """
    Finds a word based on mapping, e.g. court code search:

    Verwaltungsgericht -> VG

    :param self:
    :param haystack:
    :param mapping:
    :param mapping_list:
    :param default:
    :return:
    """
    for needle in mapping:
        # print(needle)
        if re.search(r'\b' + re.escape(needle) + r'\b', haystack, flags=re.IGNORECASE):
            if mapping_list:
                return needle
            else:
                return mapping[needle]
    return default


def get_log_level_from_env(env_var: str='OLDP_LOG', default_level: str='info') -> int:
    """
    Read logging level from environment variable.

    :param env_var: Name of env variable
    :param default_level: Default log level (default|info|warning|error)
    :return: Log level (from logging package)
    """
    if env_var in os.environ:
        log_level_str = os.environ[env_var]
    else:
        log_level_str = default_level

    if log_level_str == 'info':
        log_level = logging.INFO
    elif log_level_str == 'warning':
        log_level = logging.WARNING
    elif log_level_str == 'error':
        log_level = logging.ERROR
    elif log_level_str == 'debug':
        log_level = logging.DEBUG
    else:
        log_level = logging.DEBUG

    return log_level
