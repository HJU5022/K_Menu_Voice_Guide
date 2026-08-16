"""파이프라인 — ocr / text_gen / tts 블록을 입출력 계약대로 순서대로 연결한다.

입력:  {image_path, selected_food}
출력:  {detail_text(6개), narration_text, narration_audio_path, latency_ms}

K_Menu_Talk.py(배포 진입점)는 이 파일만 호출한다.
블록끼리 서로 직접 import 하지 않고, 연결은 전부 여기서 한다.
"""

from src.db.supabase_client import client


def get_style(food_id: int) -> str:
    """narration.py의 style 계산과 동일한 방식. get_narration이 style을 안 돌려줘서 임시로 따로 조회한다."""
    result = client.table("foods").select("spice_level").eq("id", food_id).execute()
    spice_level = result.data[0]["spice_level"]
    return "CAUTION" if spice_level >= 4 else "GUIDE"

def mock_ocr(image_path: str) -> int:
    """진짜 OCR 대신 food_id를 고정값으로 반환한다."""
    return 25  # 매운탕


def mock_text_gen(food_name: str) -> dict:
    """진짜 텍스트생성 대신 카테고리별 텍스트 + 내레이션 텍스트를 고정값으로 반환한다."""
    return {
        "detail_text": {
            "pronunciation": "Tteok-bok-ki",
            "spicy": "Level 3 out of 5",
            "description": "Stir-fried rice cakes in spicy sauce",
            "ingredient": "Rice cake, gochujang, fish cake",
            "how_to_eat": "Eat hot, straight from the pan",
            "allergy": "Contains gluten",
        },
        "narration_text": "Careful, this one's spicy! Tteokbokki is a chewy rice cake dish.",
        "style": "CAUTION",
    }


def mock_tts(text: str, style: str) -> str:
    """진짜 TTS 대신 가짜 wav 경로를 반환한다."""
    return "output/fake_answer.wav"

from src.text_gen.narration import get_narration
from src.text_gen.detail import get_details


def run(image_path: str) -> dict:
    food_id = mock_ocr(image_path)

    detail_text = get_details(food_id)
    narration_text = get_narration(food_id)
    style = get_style(food_id)

    narration_audio_path = mock_tts(narration_text, style)

    return {
        "detail_text": detail_text,
        "narration_text": narration_text,
        "narration_audio_path": narration_audio_path,
        "latency_ms": None,
    }