"""메모리 캐싱 — 서버 시작 시 전체 데이터를 한 번에 올려둔다.

음식이 50개뿐이라 전부 메모리에 두는 게 요청마다 DB를 다녀오는 것보다 빠르다.
첫 호출 때 한 번만 4개 테이블을 읽고, 그 뒤로는 메모리에 있는 값을 그대로 돌려준다.
"""

from src.db.supabase_client import client

_cache: dict[str, list[dict]] | None = None


def _load() -> dict[str, list[dict]]:
    global _cache
    if _cache is None:
        _cache = {
            "foods": client.table("foods")
            .select(
                "id, name_kr, name_en, name_respell, spice_level, "
                "thumbnail_url, thumbnail_attribution"
            )
            .execute()
            .data,
            "food_details": client.table("food_details")
            .select("food_id, category, detail_text")
            .execute()
            .data,
            "food_narration": client.table("food_narration")
            .select("food_id, style, narration_text")
            .execute()
            .data,
            "menu_modifiers": client.table("menu_modifiers")
            .select("keyword, category, keyword_en, spice_tier")
            .execute()
            .data,
        }
    return _cache


def get_foods() -> list[dict]:
    """Return all foods rows (id, name_kr, name_en, name_respell, spice_level)."""
    return _load()["foods"]


def get_food(food_id: int) -> dict | None:
    """Return one food's row, or None if food_id doesn't exist."""
    return next((food for food in get_foods() if food["id"] == food_id), None)


def get_food_details(food_id: int, categories: tuple[str, ...] | None = None) -> dict[str, str]:
    """Return {category: detail_text} for one food, optionally filtered to given categories."""
    rows = [row for row in _load()["food_details"] if row["food_id"] == food_id]
    if categories is not None:
        rows = [row for row in rows if row["category"] in categories]
    return {row["category"]: row["detail_text"] for row in rows}


def get_narration_text(food_id: int, style: str) -> str | None:
    """Return the narration_text for one food+style, or None if not found."""
    for row in _load()["food_narration"]:
        if row["food_id"] == food_id and row["style"] == style:
            return row["narration_text"]
    return None


def get_modifiers() -> list[dict]:
    """Return all menu_modifiers rows."""
    return _load()["menu_modifiers"]
