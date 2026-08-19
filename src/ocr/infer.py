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

os.environ.setdefault("FLAGS_allocator_strategy", "auto_growth")

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
from src.ocr.preprocess import preprocess_image

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


def _recognize_crop(image_bytes: bytes) -> str:
    """이미 잘라낸 글자 영역 하나에서 글자를 읽는다."""
    _load_rec_engine()
    batch = _transform({"image": image_bytes})
    images = paddle.to_tensor(np.expand_dims(batch[0], axis=0))
    preds = _rec_model(images)
    result = _rec_post_process(preds)
    text, _score = result[0]
    return text


def recognize(image_path: str) -> str:
    """이미지에서 한국어 글자를 추출해 반환한다."""
    image = preprocess_image(image_path)
    det_engine = _load_det_engine()

    det_results = det_engine.predict(image)
    if not det_results:
        return ""

    dt_polys = det_results[0].get("dt_polys", [])
    texts = []
    for poly in dt_polys:
        points = np.array(poly, dtype=np.int32)
        x, y, bw, bh = cv2.boundingRect(points)
        crop = image[y : y + bh, x : x + bw]
        ok, buf = cv2.imencode(".jpg", crop)
        if not ok:
            continue
        texts.append(_recognize_crop(buf.tobytes()))

    return " ".join(t for t in texts if t)
