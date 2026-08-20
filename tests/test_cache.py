import unittest
from types import SimpleNamespace
from unittest.mock import patch

from src.db import cache


class FakeQuery:
    def __init__(self, data):
        self.data = data

    def select(self, *_args):
        return self

    def execute(self):
        return SimpleNamespace(data=self.data)


class FakeClient:
    def __init__(self, tables):
        self.tables = tables
        self.call_counts = {name: 0 for name in tables}

    def table(self, name):
        self.call_counts[name] += 1
        return FakeQuery(self.tables[name])


class CacheTests(unittest.TestCase):
    def setUp(self):
        cache._cache = None
        self.tables = {
            "foods": [{"id": 1, "name_kr": "비빔밥", "name_en": "Bibimbap", "spice_level": 1}],
            "food_details": [
                {"food_id": 1, "category": "DESCRIPTION", "detail_text": "Mixed rice."},
                {"food_id": 1, "category": "ALLERGY", "detail_text": "Contains egg."},
            ],
            "food_narration": [
                {"food_id": 1, "style": "GUIDE", "narration_text": "A mild dish."}
            ],
            "menu_modifiers": [
                {"keyword": "매운", "category": "spice", "keyword_en": "spicy", "spice_tier": 3}
            ],
        }
        self.fake_client = FakeClient(self.tables)

    def test_loads_from_db_only_once(self):
        with patch.object(cache, "client", self.fake_client):
            cache.get_foods()
            cache.get_foods()
            cache.get_food_details(1)

        self.assertEqual(self.fake_client.call_counts["foods"], 1)
        self.assertEqual(self.fake_client.call_counts["food_details"], 1)

    def test_get_food_returns_matching_row(self):
        with patch.object(cache, "client", self.fake_client):
            result = cache.get_food(1)

        self.assertEqual(result["name_kr"], "비빔밥")
        self.assertEqual(result["name_en"], "Bibimbap")

    def test_get_food_returns_none_for_unknown_id(self):
        with patch.object(cache, "client", self.fake_client):
            result = cache.get_food(999)

        self.assertIsNone(result)

    def test_get_food_details_filters_by_food_id_and_category(self):
        with patch.object(cache, "client", self.fake_client):
            result = cache.get_food_details(1, categories=("ALLERGY",))

        self.assertEqual(result, {"ALLERGY": "Contains egg."})

    def test_get_narration_text_matches_food_id_and_style(self):
        with patch.object(cache, "client", self.fake_client):
            result = cache.get_narration_text(1, "GUIDE")

        self.assertEqual(result, "A mild dish.")

    def test_get_narration_text_returns_none_when_missing(self):
        with patch.object(cache, "client", self.fake_client):
            result = cache.get_narration_text(1, "CAUTION")

        self.assertIsNone(result)

    def test_get_modifiers_returns_all_rows(self):
        with patch.object(cache, "client", self.fake_client):
            result = cache.get_modifiers()

        self.assertEqual(result, self.tables["menu_modifiers"])


if __name__ == "__main__":
    unittest.main()
