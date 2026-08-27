"""OCR 추론 테스트 — src/ocr/infer.py의 recognize()가 글자를 뽑는 흐름을 확인한다.

recognize()의 순서는 이렇다:
  전처리(preprocess_image) → 글자 상자 찾기(detection) → 상자별로 글자 읽기(recognition)

실제 PaddleOCR 모델은 부르지 않는다(GPU·모델 파일이 필요하므로). Mock으로 "이런 상자를
찾았다"고 가짜 답을 주고, **흐름과 분기만** 검사한다.

특히 중요한 것 — **세로쓰기 처리**: 인식 모델은 가로로 긴 조각(48x320)을 가정해서 만들어져
있다. 세로 간판처럼 위아래로 긴 글자 조각을 그대로 넣으면 글자가 눌려서 못 읽는다.
그래서 세로/가로 비율이 크면 좌우 양쪽으로 90도 돌려보고 신뢰도가 높은 쪽을 채택한다.
아래 두 테스트(rotates_tall_narrow / skips_rotation_for_normal)가 그 분기를 지킨다.

실행: python -m pytest tests/test_ocr_infer.py
"""

import unittest
from unittest.mock import Mock, patch

import numpy as np

from src.ocr import infer
from src.ocr.preprocess import SourceMapping

# recognize()는 좌표 되돌리기 정보를 그냥 흘려보내기만 한다(쓰는 쪽은 src/pipeline.py).
# 그래서 아래 테스트들은 "안 건드리는 값"으로 이걸 넘긴다.
IDENTITY_MAPPING = SourceMapping(
    inverse_rotation=np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]),
    scale=1.0,
    width=100,
    height=100,
)


