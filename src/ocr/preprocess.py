"""OpenCV 전처리 — 메뉴판 이미지의 회전·대비·크기를 보정한다.

OCR에 넣기 전에 사진을 다듬는 단계. 기울어지거나 어두운 사진의 인식률을 올린다.

전처리는 사진의 모양을 바꾸므로(회전 + 크기 조정), OCR이 찾은 글자 상자 좌표는
전처리한 이미지 기준이다. 그 좌표를 사용자가 올린 원본 사진 위에 그대로 그리면
어긋나기 때문에, 되돌리는 방법을 SourceMapping으로 같이 넘긴다.
"""

from typing import NamedTuple

import cv2
import numpy as np

TARGET_LONG_SIDE = 1600


class SourceMapping(NamedTuple):
    """전처리 이미지 좌표 -> 원본 사진 좌표로 되돌리기 위한 정보."""

    inverse_rotation: np.ndarray  # 2x3 affine — deskew 회전을 되돌린다
    scale: float                  # 원본 -> 전처리 배율 (가로세로 동일)
    width: int                    # 원본 사진 폭(px)
    height: int                   # 원본 사진 높이(px)


def to_original_bbox(
    mapping: SourceMapping, x: int, y: int, width: int, height: int
) -> tuple[float, float, float, float]:
    """전처리 좌표계의 글자 상자를 원본 사진 기준 (left, top, width, height) 비율로 바꾼다.

    0~1 비율로 돌려주는 이유: 프론트가 사진을 어떤 크기로 그리든 그대로 쓸 수 있어야 한다.

    회전을 되돌리면 상자가 기울어지므로 네 꼭짓점을 각각 옮긴 뒤 그것들을 감싸는
    수평 상자를 쓴다 — 기운 사진일수록 상자가 실제 글자보다 조금 커진다.
    """
    corners = np.array(
        [[x, y], [x + width, y], [x + width, y + height], [x, y + height]],
        dtype=np.float64,
    ) / mapping.scale
    mapped = np.hstack([corners, np.ones((4, 1))]) @ mapping.inverse_rotation.T

    left, top = mapped.min(axis=0)
    right, bottom = mapped.max(axis=0)

    # 회전 보정 과정에서 가장자리가 사진 밖으로 밀려날 수 있어 0~1로 자른다.
    left = min(max(left / mapping.width, 0.0), 1.0)
    right = min(max(right / mapping.width, 0.0), 1.0)
    top = min(max(top / mapping.height, 0.0), 1.0)
    bottom = min(max(bottom / mapping.height, 0.0), 1.0)
    return left, top, right - left, bottom - top


def _deskew(image: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """기울기를 펴고, 되돌릴 때 쓸 회전 행렬을 함께 돌려준다."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    coords = np.column_stack(np.where(thresh > 0))
    angle = cv2.minAreaRect(coords)[-1]

    # minAreaRect의 각도는 90도마다 같은 사각형을 가리키므로, 수평 기준 편차(-45~45도)로
    # 접어야 한다. 이 정규화가 없으면 **똑바로 찍은 사진일수록 크게 망가진다**:
    # OpenCV 4.5부터 각도 범위가 (0, 90]으로 바뀌어 정면 페이지가 89.7도로 나오는데,
    # 예전 음수 규약을 가정한 분기는 이걸 -89.7도로 읽고 페이지를 통째로 눕혀버렸다.
    # 그러면 가로쓰기 글줄이 세로 상자로 검출돼 음식명이 통째로 뭉개진다(실측 확인).
    angle %= 90
    if angle > 45:
        angle -= 90

    (h, w) = image.shape[:2]
    center = (w // 2, h // 2)
    # 측정된 기울기만큼 반대로 돌려 편다.
    matrix = cv2.getRotationMatrix2D(center, -angle, 1.0)
    rotated = cv2.warpAffine(
        image, matrix, (w, h),
        flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE,
    )
    return rotated, matrix


def _enhance_contrast(image: np.ndarray) -> np.ndarray:
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l = clahe.apply(l)
    lab = cv2.merge((l, a, b))
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)


def _resize(image: np.ndarray, target_long_side: int = TARGET_LONG_SIDE) -> tuple[np.ndarray, float]:
    """긴 변을 target_long_side에 맞추고, 되돌릴 때 쓸 배율을 함께 돌려준다."""
    h, w = image.shape[:2]
    scale = target_long_side / max(h, w)
    # INTER_AREA는 축소(decimation)에만 적합하다 — 원본이 target_long_side보다 작아 확대해야
    # 할 때 INTER_AREA를 쓰면 가는 글자 획이 뭉개져서 detection이 깨진다(실측: 확대 시
    # 검출 박스가 엉뚱한 곳에 잡히고 인식 신뢰도가 0에 가까워짐). 확대는 INTER_CUBIC을 쓴다.
    interpolation = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
    return cv2.resize(image, (int(w * scale), int(h * scale)), interpolation=interpolation), scale


def preprocess_image_with_mapping(image_path: str) -> tuple[np.ndarray, SourceMapping]:
    """전처리한 이미지와, 그 좌표를 원본 사진 좌표로 되돌리는 방법을 함께 돌려준다."""
    # cv2.imread는 Windows에서 한글 등 비ASCII 경로를 못 읽는다(항상 None 반환).
    # 파일을 바이트로 직접 읽어 메모리에서 디코딩하면 경로 인코딩과 무관해진다.
    data = np.fromfile(image_path, dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"이미지를 불러올 수 없습니다: {image_path}")

    original_height, original_width = image.shape[:2]

    image, rotation = _deskew(image)
    image = _enhance_contrast(image)
    image, scale = _resize(image)

    mapping = SourceMapping(
        inverse_rotation=cv2.invertAffineTransform(rotation),
        scale=scale,
        width=original_width,
        height=original_height,
    )
    return image, mapping


def preprocess_image(image_path: str) -> np.ndarray:
    """전처리한 이미지만 필요할 때 쓰는 얇은 래퍼."""
    image, _mapping = preprocess_image_with_mapping(image_path)
    return image