"""매칭 테스트 — src/ocr/match.py가 OCR 글자를 등록 음식으로 이어주는지 확인한다.

**유사도 계산을 mock하지 않는다.** 예전에는 rapidfuzz를 patch해서 원하는 점수를 심고
정렬·필터만 봤는데, 그러면 점수를 만들어내는 쪽의 버그가 테스트를 그냥 통과한다.
실제로 그렇게 놓친 것이 두 가지 있었다:

1. "이름이 텍스트에 통째로 들어있는지" 먼저 거르는 코드 때문에 유사도가 항상 100이 나왔다.
   화면의 "Possible match"가 전부 100%였고, 유사도 매칭이 사실상 죽어 있었다.
2. 그 게이트를 걷어내자 점수에 소수부가 생겼는데, API 응답 모델의 score가 int라
   /api/analyze가 500으로 깨졌다. mock이 int를 돌려주고 있어서 테스트는 초록색이었다.

그래서 지금은 진짜 rapidfuzz를 쓰고, 등록 음식 목록만 축소판으로 주입한다.

실행: python -m pytest tests/test_ocr_match.py
"""

import unittest
from unittest.mock import patch

from src.db import cache
from src.ocr import match

# 이 저장소의 파이프라인(src/ocr/infer.py의 recognize)에 합성 메뉴판 이미지를 넣어
# **실제로 받은** 출력이다. 폰트·흐림·JPEG 압축을 바꿔가며 수집했다.
# 이름은 흐린 사진에서도 잘 읽히고 가격 쪽이 먼저 깨진다는 게 관찰된 경향이다.
REAL_OCR_CLEAN = "감자탕 김치찌개 비빔밥 12.0 008 C0"
REAL_OCR_SERIF = "된장찌개 삼겹살 불고기 8.00 00cT 00CT"
REAL_OCR_BLURRED = "삼겹살 순대 된장찌개 김치찌개 비빔밥 16.00 4.0 8.000 8.00 900"
REAL_OCR_VERY_BLURRED = "비빔밥 오00 김치찌개 50 된장찌개 0 순대 세0 삼겹살 60"
# 이름 두 개가 알아볼 수 없게 뭉개진 경우 — "순대"가 "또4", "김밥"이 "보"로 나왔다.
REAL_OCR_MANGLED = "떡볶이 또4 보 4.500 3.500 00p"

# 아래는 관찰된 출력이 아니라 한글 OCR에서 흔한 한 글자 오인식을 본떠 만든 것이다
# (받침 탈락, 개/게 혼동). 유사도 허용 범위를 고정해두기 위한 회귀 케이스다.
TYPO_MISSING_CHAR = "영업시간11:00 빔밥 9,000원"
TYPO_WRONG_CHAR = "영업시간11:00 김치찌게 8,000원"
# 긴 이름은 한 글자가 틀려도 임계값을 넘는다 — 짧은 이름과 다르게 취급되는 근거.
TYPO_LONG_NAME = "영업시간11:00 콩나물국법 9,000원"


def _menu_foods(*names):
    """{id, name_kr, name_en} 형태의 축소판 등록 음식 목록."""
    return [
        {"id": index, "name_kr": name, "name_en": "Food%d" % index}
        for index, name in enumerate(names, start=1)
    ]


class NameScoreTests(unittest.TestCase):
    """name_score() — 텍스트 안에 이름이 얼마나 잘 나타나는지 재는 함수.

    partial_ratio를 버린 이유가 여기 다 들어있다: 점수가 주변 글자 양에 흔들리면
    안 되고, 창이 이름보다 짧아져서도 안 된다.
    """

    def test_exact_name_scores_full(self):
        self.assertEqual(match.name_score("비빔밥9,000원", "비빔밥"), 100)

    def test_score_does_not_change_with_surrounding_text(self):
        """같은 이름은 메뉴판이 크든 작든 같은 점수여야 한다.

        회귀 방지: partial_ratio는 짧은 쪽을 needle로 삼고 정렬 구간도 스스로 골라서,
        주변 글자 수에 따라 같은 이름의 점수가 달라졌다. 실측으로 잡음 없는 짧은
        메뉴판에서 오탐 80개, 중간 길이에서 31개로 요동쳤다.
        """
        scores = {
            match.name_score("잡음" * padding + "비빔밥9,000원", "비빔밥")
            for padding in (0, 10, 40, 150)
        }
        self.assertEqual(scores, {100})

    def test_short_name_needs_more_than_one_matching_letter(self):
        """2글자 이름이 한 글자만 겹칠 때 점수가 뛰면 안 된다.

        창 너비를 이름 길이 -1까지 허용하면 2글자 이름의 창이 1글자가 되고,
        "떡" 하나만 맞아도 67점이 나와 기준(65)을 넘어버린다. 최소 창 가드가 막는다.
        """
        self.assertLess(match.name_score("떡볶이4,500원", "떡국"), match.MATCH_THRESHOLD)

    def test_short_name_with_a_missing_letter_is_rejected(self):
        """짧은 이름은 글자 하나가 빠지면 더 이상 받아주지 않는다.

        3글자 중 두 글자가 맞으면 무조건 80점인데, 그 점수대에는 살리고 싶은
        "빔밥→비빔밥"과 막고 싶은 "막국수→칼국수"가 같이 들어 있다. 실측에서
        80점대는 정탐 1 : 오탐 38이었다(MATCH_THRESHOLD 주석 참고). 그래서
        구제를 포기하고 오탐을 막는 쪽을 택했다.
        """
        score = match.name_score(TYPO_MISSING_CHAR.replace(" ", ""), "비빔밥")
        self.assertEqual(score, 80)
        self.assertLess(score, match.MATCH_THRESHOLD)

    def test_long_name_still_tolerates_one_wrong_letter(self):
        """긴 이름은 한 글자가 틀려도 살린다 — 유사도 매칭이 아직 일하는 자리."""
        score = match.name_score(TYPO_LONG_NAME.replace(" ", ""), "콩나물국밥")
        self.assertGreaterEqual(score, match.MATCH_THRESHOLD)
        self.assertLess(score, 100)

    def test_returns_an_int(self):
        """API 응답 모델의 score가 int다. 소수부가 남으면 /api/analyze가 500으로 깨진다."""
        self.assertIsInstance(match.name_score(TYPO_MISSING_CHAR, "비빔밥"), int)


