"""내레이션 테스트 — src/text_gen/narration.py가 style을 맞게 정하고 문장 3개를 잇는지 확인한다.

검사하는 건 두 가지다.
1. spice_level(맵기 1~5)에 따라 style이 GUIDE인지 CAUTION인지 — 경계는 4 이상이면 CAUTION
2. narration_text + PRONUNCIATION + ALLERGY 세 문장이 이 순서로 이어붙는지

DB는 건드리지 않는다. cache 함수들을 patch로 가짜 값으로 바꿔치기해서 로직만 검사한다.

실행: python -m pytest tests/test_narration.py
"""

import unittest
from unittest.mock import patch

from src.db import cache
from src.text_gen import narration


class NarrationTests(unittest.TestCase):
    def test_get_narration_returns_guide_text_and_style(self):
        """맵기 3(4 미만) → GUIDE. 그리고 문장 3개가 순서대로 이어붙는지 함께 확인."""
        with (
            # patch.object = "이 함수가 불리면 진짜 대신 이 값을 돌려줘라"
            patch.object(cache, "get_food", return_value={"spice_level": 3}),
            patch.object(cache, "get_narration_text", return_value="A mild dish."),
            patch.object(
                cache,
                "get_food_details",
                return_value={"PRONUNCIATION": "Pronounced 'ay'.", "ALLERGY": "Contains egg."},
            ),
        ):
            result = narration.get_narration(1)

        # 순서가 중요하다: 내레이션 → 발음 → 알레르기
        self.assertEqual(
            result,
            {"text": "A mild dish. Pronounced 'ay'. Contains egg.", "style": "GUIDE"},
        )

    def test_get_narration_returns_caution_text_and_style(self):
        """맵기 4(경계값) → CAUTION. 이 경계가 TTS 톤(경고 목소리)을 결정한다."""
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
        """등록 안 된 음식이면 빈 문장을 만들지 말고 에러를 내야 한다 (엉뚱한 안내 방지)."""
        with patch.object(cache, "get_food", return_value=None):
            with self.assertRaisesRegex(ValueError, "foods 데이터가 없습니다"):
                narration.get_narration(999)

    def test_get_narration_raises_when_pronunciation_missing(self):
        """발음 문장이 없으면 그냥 건너뛰지 말고 에러 — 빠진 걸 조용히 넘기면 나중에 못 찾는다."""
        with (
            patch.object(cache, "get_food", return_value={"spice_level": 2}),
            patch.object(cache, "get_narration_text", return_value="A dish."),
            # ALLERGY만 있고 PRONUNCIATION이 없는 상황을 일부러 만든다
            patch.object(cache, "get_food_details", return_value={"ALLERGY": "Contains soy."}),
        ):
            with self.assertRaisesRegex(ValueError, "PRONUNCIATION가 없습니다"):
                narration.get_narration(1)

    def test_get_narration_raises_when_allergy_missing(self):
        """알레르기 문장이 없어도 마찬가지로 에러 — 안전 정보라 빠뜨리면 안 된다."""
        with (
            patch.object(cache, "get_food", return_value={"spice_level": 2}),
            patch.object(cache, "get_narration_text", return_value="A dish."),
            patch.object(cache, "get_food_details", return_value={"PRONUNCIATION": "Pronounced 'ay'."}),
        ):
            with self.assertRaisesRegex(ValueError, "ALLERGY가 없습니다"):
                narration.get_narration(1)


if __name__ == "__main__":
    unittest.main()
