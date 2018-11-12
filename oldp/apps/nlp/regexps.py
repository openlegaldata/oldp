import re


class RegEx:
    """
    Shadows the regexp object returned by re.compile.
    """

    def __init__(self, exp):
        self.exp = exp

    def add_alternative(self, alt):
        self.exp += '|' + alt

    def compile(self):
        return re.compile(self.exp)

    def finditer(self, string):
        return self.compile().finditer(string)

    def match(self, string):
        return self.compile().match(string)


def euro_amount():
    return RegEx(r'(([1-9]{1}[0-9]{0,2})*(\.\d{3})+|\d+)(\,\d{2})?( )?(\€|Euro)')