class MatchFoodCandidatesTests(unittest.TestCase):
    def setUp(self):
        # "갈비"와 "닭갈비"가 핵심 조합 — 짧고 덜 구체적인 쪽이 1등이 되면 안 된다.
        self.foods = _menu_foods("갈비", "닭갈비", "비빔밥")

    def match(self, text, foods=None, **kwargs):
        with (
            patch.object(cache, "get_foods", return_value=foods or self.foods),
            patch.object(cache, "get_modifiers", return_value=[]),
        ):
            return match.match_food_candidates(text, **kwargs)

    def test_shorter_name_inside_a_longer_one_is_dropped(self):
        """"닭갈비"가 적힌 줄에서 "갈비"는 후보가 아니다.

        "닭갈비" 안에 "갈비"가 통째로 들어 있어 둘 다 100점이 나온다. 예전에는 둘 다
        후보로 두고 긴 이름을 앞에 놓는 것으로 갈음했는데(이 테스트의 이전 버전),
        화면에는 여전히 카드가 두 장 떠서 사용자가 없는 메뉴를 주문할 수 있었다 —
        실측 2026-08-26, "황기갈비탕" 한 줄이 Galbitang과 Galbi 두 장으로 나왔다.
        짧은 쪽은 긴 쪽의 일부일 뿐 별개 메뉴가 아니므로 뺀다.

        정렬 규칙(점수 → 이름 길이)은 그대로 남아 있다. 부분 문자열 관계가 아닌 서로
        다른 이름이 동점일 때는 여전히 긴 쪽이 앞에 온다. 또 줄 단위로 매칭하므로
        "갈비"와 "닭갈비"가 각각 다른 줄에 있는 메뉴판은 둘 다 후보로 남는다.
        """
        result = self.match("닭갈비 15,000원")

        self.assertEqual([c["name_kr"] for c in result], ["닭갈비"])

    def test_returns_nothing_when_no_food_is_on_the_menu(self):
        """기준 점수에 못 미치면 후보를 아예 안 준다 — 억지로 비슷한 음식을 추천하지 않는다.

        빈 목록 → 파이프라인이 이걸 보고 "미지원 음식" 안내를 띄운다.
        """
        self.assertEqual(self.match("영업시간 11:00-22:00 주차가능 포장가능"), [])

    def test_exact_name_scores_full_and_short_typo_is_dropped(self):
        """정확히 읽힌 이름은 100점, 짧은 이름의 한 글자 누락은 후보에서 빠진다.

        점수가 100 일색이 되지 않는 근거는 인식 신뢰도 쪽으로 옮겼다
        (ConfidenceWeightedScoreTests 참고) — 이름 점수만으로는 대부분 100이다.
        """
        exact = self.match("비빔밥 9,000원")
        typo = self.match(TYPO_MISSING_CHAR)

        self.assertEqual(exact[0]["score"], 100)
        self.assertEqual(typo, [])

    def test_recovers_a_name_with_a_wrong_letter(self):
        """개/게처럼 한 글자가 틀리게 읽혀도 후보로 살린다."""
        foods = _menu_foods("김치찌개", "된장찌개")

        result = self.match(TYPO_WRONG_CHAR, foods=foods)

        self.assertEqual([c["name_kr"] for c in result], ["김치찌개"])

    def test_does_not_add_a_lookalike_of_an_exact_match(self):
        """"감자탕"이 그대로 적혀 있으면 닮은 "감자전"을 후보로 올리지 않는다.

        감자전이 걸리는 건 OCR 오류 때문이 아니라 두 이름이 원래 닮아서다. 이걸 막지
        않으면 닮은 메뉴가 있는 음식마다 매번 엉뚱한 후보가 딸려 나온다.
        """
        foods = _menu_foods("감자탕", "감자전")

        result = self.match("영업시간11:00 감자탕 12,000원", foods=foods)

        self.assertEqual([c["name_kr"] for c in result], ["감자탕"])

    def test_keeps_both_lookalikes_when_both_are_printed(self):
        """반대로 둘 다 메뉴판에 적혀 있으면 둘 다 후보다 — 억누르는 건 오인식 의심분뿐이다."""
        foods = _menu_foods("감자탕", "감자전")

        result = self.match("감자탕 12,000원 감자전 8,000원", foods=foods)

        self.assertEqual(sorted(c["name_kr"] for c in result), ["감자전", "감자탕"])

    def test_match_food_returns_highest_ranked_candidate(self):
        """match_food()는 후보 목록의 1등 하나만 돌려준다 (사용자 선택 없이 바로 쓰는 경로)."""
        with (
            patch.object(cache, "get_foods", return_value=self.foods),
            patch.object(cache, "get_modifiers", return_value=[]),
        ):
            result = match.match_food("닭갈비 15,000원")

        self.assertEqual(result["name_kr"], "닭갈비")


