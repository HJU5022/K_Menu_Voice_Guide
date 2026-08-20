"""매칭 테스트 — src/ocr/match.py가 OCR 글자를 등록 음식 50개 중 맞는 것으로 이어주는지 확인한다.

OCR은 글자를 조금씩 틀리게 읽는다. 그래서 정확히 일치하는 이름을 찾는 게 아니라
RapidFuzz로 "얼마나 비슷한가"를 0~100점으로 재서 가장 비슷한 음식을 고른다.

여기서 검사하는 세 가지:
1. 점수가 같으면 **긴 이름을 먼저** 놓는가 — "닭갈비"를 "갈비"로 잘못 고르면 안 되기 때문
2. 점수가 기준(70점)에 못 미치면 후보에서 빼는가 — 엉뚱한 음식을 추천하지 않기 위해
3. match_food()가 그 정렬된 목록의 1등을 돌려주는가

RapidFuzz의 점수 계산 자체는 검증 대상이 아니므로(외부 라이브러리) patch로 원하는
점수를 직접 심어서, **정렬·필터 로직만** 검사한다.

실행: python -m pytest tests/test_ocr_match.py
"""

import unittest
from unittest.mock import patch

from src.db import cache
from src.ocr import match


class OcrMatchTests(unittest.TestCase):
    def setUp(self):
        """등록 음식 50개 대신 3개짜리 축소판을 쓴다 — "갈비"와 "닭갈비"가 핵심 조합이다."""
        self.foods = [
            {"id": 1, "name_kr": "갈비", "name_en": "Galbi"},
            {"id": 2, "name_kr": "닭갈비", "name_en": "Dakgalbi"},
            {"id": 3, "name_kr": "비빔밥", "name_en": "Bibimbap"},
        ]

    def test_match_food_candidates_sorts_by_score_then_name_length(self):
        """점수가 같으면 긴 이름이 먼저 온다 — "닭갈비"가 "갈비"보다 위에 있어야 한다.

        왜 필요한가: "닭갈비"라는 글자 안에는 "갈비"도 들어있어서 둘 다 만점(95)이 나온다.
        길이로 한 번 더 정렬하지 않으면 더 짧고 덜 구체적인 "갈비"가 1등이 될 수 있다.
        """
        # side_effect로 음식 이름마다 원하는 점수를 직접 지정한다 (갈비·닭갈비 동점 상황)
        scores = {"갈비": 95, "닭갈비": 95, "비빔밥": 90}
        with (
            patch.object(cache, "get_foods", return_value=self.foods),
            patch.object(cache, "get_modifiers", return_value=[]),
            patch.object(match.fuzz, "partial_ratio", side_effect=lambda _text, name: scores[name]),
        ):
            result = match.match_food_candidates("닭갈비 비빔밥")

        self.assertEqual([candidate["name_kr"] for candidate in result], ["닭갈비", "갈비", "비빔밥"])

    def test_match_food_candidates_excludes_scores_below_threshold(self):
        """기준 점수(70) 미만이면 후보를 아예 안 준다 — 억지로 비슷한 음식을 추천하지 않기 위해."""
        # 모든 음식이 69점(기준 바로 아래)인 상황을 만든다
        with (
            patch.object(cache, "get_foods", return_value=self.foods),
            patch.object(cache, "get_modifiers", return_value=[]),
            patch.object(match.fuzz, "partial_ratio", return_value=69),
        ):
            result = match.match_food_candidates("닭갈비")

        # 빈 목록 → 파이프라인이 이걸 보고 "미지원 음식" 안내를 띄운다
        self.assertEqual(result, [])

    def test_match_food_returns_highest_ranked_candidate(self):
        """match_food()는 후보 목록의 1등 하나만 돌려준다 (사용자 선택 없이 바로 쓰는 경로)."""
        scores = {"갈비": 95, "닭갈비": 95, "비빔밥": 90}
        with (
            patch.object(cache, "get_foods", return_value=self.foods),
            patch.object(cache, "get_modifiers", return_value=[]),
            patch.object(match.fuzz, "partial_ratio", side_effect=lambda _text, name: scores[name]),
        ):
            result = match.match_food("닭갈비 비빔밥")

        self.assertEqual(result["name_kr"], "닭갈비")


if __name__ == "__main__":
    unittest.main()
