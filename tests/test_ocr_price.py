"""메뉴판 원화 가격 인식 테스트 — src/ocr/price.py.

실행: python -m pytest tests/test_ocr_price.py
"""

import unittest

from src.ocr import price


class ThousandAbbreviatedPriceTests(unittest.TestCase):
    """"13.0" = 13,000원 — 한국 메뉴판에서 천 단위를 줄여 적는 표기.

    실측(강원 칠판 메뉴판)에서 한 가게 메뉴가 전부 이 표기였는데, 정규식이 점 뒤에
    세 자리를 요구해 하나도 못 읽었다. 값이 틀린 게 아니라 통째로 비어 보였다.
    """

    def cases(self, text):
        return [value for _start, _end, value in price.find_prices(text)]

    def test_reads_one_decimal_digit_as_thousands(self):
        self.assertEqual(self.cases("모듬전 13.0"), [13000])
        self.assertEqual(self.cases("서울생 3.5"), [3500])

    def test_reads_every_price_on_a_line(self):
        self.assertEqual(self.cases("생맥주 3.5/11.0/18.0"), [3500, 11000, 18000])

    def test_european_style_thousands_still_work(self):
        """"9.000"은 세 자리라 기존 규칙이 처리한다 — 9원이 아니라 9,000원이다."""
        self.assertEqual(self.cases("비빔밥 9.000"), [9000])

    def test_ordinary_prices_are_unaffected(self):
        self.assertEqual(self.cases("김치찌개 7,000원"), [7000])
        self.assertEqual(self.cases("갈비탕 15000"), [15000])


class FindPricesTests(unittest.TestCase):
    def test_finds_comma_formatted_price(self):
        result = price.find_prices("비빔밥9,000원")
        self.assertEqual([p for _, _, p in result], [9000])

    def test_finds_plain_digit_price(self):
        result = price.find_prices("비빔밥8000원")
        self.assertEqual([p for _, _, p in result], [8000])

    def test_finds_multiple_prices_in_order(self):
        result = price.find_prices("비빔밥9,000원김치찌개8,000원")
        self.assertEqual([p for _, _, p in result], [9000, 8000])

    def test_finds_price_written_without_won_suffix(self):
        """실제 메뉴판 대부분은 "원" 없이 숫자만 적는다 — 이것도 가격으로 잡아야 한다."""
        self.assertEqual([p for _, _, p in price.find_prices("비빔밥 9,000")], [9000])
        self.assertEqual([p for _, _, p in price.find_prices("비빔밥 9000")], [9000])

    def test_finds_price_with_won_symbol_prefix(self):
        result = price.find_prices("비빔밥 ₩9,000")
        self.assertEqual([p for _, _, p in result], [9000])

    def test_reads_dot_separator_as_thousands_separator(self):
        """OCR이 콤마를 마침표로 잘못 읽는 경우가 흔하다 — 9.000도 9,000으로 본다."""
        result = price.find_prices("비빔밥 9.000원")
        self.assertEqual([p for _, _, p in result], [9000])

    def test_ignores_phone_number(self):
        """하이픈으로 이어진 숫자열(전화번호)은 일부만 잘라내서 가격으로 쓰면 안 된다."""
        self.assertEqual(price.find_prices("문의 010-1234-5678"), [])
        self.assertEqual(price.find_prices("예약 02-123-4500"), [])

    def test_ignores_bare_number_that_is_not_a_round_price(self):
        """표시 없는 맨숫자는 100원 단위로 떨어질 때만 가격으로 본다 (좌석번호·연도 오탐 방지)."""
        self.assertEqual(price.find_prices("2026 신메뉴"), [])
        self.assertEqual(price.find_prices("테이블 1234"), [])

    def test_ignores_bare_number_below_minimum_price(self):
        """맨숫자 500원 미만은 수량·번호일 가능성이 커서 가격으로 보지 않는다."""
        self.assertEqual(price.find_prices("300 인분"), [])

    def test_still_reads_small_price_when_won_is_written(self):
        """"원"이 명시돼 있으면 작은 금액도 가격이다 — 표시가 곧 근거."""
        result = price.find_prices("공기밥 100원")
        self.assertEqual([p for _, _, p in result], [100])

    def test_ignores_too_short_digit_run(self):
        """두 자리 이하 숫자는 가격으로 보기엔 너무 작다(오탐 방지)."""
        result = price.find_prices("1번 세트 99원")
        # 3자리 미만 + 콤마 없음은 패턴에 안 걸린다
        self.assertEqual(result, [])


