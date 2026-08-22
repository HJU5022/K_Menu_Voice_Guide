"""OCR 추론 — 파인튜닝된 모델로 이미지에서 한국어 글자를 추출한다.

배포 경로에서 실제로 쓰이는 쪽. 사용할 체크포인트 ID는 models/README.md 참고.

PaddleOCR의 export(배포용 정적 그래프 변환) 기능이 이 모델 구조(korean_PP-OCRv5_mobile_rec,
PPLCNetV3+MultiHead)에서 버그로 작동하지 않아(export_model.py, PaddleX main.py 양쪽 다 여러
Paddle 버전에서 재현됨 — 자세한 경위는 docs/specs/ocr-finetuning.md 참고), 원본 학습
체크포인트(.pdparams)를 PaddleOCR 저장소의 내부 코드(vendor/ppocr, Apache-2.0)로 직접
불러오는 방식으로 대체했다. detection은 기존처럼 파인튜닝 안 한 PaddleOCR 기본 모델을 쓴다.

vendor/ppocr 안의 __init__.py 몇 개는 우리가 안 쓰는 기능(CopyPaste 등)이 저장소 밖(tools/)을
참조하다 깨져서, 그 import만 지우고 가져왔다 — vendor/ppocr/README_VENDOR.md(있다면) 참고.
"""

import os
import re
import statistics
from typing import NamedTuple

os.environ.setdefault("FLAGS_allocator_strategy", "auto_growth")
# PP-OCRv5_mobile_det + oneDNN 조합에서 이 Paddle 버전(3.3.1)의 새 실행기가
# `ConvertPirAttribute2RuntimeAttribute not support` NotImplementedError로 죽는다
# (paddle/fluid/framework/new_executor/instruction/onednn/onednn_instruction.cc).
# oneDNN 가속을 기본으로 켜지 않게 해서 이 경로 자체를 피한다.
os.environ.setdefault("PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT", "False")

import cv2
import numpy as np
import paddle
from huggingface_hub import hf_hub_download
from paddleocr import PaddleOCR

from src.ocr.vendor.ppocr.data.imaug.operators import DecodeImage, KeepKeys
from src.ocr.vendor.ppocr.data.imaug.rec_img_aug import RecResizeImg
from src.ocr.vendor.ppocr.modeling.architectures import build_model
from src.ocr.vendor.ppocr.postprocess.rec_postprocess import CTCLabelDecode
from src.ocr.vendor.ppocr.utils.save_load import load_model
from src.ocr.preprocess import SourceMapping, preprocess_image_with_mapping
from src.ocr.price import TextBox, find_prices

OCR_MODEL_REPO_ID = "k-bite-team/K_Bite_OCR"

# 학습 때 쓴 아키텍처 그대로 — docs/specs/ocr-finetuning.md 참고
_ARCHITECTURE_CONFIG = {
    "model_type": "rec",
    "algorithm": "SVTR_LCNet",
    "Transform": None,
    "Backbone": {"name": "PPLCNetV3", "scale": 0.95},
    "Head": {
        "name": "MultiHead",
        "head_list": [
            {
                "CTCHead": {
                    "Neck": {
                        "name": "svtr",
                        "dims": 120,
                        "depth": 2,
                        "hidden_dims": 120,
                        "kernel_size": [1, 3],
                        "use_guide": True,
                    },
                    "Head": {"fc_decay": 0.00001},
                }
            },
            {"NRTRHead": {"nrtr_dim": 384, "max_text_length": 25}},
        ],
    },
}

_det_engine = None
_rec_model = None
_rec_ops = None
_rec_post_process = None


def _load_det_engine() -> PaddleOCR:
    """글자 위치 찾기(detection) — 파인튜닝 안 한 PaddleOCR 기본 모델(가벼운 버전) 그대로 사용."""
    global _det_engine
    if _det_engine is None:
        _det_engine = PaddleOCR(
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            text_detection_model_name="PP-OCRv5_mobile_det",
            lang="korean",
        )
    return _det_engine