class MatchByLineTests(unittest.TestCase):
    """match_food_candidates_by_line() — 메뉴판을 줄 단위로 보는 쪽.

    통짜 텍스트로 보던 때의 두 가지 어긋남을 여기서 고정한다.
      1. 같은 음식이 여러 줄에 있으면 줄마다 후보가 나와야 한다 (물만두 / 군만두)
      2. 수식어는 그 줄에서만 뽑혀야 한다 (메뉴판 어딘가의 "해물"이 비빔밥에 붙으면 안 된다)
    """

    FOODS = _menu_foods("만두", "칼국수", "비빔밥", "김치찌개")
    MODIFIERS = [
        {"keyword": "해물", "category": "ingredient", "keyword_en": "Seafood", "spice_tier": None},
        {"keyword": "물", "category": "ingredient", "keyword_en": "Water", "spice_tier": None},
    ]

    # 한 줄에 이름과 가격이 같이 있는, 흔한 메뉴판 모양.
    BOXES = [
        (10, 10, 200, 30, "물만두 5,000", 0.99),
        (10, 60, 200, 30, "군만두 6,000", 0.99),
        (10, 110, 260, 30, "해물칼국수 8,000", 0.99),
        (10, 160, 200, 30, "비빔밥 9,000", 0.99),
    ]

    def by_line(self, boxes=None):
        with (
            patch.object(cache, "get_foods", return_value=self.FOODS),
            patch.object(cache, "get_modifiers", return_value=self.MODIFIERS),
        ):
            return match.match_food_candidates_by_line(boxes or self.BOXES)

    def test_same_food_on_two_lines_yields_two_candidates(self):
        """물만두와 군만두는 둘 다 "만두"지만 별개 메뉴다 — 하나로 합치면 하나가 사라진다."""
        mandu = [c for c in self.by_line() if c["name_kr"] == "만두"]

        self.assertEqual(len(mandu), 2)
        self.assertEqual(
            [c["menu_text"] for c in mandu],
            ["물만두 5,000", "군만두 6,000"],
        )

    def test_each_line_keeps_its_own_price(self):
        """가격이 줄에서 나오므로 옆 줄 가격을 가져오지 않는다."""
        prices = {c["menu_text"]: c["price_krw"] for c in self.by_line()}

        self.assertEqual(prices["물만두 5,000"], 5000)
        self.assertEqual(prices["군만두 6,000"], 6000)
        self.assertEqual(prices["비빔밥 9,000"], 9000)

    def test_modifier_does_not_leak_to_another_line(self):
        """메뉴판에 "해물"이 있어도 그 줄이 아니면 붙지 않는다.

        통짜 텍스트로 보던 때는 수식어를 메뉴판 전체에서 찾아 모든 후보에 똑같이
        붙였다. 실측에서 수식어 부착의 97%가 이렇게 엉뚱한 메뉴에 붙은 것이었다.
        """
        by_name = {c["name_kr"]: c for c in self.by_line()}

        칼국수_mods = [m["keyword"] for m in by_name["칼국수"]["modifiers"]["ingredient"]]
        비빔밥_mods = [m["keyword"] for m in by_name["비빔밥"]["modifiers"]["ingredient"]]

        self.assertIn("해물", 칼국수_mods)
        self.assertEqual(비빔밥_mods, [])

    def test_candidates_follow_reading_order(self):
        """화면 카드 순서가 메뉴판 순서와 같아야 눈으로 대조할 수 있다."""
        self.assertEqual(
            [c["menu_text"] for c in self.by_line()],
            ["물만두 5,000", "군만두 6,000", "해물칼국수 8,000", "비빔밥 9,000"],
        )

    def test_shop_name_on_the_sign_is_not_a_menu_line(self):
        """간판의 가게 이름은 후보가 되면 안 된다 — 같은 이름이 메뉴에도 있어도.

        실기기 확인에서 나온 회귀다. "연정김치찌개" 간판이 걸린 메뉴판에서 김치찌개
        후보가 셋(간판 + 메뉴 두 줄) 나왔다. 간판을 거르는 검사가 "이 이름을 담은
        상자 중 하나라도 메뉴 줄이면 통과"라, 줄 단위로 부를 때 판정 대상까지 사진
        전체로 넘기면 간판 줄이 **다른 줄 덕분에** 살아남는다.
        """
        boxes = [
            # 간판: 유난히 크고, 사진 맨 위이고, 가격이 없다.
            (10, 5, 400, 60, "연정김치찌개", 0.99),
            (10, 120, 300, 24, "쌈싸먹는 김치찌개 7,000원", 0.99),
            (10, 170, 300, 24, "쌈싸먹는 꽁치김치찌개 7,000원", 0.99),
        ]

        result = self.by_line(boxes)

        self.assertEqual(
            [c["menu_text"] for c in result],
            ["쌈싸먹는 김치찌개 7,000원", "쌈싸먹는 꽁치김치찌개 7,000원"],
        )

    def test_one_line_does_not_produce_the_same_food_twice(self):
        """줄 하나가 카드 하나다 — 같은 줄에서 같은 음식이 두 번 나오면 겹쳐 보인다."""
        boxes = [(10, 10, 300, 30, "만두 만두 5,000", 0.99)]

        result = self.by_line(boxes)

        self.assertEqual([c["name_kr"] for c in result], ["만두"])


