from django.test import LiveServerTestCase


class ExtendedLiveServerTestCase(LiveServerTestCase):

    def assertStringOrder(self, response, first, second,
                          msg_fmt='Strings do not appear in correct order (first: %(first)s, %(second)s)'):
        body = str(response.content)

        pos1 = body.find(first)
        pos2 = body.find(second)

        self.assertTrue(pos1 < pos2, msg_fmt % {'first': first, 'second': second})
