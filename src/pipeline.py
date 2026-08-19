"""Narration and TTS pipeline skeleton.

The OCR and UI layers are deliberately outside this module. Given a matched
``food_id``, this module connects text generation to TTS and returns one
UI-friendly response.
"""

from src.text_gen.narration import get_narration
from src.tts.infer import synthesize
from src.ocr.infer import recognize
from src.ocr.match import match_food
from src.text_gen.detail import get_details

def create_tts_response(food_id: int) -> dict[str, object]:
    """Create the text-and-audio response for one already-matched food.

    ``synthesize()`` now calls the real TTS model (see src/tts/infer.py),
    so ``narration_audio_path`` and ``tts_status`` reflect its actual result.
    """
    narration = get_narration(food_id)
    tts_result = synthesize(narration["text"], narration["style"])

    return {
        "narration_text": narration["text"],
        "style": narration["style"],
        "narration_audio_path": tts_result["audio_path"],
        "tts_status": tts_result["status"],
        "tts_latency_ms": tts_result["latency_ms"],
    }

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

