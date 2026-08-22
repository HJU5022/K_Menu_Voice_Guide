"""preprocess_image의 이미지 읽기 로직 테스트.

cv2.imread는 Windows에서 한글 등 비ASCII 경로를 못 읽는 버그가 있어
np.fromfile + cv2.imdecode로 바꿨다 — 이 테스트는 그 구현이 정상 이미지에서
여전히 잘 동작하는지, 그리고 못 읽는 경우 기존과 같은 ValueError를 내는지 확인한다.
(Windows 전용 버그라 이 macOS/Linux 환경에서 원래 버그 자체는 재현되지 않는다.)

**왜 이런 버그가 생기나**: cv2.imread는 파일 경로를 내부적으로 ASCII로만 다뤄서,
경로에 한글이 섞이면(예: C:\\Users\\만득\\...) 파일을 못 찾고 조용히 None을 돌려준다.
에러도 안 나서 원인을 찾기 어렵다. 그래서 파일을 바이트로 먼저 읽고(np.fromfile),
그 바이트를 이미지로 해석하는(cv2.imdecode) 두 단계로 나눴다 — 파일 읽기는
파이썬이 하므로 경로에 한글이 있어도 문제없다.

실행: python -m pytest tests/test_ocr_preprocess.py
"""

import os
import tempfile
import unittest

import cv2
import numpy as np

from src.ocr import preprocess
from src.ocr.preprocess import SourceMapping, preprocess_image, preprocess_image_with_mapping, to_original_bbox


class PreprocessImageTests(unittest.TestCase):
    def test_reads_valid_image(self):
        """정상 이미지는 그대로 잘 읽히는지 — 버그 고치면서 멀쩡하던 동작을 깨뜨리지 않았는지 확인."""
        # 50x80 크기의 회색(200) 단색 이미지를 만든다 — 내용은 중요하지 않고 읽히기만 하면 된다
        image = np.full((50, 80, 3), 200, dtype=np.uint8)
        fd, path = tempfile.mkstemp(suffix=".jpg")
        os.close(fd)
        try:
            cv2.imwrite(path, image)
            result = preprocess_image(path)
            self.assertIsInstance(result, np.ndarray)
            self.assertEqual(result.ndim, 3)
        finally:
            os.remove(path)

    def test_raises_file_not_found_for_missing_file(self):
        """없는 경로를 주면 FileNotFoundError."""
        # np.fromfile이 존재하지 않는 경로에서 먼저 FileNotFoundError를 낸다
        # (기존 cv2.imread 방식은 이 경우도 ValueError였음 — np.fromfile로 바꾸며
        # 생긴 의도된 동작 변화. 실제로는 방금 저장한 파일을 바로 읽는 상황이라
        # 이 케이스가 거의 발생하지 않아 우선순위 낮음).
        with self.assertRaises(FileNotFoundError):
            preprocess_image("/no/such/path/menu.jpg")

    def test_raises_value_error_for_non_image_file(self):
        """파일은 있는데 이미지가 아니면 ValueError — 깨진 사진이 들어와도 조용히 넘어가면 안 된다."""
        fd, path = tempfile.mkstemp(suffix=".jpg")
        os.close(fd)
        try:
            # 확장자만 .jpg이고 내용은 그냥 글자인 파일을 만든다
            with open(path, "wb") as f:
                f.write(b"not an image")
            with self.assertRaises(ValueError):
                preprocess_image(path)
        finally:
            os.remove(path)


