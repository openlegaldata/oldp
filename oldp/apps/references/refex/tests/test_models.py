from unittest import TestCase

from oldp.apps.references.refex.models import Ref, RefType


class RefExTest(TestCase):
    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_init(self):
        a = Ref(ref_type=RefType.LAW, book='foo')
        print(a)
