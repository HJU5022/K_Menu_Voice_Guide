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
            patch.object(infer, "preprocess_image", return_value=processed_image) as mock_preprocess,
            patch.object(infer, "_load_det_engine", return_value=detector),
            patch.object(infer, "_recognize_crop", return_value="비빔밥"),
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
            patch.object(infer, "preprocess_image", side_effect=ValueError("이미지를 불러올 수 없습니다")),
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

        def fake_imencode(_ext, image):
            return True, image  # 실제 cv2.imencode처럼 .tobytes()를 가진 버퍼를 돌려준다

        def fake_recognize_with_score(image_bytes):
            # 시계방향으로 돌린 쪽만 신뢰도를 높게 준다 — 그쪽이 채택돼야 한다
            if image_bytes == cw_marker.tobytes():
                return "삼겹살", 0.95
            return "wrong", 0.10

        with (
            patch.object(infer, "preprocess_image", return_value=processed_image),
            patch.object(infer, "_load_det_engine", return_value=detector),
            patch.object(infer.cv2, "rotate", side_effect=fake_rotate),
            patch.object(infer.cv2, "imencode", side_effect=fake_imencode),
            patch.object(infer, "_recognize_crop_with_score", side_effect=fake_recognize_with_score),
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
            patch.object(infer, "preprocess_image", return_value=processed_image),
            patch.object(infer, "_load_det_engine", return_value=detector),
            patch.object(infer, "_recognize_crop", return_value="비빔밥") as mock_recognize_crop,
            patch.object(infer, "_recognize_crop_with_score") as mock_with_score,
        ):
            result = infer.recognize("menu.jpg")

        self.assertEqual(result, "비빔밥")
        mock_recognize_crop.assert_called_once()  # 그냥 한 번 읽고 끝
        mock_with_score.assert_not_called()       # 회전·비교 경로는 안 탔어야 한다
