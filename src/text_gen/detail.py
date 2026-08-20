"""상세 텍스트 — food_details의 6개 카테고리를 조회해 카드 형태로 조합한다.

화면에 보여줄 설명 카드를 만드는 단계.
카테고리 6개가 무엇인지는 docs/specs/text-generation.md 참고.
"""

from src.db import cache


def get_details(food_id: int) -> dict:
    details = cache.get_food_details(food_id)
    if not details:
        raise ValueError(f"food_id {food_id}에 대한 food_details가 없습니다.")
    return details


def get_food_info(food_id: int) -> dict:
    """Return {food_id, name_kr, name_en} for one food (API 응답에 음식명을 포함시키기 위함)."""
    food = cache.get_food(food_id)
    if food is None:
        raise ValueError(f"food_id {food_id}에 대한 foods 데이터가 없습니다.")
    return {"food_id": food["id"], "name_kr": food["name_kr"], "name_en": food["name_en"]}
