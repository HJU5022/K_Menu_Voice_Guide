"""RapidFuzz 매칭 — 추출된 글자를 등록 음식명 50개와 유사도 비교한다.

OCR이 글자를 조금 틀리게 읽어도 가장 비슷한 등록 음식으로 이어주는 단계.
유사도 임계값은 docs/specs/ocr-finetuning.md에서 정한다.

메뉴 텍스트에 붙는 맵기·재료 수식어(예: "매운닭발")는 menu_modifiers 테이블 기준으로 매칭 후
따로 뽑아낸다. partial_ratio는 부분 문자열도 점수 100이 나오기 때문에 매칭 자체엔 수식어를
지울 필요가 없다 — 그냥 매칭된 음식명에 그 단어가 이미 들어있는 경우만(예: "매운탕"의 "매운")
수식어 목록에서 제외한다.
"""

from rapidfuzz import fuzz

from src.db import cache

MATCH_THRESHOLD = 70

# 5단계 맵기 스케일 — 거의 안 바뀌는 값이라 DB 대신 상수로 둔다.
SPICE_TIERS = {
    1: {"label_en": "Mild", "emoji": "🌶️", "reference_pepper": "Jalapeño", "shu": 5000},
    2: {"label_en": "Medium", "emoji": "🌶️🌶️", "reference_pepper": "Cayenne", "shu": 40000},
    3: {"label_en": "Hot", "emoji": "🌶️🌶️🌶️", "reference_pepper": "Habanero", "shu": 250000},
    4: {"label_en": "Very Hot", "emoji": "🌶️🌶️🌶️🌶️", "reference_pepper": "Ghost Pepper", "shu": 1000000},
    5: {"label_en": "Extreme", "emoji": "🌶️🌶️🌶️🌶️🌶️", "reference_pepper": "Carolina Reaper", "shu": 2200000},
}

def _normalize(text: str) -> str:
    return text.replace(" ", "")


def _extract_modifiers(normalized_text: str, matched_name: str) -> tuple[list[dict], list[dict]]:
    """긴 키워드부터 먼저 찾고, 이미 매칭된 글자 구간은 다시 쓰지 않는다.

    한 글자짜리 키워드(파, 김 등)가 "스파이시"처럼 상관없는 단어 안에 우연히
    끼어있는 걸 걸러내기 위함 — "스파이시"(4글자)가 먼저 그 구간을 차지하면
    그 안의 "파"(1글자)는 겹쳐서 못 잡힌다.
    """
    consumed = [False] * len(normalized_text)
    spice_hits = []
    ingredient_hits = []

    modifiers = sorted(cache.get_modifiers(), key=lambda row: len(row["keyword"]), reverse=True)

    for row in modifiers:
        keyword = row["keyword"]
        if keyword in matched_name:
            continue  # 매칭된 음식명 자체에 포함된 단어면 수식어로 보지 않는다

        start = 0
        found = False
        while True:
            idx = normalized_text.find(keyword, start)
            if idx == -1:
                break
            span = range(idx, idx + len(keyword))
            if not any(consumed[i] for i in span):
                for i in span:
                    consumed[i] = True
                found = True
                break
            start = idx + 1

        if not found:
            continue

        if row["category"] == "spice":
            spice_hits.append({"keyword": keyword, "tier": row["spice_tier"]})
        else:
            ingredient_hits.append({"keyword": keyword, "keyword_en": row["keyword_en"]})

    return spice_hits, ingredient_hits


def match_food_candidates(text: str) -> list[dict]:
    """Return every supported food candidate, ordered by match score."""
    normalized_text = _normalize(text)
    foods = cache.get_foods()

    candidates = []
    for food in foods:
        name = _normalize(food["name_kr"])
        if name not in normalized_text and normalized_text not in name:
            continue
        score = fuzz.partial_ratio(normalized_text, name)
        if score < MATCH_THRESHOLD:
            continue

        spice_hits, ingredient_hits = _extract_modifiers(normalized_text, name)
        candidates.append(
            {
                "food_id": food["id"],
                "name_kr": food["name_kr"],
                "name_en": food["name_en"],
                "score": score,
                "modifiers": {"spice": spice_hits, "ingredient": ingredient_hits},
            }
        )

    return sorted(
        candidates,
        key=lambda candidate: (-candidate["score"], -len(candidate["name_kr"])),
    )


def match_food(text: str) -> dict | None:
    """Return the highest-ranked supported food candidate for existing callers."""
    candidates = match_food_candidates(text)
    return candidates[0] if candidates else None
