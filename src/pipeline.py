"""Narration and TTS pipeline skeleton.

The OCR and UI layers are deliberately outside this module. Given a matched
``food_id``, this module connects text generation to TTS and returns one
UI-friendly response.
"""

from src.text_gen.narration import get_narration
from src.tts.infer import synthesize


def create_tts_response(food_id: int) -> dict[str, object]:
    """Create the text-and-audio response for one already-matched food.

    A real TTS model is not connected yet, so ``narration_audio_path`` is
    currently ``None`` and ``tts_status`` is ``"not_ready"``.
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