class ScanMenuLinesTests(unittest.TestCase):
    """scan_menu_lines() — 안내 가능한 후보와 그러지 못한 메뉴 줄을 함께 돌려준다.

    등록 음식이 50개뿐이라 메뉴판의 대부분은 매칭되지 않는다(실측 22.9%만 매칭).
    그 줄을 버리면 여행자는 그 메뉴가 아예 없는 것처럼 본다. 설명은 못 해도
    이름과 가격은 보여줄 수 있다.
    """

    FOODS = _menu_foods("김치찌개", "동태찌개")

    def scan(self, boxes):
        with (
            patch.object(cache, "get_foods", return_value=self.FOODS),
            patch.object(cache, "get_modifiers", return_value=[]),
        ):
            return match.scan_menu_lines(boxes)

    # 실제로 찍은 부산 메뉴판을 본뜬 배치 — 간판 + 메뉴 + 지자체 표기.
    BOXES = [
        (10, 5, 400, 60, "연정김치찌개", 0.99),
        (10, 120, 320, 24, "쌈싸먹는 김치찌개 7,000원", 0.99),
        (10, 170, 320, 24, "여름막국수 6,000원", 0.99),
        (10, 220, 320, 24, "겨울동태찌개 8,000원", 0.99),
        (10, 270, 320, 24, "두루치기(小) 12,000원", 0.99),
        (10, 320, 320, 24, "부산광역시 강서구", 0.99),
    ]

    def test_unmatched_lines_with_a_price_are_kept(self):
        """등록 음식이 아니어도 값이 적혀 있으면 메뉴로 본다."""
        _candidates, unsupported = self.scan(self.BOXES)

        self.assertEqual(
            [(line["menu_text"], line["price_krw"]) for line in unsupported],
            [("여름막국수 6,000원", 6000), ("두루치기(小) 12,000원", 12000)],
        )

    def test_lines_carry_a_name_without_the_price(self):
        """화면이 가격을 따로 보여주므로, 이름 자리에 쓸 글자에는 가격이 없어야 한다.

        후보 줄과 안내 못 하는 줄 모두 필요하다 — 둘 다 카드에서 이름 자리에
        줄 글자를 그대로 쓰기 때문이다.
        """
        candidates, unsupported = self.scan(self.BOXES)

        self.assertEqual(
            [line["name_text"] for line in unsupported],
            ["여름막국수", "두루치기(小)"],
        )
        self.assertEqual(
            [candidate["name_text"] for candidate in candidates],
            ["쌈싸먹는 김치찌개", "겨울동태찌개"],
        )

    def test_two_column_menu_splits_at_the_column_boundary(self):
        """2단 메뉴판에서 왼쪽 칸과 오른쪽 칸이 한 항목으로 뭉치면 안 된다.

        줄 묶기는 세로 위치만 보므로, 같은 높이에 있는 두 칸이 한 줄이 된다.
        그러면 한 항목에 이름과 가격이 두 벌씩 들어가 어느 가격을 집어도 틀린다
        (실측: 가격 정확도 60.0% → 76.7%).

        가로로 훑다가 가격이 나온 뒤에 또 이름이 나오면 거기가 칸 경계다.
        """
        boxes = [
            (10, 100, 120, 24, "모듬전", 0.99),
            (150, 100, 60, 24, "13.0", 0.99),
            (400, 100, 140, 24, "그집막걸리", 0.99),
            (560, 100, 60, 24, "6.0", 0.99),
        ]

        _candidates, unsupported = self.scan(boxes)

        self.assertEqual(
            [(line["menu_text"], line["price_krw"]) for line in unsupported],
            [("모듬전 13.0", 13000), ("그집막걸리 6.0", 6000)],
        )

    def test_one_column_line_is_not_split(self):
        """1단 메뉴판은 쪼개지면 안 된다 — 이름 뒤에 가격이 오고 끝난다."""
        boxes = [
            (10, 100, 200, 24, "여름막국수", 0.99),
            (300, 100, 80, 24, "6,000원", 0.99),
        ]

        _candidates, unsupported = self.scan(boxes)

        self.assertEqual(
            [(line["menu_text"], line["price_krw"]) for line in unsupported],
            [("여름막국수 6,000원", 6000)],
        )

    def test_a_line_of_only_numbers_is_not_a_menu(self):
        """숫자만 있는 줄은 메뉴가 아니다.

        실기기 확인에서 나온 회귀다. 생맥주 용량 표기 "(500/1700/2700)"이 값 세
        개로 읽혀 메뉴 카드로 올라왔고, 가격까지 ₩2,700으로 붙었다. 이름 없는
        메뉴는 존재하지 않으므로 이름 유무가 가장 확실한 잣대다.
        """
        boxes = [
            (10, 10, 320, 24, "쌈싸먹는 김치찌개 7,000원", 0.99),
            (10, 60, 320, 24, "(500/1700/2700)", 0.99),
            (10, 110, 320, 24, "3.5/11.0/18.0", 0.99),
        ]

        _candidates, unsupported = self.scan(boxes)

        self.assertEqual(unsupported, [])

    def test_a_thousand_abbreviated_price_is_read(self):
        """"13.0"은 13,000원이다 — 한국 메뉴판에서 흔한 축약 표기."""
        boxes = [(10, 10, 320, 24, "모듬전 13.0", 0.99)]

        _candidates, unsupported = self.scan(boxes)

        self.assertEqual(
            [(line["menu_text"], line["price_krw"]) for line in unsupported],
            [("모듬전 13.0", 13000)],
        )

    def test_lines_without_a_price_are_dropped(self):
        """가격이 없는 줄은 메뉴가 아니다 — 지자체 표기·전화번호·안내문."""
        _candidates, unsupported = self.scan(self.BOXES)

        self.assertNotIn("부산광역시 강서구", [line["menu_text"] for line in unsupported])

    def test_the_shop_sign_is_not_kept_either(self):
        """간판은 가격이 없어 애초에 걸리지만, 후보로도 안 올라간다."""
        candidates, unsupported = self.scan(self.BOXES)

        texts = [c["menu_text"] for c in candidates] + [u["menu_text"] for u in unsupported]
        self.assertNotIn("연정김치찌개", texts)

    def test_line_numbers_let_the_screen_restore_menu_order(self):
        """화면이 두 목록을 합쳐 메뉴판 순서대로 늘어놓을 수 있어야 한다."""
        candidates, unsupported = self.scan(self.BOXES)

        merged = sorted(candidates + unsupported, key=lambda item: item["line_no"])
        self.assertEqual(
            [item["menu_text"] for item in merged],
            [
                "쌈싸먹는 김치찌개 7,000원",
                "여름막국수 6,000원",
                "겨울동태찌개 8,000원",
                "두루치기(小) 12,000원",
            ],
        )

    def test_a_matched_line_is_not_repeated_as_unsupported(self):
        """안내 가능한 줄은 후보 쪽에만 있어야 한다 — 양쪽에 나오면 카드가 두 개 뜬다."""
        candidates, unsupported = self.scan(self.BOXES)

        matched_texts = {c["menu_text"] for c in candidates}
        self.assertTrue(matched_texts.isdisjoint({u["menu_text"] for u in unsupported}))


