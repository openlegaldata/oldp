import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)


class BaseMarker(object):
    def get_start_position(self) -> int:
        raise NotImplementedError()

    def get_end_position(self) -> int:
        raise NotImplementedError()

    def get_marker_open_format(self) -> str:
        """Format of opening tag, e.g. [ref={uuid}]. Available placeholders: all marker class attributes.

        :return: format string
        """
        raise NotImplementedError()

    def get_marker_close_format(self) -> str:
        """Format of opening tag, e.g. [/ref]. Available placeholders: all marker class attributes.

        :return: format string
        """
        raise NotImplementedError()

    def get_marker_open(self):
        return self.get_marker_open_format().format(**self.__dict__)

    def get_marker_close(self):
        return self.get_marker_close_format().format(**self.__dict__)

    def insert_marker(self, content, marker_offset) -> Tuple[str, int]:
        """
        Replace the original content with markers, e.g. [ref]xy[/ref].

        :param content: Original content
        :param marker_offset: Offset from previous markers
        :return: Content with markers
        """
        start = self.get_start_position() + marker_offset
        end = self.get_end_position() + marker_offset

        # marker_open = '[ref=%i]' % key
        # Instead of key use uuid
        marker_open = self.get_marker_open()
        marker_close = self.get_marker_close()

        marker_offset += len(marker_open) + len(marker_close)

        # double replacements
        # alternative: content[start:end]
        content = content[:start] \
                  + marker_open \
                  + content[start:end] \
                  + marker_close \
                  + content[end:]

        return content, marker_offset


def insert_markers(content: str, markers: List[BaseMarker]):
    """
    Insert markers into content

    :param content: Without markers
    :param markers:
    :return:
    """
    marker_offset = 0
    content_with_markers = content
    sorted_markers = sorted(markers, key=lambda k: k.get_start_position())  # order by occurrence in text

    for i, marker in enumerate(sorted_markers):
        # Check on overlaps
        if i > 0 and sorted_markers[i - 1].get_end_position() >= marker.get_start_position():
            logger.error('Marker overlaps with previous marker: %s' % marker)
        elif i + 1 < len(sorted_markers) and sorted_markers[i + 1].get_start_position() <= marker.get_end_position():
            logger.error('Marker overlaps with next marker: %s' % marker)
        else:
            # Everything fine, replace content
            content_with_markers, marker_offset = marker.insert_marker(content_with_markers, marker_offset)

    return content_with_markers
