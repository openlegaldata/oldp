from django.apps import AppConfig
from django.template.defaulttags import register


class CasesConfig(AppConfig):
    name = 'oldp.apps.cases'


@register.filter
def is_read_more(line_counter, forloop): # section_counter=0, content_counter=0
    LINE_COUNT = 30
    CONTENT_COUNT = 3

    # print(previous_line_length)
    content_counter = forloop['counter0']
    section_counter = 0
    if 'counter0' in forloop['parentloop']:
        section_counter = forloop['parentloop']['counter0']

    # print(forloop)
    # return not (self.get_title() == 'Leitsatz' or self.get_title() == 'Tenor')
    return (line_counter > 42 and content_counter > 3) or (line_counter > LINE_COUNT + CONTENT_COUNT)#and previous_line_length > 100

