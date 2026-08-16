import sys
import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import patch


# 실제 Supabase 모듈을 import하기 전에 가짜 모듈을 등록한다.
fake_supabase_module = ModuleType("src.db.supabase_client")
fake_supabase_module.client = None
sys.modules["src.db.supabase_client"] = fake_supabase_module

from src.text_gen import narration


class FakeQuery:
    def __init__(self, result):
        self.result = result

    def select(self, *_args):
        return self

    def eq(self, *_args):
        return self

    def execute(self):
        return SimpleNamespace(data=self.result)


class FakeClient:
    def __init__(self, food_result, narration_result):
        self.food_result = food_result
        self.narration_result = narration_result

    def table(self, name):
        result = self.food_result if name == "foods" else self.narration_result
        return FakeQuery(result)


class NarrationTests(unittest.TestCase):
    def test_get_narration_returns_guide_text_and_style(self):
        fake_client = FakeClient(
            [{"spice_level": 3}], [{"narration_text": "A mild dish."}]
        )
        with patch.object(narration, "client", fake_client):
            result = narration.get_narration(1)

        self.assertEqual(result, {"text": "A mild dish.", "style": "GUIDE"})

    def test_get_narration_returns_caution_text_and_style(self):
        fake_client = FakeClient(
            [{"spice_level": 4}], [{"narration_text": "It is spicy."}]
        )
        with patch.object(narration, "client", fake_client):
            result = narration.get_narration(1)

        self.assertEqual(result, {"text": "It is spicy.", "style": "CAUTION"})

    def test_get_narration_raises_for_unknown_food(self):
        with patch.object(narration, "client", FakeClient([], [])):
            with self.assertRaisesRegex(ValueError, "foods 데이터가 없습니다"):
                narration.get_narration(999)