class NonMenuTextTests(unittest.TestCase):
    """메뉴판에는 메뉴가 아닌 글자도 실린다 — 거기 들어있는 음식명을 메뉴로 잡으면 안 된다.

    좌표가 있을 때만 동작한다. 어느 상자에서 나왔는지 알아야 "그 상자가 메뉴 줄인가"를
    물을 수 있기 때문이다.
    """

    FOODS = _menu_foods("김밥", "떡볶이", "순대", "불고기", "갈비", "된장찌개", "족발")

    def match(self, boxes):
        text = " ".join(box[4] for box in boxes)
        with (
            patch.object(cache, "get_foods", return_value=self.FOODS),
            patch.object(cache, "get_modifiers", return_value=[]),
        ):
            return {c["name_kr"] for c in match.match_food_candidates(text, boxes=boxes)}

    def test_shop_name_is_not_offered_as_a_dish(self):
        """"김밥천국" 간판의 김밥은 메뉴가 아니다 — 큰 글씨 + 사진 위쪽 + 가격 없음."""
        boxes = [
            (250, 30, 400, 90, "김밥천국"),        # 간판: 높이 90 (본문의 3배), 맨 위, 가격 없음
            (80, 300, 200, 30, "떡볶이"),
            (620, 300, 150, 30, "4,500"),
            (80, 400, 160, 30, "순대"),
            (620, 400, 150, 30, "4,000"),
        ]

        self.assertEqual(self.match(boxes), {"떡볶이", "순대"})

    def test_a_dish_that_is_also_in_the_shop_name_still_counts(self):
        """간판에도 있고 메뉴 줄에도 있으면 메뉴다 — 간판을 이유로 지우면 안 된다."""
        boxes = [
            (250, 30, 400, 90, "김밥천국"),
            (80, 300, 200, 30, "김밥"),
            (620, 300, 150, 30, "3,500"),
        ]

        self.assertEqual(self.match(boxes), {"김밥"})

    def test_large_top_text_with_a_price_is_a_dish_not_a_sign(self):
        """큰 글씨로 맨 위에 적힌 대표 메뉴는 살린다 — 가격이 붙어 있으면 간판이 아니다."""
        boxes = [
            (80, 30, 400, 90, "불고기 12,000"),
            (80, 300, 200, 30, "순대"),
            (620, 300, 150, 30, "4,000"),
        ]

        self.assertEqual(self.match(boxes), {"불고기", "순대"})

    def test_catches_a_sign_only_moderately_larger_than_the_menu(self):
        """간판이 본문의 1.5배 정도만 큰 사진도 잡아야 한다.

        임계값을 1.8배로 뒀을 때 이 케이스가 그대로 새어나갔다. 실제 메뉴판은 간판을
        아주 크게 박지 않는 경우가 많다.
        """
        boxes = [
            (250, 30, 400, 45, "김밥천국"),  # 높이 45 = 본문(30)의 1.5배
            (80, 300, 200, 30, "떡볶이"),
            (620, 300, 150, 30, "4,500"),
        ]

        self.assertEqual(self.match(boxes), {"떡볶이"})

    def test_a_sign_the_same_size_as_the_menu_is_not_caught(self):
        """**알려진 한계** — 간판이 본문과 같은 크기면 크기 신호가 없어 걸러지지 않는다.

        이 경우까지 잡으려고 "한글 합성어는 뒤가 머리"라는 규칙(김밥천국은 '천국'이므로
        김밥이 아니다)을 시도했지만, 실제 사진 50장에 적용하니 진짜 메뉴 21개가 함께
        날아갔다 — 'colon국수c0pcp500lcs'(OCR 쓰레기가 뒤에 붙음), '불고기접시',
        '보쌈정식' 같은 것들이다. 후보가 하나 더 뜨는 것보다 진짜 메뉴를 잃는 게 나쁘므로
        그 규칙은 채택하지 않았다. 이 테스트는 현재 동작을 기록해두는 것이다.
        """
        boxes = [
            (250, 30, 400, 30, "김밥천국"),
            (80, 300, 200, 30, "떡볶이"),
            (620, 300, 150, 30, "4,500"),
        ]

        self.assertEqual(self.match(boxes), {"김밥", "떡볶이"})

    def test_origin_notice_is_not_a_menu_line(self):
        """법정 원산지 표시에 든 음식명은 메뉴가 아니다 (산지 표기 2개 이상일 때만)."""
        boxes = [
            (80, 300, 600, 30, "돼지고기(국내산)쌀(국내산),고추가루(중국산)"),
            (80, 400, 200, 30, "순대"),
            (620, 400, 150, 30, "4,000"),
        ]

        self.assertEqual(self.match(boxes), {"순대"})

    def test_a_single_origin_tag_on_a_dish_is_kept(self):
        """"한우불고기(국내산)"처럼 메뉴에 산지가 하나 붙는 건 흔하다 — 지우면 안 된다."""
        boxes = [(80, 300, 400, 30, "한우불고기(국내산)"), (620, 300, 150, 30, "22,000")]

        self.assertEqual(self.match(boxes), {"불고기"})

    def test_promotional_line_is_not_a_menu_line(self):
        """"...무한리필전문점입니다" 같은 홍보 문구의 갈비는 메뉴가 아니다."""
        boxes = [
            (80, 300, 700, 30, "제공하는돼지갈비무한리필전문점입니다"),
            (80, 400, 200, 30, "순대"),
            (620, 400, 150, 30, "4,000"),
        ]

        self.assertEqual(self.match(boxes), {"순대"})

    def test_notice_sentence_is_not_a_menu_line(self):
        """"당일 삶은 족발만 판매합니다" 같은 가게 안내 문장의 족발은 메뉴가 아니다.

        실기기 확인에서 나온 회귀다. 족발집 메뉴판의 안내 문구가 정식 메뉴 카드로
        올라와, 여행자에게 존재하지 않는 메뉴가 보였다.
        """
        boxes = [
            (80, 300, 700, 30, "당일 삶은 족발만 판매합니다"),
            (80, 400, 200, 30, "순대"),
            (620, 400, 150, 30, "4,000"),
        ]

        self.assertEqual(self.match(boxes), {"순대"})

    def test_a_dish_name_ending_in_a_noun_is_kept(self):
        """종결 어미로 거르는 것이지 이름 조각으로 거르는 게 아니다 — 명사로 끝나면 메뉴다.

        걸림말을 넓게 잡았을 때 무엇이 깨지는지 기록해두는 자리다. "족발정식"에는
        종결 어미가 없으므로 안내 문장 판정이 건드리면 안 된다.
        """
        boxes = [(80, 300, 400, 30, "족발정식"), (620, 300, 150, 30, "25,000")]

        self.assertEqual(self.match(boxes), {"족발"})

    def test_all_you_can_eat_qualifier_on_a_dish_is_kept(self):
        """회귀 방지: "무한리필"을 걸림말에 넣었다가 실제 사진의 메뉴가 통째로 사라졌다.

        무한리필 식당에서 "된장찌개(무한리필 이용시)"는 메뉴 조건 문구다.
        """
        boxes = [(80, 300, 500, 30, "된장찌개(무한리필이용시)"), (620, 300, 150, 30, "3,000")]

        self.assertEqual(self.match(boxes), {"된장찌개"})

    def test_filter_is_skipped_without_coordinates(self):
        """좌표가 없으면 어느 상자에서 나왔는지 알 수 없다 — 기존처럼 후보로 둔다."""
        with (
            patch.object(cache, "get_foods", return_value=self.FOODS),
            patch.object(cache, "get_modifiers", return_value=[]),
        ):
            result = match.match_food_candidates("김밥천국 떡볶이 4,500")

        self.assertEqual({c["name_kr"] for c in result}, {"김밥", "떡볶이"})


