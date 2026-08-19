import unittest
from unittest.mock import patch

from src.db import cache
from src.text_gen import narration


class NarrationTests(unittest.TestCase):
    def test_get_narration_returns_guide_text_and_style(self):
        with (
            patch.object(cache, "get_food", return_value={"spice_level": 3}),
            patch.object(cache, "get_narration_text", return_value="A mild dish."),
            patch.object(
                cache,
                "get_food_details",
                return_value={"PRONUNCIATION": "Pronounced 'ay'.", "ALLERGY": "Contains egg."},
            ),
        ):
            result = narration.get_narration(1)

        self.assertEqual(
            result,
            {"text": "A mild dish. Pronounced 'ay'. Contains egg.", "style": "GUIDE"},
        )

    def test_get_narration_returns_caution_text_and_style(self):
        with (
            patch.object(cache, "get_food", return_value={"spice_level": 4}),
            patch.object(cache, "get_narration_text", return_value="It is spicy."),
            patch.object(
                cache,
                "get_food_details",
                return_value={"PRONUNCIATION": "Pronounced 'ay'.", "ALLERGY": "Contains egg."},
            ),
        ):
            result = narration.get_narration(1)

        self.assertEqual(
            result,
            {"text": "It is spicy. Pronounced 'ay'. Contains egg.", "style": "CAUTION"},
        )

    def test_get_narration_raises_for_unknown_food(self):
        with patch.object(cache, "get_food", return_value=None):
            with self.assertRaisesRegex(ValueError, "foods 데이터가 없습니다"):
                narration.get_narration(999)

    def test_get_narration_raises_when_pronunciation_missing(self):
        with (
            patch.object(cache, "get_food", return_value={"spice_level": 2}),
            patch.object(cache, "get_narration_text", return_value="A dish."),
            patch.object(cache, "get_food_details", return_value={"ALLERGY": "Contains soy."}),
        ):
            with self.assertRaisesRegex(ValueError, "PRONUNCIATION가 없습니다"):
                narration.get_narration(1)

    def test_get_narration_raises_when_allergy_missing(self):
        with (
            patch.object(cache, "get_food", return_value={"spice_level": 2}),
            patch.object(cache, "get_narration_text", return_value="A dish."),
            patch.object(cache, "get_food_details", return_value={"PRONUNCIATION": "Pronounced 'ay'."}),
        ):
            with self.assertRaisesRegex(ValueError, "ALLERGY가 없습니다"):
                narration.get_narration(1)


if __name__ == "__main__":
    unittest.main()
