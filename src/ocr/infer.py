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

from src.ocr.vendor.ppocr.data.imaug.operators import KeepKeys
from src.ocr.vendor.ppocr.data.imaug.rec_img_aug import RecResizeImg
from src.ocr.vendor.ppocr.modeling.architectures import build_model
from src.ocr.vendor.ppocr.postprocess.rec_postprocess import CTCLabelDecode
from src.ocr.vendor.ppocr.utils.save_load import load_model
from src.ocr.preprocess import SourceMapping, preprocess_image_with_mapping
from src.ocr.price import TextBox

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

    # DecodeImage를 빼두었다. 넣으면 잘라낸 조각을 JPEG로 압축했다가 곧바로 다시 푸는
    # 왕복이 생기는데, 조각은 이미 메모리 위의 BGR 배열이라 그 왕복이 통째로 낭비다.
    _rec_ops = [
        RecResizeImg(image_shape=[3, 48, 320], infer_mode=True),
        KeepKeys(keep_keys=["image"]),
    ]


def _transform(data: dict) -> list:
    """학습 때 쓰던 전처리 단계들을 순서대로 통과시킨다.

    중간에 어느 단계가 None을 주면 그대로 None을 돌려준다 — ppocr의 관례로, "이 조각은
    쓸 수 없다"는 뜻이다. 호출부가 그 조각을 건너뛴다.

    학습과 **같은** 전처리를 써야 한다. 크기·정규화 방식이 다르면 같은 사진에서도
    다른 값이 나와 정확도가 조용히 떨어진다.
    """
    for op in _rec_ops:
        data = op(data)
        if data is None:
            return None
    return data


# 한 번의 forward에 몰아넣을 조각 수. 조각은 전부 [3,48,320]로 맞춰지므로 그냥 쌓으면 된다.
#
# 무한정 키우지 않는 이유는 메모리다 — 조각 하나가 약 180KB(3*48*320*4바이트)라
# 32개면 6MB 남짓이고, 메뉴판 한 장의 조각 수(실측 92~161개)를 몇 번에 나눠 처리한다.
_REC_BATCH_SIZE = 32


def _recognize_crops(crops: list[np.ndarray]) -> list[tuple[str, float]]:
    """잘라낸 글자 조각 여러 개를 **한 번에** 읽는다. 입력 순서 그대로 돌려준다.

    조각마다 따로 부르면 forward를 조각 수만큼 하게 된다(실측: 92개 조각에 16.8초).
    크기가 [3,48,320]로 고정이라 그냥 쌓아서 한 번에 넣을 수 있다.

    전처리에 실패한 조각은 ("", 0.0)으로 채워 자리를 지킨다 — 입력과 출력의 길이가
    같아야 부르는 쪽이 원래 조각과 짝지을 수 있다.
    """
    if not crops:
        return []

    _load_rec_engine()

    prepared = [_transform({"image": crop}) for crop in crops]
    results: list[tuple[str, float] | None] = [None] * len(crops)

    # 같은 크기끼리 묶는다. 리사이즈(resize_norm_img_chinese)는 폭을 48*max(320/48, w/h)로
    # 잡아서, 아주 납작한 조각(가로/세로 > 6.67)만 320보다 넓어진다. 대부분은 320이라
    # 한 묶음으로 들어가고, 나머지는 작은 묶음이 된다.
    #
    # 폭을 억지로 맞추지 않는 이유는 결과를 바꾸지 않기 위해서다 — 오른쪽에 여백을 더
    # 붙이면 모델이 보는 그림 자체가 달라진다.
    groups: dict[tuple, list[int]] = {}
    for index, item in enumerate(prepared):
        if item is None:
            results[index] = ("", 0.0)
            continue
        groups.setdefault(item[0].shape, []).append(index)

    for indices in groups.values():
        for start in range(0, len(indices), _REC_BATCH_SIZE):
            chunk = indices[start : start + _REC_BATCH_SIZE]
            images = paddle.to_tensor(np.stack([prepared[index][0] for index in chunk], axis=0))
            preds = _rec_model(images)
            decoded = _rec_post_process(preds)
            for position, index in enumerate(chunk):
                results[index] = decoded[position]

    return [result if result is not None else ("", 0.0) for result in results]


def _recognize_crop_with_score(image_bytes: bytes) -> tuple[str, float]:
    """JPEG 바이트 하나를 읽는다 — eval 스크립트처럼 바이트를 들고 있는 호출부용이다.

    추론 경로는 이 함수를 쓰지 않는다. 거기서는 조각이 이미 배열이라 압축할 이유가 없다.
    """
    crop = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if crop is None:
        return "", 0.0
    return _recognize_crops([crop])[0]