class ExtractPriceNearTests(unittest.TestCase):
    def test_extracts_price_immediately_after_food_name(self):
        self.assertEqual(price.extract_price_near("비빔밥9,000원", "비빔밥"), 9000)

    def test_returns_none_when_food_name_not_found(self):
        self.assertIsNone(price.extract_price_near("김치찌개8,000원", "비빔밥"))

    def test_returns_none_when_no_price_nearby(self):
        far_text = "비빔밥" + ("x" * 50) + "9,000원"
        self.assertIsNone(price.extract_price_near(far_text, "비빔밥"))

    def test_picks_nearest_price_when_multiple_foods_listed(self):
        """메뉴 여러 줄이 이어붙었을 때, 각 음식명에 붙은 가격만 정확히 골라야 한다."""
        text = "비빔밥9,000원김치찌개8,000원불고기12,000원"
        self.assertEqual(price.extract_price_near(text, "비빔밥"), 9000)
        self.assertEqual(price.extract_price_near(text, "김치찌개"), 8000)
        self.assertEqual(price.extract_price_near(text, "불고기"), 12000)

    def test_matches_each_food_to_its_own_price_without_won_suffix(self):
        """실제 메뉴판 형태(원 없이 숫자만, 공백 제거된 OCR 문자열)에서도 짝이 맞아야 한다."""
        text = "비빔밥9,000김치찌개8,000불고기12,000"
        self.assertEqual(price.extract_price_near(text, "비빔밥"), 9000)
        self.assertEqual(price.extract_price_near(text, "김치찌개"), 8000)
        self.assertEqual(price.extract_price_near(text, "불고기"), 12000)

    def test_finds_price_before_food_name_when_no_price_after(self):
        """"가격 음식명" 순서로 적힌 경우에도(드물지만) 앞쪽 가격을 찾아야 한다."""
        text = "9,000원비빔밥"
        self.assertEqual(price.extract_price_near(text, "비빔밥"), 9000)


class DigitLookalikeRepairTests(unittest.TestCase):
    """OCR이 숫자를 글자로 잘못 읽는 경우를 되돌린다 (0/O, 1/I/l, 5/S, 8/B ...).

    실제 관측 근거: eval/measure_ocr_final.json(실제 메뉴판 50장)의 OCR 원문에 '0I',
    's0' 같은 토큰이 남아 있고, eval/measure_digits.py 실행에서 '9,000'이 'C0'으로
    읽힌 사례가 나왔다.
    """

    def test_repairs_letters_inside_a_numeric_token(self):
        self.assertEqual(price.repair_digit_lookalikes("9,0O0"), "9,000")
        self.assertEqual(price.repair_digit_lookalikes("l2,000"), "12,000")
        # 맨 앞 글자가 오인식된 경우도 복원한다 — 뒤의 "000"이 숫자 덩어리임을 보증한다
        self.assertEqual(price.repair_digit_lookalikes("S,000"), "5,000")
        self.assertEqual(price.repair_digit_lookalikes("B,000"), "8,000")

    def test_leaves_words_alone(self):
        """멀쩡한 글자를 망치면 안 된다 — 숫자가 하나도 없는 덩어리는 건드리지 않는다."""
        for text in ("Bibimbap", "SOS", "Seoul", "비빔밥"):
            self.assertEqual(price.repair_digit_lookalikes(text), text)

    def test_repair_keeps_the_string_length(self):
        """find_prices()가 돌려주는 위치가 원본 기준이어야 하므로 길이가 변하면 안 된다."""
        for text in ("비빔밥 9,0O0원", "8OOO", "l6,000"):
            self.assertEqual(len(price.repair_digit_lookalikes(text)), len(text))

    def test_price_parser_recovers_a_misread_price(self):
        result = price.find_prices("비빔밥 9,0O0원")

        self.assertEqual([value for _s, _e, value in result], [9000])

    def test_reported_position_points_into_the_original_text(self):
        text = "비빔밥 9,0O0원"
        start, _end, _value = price.find_prices(text)[0]

        # 복원본이 아니라 원본에서 그 자리가 실제로 숫자 토큰의 시작이어야 한다
        self.assertEqual(text[start], "9")


