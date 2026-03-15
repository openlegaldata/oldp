from django.test import LiveServerTestCase


class APIViewsTestCase(LiveServerTestCase):
    fixtures = ["laws/laws.json"]

    def test_index(self):
        res = self.client.get("/api/")
        self.assertEqual(res.status_code, 200, "Invalid status code returned")

    def test_index_laws(self):
        res = self.client.get("/api/laws/")
        self.assertEqual(res.status_code, 200, "Invalid status code returned")

    def test_schema(self):
        res = self.client.get("/api/schema/")

        self.assertEqual(res.status_code, 200, "Invalid status code returned")

    def test_index_cases_without_text_returns_400(self):
        res = self.client.get("/api/cases/search/")
        self.assertEqual(res.status_code, 400, "Missing text param should return 400")

    def test_index_cases_with_text(self):
        res = self.client.get("/api/cases/search/", {"text": "test"})
        self.assertEqual(res.status_code, 200, "Invalid status code returned")
