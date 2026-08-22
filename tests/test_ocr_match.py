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

    def test_sorts_by_score_then_name_length(self):
        """점수가 같으면 긴 이름이 먼저 — "닭갈비"를 "갈비"로 잘못 고르면 안 된다.

        "닭갈비"라는 글자 안에는 "갈비"도 들어있어서 둘 다 100점이 나온다.
        길이로 한 번 더 정렬하지 않으면 더 짧고 덜 구체적인 쪽이 1등이 될 수 있다.
        """
        result = self.match("닭갈비 15,000원")

        self.assertEqual([c["name_kr"] for c in result], ["닭갈비", "갈비"])

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


class NonMenuTextTests(unittest.TestCase):
    """메뉴판에는 메뉴가 아닌 글자도 실린다 — 거기 들어있는 음식명을 메뉴로 잡으면 안 된다.

    좌표가 있을 때만 동작한다. 어느 상자에서 나왔는지 알아야 "그 상자가 메뉴 줄인가"를
    물을 수 있기 때문이다.
    """

    FOODS = _menu_foods("김밥", "떡볶이", "순대", "불고기", "갈비", "된장찌개")

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
