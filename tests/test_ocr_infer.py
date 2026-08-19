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