def _load_rec_engine():
    """글자 읽기(recognition) — 우리가 파인튜닝한 원본 체크포인트를 직접 불러온다."""
    global _rec_model, _rec_ops, _rec_post_process
    if _rec_model is not None:
        return

    if not OCR_MODEL_REPO_ID:
        raise ValueError("OCR_MODEL_REPO_ID가 비어있다. HF Hub 업로드 후 채워야 한다.")

    weight_path = hf_hub_download(repo_id=OCR_MODEL_REPO_ID, filename="best_accuracy.pdparams")
    dict_path = hf_hub_download(repo_id=OCR_MODEL_REPO_ID, filename="dict.txt")

    _rec_post_process = CTCLabelDecode(character_dict_path=dict_path, use_space_char=True)

    char_num = len(_rec_post_process.character)
    architecture_config = dict(_ARCHITECTURE_CONFIG)
    architecture_config["Head"] = dict(_ARCHITECTURE_CONFIG["Head"])
    architecture_config["Head"]["out_channels_list"] = {
        "CTCLabelDecode": char_num,
        "SARLabelDecode": char_num + 2,
        "NRTRLabelDecode": char_num + 3,
    }

    _rec_model = build_model(architecture_config)
    pretrained_model = weight_path[: -len(".pdparams")]
    load_model({"Global": {"pretrained_model": pretrained_model, "checkpoints": None}}, _rec_model)
    _rec_model.eval()

    _rec_ops = [
        DecodeImage(img_mode="BGR", channel_first=False),
        RecResizeImg(image_shape=[3, 48, 320], infer_mode=True),
        KeepKeys(keep_keys=["image"]),
    ]


def _transform(data: dict) -> list:
    for op in _rec_ops:
        data = op(data)
        if data is None:
            return None
    return data


def _recognize_crop_with_score(image_bytes: bytes) -> tuple[str, float]:
    """이미 잘라낸 글자 영역 하나에서 글자와 신뢰도 점수를 읽는다."""
    _load_rec_engine()
    batch = _transform({"image": image_bytes})
    images = paddle.to_tensor(np.expand_dims(batch[0], axis=0))
    preds = _rec_model(images)
    result = _rec_post_process(preds)
    text, score = result[0]
    return text, score




# 이 값보다 세로/가로 비율이 크면(세로로 긴 조각) 글자가 90도 돌아간 세로 간판/배너로 보고
# 회전을 시도한다 — 인식 모델(RecResizeImg)이 가로 48x320 모양을 가정하기 때문에, 세로로
# 긴 조각을 그대로 넣으면 글자가 눌려서 뭉개진다.
_VERTICAL_ASPECT_RATIO = 1.5


def _recognize_vertical_crop(crop: np.ndarray) -> tuple[str, float]:
    """세로로 긴 조각은 90도 양쪽으로 돌려보고, 신뢰도 점수가 더 높은 쪽을 채택한다."""
    best_text, best_score = "", 0.0
    for rotation in (cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_90_COUNTERCLOCKWISE):
        rotated = cv2.rotate(crop, rotation)
        ok, buf = cv2.imencode(".jpg", rotated)
        if not ok:
            continue
        text, score = _recognize_crop_with_score(buf.tobytes())
        if score > best_score:
            best_text, best_score = text, score
    return best_text, best_score


_HANGUL = re.compile(r"[가-힣]")