# 이 값보다 세로/가로 비율이 크면(세로로 긴 조각) 글자가 90도 돌아간 세로 간판/배너로 보고
# 회전을 시도한다 — 인식 모델(RecResizeImg)이 가로 48x320 모양을 가정하기 때문에, 세로로
# 긴 조각을 그대로 넣으면 글자가 눌려서 뭉개진다.
_VERTICAL_ASPECT_RATIO = 1.5


def _rotated_pair(crop: np.ndarray) -> list[np.ndarray]:
    """세로로 긴 조각을 시계·반시계로 돌린 두 장. 어느 쪽이 바로 선 것인지 모르기 때문이다."""
    return [
        cv2.rotate(crop, cv2.ROTATE_90_CLOCKWISE),
        cv2.rotate(crop, cv2.ROTATE_90_COUNTERCLOCKWISE),
    ]


def _recognize_vertical_crop(crop: np.ndarray) -> tuple[str, float]:
    """세로로 긴 조각은 90도 양쪽으로 돌려보고, 신뢰도 점수가 더 높은 쪽을 채택한다."""
    readings = _recognize_crops(_rotated_pair(crop))
    return max(readings, key=lambda reading: reading[1], default=("", 0.0))


_HANGUL = re.compile(r"[가-힣]")


# 파인튜닝 인식을 건너뛰어도 되는 기준 점수.
#
# 기본 인식기가 한글 없는 글자를 이만큼 확신하면, 파인튜닝 모델을 돌려봐야 그 결과는
# _better_reading()에서 어차피 버려진다. 그런 조각에서 두 번째 인식은 순수한 낭비다.
#
# 값을 낮추면 더 많이 건너뛰어 빨라지지만, 기본 인식기가 **한글을 한자로 잘못 읽은**
# 조각까지 확정해버릴 위험이 커진다(실측: "김치찌개" -> "召大|", 0.855). 그 사례보다
# 확실히 위에 두어야 이름을 잃지 않는다.
_STOCK_TRUSTED_SCORE = 0.95


def _stock_is_trustworthy(stock: tuple[str, float]) -> bool:
    """기본 인식기 결과만으로 확정해도 되는 조각인지 — 파인튜닝 인식을 건너뛸지 판단한다.

    한글이 없다는 것만으로는 부족하다. 기본 인식기는 한글을 한자·기호로 바꿔 읽고도
    높은 점수를 주는 일이 있어서, 점수까지 함께 봐야 이름 조각을 놓치지 않는다.
    """
    text, score = stock
    return bool(text) and not _HANGUL.search(text) and score >= _STOCK_TRUSTED_SCORE


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


# 두 글자 상자를 같은 줄로 볼 세로 중심 허용 오차 — 상자 높이 중앙값에 대한 비율.
# 같은 줄에 있는 글자들은 세로 중심이 거의 일치하고, 다음 줄은 최소 한 줄 높이만큼
# 떨어져 있으므로 0.6이면 줄 간격이 좁은 메뉴판에서도 섞이지 않는다.
_ROW_CENTER_TOLERANCE = 0.6


def group_boxes_into_row_groups(boxes: list[TextBox]) -> list[list[TextBox]]:
    """글자 상자들을 줄 단위로 묶되, **상자 그대로** 돌려준다.

    [group_boxes_into_rows]가 문자열만 돌려주면 줄마다 가격·신뢰도·좌표를 다시 쓸 수
    없다. 줄 단위 매칭(src/ocr/match.py의 match_food_candidates_by_line)이 그 정보를
    필요로 해서 상자를 살린 버전을 따로 둔다. 줄을 나누는 규칙은 아래 문자열 버전과
    같고, 실제로 그쪽이 이 함수를 감싼다 — 규칙이 두 벌로 갈라지지 않게 하기 위함이다.

    허용 오차는 **그 사진에 있는 상자 높이의 중앙값**에 건다. 예전에는
    그 줄을 처음 연 상자와 지금 상자 중 큰 쪽 높이(max)에 걸었는데, 그러면 같은 규칙이
    아니었다. "(2인기준)" 같은 작은 첨자(높이 19)가 줄을 먼저 열면 오차가 그 상자 크기로
    좁아져서, 정작 그 메뉴의 가격 상자(높이 37)가 아래 줄로 밀려난다. 밀려난 자리에는
    옆 칸 메뉴의 가격만 남아 그것이 메뉴에 붙었다(실측: 낙지볶음 35,000 -> 20,000).
    중앙값은 상자 하나가 크거나 작다고 흔들리지 않아 줄을 여는 순서와 무관하다.

    고정 픽셀 값을 안 쓰는 이유도 같은 자리에 적어둔다. 사진 해상도와 글자 크기가
    제각각이라, 고정값을 쓰면 어떤 사진에서는 두 줄이 붙고 다른 사진에서는 한 줄이
    쪼개진다. 평균이 아니라 중앙값인 이유는 메뉴판에 큰 제목과 작은 설명이 섞여
    있어서다 — 평균은 그런 극단값 하나에 끌려간다.
    """
    if not boxes:
        return []

    tolerance = _ROW_CENTER_TOLERANCE * statistics.median(float(box[3]) for box in boxes)

    rows: list[list[TextBox]] = []
    for box in sorted(boxes, key=lambda b: b[1] + b[3] / 2):
        _x, y, _w, h, _text = box[:5]
        center = y + h / 2
        for row in rows:
            _anchor_x, anchor_y, _anchor_w, anchor_h, _anchor_text = row[0][:5]
            anchor_center = anchor_y + anchor_h / 2
            if abs(center - anchor_center) <= tolerance:
                row.append(box)
                break
        else:
            rows.append([box])

    # 줄 안에서는 왼쪽 → 오른쪽 순서로 되돌린다.
    return [sorted(row, key=lambda b: b[0]) for row in rows]