class RealOcrRegressionTests(unittest.TestCase):
    """실제 OCR 출력 픽스처 — 파이프라인이 진짜로 뱉은 문자열로 회귀를 막는다."""

    FOODS = _menu_foods(
        "비빔밥", "김치찌개", "감자탕", "된장찌개", "삼겹살", "불고기", "순대", "김밥", "떡볶이"
    )

    def match(self, text):
        with (
            patch.object(cache, "get_foods", return_value=self.FOODS),
            patch.object(cache, "get_modifiers", return_value=[]),
        ):
            return {c["name_kr"] for c in match.match_food_candidates(text)}

    def test_clean_photo_finds_every_dish_and_nothing_else(self):
        self.assertEqual(self.match(REAL_OCR_CLEAN), {"감자탕", "김치찌개", "비빔밥"})

    def test_serif_font_photo(self):
        self.assertEqual(self.match(REAL_OCR_SERIF), {"된장찌개", "삼겹살", "불고기"})

    def test_blurred_photo_still_finds_every_dish(self):
        self.assertEqual(
            self.match(REAL_OCR_BLURRED), {"삼겹살", "순대", "된장찌개", "김치찌개", "비빔밥"}
        )

    def test_heavily_blurred_photo_still_finds_every_dish(self):
        """가격이 "오00", "세0"처럼 깨져도 이름 쪽은 살아있다 — 그 이름만 보고 맞춰야 한다."""
        self.assertEqual(
            self.match(REAL_OCR_VERY_BLURRED), {"삼겹살", "순대", "된장찌개", "김치찌개", "비빔밥"}
        )

    def test_unreadable_names_are_not_guessed(self):
        """"순대"가 "또4", "김밥"이 "보"로 뭉개진 사진. 알아볼 수 없으면 지어내지 않는다.

        읽힌 "떡볶이"만 나와야 하고, 뭉개진 두 글자를 억지로 어떤 음식에 붙이면 안 된다.
        """
        self.assertEqual(self.match(REAL_OCR_MANGLED), {"떡볶이"})


