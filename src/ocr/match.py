"""RapidFuzz 매칭 — 추출된 글자를 등록 음식명 30개와 유사도 비교한다.

OCR이 글자를 조금 틀리게 읽어도 가장 비슷한 등록 음식으로 이어주는 단계.
유사도 임계값은 docs/specs/ocr-finetuning.md에서 정한다.
"""

from rapidfuzz import fuzz

from src.db.supabase_client import client

MATCH_THRESHOLD = 70


def _normalize(text: str) -> str:
    return text.replace(" ", "")


def match_food(text: str) -> dict | None:
    normalized_text = _normalize(text)
    foods = client.table("foods").select("id, name_kr").execute().data

    best_food = None
    best_score = 0
    for food in foods:
        name = _normalize(food["name_kr"])
        if name not in normalized_text and normalized_text not in name:
            continue
        score = fuzz.partial_ratio(normalized_text, name)
        if score > best_score:
            best_score = score
            best_food = food

    if best_food is None or best_score < MATCH_THRESHOLD:
        return None

    return {"food_id": best_food["id"], "name_kr": best_food["name_kr"], "score": best_score}