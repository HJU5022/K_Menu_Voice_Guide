import unittest
from unittest.mock import Mock, patch

import numpy as np

from src.ocr import infer


class OcrInferTests(unittest.TestCase):
    def test_recognize_runs_detection_on_preprocessed_image(self):
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
        mock_imread.assert_not_called()
        detector.predict.assert_called_once_with(processed_image)

    def test_recognize_propagates_preprocess_value_error(self):
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
        processed_image = np.full((100, 100, 3), 255, dtype=np.uint8)
        detector = Mock()
        # 세로로 긴 상자(폭 10, 높이 60) — 세로쓰기 간판을 흉내냄
        detector.predict.return_value = [
            {"dt_polys": [np.array([[5, 0], [15, 0], [15, 60], [5, 60]])]}
        ]

        cw_marker = np.array([[1]])
        ccw_marker = np.array([[2]])

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
        mock_recognize_crop.assert_called_once()
        mock_with_score.assert_not_called()
