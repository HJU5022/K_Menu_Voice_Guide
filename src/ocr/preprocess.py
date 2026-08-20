"""OpenCV 전처리 — 메뉴판 이미지의 회전·대비·크기를 보정한다.

OCR에 넣기 전에 사진을 다듬는 단계. 기울어지거나 어두운 사진의 인식률을 올린다.
"""

import cv2
import numpy as np

TARGET_LONG_SIDE = 1600


def _deskew(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    coords = np.column_stack(np.where(thresh > 0))
    angle = cv2.minAreaRect(coords)[-1]

    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle

    (h, w) = image.shape[:2]
    center = (w // 2, h // 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(
        image, matrix, (w, h),
        flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE,
    )


def _enhance_contrast(image: np.ndarray) -> np.ndarray:
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l = clahe.apply(l)
    lab = cv2.merge((l, a, b))
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)


def _resize(image: np.ndarray, target_long_side: int = TARGET_LONG_SIDE) -> np.ndarray:
    h, w = image.shape[:2]
    scale = target_long_side / max(h, w)
    # INTER_AREA는 축소(decimation)에만 적합하다 — 원본이 target_long_side보다 작아 확대해야
    # 할 때 INTER_AREA를 쓰면 가는 글자 획이 뭉개져서 detection이 깨진다(실측: 확대 시
    # 검출 박스가 엉뚱한 곳에 잡히고 인식 신뢰도가 0에 가까워짐). 확대는 INTER_CUBIC을 쓴다.
    interpolation = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
    return cv2.resize(image, (int(w * scale), int(h * scale)), interpolation=interpolation)


def preprocess_image(image_path: str) -> np.ndarray:
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError(f"이미지를 불러올 수 없습니다: {image_path}")

    image = _deskew(image)
    image = _enhance_contrast(image)
    image = _resize(image)
    return image