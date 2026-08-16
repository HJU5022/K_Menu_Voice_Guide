"""OCR 추론 — 파인튜닝된 모델로 이미지에서 한국어 글자를 추출한다.

배포 경로에서 실제로 쓰이는 쪽. 사용할 체크포인트 ID는 models/README.md 참고.
"""

from huggingface_hub import snapshot_download
from paddleocr import PaddleOCR

# TODO: OCR 체크포인트를 Hugging Face Hub에 올린 뒤, models/README.md에 기록하고 여기에도 채운다.
# 예: "your-username/kmenu-ocr-rec"
OCR_MODEL_REPO_ID = ""

# TODO: prepare_dataset.py가 만드는 커스텀 딕셔너리 파일 경로 — 지금은 개인 절대경로에
# 하드코딩돼 있어서(백로그 3번), 그거 정리되면 이 경로도 맞춰서 고쳐야 한다.
CUSTOM_DICT_PATH = ""

_ocr_engine = None


def _load_ocr_engine() -> PaddleOCR:
    """모델을 한 번만 불러오고, 그다음부터는 이미 불러온 걸 재사용한다."""
    global _ocr_engine
    if _ocr_engine is not None:
        return _ocr_engine

    if not OCR_MODEL_REPO_ID:
        raise ValueError("OCR_MODEL_REPO_ID가 비어있다. HF Hub 업로드 후 채워야 한다.")

    model_dir = snapshot_download(repo_id=OCR_MODEL_REPO_ID)

    _ocr_engine = PaddleOCR(
        rec_model_dir=model_dir,          # 파인튜닝한 recognition 모델
        rec_char_dict_path=CUSTOM_DICT_PATH,
        use_angle_cls=False,
        lang="korean",
        # det_model_dir은 일부러 안 넣음 — detection은 파인튜닝 안 했으니 PaddleOCR 기본 모델 그대로 사용
    )
    return _ocr_engine


def recognize(image_path: str) -> str:
    """이미지에서 한국어 글자를 추출해 반환한다."""
    engine = _load_ocr_engine()
    result = engine.ocr(image_path, cls=False)
    texts = [line[1][0] for line in result[0]] if result and result[0] else []
    return " ".join(texts)