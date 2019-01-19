import json
import logging
import os

import lxml.html
from lxml.cssselect import CSSSelector

logger = logging.getLogger(__name__)
RESOURCE_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'resources')

with open(os.path.join(RESOURCE_DIR, '../templates/annotations/a.html')) as f:
    print()
    html_str = f.read()

    tree = lxml.html.fromstring(html_str)
    # json_str = '{"start":{"selector":"div>p:nth-of-type(2)","textNodeIndex":0,"offset":0},"end":{"selector":"div>p:nth-of-type(2)","textNodeIndex":0,"offset":35}}'
    # json_str = '{"start":{"selector":"div>p:nth-of-type(2)","textNodeIndex":2,"offset":1},"end":{"selector":"div>p:nth-of-type(2)","textNodeIndex":2,"offset":28}}'
    json_str = '{"start":{"selector":"div>h2:nth-of-type(2)","textNodeIndex":0,"offset":4},"end":{"selector":"div>h2:nth-of-type(2)","textNodeIndex":0,"offset":10}}'
    json_str = '{"start":{"selector":"div>p:nth-of-type(2)","textNodeIndex":2,"offset":1},"end":{"selector":"div>p:nth-of-type(2)","textNodeIndex":2,"offset":6}}'
    x = json.loads(json_str)

    start = x['start']
    end = x['end']
    selected_text = None

    if start['selector'] == end['selector']:

        start_matches = CSSSelector(start['selector'])(tree)

        if len(start_matches) == 1:
            if start['textNodeIndex'] == 0 and end['textNodeIndex'] == 0:
                selected_text = start_matches[0].text[start['offset']:end['offset']]

                # replace text with {annotation}text{annotation}
            else:

                print('textNodeIndex != 0')
                start_matches = CSSSelector(start['selector'])(tree)

                for child in start_matches[0].getchildren():
                    print('Text: %s ' % child.text)
                    print('Tail: %s' % child.tail)

                    selected_text = child.tail[start['offset']:end['offset']]

        elif len(start_matches) > 1:
            raise ValueError('Multiple start matches found')
        else:
            raise ValueError('Start node does not exist')

        # for elem in :
        #     print(lxml.html.tostring(elem))
        #     print('Text: %s' % elem.text)
        #     print('Tail: %s' % elem.tail)
        #
        #     res = elem.text[x['start']]
        #
        #     print('---\nChildren')
        #
        #
        #     for c in elem.getchildren():
        #         print('Text: %s ' % c.text)
        #         print('Tail: %s' % c.tail)


    else:
        raise ValueError('start != end selector')


    print('Selected text: %s' % selected_text)

    # Processed tree -> HTML
    # Extract annotation markers with positions

    # for elem in CSSSelector(x['end']['selector'])(tree):
    #     print(lxml.html.tostring(elem))
