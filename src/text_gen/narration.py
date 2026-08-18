"""내레이션 텍스트 — spice_level로 style(GUIDE/CAUTION)을 정하고, 문장 3개를 이어붙인다.

매운 정도에 따라 안내 톤이 달라진다. 여기서 정한 style이 src/tts/로 넘어간다.
경계값은 docs/specs/text-generation.md에서 정한다.

narration_text(food_narration) + PRONUNCIATION(food_details) + ALLERGY(food_details)를
순서대로 이어붙여 반환한다. 셋 다 이미 완성된 문장이라 새로 생성하지 않고 그대로 조합만 한다.
"""

from src.db.supabase_client import client

_NARRATION_DETAIL_CATEGORIES = ("PRONUNCIATION", "ALLERGY")


def get_narration(food_id: int) -> dict[str, str]:
    """Return the combined narration text and the TTS style for one food."""
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

    details_result = (
        client.table("food_details")
        .select("category, detail_text")
        .eq("food_id", food_id)
        .in_("category", _NARRATION_DETAIL_CATEGORIES)
        .execute()
    )
    details_by_category = {row["category"]: row["detail_text"].strip() for row in details_result.data}

    sentences = [narration_text]
    for category in _NARRATION_DETAIL_CATEGORIES:
        detail_text = details_by_category.get(category)
        if not detail_text:
            raise ValueError(f"food_id {food_id}의 {category}가 없습니다.")
        sentences.append(detail_text)

    return {"text": " ".join(sentences), "style": style}
