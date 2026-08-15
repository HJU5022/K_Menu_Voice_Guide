"""상세 텍스트 — food_details의 6개 카테고리를 조회해 카드 형태로 조합한다.

화면에 보여줄 설명 카드를 만드는 단계.
카테고리 6개가 무엇인지는 docs/specs/text-generation.md 참고.
"""

from src.db.supabase_client import client


def get_details(food_id: int) -> dict:
    result = (
        client.table("food_details")
        .select("category, detail_text")
        .eq("food_id", food_id)
        .execute()
    )
    if not result.data:
        raise ValueError(f"food_id {food_id}에 대한 food_details가 없습니다.")

    return {row["category"]: row["detail_text"] for row in result.data}