class ConfidenceWeightedScoreTests(unittest.TestCase):
    """점수 = 이름을 얼마나 정확히 읽었나 × 인식 모델이 얼마나 확신했나.

    글자만 보면 "이름이 정확히 일치"라 100인데, 그 글자를 읽은 인식 신뢰도가 0.6이면
    실제로 확신할 수 있는 정도는 60이다. 신뢰도를 빼면 깨끗한 사진이든 뭉개진 사진이든
    전부 100이 나와서 화면의 숫자가 아무 정보도 담지 못한다.
    """

    FOODS = _menu_foods("비빔밥")

    def match(self, boxes):
        text = " ".join(box[4] for box in boxes)
        with (
            patch.object(cache, "get_foods", return_value=self.FOODS),
            patch.object(cache, "get_modifiers", return_value=[]),
        ):
            return match.match_food_candidates(text, boxes=boxes)

    def test_confident_reading_keeps_the_full_score(self):
        result = self.match([(40, 100, 90, 24, "비빔밥 9,000", 1.0)])

        self.assertEqual(result[0]["score"], 100)

    def test_unsure_reading_lowers_the_score(self):
        """또렷하게 읽은 "비빔밥"과 겨우 알아본 "비빔밥"이 같은 점수면 안 된다."""
        result = self.match([(40, 100, 90, 24, "비빔밥 9,000", 0.62)])

        self.assertEqual(result[0]["score"], 62)

    def test_score_stays_full_for_boxes_without_confidence(self):
        """신뢰도가 없는 5개짜리 상자(옛 호출부·테스트)는 1.0으로 본다 — 점수를 깎지 않는다."""
        result = self.match([(40, 100, 90, 24, "비빔밥 9,000")])

        self.assertEqual(result[0]["score"], 100)

    def test_confidence_lowers_the_score_below_the_threshold_value(self):
        """확신이 낮으면 정확히 읽힌 이름도 점수가 깎인다.

        신뢰도는 임계값 통과 **뒤에** 곱해진다. 그래서 결과 점수가 임계값보다
        낮아도 후보에서 빠지지 않는다 — 이름은 맞게 읽었고, 다만 얼마나 확신하는지를
        점수에 남기는 것이기 때문이다.

        채움말로 "영업시간"을 쓰지 않는다 — 안내 문구로 분류돼 후보가 통째로 걸러진다
        (NonMenuTextTests 참고). 메뉴 줄에 실제로 있을 법한 글자만 쓴다.
        """
        boxes = [(40, 100, 90, 24, "비빔밥 9,000", 0.80)]

        result = self.match(boxes)

        self.assertEqual(result[0]["score"], 80)
        self.assertLess(result[0]["score"], match.MATCH_THRESHOLD)


class FoodRowPassthroughTests(unittest.TestCase):
    """foods row의 부가 컬럼(사진·출처)이 후보에 그대로 실려 나가는지."""

    def match(self, text, foods):
        with (
            patch.object(cache, "get_foods", return_value=foods),
            patch.object(cache, "get_modifiers", return_value=[]),
        ):
            return match.match_food_candidates(text)

    def test_passes_through_thumbnail_fields(self):
        foods = [
            {
                "id": 1,
                "name_kr": "비빔밥",
                "name_en": "Bibimbap",
                "thumbnail_url": "https://example.com/bibimbap.jpg",
                "thumbnail_attribution": "Source: AI Hub",
            }
        ]

        result = self.match("비빔밥 9,000원", foods)

        self.assertEqual(result[0]["thumbnail_url"], "https://example.com/bibimbap.jpg")
        self.assertEqual(result[0]["thumbnail_attribution"], "Source: AI Hub")

    def test_defaults_thumbnail_fields_to_none(self):
        """사진이 아직 없는 음식(row에 컬럼 자체가 없음)이어도 KeyError 없이 None으로 채운다."""
        result = self.match("비빔밥 9,000원", _menu_foods("비빔밥"))

        self.assertIsNone(result[0]["thumbnail_url"])
        self.assertIsNone(result[0]["thumbnail_attribution"])