class DeskewTests(unittest.TestCase):
    """_deskew() — 기울어진 사진을 펴되, 안 기울어진 사진은 건드리지 않아야 한다.

    회귀 방지: minAreaRect의 각도 범위가 OpenCV 4.5에서 (0, 90]으로 바뀌었는데 코드가
    예전 음수 규약을 가정하고 있어서, **똑바로 찍은 페이지를 90도 눕혀버렸다.**
    그러면 가로쓰기 글줄이 세로 상자로 검출돼 음식명이 통째로 뭉개진다.
    """

    def _text_like_image(self, tilt_degrees=0):
        """가로로 긴 글줄 세 개를 흉내낸 이미지. 기울기를 판별할 수 있을 만큼만 단순하게."""
        image = np.full((300, 600, 3), 255, dtype=np.uint8)
        for row in (60, 150, 240):
            cv2.rectangle(image, (80, row), (520, row + 26), (0, 0, 0), -1)
        if tilt_degrees:
            matrix = cv2.getRotationMatrix2D((300, 150), tilt_degrees, 1.0)
            image = cv2.warpAffine(
                image, matrix, (600, 300), flags=cv2.INTER_CUBIC, borderValue=(255, 255, 255)
            )
        return image

    def _widest_run(self, image):
        """가장 넓은 검은 덩어리의 (폭, 높이) — 글줄이 가로로 누워있는지 보는 지표."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY_INV)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        boxes = [cv2.boundingRect(c) for c in contours]
        _x, _y, width, height = max(boxes, key=lambda b: b[2] * b[3])
        return width, height

    def test_leaves_a_straight_page_horizontal(self):
        """안 기울어진 페이지의 글줄은 보정 뒤에도 가로로 남아야 한다(세로로 서면 안 된다)."""
        deskewed, _matrix = preprocess._deskew(self._text_like_image())

        width, height = self._widest_run(deskewed)
        self.assertGreater(width, height)

    def test_straightens_a_tilted_page(self):
        """기울어진 페이지는 편다 — 보정 뒤 글줄이 보정 전보다 더 납작해야 한다."""
        tilted = self._text_like_image(tilt_degrees=7)
        before_width, before_height = self._widest_run(tilted)

        deskewed, _matrix = preprocess._deskew(tilted)
        after_width, after_height = self._widest_run(deskewed)

        self.assertGreater(after_width / after_height, before_width / before_height)

    def test_returns_a_matrix_that_can_be_inverted(self):
        """되돌리기(to_original_bbox)가 이 행렬을 쓴다 — 2x3 affine이어야 한다."""
        _deskewed, matrix = preprocess._deskew(self._text_like_image())

        self.assertEqual(matrix.shape, (2, 3))


class ToOriginalBboxTests(unittest.TestCase):
    """OCR 상자 좌표를 원본 사진 기준 비율로 되돌리는 함수.

    OCR은 전처리(회전 + 크기 조정)를 거친 이미지에서 글자를 찾는다. 그 좌표를 사용자가
    올린 사진 위에 그대로 그리면 어긋나므로, 전처리를 되돌려야 상자가 실제 글자 위에 앉는다.
    """

    def _mapping(self, angle_degrees=0.0, scale=1.0, width=1000, height=800):
        rotation = cv2.getRotationMatrix2D((width // 2, height // 2), angle_degrees, 1.0)
        return SourceMapping(
            inverse_rotation=cv2.invertAffineTransform(rotation),
            scale=scale,
            width=width,
            height=height,
        )

    def test_returns_ratios_not_pixels(self):
        """프론트가 사진을 어떤 크기로 그리든 쓸 수 있도록 0~1 비율로 돌려준다."""
        left, top, width, height = to_original_bbox(self._mapping(), 100, 200, 300, 80)

        self.assertAlmostEqual(left, 0.1)
        self.assertAlmostEqual(top, 0.25)
        self.assertAlmostEqual(width, 0.3)
        self.assertAlmostEqual(height, 0.1)

    def test_undoes_the_resize(self):
        """전처리에서 2배로 키웠으면, 상자 좌표도 절반으로 되돌려야 원본 위치가 된다."""
        left, top, width, _height = to_original_bbox(self._mapping(scale=2.0), 200, 400, 600, 160)

        self.assertAlmostEqual(left, 0.1)
        self.assertAlmostEqual(top, 0.25)
        self.assertAlmostEqual(width, 0.3)

    def test_undoes_the_deskew_rotation(self):
        """기울기 보정을 되돌린다 — 회전을 무시하면 기운 사진일수록 상자가 밀린다."""
        mapping = self._mapping(angle_degrees=10.0)
        # 회전 중심(사진 한가운데)은 회전해도 제자리다 — 여기를 기준으로 검증한다.
        left, top, width, height = to_original_bbox(mapping, 480, 380, 40, 40)

        self.assertAlmostEqual(left + width / 2, 0.5, places=2)
        self.assertAlmostEqual(top + height / 2, 0.5, places=2)

    def test_clamps_boxes_that_fall_outside_the_original_photo(self):
        """회전 보정 때 가장자리가 사진 밖으로 밀릴 수 있다 — 0~1을 벗어난 상자는 잘라낸다."""
        left, top, width, height = to_original_bbox(self._mapping(), -50, -50, 200, 200)

        self.assertGreaterEqual(left, 0.0)
        self.assertGreaterEqual(top, 0.0)
        self.assertLessEqual(left + width, 1.0)
        self.assertLessEqual(top + height, 1.0)

    def test_mapping_records_the_original_photo_size(self):
        """되돌리려면 원본 크기를 알아야 한다 — 전처리로 바뀐 크기가 아니라 올린 사진 크기."""
        image = np.full((50, 80, 3), 200, dtype=np.uint8)
        fd, path = tempfile.mkstemp(suffix=".jpg")
        os.close(fd)
        try:
            cv2.imwrite(path, image)
            processed, mapping = preprocess_image_with_mapping(path)
        finally:
            os.remove(path)

        self.assertEqual((mapping.width, mapping.height), (80, 50))
        # 긴 변을 1600에 맞추므로 전처리 결과는 원본보다 커진다 — 배율도 그걸 반영해야 한다
        self.assertGreater(mapping.scale, 1.0)
        self.assertNotEqual(processed.shape[:2], (50, 80))


if __name__ == "__main__":
    unittest.main()
