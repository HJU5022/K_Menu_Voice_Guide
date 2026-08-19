import unittest
from types import SimpleNamespace
from unittest.mock import patch

from src.ocr import match


class FakeQuery:
    def __init__(self, data):
        self.data = data

    def select(self, *_args):
        return self

    def execute(self):
        return SimpleNamespace(data=self.data)


class FakeClient:
    def __init__(self, foods):
        self.foods = foods

    def table(self, name):
        data = self.foods if name == "foods" else []
        return FakeQuery(data)


class OcrMatchTests(unittest.TestCase):
    def setUp(self):
        match._modifiers_cache = None
        self.foods = [
            {"id": 1, "name_kr": "갈비"},
            {"id": 2, "name_kr": "닭갈비"},
            {"id": 3, "name_kr": "비빔밥"},
        ]

    def test_match_food_candidates_sorts_by_score_then_name_length(self):
        scores = {"갈비": 95, "닭갈비": 95, "비빔밥": 90}
        with (
            patch.object(match, "client", FakeClient(self.foods)),
            patch.object(match.fuzz, "partial_ratio", side_effect=lambda _text, name: scores[name]),
        ):
            result = match.match_food_candidates("닭갈비 비빔밥")

        self.assertEqual([candidate["name_kr"] for candidate in result], ["닭갈비", "갈비", "비빔밥"])

    def test_match_food_candidates_excludes_scores_below_threshold(self):
        with (
            patch.object(match, "client", FakeClient(self.foods)),
            patch.object(match.fuzz, "partial_ratio", return_value=69),
        ):
            result = match.match_food_candidates("닭갈비")

        self.assertEqual(result, [])

    def test_match_food_returns_highest_ranked_candidate(self):
        scores = {"갈비": 95, "닭갈비": 95, "비빔밥": 90}
        with (
            patch.object(match, "client", FakeClient(self.foods)),
            patch.object(match.fuzz, "partial_ratio", side_effect=lambda _text, name: scores[name]),
        ):
            result = match.match_food("닭갈비 비빔밥")

        self.assertEqual(result["name_kr"], "닭갈비")
