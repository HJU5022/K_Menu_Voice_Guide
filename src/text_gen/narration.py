"""내레이션 텍스트 — spice_level로 style(GUIDE/CAUTION)을 정하고 문장을 조회한다.

매운 정도에 따라 안내 톤이 달라진다. 여기서 정한 style이 src/tts/로 넘어간다.
경계값은 docs/specs/text-generation.md에서 정한다.
"""

from src.db.supabase_client import client


def get_narration(food_id: int) -> dict[str, str]:
    """Return the narration text and the TTS style for one food."""
    food_result = client.table("foods").select("spice_level").eq("id", food_id).execute()
    if not food_result.data:
        raise ValueError(f"food_id {food_id}에 대한 foods 데이터가 없습니다.")

    spice_level = food_result.data[0]["spice_level"]
    if not isinstance(spice_level, int):
        raise ValueError(f"food_id {food_id}의 spice_level이 숫자가 아닙니다.")
    style = "CAUTION" if spice_level >= 4 else "GUIDE"

    narration_result = (
        client.table("food_narration")
        .select("narration_text")
        .eq("food_id", food_id)
        .eq("style", style)
        .execute()
    )
    if not narration_result.data:
        raise ValueError(f"food_id {food_id}, style {style}에 대한 narration이 없습니다.")

    narration_text = narration_result.data[0]["narration_text"].strip()
    if not narration_text:
        raise ValueError(f"food_id {food_id}, style {style}의 narration_text가 비어 있습니다.")

    return {"text": narration_text, "style": style}