class OcrInferTests(unittest.TestCase):
    def test_recognize_runs_detection_on_preprocessed_image(self):
        """detection에 넣는 이미지가 '전처리를 거친' 것이어야 한다 (원본을 그대로 넣으면 안 됨).

        전처리(회전·대비·크기 보정)를 건너뛰면 인식률이 떨어진다. 실제로 전처리가
        추론 경로에 연결되지 않았던 적이 있어서, 이 연결을 테스트로 고정해둔 것이다.
        """
        raw_image = np.zeros((20, 20, 3), dtype=np.uint8)
        processed_image = np.full((30, 30, 3), 255, dtype=np.uint8)
        detector = Mock()
        detector.predict.return_value = [
            {"dt_polys": [np.array([[2, 2], [12, 2], [12, 12], [2, 12]])]}
        ]

        with (
            patch.object(
                infer, "preprocess_image_with_mapping", return_value=(processed_image, IDENTITY_MAPPING)
            ) as mock_preprocess,
            patch.object(infer, "_load_det_engine", return_value=detector),
            patch.object(infer, "_recognize_crops", return_value=[("비빔밥", 1.0)]),
            patch.object(infer.cv2, "imread", return_value=raw_image) as mock_imread,
        ):
            result = infer.recognize("menu.jpg")

        self.assertEqual(result, "비빔밥")
        mock_preprocess.assert_called_once_with("menu.jpg")
        # cv2.imread를 직접 쓰면 전처리를 건너뛴 것 = 버그. 그래서 "안 불렸는지"를 검사한다
        mock_imread.assert_not_called()
        # detection에 들어간 게 원본(raw_image)이 아니라 전처리 결과(processed_image)여야 한다
        detector.predict.assert_called_once_with(processed_image)

    def test_recognize_propagates_preprocess_value_error(self):
        """전처리가 실패하면 거기서 멈추고 에러를 그대로 올려보낸다 — 무거운 모델을 안 띄우기 위해."""
        with (
            patch.object(
                infer, "preprocess_image_with_mapping", side_effect=ValueError("이미지를 불러올 수 없습니다")
            ),
            patch.object(infer, "_load_det_engine") as mock_load_det_engine,
            patch.object(infer.cv2, "imread") as mock_imread,
        ):
            with self.assertRaisesRegex(ValueError, "이미지를 불러올 수 없습니다"):
                infer.recognize("missing.jpg")

        mock_imread.assert_not_called()
        mock_load_det_engine.assert_not_called()

    def test_recognize_rotates_tall_narrow_crop_and_prefers_higher_score(self):
        """세로로 긴 조각은 양쪽으로 돌려보고, 신뢰도가 높은 쪽 결과를 채택하는지.

        세로쓰기 간판을 못 읽던 버그의 회귀 방지 테스트다. 어느 방향으로 돌려야 맞는지는
        미리 알 수 없어서(간판이 시계/반시계 어느 쪽으로 쓰였는지 모름), 둘 다 시도하고
        모델이 더 자신 있어 하는(신뢰도 높은) 쪽을 고른다.
        """
        processed_image = np.full((100, 100, 3), 255, dtype=np.uint8)
        detector = Mock()
        # 세로로 긴 상자(폭 10, 높이 60) — 세로쓰기 간판을 흉내냄
        detector.predict.return_value = [
            {"dt_polys": [np.array([[5, 0], [15, 0], [15, 60], [5, 60]])]}
        ]

        # 실제 이미지 회전 대신 "표식"만 쓴다 — 어느 방향으로 돌린 결과인지 구분만 되면 되므로
        cw_marker = np.array([[1]])   # 시계방향으로 돌린 결과
        ccw_marker = np.array([[2]])  # 반시계방향으로 돌린 결과

        def fake_rotate(_crop, rotation_code):
            return cw_marker if rotation_code == infer.cv2.ROTATE_90_CLOCKWISE else ccw_marker

        def fake_recognize_crops(crops):
            # 시계방향으로 돌린 쪽만 신뢰도를 높게 준다 — 그쪽이 채택돼야 한다
            return [
                ("삼겹살", 0.95) if crop is cw_marker else ("wrong", 0.10) for crop in crops
            ]

        with (
            patch.object(
                infer, "preprocess_image_with_mapping", return_value=(processed_image, IDENTITY_MAPPING)
            ),
            patch.object(infer, "_load_det_engine", return_value=detector),
            patch.object(infer.cv2, "rotate", side_effect=fake_rotate),
            patch.object(infer, "_recognize_crops", side_effect=fake_recognize_crops),
        ):
            result = infer.recognize("menu.jpg")

        self.assertEqual(result, "삼겹살")

    def test_recognize_skips_rotation_for_normal_wide_crop(self):
        """반대 경우 — 평범한 가로 조각은 돌리지 않고 한 번만 읽는다.

        모든 조각을 다 돌려보면 인식을 두 번씩 하게 돼서 느려진다. 세로로 긴 것만
        골라서 돌리는지 확인하는 테스트다.
        """
        processed_image = np.full((100, 100, 3), 255, dtype=np.uint8)
        detector = Mock()
        # 일반적인 가로 상자(폭 60, 높이 10)
        detector.predict.return_value = [
            {"dt_polys": [np.array([[0, 0], [60, 0], [60, 10], [0, 10]])]}
        ]

        with (
            patch.object(
                infer, "preprocess_image_with_mapping", return_value=(processed_image, IDENTITY_MAPPING)
            ),
            patch.object(infer, "_load_det_engine", return_value=detector),
            patch.object(
                infer, "_recognize_crops", return_value=[("비빔밥", 1.0)]
            ) as mock_recognize,
            patch.object(infer.cv2, "rotate") as mock_rotate,
        ):
            result = infer.recognize("menu.jpg")

        self.assertEqual(result, "비빔밥")
        # 조각 하나만 넘어가야 한다 — 회전본까지 넣었으면 두 장이 된다
        self.assertEqual(len(mock_recognize.call_args.args[0]), 1)
        mock_rotate.assert_not_called()       # 회전·비교 경로는 안 탔어야 한다


