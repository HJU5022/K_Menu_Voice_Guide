"""상세 텍스트 — food_details의 6개 카테고리를 조회해 카드 형태로 조합한다.

화면에 보여줄 설명 카드를 만드는 단계.
카테고리 6개가 무엇인지는 docs/specs/text-generation.md 참고.
"""

from src.db import cache


def get_details(food_id: int) -> dict:
    """한 음식의 {카테고리: 설명문}을 돌려준다.

    카테고리를 걸러내지 않고 DB에 있는 대로 다 넘긴다. 어떤 카드를 어떤 순서로 그릴지는
    화면이 정하기 때문이다(정본은 `docs/content-style.md`의 "상세 카드 6개" 표). 서버가
    순서를 정해 보내면 웹과 앱 중 한쪽만 고쳤을 때 둘이 조용히 갈라진다.

    설명이 한 줄도 없으면 빈 dict를 돌려주지 않고 예외를 낸다. 빈 카드가 뜨는 화면보다
    "이 음식은 데이터가 비어 있다"가 드러나는 편이 낫고, API 레이어가 이 예외를 404로
    바꿔 프론트에 알려준다(`docs/specs/api-layer.md` EC-01).
    """
    details = cache.get_food_details(food_id)
    if not details:
        raise ValueError(f"food_id {food_id}에 대한 food_details가 없습니다.")
    return details


def get_food_info(food_id: int) -> dict:
    """음식 한 개의 {food_id, name_kr, name_en}.

    상세 응답에 음식명을 같이 실어 보내려고 쓴다 — 프론트가 후보 목록을 잃어버린 상태에서
    상세 화면만 열어도(새로고침·딥링크) 이름을 표시할 수 있어야 하기 때문이다.
    """
    food = cache.get_food(food_id)
    if food is None:
        raise ValueError(f"food_id {food_id}에 대한 foods 데이터가 없습니다.")
    return {"food_id": food["id"], "name_kr": food["name_kr"], "name_en": food["name_en"]}
