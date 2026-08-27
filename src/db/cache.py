"""메모리 캐싱 — 서버 시작 시 전체 데이터를 한 번에 올려둔다.

음식이 50개뿐이라 전부 메모리에 두는 게 요청마다 DB를 다녀오는 것보다 빠르다.
첫 호출 때 한 번만 4개 테이블을 읽고, 그 뒤로는 메모리에 있는 값을 그대로 돌려준다.

실측(2026-08-25): 첫 요청의 4개 테이블 왕복이 약 2.5초, 그 뒤로는 2ms 미만.
서비스 응답에서 눈에 띄는 콜드 비용은 이 한 번뿐이다.

**조회 함수들이 리스트를 그냥 훑는 이유**(dict 색인을 미리 만들지 않는 이유)는 데이터가
작아서다. 50행을 처음부터 끝까지 보는 비용은 마이크로초 단위라, 색인을 만들어 관리하는
복잡도가 얻는 것보다 크다. 행이 수천 개로 늘면 그때 바꾸면 된다.
"""

from src.db.supabase_client import client

# 모듈 전역에 한 벌만 둔다. None이면 "아직 안 읽었다"는 뜻이다.
# 빈 dict를 초깃값으로 쓰지 않는 이유: DB가 정말로 비어 있는 경우와 구별이 안 된다.
_cache: dict[str, list[dict]] | None = None


def _load() -> dict[str, list[dict]]:
    """캐시를 채우고 돌려준다. 두 번째 호출부터는 DB를 건드리지 않는다."""
    global _cache
    if _cache is None:
        # 쓰는 컬럼만 골라서 select한다 — `*`로 통째로 받으면 나중에 DB에 컬럼이
        # 하나 늘 때마다 이 왕복이 같이 무거워지고, 어떤 컬럼을 실제로 쓰는지도
        # 코드만 봐서는 알 수 없게 된다.
        _cache = {
            "foods": client.table("foods")
            .select(
                "id, name_kr, name_en, spice_level, "
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
    """등록된 음식 50개 전체를 돌려준다."""
    return _load()["foods"]


def get_food(food_id: int) -> dict | None:
    """음식 한 개의 행. 없는 id면 None."""
    return next((food for food in get_foods() if food["id"] == food_id), None)


def get_food_details(food_id: int, categories: tuple[str, ...] | None = None) -> dict[str, str]:
    """한 음식의 {카테고리: 설명문}. categories를 주면 그중에서만 고른다.

    카테고리를 걸러 받는 쓰임새가 있는 이유는, 화면에 쓰는 6개와 나레이션에 이어붙이는
    2개(PRONUNCIATION·ALLERGY)가 서로 다르기 때문이다.
    """
    rows = [row for row in _load()["food_details"] if row["food_id"] == food_id]
    if categories is not None:
        rows = [row for row in rows if row["category"] in categories]
    return {row["category"]: row["detail_text"] for row in rows}


def get_narration_text(food_id: int, style: str) -> str | None:
    """음식+스타일에 해당하는 내레이션 문장. 없으면 None.

    실제로는 음식마다 한 행뿐이다 — 스타일은 spice_level이 정하므로(4 이상이면 CAUTION)
    한 음식에 GUIDE·CAUTION을 둘 다 두지 않는다. 그래도 style로 함께 거르는 이유는,
    호출부가 정한 스타일과 DB 행이 어긋나면 조용히 다른 문장을 읽는 대신 None으로
    드러나게 하기 위해서다.
    """
    for row in _load()["food_narration"]:
        if row["food_id"] == food_id and row["style"] == style:
            return row["narration_text"]
    return None


def get_modifiers() -> list[dict]:
    """메뉴판 수식어 전체(`매운`, `해산물` 등). 후보 카드의 영어 태그가 여기서 나온다."""
    return _load()["menu_modifiers"]