class GroupBoxesIntoLinesTests(unittest.TestCase):
    """group_boxes_into_lines() — 줄로 묶고 각 줄을 이름 영역/가격 영역으로 나눈다."""

    def test_splits_a_line_into_name_and_price(self):
        boxes = [
            (600, 100, 140, 40, "9,000"),
            (70, 102, 200, 40, "비빔밥"),
        ]

        lines = infer.group_boxes_into_lines(boxes)

        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].text, "비빔밥 9,000")
        self.assertEqual([b[4] for b in lines[0].name_boxes], ["비빔밥"])
        self.assertEqual([b[4] for b in lines[0].price_boxes], ["9,000"])

    def test_keeps_separate_rows_apart(self):
        boxes = [
            (70, 100, 200, 40, "비빔밥"),
            (600, 100, 140, 40, "9,000"),
            (70, 260, 200, 40, "불고기"),
            (600, 260, 150, 40, "12,000"),
        ]

        lines = infer.group_boxes_into_lines(boxes)

        self.assertEqual([line.text for line in lines], ["비빔밥 9,000", "불고기 12,000"])

    def test_tolerance_scales_with_box_height(self):
        """허용 오차가 고정 픽셀이면, 글자가 큰 사진에서 같은 줄이 쪼개진다.

        아래 두 상자는 세로 중심이 30px 어긋나 있다. 글자 높이가 40일 때는 다른 줄이고,
        글자 높이가 200일 때는(고해상도 사진) 같은 줄이어야 한다.
        """
        small = [(70, 100, 200, 40, "비빔밥"), (600, 130, 140, 40, "9,000")]
        large = [(70, 100, 400, 200, "비빔밥"), (600, 130, 300, 200, "9,000")]

        self.assertEqual(len(infer.group_boxes_into_lines(small)), 2)
        self.assertEqual(len(infer.group_boxes_into_lines(large)), 1)

    def test_price_below_the_name_stays_on_its_own_line(self):
        """사진형 메뉴판(이름 아래 가격)에서는 줄이 나뉜다.

        그래서 이름-가격 연결을 줄 단위 좌우 규칙에만 맡기면 안 된다 — 실제 연결은
        src/ocr/price.py의 match_prices_to_names()가 위·아래 배치까지 함께 본다.
        """
        boxes = [(70, 100, 200, 40, "비빔밥"), (72, 170, 140, 40, "9,000")]

        lines = infer.group_boxes_into_lines(boxes)

        self.assertEqual(len(lines), 2)
        self.assertEqual([b[4] for b in lines[0].name_boxes], ["비빔밥"])
        self.assertEqual([b[4] for b in lines[1].price_boxes], ["9,000"])

    def test_returns_nothing_for_no_boxes(self):
        self.assertEqual(infer.group_boxes_into_lines([]), [])


class BetterReadingTests(unittest.TestCase):
    """_better_reading() — 파인튜닝 인식기와 PaddleOCR 기본 인식기 중 하나를 고른다.

    둘은 상보적이다(실측): 파인튜닝 모델은 한글 메뉴명을 1.00으로 읽지만 "9,000"을
    "C.00"(0.65)으로 흘리고, 기본 모델은 "9,000"을 0.9999로 읽지만 "김치찌개"를
    "召大|"(0.855)로 읽는다.
    """

    def test_takes_the_stock_reading_for_a_price(self):
        """숫자 조각은 기본 인식기 쪽이 훨씬 확신하므로 그쪽을 쓴다."""
        self.assertEqual(
            infer._better_reading(("C.00", 0.65), ("9,000", 0.9999)), ("9,000", 0.9999)
        )

    def test_keeps_the_tuned_reading_for_a_korean_name(self):
        """한글 조각은 파인튜닝 모델에 맡긴다 — 이쪽이 이 모델의 학습 목적이다."""
        self.assertEqual(
            infer._better_reading(("김치찌개", 1.0), ("", 0.0)), ("김치찌개", 1.0)
        )

    def test_never_lets_a_confident_stock_reading_overwrite_hangul(self):
        """기본 인식기가 한글을 한자로 자신 있게 잘못 읽어도 넘겨주지 않는다.

        점수만 비교하면 흐린 사진에서 파인튜닝 모델 신뢰도가 떨어질 때 이름이 통째로
        엉뚱한 글자로 바뀐다. 한글이 섞인 결과는 조건 없이 파인튜닝 쪽을 쓴다.
        """
        self.assertEqual(
            infer._better_reading(("김치찌개", 0.62), ("김大|", 0.98)), ("김치찌개", 0.62)
        )

    def test_ignores_an_empty_stock_reading(self):
        self.assertEqual(infer._better_reading(("순대", 0.4), ("", 0.99)), ("순대", 0.4))