def _better_reading(tuned: tuple[str, float], stock: tuple[str, float]) -> tuple[str, float]:
    """같은 글자 조각에 대한 두 인식 결과 중 하나를 고른다.

    우리가 파인튜닝한 모델은 한글 메뉴명에 맞춰 학습돼서 **숫자를 거의 못 읽는다** —
    깨끗하게 렌더한 "9,000"조차 "C.00"으로 읽는다(신뢰도 0.65). 반대로 detection 단계에서
    이미 함께 돌아가는 PaddleOCR 기본 인식기는 같은 가격을 0.9999로 정확히 읽고, 대신
    한글 메뉴명은 못 읽는다. 둘이 정확히 상보적이다.

    그래서 **한글이 없는 조각**(= 가격·수량)에서 기본 인식기가 더 확신하면 그쪽을 쓴다.
    한글이 섞인 조각은 조건 없이 파인튜닝 모델에 맡긴다 — 기본 인식기가 한글을 엉뚱한
    한자로 자신 있게 읽어버리는 경우가 있어서(실측: "김치찌개" -> "召大|", 0.855),
    점수만으로 비교하면 흐린 사진에서 이름을 망칠 수 있다.
    """
    tuned_text, tuned_score = tuned
    stock_text, stock_score = stock
    if stock_text and not _HANGUL.search(stock_text) and stock_score > tuned_score:
        return stock_text, stock_score
    return tuned_text, tuned_score


# 두 글자 상자를 같은 줄로 볼 세로 중심 허용 오차 — 큰 쪽 상자 높이에 대한 비율.
# 같은 줄에 있는 글자들은 세로 중심이 거의 일치하고, 다음 줄은 최소 한 줄 높이만큼
# 떨어져 있으므로 0.6이면 줄 간격이 좁은 메뉴판에서도 섞이지 않는다.
_ROW_CENTER_TOLERANCE = 0.6


def group_boxes_into_rows(boxes: list[TextBox]) -> list[str]:
    """(x, y, w, h, text) 글자 상자들을 줄 단위 문자열 목록으로 묶는다.

    detection이 돌려주는 상자 순서는 사람이 읽는 순서가 아니다. 그대로 이어붙이면
    "비빔밥" 바로 옆에 엉뚱한 줄의 "12,000"이 놓여서, 가격을 음식명에 짝지을 때
    다른 메뉴의 가격이 붙는다. 위→아래로 줄을 나누고 줄 안에서는 왼쪽→오른쪽으로
    정렬해 실제 읽기 순서로 되돌린다.
    """
    rows: list[list[TextBox]] = []
    for box in sorted(boxes, key=lambda b: b[1] + b[3] / 2):
        _x, y, _w, h, _text = box[:5]
        center = y + h / 2
        for row in rows:
            _anchor_x, anchor_y, _anchor_w, anchor_h, _anchor_text = row[0][:5]
            anchor_center = anchor_y + anchor_h / 2
            if abs(center - anchor_center) <= _ROW_CENTER_TOLERANCE * max(anchor_h, h):
                row.append(box)
                break
        else:
            rows.append([box])

    lines = []
    for row in rows:
        line = " ".join(box[4] for box in sorted(row, key=lambda b: b[0]) if box[4])
        if line:
            lines.append(line)
    return lines


class MenuLine(NamedTuple):
    """메뉴판 한 줄 — 같은 줄로 묶인 상자들을 이름 쪽과 가격 쪽으로 나눠 담는다."""

    boxes: list[TextBox]       # 왼쪽 -> 오른쪽 순
    text: str                  # 줄 전체 글자 (공백으로 이어붙임)
    name_boxes: list[TextBox]  # 가격으로 안 읽히는 조각 = 메뉴 이름 후보
    price_boxes: list[TextBox] # 가격으로 파싱되는 조각