class PriceAndSourceTests(unittest.TestCase):
    """메뉴판에서 읽은 가격과, 그 후보가 사진 어디에서 나왔는지."""

    def match(self, text, foods, **kwargs):
        with (
            patch.object(cache, "get_foods", return_value=foods),
            patch.object(cache, "get_modifiers", return_value=[]),
        ):
            return match.match_food_candidates(text, **kwargs)

    def test_extracts_price_from_ocr_text(self):
        result = self.match("비빔밥 9,000원", _menu_foods("비빔밥"))

        self.assertEqual(result[0]["price_krw"], 9000)
        self.assertEqual(result[0]["price_krw_display"], "₩9,000")

    def test_price_is_none_when_not_printed_on_menu(self):
        """메뉴판에 가격이 안 적혀 있으면 None — 임의로 채우지 않는다."""
        result = self.match("오늘의 추천 비빔밥", _menu_foods("비빔밥"))

        self.assertIsNone(result[0]["price_krw"])
        self.assertIsNone(result[0]["price_krw_display"])

    def test_uses_box_coordinates_when_given(self):
        """boxes를 주면 가격이 이름 아래 줄에 적혀 있어도 각자 자기 가격을 가져간다."""
        boxes = [
            (40, 100, 90, 24, "비빔밥"),
            (42, 132, 70, 22, "9,000"),
            (240, 100, 90, 24, "불고기"),
            (242, 132, 80, 22, "12,000"),
        ]

        result = self.match(
            "비빔밥 9,000 불고기 12,000", _menu_foods("비빔밥", "불고기"), boxes=boxes
        )

        self.assertEqual(
            {c["name_kr"]: c["price_krw"] for c in result}, {"비빔밥": 9000, "불고기": 12000}
        )

    def test_omits_price_for_food_the_photo_does_not_price(self):
        """가격이 안 적힌 메뉴는 None으로 남는다 — 옆 메뉴 가격을 끌어오지 않는다."""
        boxes = [
            (40, 100, 90, 24, "떡볶이"),
            (40, 160, 90, 24, "불고기"),
            (340, 160, 80, 22, "12,000"),
        ]

        result = self.match(
            "떡볶이 불고기 12,000", _menu_foods("떡볶이", "불고기"), boxes=boxes
        )

        self.assertEqual(
            {c["name_kr"]: c["price_krw"] for c in result}, {"떡볶이": None, "불고기": 12000}
        )

    def test_reports_the_box_each_match_came_from(self):
        """후보마다 "사진 어디의 어떤 글자에서 나왔는지"를 실어 보낸다 — 추적용."""
        boxes = [
            (40, 100, 200, 24, "비빔밥 9,000"),
            (40, 160, 200, 24, "불고기 12,000"),
        ]

        result = self.match(
            "비빔밥 9,000 불고기 12,000", _menu_foods("비빔밥", "불고기"), boxes=boxes
        )

        sources = {c["name_kr"]: (c["source_text"], c["source_box"]) for c in result}
        # OCR이 읽은 글자를 그대로 — 음식명만 잘라내지 않는다(가격까지 보여야 추적이 된다)
        self.assertEqual(sources["비빔밥"], ("비빔밥 9,000", (40, 100, 200, 24)))
        self.assertEqual(sources["불고기"], ("불고기 12,000", (40, 160, 200, 24)))

    def test_has_no_source_without_boxes(self):
        """좌표를 안 넘기면 위치를 알 수 없다 — 지어내지 않고 None."""
        result = self.match("비빔밥 9,000원", _menu_foods("비빔밥"))

        self.assertIsNone(result[0]["source_text"])
        self.assertIsNone(result[0]["source_box"])


class FindSourceBoxTests(unittest.TestCase):
    def test_returns_none_when_name_spans_two_boxes(self):
        """이름이 두 상자에 걸쳐 잘리면 위치를 특정할 수 없다 — 엉뚱한 자리를 고르지 않는다."""
        boxes = [(40, 100, 60, 24, "비빔"), (110, 100, 60, 24, "밥 9,000")]

        self.assertIsNone(match.find_source_box(boxes, "비빔밥"))

    def test_prefers_the_menu_line_over_the_shop_sign(self):
        """이름이 간판과 메뉴 줄 양쪽에 있으면 메뉴 줄을 가리켜야 한다.

        실측(손칼국수·등뼈찜 메뉴판): "칼국수"가 맨 위 간판과 면류 목록 양쪽에 있다.
        검출 순서상 간판이 먼저 나오는데 그걸 그대로 쓰면, 사진 위 상자가 간판에 그려져서
        후보는 맞는데도 간판을 메뉴로 읽은 것처럼 보인다.
        """
        sign = (200, 30, 500, 60, "손칼국수 등뼈찜")   # 간판: 크고 맨 위, 가격 없음
        menu_line = (80, 300, 200, 30, "칼국수")
        boxes = [sign, menu_line, (620, 300, 150, 30, "7,000")]

        self.assertEqual(match.find_source_box(boxes, "칼국수"), menu_line)

    def test_falls_back_to_the_sign_when_there_is_no_menu_line(self):
        """메뉴 줄에 없고 간판에만 있으면 그 간판이라도 가리킨다 — 위치를 아예 잃지 않는다."""
        sign = (200, 30, 500, 60, "손칼국수 등뼈찜")
        boxes = [sign, (80, 300, 200, 30, "떡볶이"), (620, 300, 150, 30, "4,500")]

        self.assertEqual(match.find_source_box(boxes, "칼국수"), sign)

    def test_ignores_spacing_differences(self):
        """OCR이 띄어쓰기를 다르게 읽어도 같은 이름으로 본다(매칭 규칙과 동일하게)."""
        boxes = [(40, 100, 200, 24, "비 빔 밥 9,000")]

        self.assertEqual(match.find_source_box(boxes, "비빔밥"), boxes[0])


if __name__ == "__main__":
    unittest.main()