class GroupBoxesIntoRowsTests(unittest.TestCase):
    """group_boxes_into_rows() — 글자 상자를 실제 읽기 순서(줄 단위)로 되돌리는 함수.

    detection이 상자를 돌려주는 순서는 읽기 순서가 아니다. 이 정렬이 없으면 음식명 옆에
    엉뚱한 줄의 가격이 놓여서, 메뉴에 없는 금액이 붙는다(src/ocr/price.py).
    """

    def test_groups_boxes_on_the_same_line_and_sorts_left_to_right(self):
        # 같은 줄(y=100)에 있지만 detection이 오른쪽(가격)을 먼저 돌려준 상황
        boxes = [
            (300, 100, 60, 20, "9,000"),
            (10, 102, 80, 20, "비빔밥"),
        ]
        self.assertEqual(infer.group_boxes_into_rows(boxes), ["비빔밥 9,000"])

    def test_splits_separate_lines_top_to_bottom(self):
        """줄이 다르면 나눠야 한다 — 그래야 2번째 줄 가격이 1번째 음식에 안 붙는다."""
        boxes = [
            (10, 200, 80, 20, "불고기"),
            (300, 100, 60, 20, "9,000"),
            (300, 200, 60, 20, "12,000"),
            (10, 100, 80, 20, "비빔밥"),
        ]
        self.assertEqual(
            infer.group_boxes_into_rows(boxes),
            ["비빔밥 9,000", "불고기 12,000"],
        )

    def test_keeps_slightly_misaligned_boxes_on_one_line(self):
        """사진이 살짝 기울어 상자 높이가 조금씩 어긋나도 같은 줄로 봐야 한다."""
        boxes = [
            (10, 100, 80, 24, "비빔밥"),
            (300, 106, 60, 18, "9,000"),
        ]
        self.assertEqual(infer.group_boxes_into_rows(boxes), ["비빔밥 9,000"])

    def test_accepts_boxes_that_carry_a_confidence(self):
        """recognize_boxes()는 신뢰도까지 붙인 6개짜리 상자를 준다 — 여기서 깨지면 안 된다.

        회귀 방지: 좌표만 쓰는 자리들이 상자를 5개로 언패킹하고 있어서, 신뢰도가 붙는
        순간 ValueError로 파이프라인 전체가 죽었다. 테스트가 5개짜리만 넘기고 있어
        못 잡았던 케이스다.
        """
        boxes = [
            (300, 100, 60, 20, "9,000", 0.91),
            (10, 100, 80, 22, "비빔밥", 0.99),
        ]

        self.assertEqual(infer.group_boxes_into_rows(boxes), ["비빔밥 9,000"])

    def test_drops_empty_text_boxes(self):
        """아무 글자도 못 읽은 상자는 빈 줄을 만들지 않는다."""
        boxes = [(10, 100, 80, 20, ""), (10, 200, 80, 20, "비빔밥")]
        self.assertEqual(infer.group_boxes_into_rows(boxes), ["비빔밥"])

    def test_small_subscript_opening_a_row_keeps_the_price_on_that_row(self):
        """작은 첨자가 줄을 먼저 열어도 그 줄의 가격 상자가 밀려나면 안 된다.

        허용 오차를 "그 줄을 연 상자와 지금 상자 중 큰 쪽 높이"에 걸면, "(2인기준)"처럼
        작은 첨자(높이 19)가 줄을 열었을 때 그 줄의 중심이 첨자 쪽으로 당겨진다. 그러면
        정작 그 메뉴의 가격(높이 37)은 오차 22.2px 밖으로 나가 아래 줄로 떨어지고,
        남은 자리에 옆 칸 가격이 붙는다(실측: 낙지볶음 35,000 -> 20,000). 상자 높이의
        중앙값(48)에 걸면 오차가 28.8px이 되어 같은 줄에 남는다.

        줄 단위 매칭(src/ocr/match.py)도 같은 줄 묶기를 쓰므로 여기서 고정해둔다.
        """
        boxes = [
            (100, 496, 200, 48, "낙지볶음"),    # 중심 520
            (320, 499, 110, 19, "(2인기준)"),   # 중심 508.5 — 가장 위라 이 줄을 연다
            (700, 515, 170, 37, "35,000"),     # 중심 533.5 — 첨자와 25px 차이
            (100, 616, 240, 48, "코다리회무침"),
            (700, 622, 170, 37, "20,000"),
            (100, 736, 120, 48, "공기밥"),
            (400, 736, 160, 48, "해물추가"),
        ]

        self.assertEqual(
            infer.group_boxes_into_rows(boxes),
            ["낙지볶음 (2인기준) 35,000", "코다리회무침 20,000", "공기밥 해물추가"],
        )

    def test_returns_nothing_for_no_boxes(self):
        """상자가 하나도 없으면 중앙값을 낼 것이 없다 — 빈 목록으로 끝낸다."""
        self.assertEqual(infer.group_boxes_into_row_groups([]), [])
        self.assertEqual(infer.group_boxes_into_rows([]), [])
