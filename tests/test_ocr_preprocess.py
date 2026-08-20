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

from src.ocr.preprocess import preprocess_image


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


if __name__ == "__main__":
    unittest.main()
