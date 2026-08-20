"""Narration and TTS pipeline skeleton.

The OCR and UI layers are deliberately outside this module. Given a matched
``food_id``, this module connects text generation to TTS and returns one
UI-friendly response.
"""

import json
import os
import subprocess
from pathlib import Path

from src.text_gen.narration import get_narration
from src.ocr.infer import recognize
from src.ocr.match import match_food, match_food_candidates
from src.text_gen.detail import get_details

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# torch(TTS)는 이 프로세스가 이미 로드한 paddle(OCR)과 같은 venv/프로세스에 못 올라간다 —
# paddleocr → paddlex → modelscope가 내부적으로 torch를 끌어오는데, paddle이 먼저 로드한
# 네이티브 DLL과 얽혀 torch의 shm.dll 로딩이 깨진다(Windows, WinError 127). 그래서 TTS는
# torch만 깔린 별도 venv(.venv-tts)의 파이썬으로 완전히 다른 자식 프로세스에서 실행한다.
# 이 환경변수로 실제 경로를 다르게 지정할 수 있다(팀원마다 venv 위치가 다를 수 있어서).
_TTS_PYTHON = os.environ.get("TTS_VENV_PYTHON") or str(_PROJECT_ROOT / ".venv-tts" / "Scripts" / "python.exe")


def _synthesize_via_subprocess(text: str, style: str) -> dict[str, object]:
    """TTS(torch)를 별도 venv의 자식 프로세스(``src/tts/worker.py``)에서 실행한다."""
    try:
        completed = subprocess.run(
            [_TTS_PYTHON, "-m", "src.tts.worker"],
            input=json.dumps({"text": text, "style": style}),
            capture_output=True,
            text=True,
            cwd=_PROJECT_ROOT,
            timeout=300,
        )
        return json.loads(completed.stdout)
    except Exception:
        return {"audio_path": None, "status": "not_ready", "latency_ms": 0.0}


def create_tts_response(food_id: int) -> dict[str, object]:
    """Create the text-and-audio response for one already-matched food.

    TTS 합성이 실패해도(GPU 없음, 모델 로딩 실패, 자식 프로세스 크래시 등) 텍스트 응답까지
    막지 않는다 — narration_text/style은 그대로 반환하고 tts_status만 "not_ready"로 남긴다
    (README 9절 "TTS 생성 실패 | 상세 텍스트 우선 출력" 참고).
    """
    narration = get_narration(food_id)
    tts_result = _synthesize_via_subprocess(narration["text"], narration["style"])

    return {
        "narration_text": narration["text"],
        "style": narration["style"],
        "narration_audio_path": tts_result.get("audio_path"),
        "tts_status": tts_result.get("status", "not_ready"),
        "tts_latency_ms": tts_result.get("latency_ms", 0.0),
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
