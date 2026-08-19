"""Narration and TTS pipeline skeleton.

The OCR and UI layers are deliberately outside this module. Given a matched
``food_id``, this module connects text generation to TTS and returns one
UI-friendly response.
"""

from src.text_gen.narration import get_narration
from src.tts.infer import synthesize
from src.ocr.infer import recognize
from src.ocr.match import match_food, match_food_candidates
from src.text_gen.detail import get_details

def create_tts_response(food_id: int) -> dict[str, object]:
    """Create the text-and-audio response for one already-matched food.

    ``synthesize()`` now calls the real TTS model (see src/tts/infer.py),
    so ``narration_audio_path`` and ``tts_status`` reflect its actual result.

    TTS 합성이 실패해도(GPU 없음, 모델 로딩 실패 등) 텍스트 응답까지 막지 않는다 —
    narration_text/style은 그대로 반환하고 tts_status만 "not_ready"로 남긴다
    (README 9절 "TTS 생성 실패 | 상세 텍스트 우선 출력" 참고).
    """
    narration = get_narration(food_id)
    try:
        tts_result = synthesize(narration["text"], narration["style"])
    except Exception:
        tts_result = {"audio_path": None, "status": "not_ready", "latency_ms": 0.0}

    return {
        "narration_text": narration["text"],
        "style": narration["style"],
        "narration_audio_path": tts_result["audio_path"],
        "tts_status": tts_result["status"],
        "tts_latency_ms": tts_result["latency_ms"],
    }


def analyze_image(image_path: str) -> dict:
    """Return OCR analysis status and food candidates without creating a response."""
    ocr_text = recognize(image_path).strip()
    if not ocr_text:
        return {"status": "ocr_empty", "ocr_text": "", "candidates": []}

    candidates = match_food_candidates(ocr_text)
    if not candidates:
        return {"status": "unsupported_food", "ocr_text": ocr_text, "candidates": []}

    return {"status": "candidates_found", "ocr_text": ocr_text, "candidates": candidates}


def run(image_path: str) -> dict:
    """이미지 하나를 받아 OCR → 매칭 → 텍스트생성 → TTS까지 이어서 최종 응답을 만든다."""
    text = recognize(image_path)
    match_result = match_food(text)
    if match_result is None:
        return {"matched_food": None}

    food_id = match_result["food_id"]
    response = create_tts_response(food_id)
    response["matched_food"] = match_result
    response["details"] = get_details(food_id)
    return response
