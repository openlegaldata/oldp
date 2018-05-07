import re

from bs4 import BeautifulSoup
from markdown import Extension
from markdown.postprocessors import Postprocessor
from markdown.preprocessors import Preprocessor

TABLE_CLASS = 'table table-lines'
TR_CLASS = 'line'
TD_LINE_NUMBER_CLASS = 'line-number'
TD_LINE_CONTENT_CLASS = 'line-content'

PLACEHOLDER_BEGIN = '{{{{{'
PLACEHOLDER_END = '}}}}}'


class LineNumberExtension(Extension):
    """Line number extension.

    Usage:

    output = markdown.markdown(text_legal_md, extensions=[
        'legal_md.extensions.line_numbers',
        'markdown.extensions.tables',
        'markdown.extensions.footnotes'
    ])

    Example:
    ```
    ## Some heading without line number

    1| Some paragraph with text and line number.

    2| Another paragraph, number two, but

    :| the line number continues in a second paragraph

    Other content without line numbers...
    ```

    """
    table_class = TABLE_CLASS
    tr_class = TR_CLASS
    td_line_number_class = TD_LINE_NUMBER_CLASS
    td_line_content_class = TD_LINE_CONTENT_CLASS

    def __init__(self, *args, **kwargs):
        """Initialize."""

        super(LineNumberExtension, self).__init__(*args, **kwargs)

    def extendMarkdown(self, md, md_globals):
        """Register the extension."""

        md.registerExtension(self)

        md.preprocessors.add('legal_pre', LineNumberPreprocessor(), '<normalize_whitespace')  # '_begin') html_blocks
        md.postprocessors.add('legal_post', LineNumberPostprocessor(self.table_class,
                                                                    self.tr_class,
                                                                    self.td_line_number_class,
                                                                    self.td_line_content_class),
                              '>raw_html')  # >raw_html


class LineNumberPostprocessor(Postprocessor):
    """Handle cleanup on post process for viewing critic marks."""
    table_class = TABLE_CLASS
    tr_class = TR_CLASS
    td_line_number_class = TD_LINE_NUMBER_CLASS
    td_line_content_class = TD_LINE_CONTENT_CLASS
    link_line_number = True

    def __init__(self, table_class, tr_class, td_line_number_class, td_line_content_class):
        """Initialize."""
        super(LineNumberPostprocessor, self).__init__()

        self.table_class = table_class
        self.tr_class = tr_class
        self.td_line_content_class = td_line_content_class
        self.td_line_number_class = td_line_number_class

    def run(self, text):
        """Replace line number placeholders."""

        out_lines = []
        last_with_line_no = False
        last_line_no = 0
        lines = text.split('\n')
        for i, line in enumerate(lines):
            is_last_line = i == len(lines) - 1

            # print('POST: %s' % line)

            pattern = r'' + re.escape(PLACEHOLDER_BEGIN) + '([0-9]+|:|#)' + re.escape(PLACEHOLDER_END)
            match = re.search(pattern, line)

            if match:  # Placeholder found
                line_no = match.group(1)
                line_content = line[:match.start(0)] + line[match.end(0):]

                # Close all html-tags
                line_content = BeautifulSoup(line_content, 'html.parser').prettify()

                # print('>> %s' % match.group(1))
                # print('>> %s' % match.group(2))
                # print('>> %s' % line_content)

                if line_no == ':':  # no line number
                    line_label = ''
                    line_no = last_line_no
                else:
                    # with line number
                    if line_no == '#':  # auto line numbers
                        line_no = int(last_line_no) + 1
                    line_label = line_no
                    last_line_no = line_no

                if self.link_line_number and line_label != '':
                    # Make line labels clickable
                    line_label = '<a href="#L' + str(line_no) + '">' + str(line_label) + '</a>'

                # Build table row
                line = ('<tr class="' + self.tr_class + '" data-line="%(no)s"><td class="'
                        + self.td_line_number_class + '">%(label)s</td><td class="'
                        + self.td_line_content_class + '">%(content)s') % (
                           {'no': line_no, 'label': line_label, 'content': line_content})

                # Open table-tag if last line was not with line number
                if not last_with_line_no:
                    line = '<table class="' + self.table_class + '">\n' + line

                # last_with_line_no = True

            match_close = re.search(r'' + re.escape(PLACEHOLDER_BEGIN) + '/' + re.escape(PLACEHOLDER_END), line)

            if match_close:
                # Close line
                # print('>> FOUND CLOSE')
                last_with_line_no = True
                line = line[:match_close.start(0)] + line[match_close.end(0):] + '</td></tr>'

            # Close table-tag (when this one is without line-number but previous was, or last line)
            if (not match_close and last_with_line_no) \
                    or (match and i >= len(lines)):
                line = '</table>\n' + line

            if match and is_last_line:
                line = line + '\n</table>'

            if not match_close:
                last_with_line_no = False

            out_lines.append(line)

        return '\n'.join(out_lines)


class LineNumberPreprocessor(Preprocessor):
    """Handle viewing critic marks in Markdown content."""

    def __init__(self):
        """Initialize."""

        super(LineNumberPreprocessor, self).__init__()

    def run(self, lines):
        pattern = r'^([0-9]+|#|:)\|\s(.*)$'
        ln_marker_close = PLACEHOLDER_BEGIN + '/' + PLACEHOLDER_END
        ln_with_marker = []  # store index of lines with number

        for i, line in enumerate(lines):
            match = re.search(pattern, line)

            if match:  # If line marker found
                line_content = match.group(2)
                ln_marker = PLACEHOLDER_BEGIN + match.group(1) + PLACEHOLDER_END

                # Write marker at the end of line
                lines[i] = line_content + ln_marker + ln_marker_close
                ln_with_marker.append(i)

        # print('\n'.join(lines) + '\n-------------------')

        return lines

    def _run(self, lines):
        """Process line number marks."""

        # Find and process critic marks
        # text = '\n'.join(lines)
        out_lines = []
        pattern = r'^([0-9]+|#|:)\|\s(.*)$'
        found_ln_marker = False
        ln_marker_close = None

        for i, l in enumerate(lines):
            is_last_line = i == len(lines) - 1
            # print('PRE: %s' % l)
            match = re.search(pattern, l)
            if match:
                # print('found LN')
                line_content = match.group(2)
                ln_marker = PLACEHOLDER_BEGIN + match.group(1) + PLACEHOLDER_END
                ln_marker_close = PLACEHOLDER_BEGIN + '/' + PLACEHOLDER_END

                if is_last_line:
                    # last line, set closing marker
                    l = line_content + ln_marker + ln_marker_close
                    ln_marker_close = None
                else:
                    # not last line
                    if lines[i + 1].strip() == '':
                        # next line is empty
                        l = line_content + ln_marker + ln_marker_close
                        ln_marker_close = None
                    else:
                        # next line is not empty, write marker to end of the line which next lines is empty
                        l = line_content + ln_marker
                        pass
                    pass
            else:
                if ln_marker_close is not None:
                    if is_last_line:
                        # Set close marker if is last line
                        l = l + ln_marker_close
                        ln_marker_close = None
                    else:
                        # Set close marker if next line is empty
                        if lines[i + 1].strip() == '':
                            l = l + ln_marker_close
                            ln_marker_close = None
                        else:
                            pass

            out_lines.append(l)

        return out_lines


def makeExtension(**kwargs):  # pragma: no cover
    return LineNumberExtension(**kwargs)