class MatchPricesToNamesTests(unittest.TestCase):
    """좌표 기반 짝짓기 — 사진 위 위치를 보고 각 메뉴에 그 메뉴의 가격을 붙인다.

    상자는 (x, y, 폭, 높이, 글자). 글자는 공백이 제거된 상태로 들어온다
    (정규화는 src/ocr/match.py의 _normalize 하나로 통일).
    """

    def test_matches_price_printed_to_the_right_of_the_name(self):
        """가장 흔한 형태 — 이름 왼쪽, 가격 오른쪽."""
        boxes = [
            (40, 100, 90, 24, "비빔밥"),
            (340, 100, 70, 22, "9,000"),
            (40, 160, 110, 24, "김치찌개"),
            (340, 160, 70, 22, "8,000"),
        ]
        self.assertEqual(
            price.match_prices_to_names(boxes, ["비빔밥", "김치찌개"]),
            {"비빔밥": 9000, "김치찌개": 8000},
        )

    def test_matches_price_printed_on_the_line_below_the_name(self):
        """사진형 메뉴판 — 가격이 이름 바로 아래 줄에 있어도 찾아야 한다."""
        boxes = [
            (40, 100, 90, 24, "비빔밥"),
            (42, 132, 70, 22, "9,000"),
            (240, 100, 90, 24, "불고기"),
            (242, 132, 80, 22, "12,000"),
        ]
        self.assertEqual(
            price.match_prices_to_names(boxes, ["비빔밥", "불고기"]),
            {"비빔밥": 9000, "불고기": 12000},
        )

    def test_matches_price_two_lines_below_when_a_description_sits_between(self):
        """이름과 가격 사이에 설명 줄이 껴 있어도(다른 메뉴 이름만 아니면) 짝을 찾는다."""
        boxes = [
            (40, 100, 90, 24, "비빔밥"),
            (40, 130, 200, 20, "고소한나물비빔"),
            (40, 160, 70, 22, "9,000"),
        ]
        self.assertEqual(price.match_prices_to_names(boxes, ["비빔밥"]), {"비빔밥": 9000})

    def test_stops_at_the_next_dish_name_below(self):
        """아래로 내려가다 다른 메뉴 이름을 만나면 거기서 멈춘다 — 그 아래 가격은 그 메뉴 것."""
        boxes = [
            (40, 100, 90, 24, "비빔밥"),
            (40, 140, 90, 24, "불고기"),
            (40, 180, 80, 22, "12,000"),
        ]
        result = price.match_prices_to_names(boxes, ["비빔밥", "불고기"])
        self.assertEqual(result, {"불고기": 12000})

    def test_does_not_let_a_priceless_dish_steal_its_neighbour_price(self):
        """가격 하나는 메뉴 하나에만 붙는다 — 가까운 쪽이 먼저 가져간다."""
        boxes = [
            (40, 100, 90, 24, "떡볶이"),
            (40, 160, 90, 24, "불고기"),
            (340, 160, 80, 22, "12,000"),
        ]
        result = price.match_prices_to_names(boxes, ["떡볶이", "불고기"])
        self.assertEqual(result, {"불고기": 12000})

    def test_splits_two_menus_detected_inside_one_box(self):
        """detection이 한 줄을 상자 하나로 잡아도, 상자 안 좌우 순서로 짝을 가린다."""
        boxes = [(40, 100, 400, 24, "비빔밥9,000불고기12,000")]
        self.assertEqual(
            price.match_prices_to_names(boxes, ["비빔밥", "불고기"]),
            {"비빔밥": 9000, "불고기": 12000},
        )

    def test_matches_a_price_on_the_next_row_and_to_the_side(self):
        """이름과 가격이 **다른 행이면서 좌우로도 떨어진** 배치.

        같은 줄도 아니고 같은 칸도 아니라 기존 네 규칙 어디에도 안 걸려서 가격을 통째로
        놓쳤다. 메뉴판에서 흔한 배치다:
            등뼈찜
                        44,000
        """
        boxes = [(80, 100, 200, 40, "등뼈찜"), (600, 160, 150, 40, "44,000")]

        self.assertEqual(price.match_prices_to_names(boxes, ["등뼈찜"]), {"등뼈찜": 44000})

    def test_does_not_reach_past_another_dish_to_a_lower_price(self):
        """다음 행에 다른 메뉴가 있으면 그 가격은 그 메뉴 것이다 — 끌어오면 안 된다."""
        boxes = [
            (80, 100, 200, 40, "등뼈찜"),
            (80, 160, 220, 40, "해물부추전"),
            (600, 160, 150, 40, "15,000"),
        ]

        result = price.match_prices_to_names(boxes, ["등뼈찜", "해물부추전"])

        self.assertEqual(result, {"해물부추전": 15000})

    def test_same_row_price_wins_over_a_lower_one(self):
        """같은 줄에 가격이 있으면 그걸 쓴다 — 大/中/小처럼 아래에 가격이 더 있어도 마찬가지."""
        boxes = [
            (560, 220, 150, 40, "감자탕"),
            (830, 220, 160, 40, "39,000"),
            (830, 280, 160, 40, "34,000"),
        ]

        self.assertEqual(price.match_prices_to_names(boxes, ["감자탕"]), {"감자탕": 39000})

    def test_longer_dish_name_keeps_its_own_price(self):
        """"닭갈비" 상자 안에는 "갈비"도 들어있다 — 짧은 이름이 긴 이름의 가격을 가로채면 안 된다.

        회귀 방지: 고치기 전에는 갈비가 닭갈비의 12,000을 가져가고 닭갈비는 가격을 잃었다.
        """
        boxes = [
            (80, 100, 120, 40, "갈비"),
            (600, 100, 150, 40, "16,000"),
            (80, 170, 160, 40, "닭갈비"),
            (600, 170, 150, 40, "12,000"),
        ]

        result = price.match_prices_to_names(boxes, ["갈비", "닭갈비"])

        self.assertEqual(result, {"갈비": 16000, "닭갈비": 12000})

    def test_ignores_a_price_far_away_in_another_column(self):
        """세로로도 가로로도 안 겹치는(대각선 저 멀리) 가격은 남의 것이다."""
        boxes = [
            (40, 100, 90, 24, "비빔밥"),
            (600, 500, 80, 22, "12,000"),
        ]
        self.assertEqual(price.match_prices_to_names(boxes, ["비빔밥"]), {})

    def test_returns_empty_when_photo_shows_no_price(self):
        boxes = [(40, 100, 90, 24, "비빔밥"), (40, 160, 200, 24, "오늘의추천")]
        self.assertEqual(price.match_prices_to_names(boxes, ["비빔밥"]), {})


