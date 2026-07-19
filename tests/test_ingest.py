import unittest

from src.ingest import build_request_params


class IngestTests(unittest.TestCase):
    def test_build_request_params_uses_supplied_values(self):
        params = build_request_params(
            app_id="abc123",
            app_key="xyz789",
            what="data engineer",
            where="London",
            results_per_page=25,
            page=2,
        )

        self.assertEqual(params["app_id"], "abc123")
        self.assertEqual(params["app_key"], "xyz789")
        self.assertEqual(params["what"], "data engineer")
        self.assertEqual(params["where"], "London")
        self.assertEqual(params["results_per_page"], 25)
        self.assertEqual(params["page"], 2)

    def test_build_request_params_uses_defaults(self):
        params = build_request_params(app_id="abc123", app_key="xyz789")

        self.assertEqual(params["results_per_page"], 20)
        self.assertEqual(params["page"], 1)
        self.assertEqual(params["country"], "gb")