def group_boxes_into_lines(boxes: list[TextBox]) -> list[MenuLine]:
    """상자를 줄로 묶고, 각 줄을 이름 영역과 가격 영역으로 나눈다.

    줄 묶기 허용 오차를 **상자 높이의 중앙값**에 비례시킨다. 고정 픽셀 값을 쓰면 사진
    해상도와 글자 크기에 따라 어떤 사진에서는 두 줄을 붙여버리고 다른 사진에서는 같은
    줄을 쪼갠다. 중앙값을 쓰는 이유는 평균과 달리 아주 크거나 작은 상자 하나에 끌려가지
    않기 때문이다(메뉴판에는 큰 제목과 작은 설명이 섞여 있다).

    이름/가격 구분은 위치가 아니라 **내용**으로 한다. 가격을 오른쪽에 적는 메뉴판이
    많지만 이름 아래에 적는 사진형 메뉴판도 있어서, "오른쪽 = 가격"으로 단정하면 후자를
    통째로 놓친다. 가격으로 파싱되는 조각만 가격으로 본다.
    """
    if not boxes:
        return []

    line_height = statistics.median(float(box[3]) for box in boxes)
    tolerance = _ROW_CENTER_TOLERANCE * line_height

    rows: list[list[TextBox]] = []
    for box in sorted(boxes, key=lambda b: b[1] + b[3] / 2):
        center = box[1] + box[3] / 2
        for row in rows:
            anchor = row[0]
            if abs(center - (anchor[1] + anchor[3] / 2)) <= tolerance:
                row.append(box)
                break
        else:
            rows.append([box])

    lines = []
    for row in rows:
        ordered = sorted(row, key=lambda b: b[0])
        text = " ".join(box[4] for box in ordered if box[4])
        if not text:
            continue
        price_boxes = [box for box in ordered if box[4] and find_prices(box[4])]
        name_boxes = [box for box in ordered if box[4] and not find_prices(box[4])]
        lines.append(MenuLine(boxes=ordered, text=text, name_boxes=name_boxes, price_boxes=price_boxes))
    return lines


def recognize_boxes_with_mapping(image_path: str) -> tuple[list[TextBox], SourceMapping]:
    """글자 상자 목록과, 그 좌표를 원본 사진 좌표로 되돌리는 방법을 함께 돌려준다.

    상자는 **전처리한 이미지** 기준 (x, y, w, h, text)다. 가격 짝짓기처럼 상자끼리의
    상대 위치만 보는 곳은 이대로 쓰면 되고, 사용자가 올린 사진 위에 그려야 하는 곳은
    mapping으로 원본 좌표로 옮겨야 한다(src/ocr/preprocess.py의 to_original_bbox).
    """
    image, mapping = preprocess_image_with_mapping(image_path)
    det_engine = _load_det_engine()

    det_results = det_engine.predict(image)
    if not det_results:
        return [], mapping

    detection = det_results[0]
    dt_polys = detection.get("dt_polys", [])
    # detection 파이프라인이 이미 함께 돌린 기본 인식기 결과. dt_polys와 같은 순서다.
    stock_texts = detection.get("rec_texts", [])
    stock_scores = detection.get("rec_scores", [])

    boxes = []
    for index, poly in enumerate(dt_polys):
        points = np.array(poly, dtype=np.int32)
        x, y, bw, bh = cv2.boundingRect(points)
        crop = image[y : y + bh, x : x + bw]

        if bh > bw * _VERTICAL_ASPECT_RATIO:
            tuned = _recognize_vertical_crop(crop)
        else:
            ok, buf = cv2.imencode(".jpg", crop)
            if not ok:
                continue
            tuned = _recognize_crop_with_score(buf.tobytes())

        stock = (
            stock_texts[index] if index < len(stock_texts) else "",
            stock_scores[index] if index < len(stock_scores) else 0.0,
        )
        text, confidence = _better_reading(tuned, stock)
        boxes.append(TextBox(x, y, bw, bh, text, confidence))

    return boxes, mapping


def recognize_boxes(image_path: str) -> list[TextBox]:
    """좌표 되돌리기가 필요 없을 때 쓰는 얇은 래퍼."""
    boxes, _mapping = recognize_boxes_with_mapping(image_path)
    return boxes


def recognize_lines(image_path: str) -> list[str]:
    """이미지에서 한국어 글자를 추출해 읽기 순서대로 **줄 단위** 목록으로 반환한다."""
    return group_boxes_into_rows(recognize_boxes(image_path))


def recognize(image_path: str) -> str:
    """이미지에서 한국어 글자를 추출해 하나의 문자열로 반환한다(줄은 공백으로 이어붙임)."""
    return " ".join(recognize_lines(image_path))