class TextBoxShapeTests(unittest.TestCase):
    """가격 매칭이 쓰는 상자 구조 — 좌표·신뢰도가 보존되는지."""

    def test_exposes_center_and_bbox(self):
        box = price.TextBox(40, 100, 200, 24, "비빔밥 9,000", 0.93)

        self.assertEqual((box.center_x, box.center_y), (140.0, 112.0))
        self.assertEqual(box.bbox, (40, 100, 240, 124))
        self.assertEqual(box.confidence, 0.93)

    def test_confidence_defaults_to_full(self):
        """신뢰도 없이 만든 상자(옛 호출부·테스트)는 점수를 깎지 않는다."""
        self.assertEqual(price.box_confidence(price.TextBox(0, 0, 10, 10, "가")), 1.0)
        self.assertEqual(price.box_confidence((0, 0, 10, 10, "가")), 1.0)
        self.assertEqual(price.box_confidence(None), 1.0)


class FormatPriceKrwTests(unittest.TestCase):
    def test_formats_with_won_sign_and_thousands_separator(self):
        self.assertEqual(price.format_price_krw(9000), "₩9,000")

    def test_formats_large_number_with_multiple_separators(self):
        self.assertEqual(price.format_price_krw(123456), "₩123,456")

    def test_returns_none_when_price_is_none(self):
        self.assertIsNone(price.format_price_krw(None))


if __name__ == "__main__":
    unittest.main()