def row_text(row: list[TextBox]) -> str:
    """줄 하나를 읽기 순서 그대로 이어붙인다."""
    return " ".join(box[4] for box in row if box[4])


def group_boxes_into_rows(boxes: list[TextBox]) -> list[str]:
    """(x, y, w, h, text) 글자 상자들을 줄 단위 문자열 목록으로 묶는다.

    detection이 돌려주는 상자 순서는 사람이 읽는 순서가 아니다. 그대로 이어붙이면
    "비빔밥" 바로 옆에 엉뚱한 줄의 "12,000"이 놓여서, 가격을 음식명에 짝지을 때
    다른 메뉴의 가격이 붙는다. 위→아래로 줄을 나누고 줄 안에서는 왼쪽→오른쪽으로
    정렬해 실제 읽기 순서로 되돌린다.
    """
    lines = [row_text(row) for row in group_boxes_into_row_groups(boxes)]
    return [line for line in lines if line]


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

    # 1단계 — 조각을 훑으면서 "파인튜닝 인식이 필요한 것"만 모은다. 아직 읽지 않는다.
    #
    # 읽기를 뒤로 미루는 이유는 한 번에 몰아서 넣기 위해서다. 조각마다 바로 읽으면
    # forward를 조각 수만큼 하게 된다.
    placements: list[tuple[int, int, int, int, tuple[str, float]]] = []
    pending_crops: list[np.ndarray] = []
    # placements의 몇 번째가 pending_crops의 어디서 어디까지를 쓰는지. 세로 조각은 두 장이다.
    pending_spans: dict[int, tuple[int, int]] = {}

    for index, poly in enumerate(dt_polys):
        points = np.array(poly, dtype=np.int32)
        x, y, bw, bh = cv2.boundingRect(points)

        stock = (
            stock_texts[index] if index < len(stock_texts) else "",
            stock_scores[index] if index < len(stock_scores) else 0.0,
        )

        # 기본 인식기 결과를 먼저 본다. 가격·수량처럼 한글이 없고 확신이 높은 조각은
        # 파인튜닝 모델을 돌려도 그 답이 아래 _better_reading()에서 버려지므로,
        # 두 번째 인식을 통째로 생략한다. 메뉴판은 절반 가까이가 이런 조각이다.
        if _stock_is_trustworthy(stock):
            placements.append((x, y, bw, bh, stock))
            continue

        crop = image[y : y + bh, x : x + bw]
        # 세로로 긴 조각은 어느 쪽으로 돌려야 바로 서는지 몰라 두 장을 다 넣는다.
        crops = _rotated_pair(crop) if bh > bw * _VERTICAL_ASPECT_RATIO else [crop]

        start = len(pending_crops)
        pending_crops.extend(crops)
        pending_spans[len(placements)] = (start, start + len(crops))
        placements.append((x, y, bw, bh, stock))

    # 2단계 — 모아둔 조각을 한 번에 읽는다.
    readings = _recognize_crops(pending_crops)

    # 3단계 — 원래 순서대로 되돌려 놓는다.
    boxes = []
    for position, (x, y, bw, bh, stock) in enumerate(placements):
        span = pending_spans.get(position)
        if span is None:
            # 기본 인식기만으로 확정한 조각.
            text, confidence = stock
        else:
            start, end = span
            tuned = max(readings[start:end], key=lambda reading: reading[1], default=("", 0.0))
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
