from django.test import TestCase

import oldp.apps.nlp.regexps as regex


class BaseTestCase:

    class RegEx(TestCase):
        def assert_match_all(self, strings, r):
            for string in strings:
                self.assertTrue(r.match(string))

        def assert_match_none(self, strings, r):
            for string in strings:
                self.assertFalse(r.match(string))


class EuroAmountTestCase(BaseTestCase.RegEx):

    def test_euro_amounts(self):
        euros = ['1€', '1000000€', '3.000€', '3.000.000 €', '999,99€', '100 Euro', '1,20Euro']
        self.assert_match_all(euros, regex.euro_amount())

    def test_non_euro_amounts(self):
        not_euros = ['€1', '10$', '30.00€', '100,000€', 'Euro', 'Euro 1000']
        self.assert_match_none(not_euros, regex.euro_amount())
