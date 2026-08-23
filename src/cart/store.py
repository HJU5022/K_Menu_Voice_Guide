"""장바구니 — 여행자가 고른 메뉴와 수량을 담아두고 원화 총계를 계산한다.

docs/specs/cart.md 참고. 규칙 네 가지가 이 파일의 전부다:

- 같은 **메뉴판 줄**은 한 줄로 합친다 (food_id + menu_text 기준)
- 수량은 0 밑으로 내려가지 않는다 (음수 금지)
- 수량이 0이 되면 그 줄을 지운다
- 어떤 요청이든 카트 **전체** 상태를 돌려준다 — 프론트가 부분 갱신을 짜맞출 필요가 없게

가격은 메뉴판 사진에서 읽은 값이라(src/ocr/price.py) 없을 수 있다. 가격을 못 읽은 메뉴도
담을 수는 있고 총계에는 0으로 들어가되, has_unpriced_items로 "총계가 일부만 반영됐다"고
알린다 — 실제보다 싸 보이는 합계를 말없이 보여주지 않기 위해서다.

저장은 서버 프로세스 메모리에만 한다. 재시작하면 비워지고 여러 워커로 띄우면 공유되지
않는다 — 영속 저장은 Spec의 Out of Scope다. 로그인이 없는 서비스라 계정 대신 브라우저가
만든 카트 ID(UUID)로 구분한다.
"""

from src.ocr.price import format_price_krw, strip_prices

# {카트 ID: [담긴 줄, ...]} — 줄은 처음 담은 순서를 유지한다.
_carts: dict[str, list[dict]] = {}


def _build_state(cart_id: str, items: list[dict]) -> dict:
    """담긴 줄들로 응답용 카트 전체 상태를 만든다(합계·표시용 문자열 포함)."""
    lines = []
    total_krw = 0
    item_count = 0
    has_unpriced_items = False

    for item in items:
        price_krw = item["price_krw"]
        quantity = item["quantity"]
        item_count += quantity

        if price_krw is None:
            line_total_krw = None
            has_unpriced_items = True
        else:
            line_total_krw = price_krw * quantity
            total_krw += line_total_krw

        lines.append(
            {
                "food_id": item["food_id"],
                "name_kr": item["name_kr"],
                "name_en": item["name_en"],
                # 메뉴판에 인쇄된 그 줄 글자. 주문 확인 화면이 종업원에게 보여줄 때
                # 등록 이름("김치찌개")보다 이쪽("쌈싸먹는 꽁치김치찌개")이 정확하다.
                #
                # 줄을 묶는 기준(_line_key)이므로 담을 때 받은 값을 그대로 둔다.
                "menu_text": item.get("menu_text"),
                # 같은 줄에서 가격만 뗀 것. 화면이 가격을 따로 보여주는 자리에서
                # 이름까지 가격을 달고 있으면 같은 값이 두 번 보인다.
                "name_text": strip_prices(item.get("menu_text") or "") or item.get("menu_text"),
                "price_krw": price_krw,
                "price_krw_display": format_price_krw(price_krw),
                "quantity": quantity,
                "line_total_krw": line_total_krw,
                "line_total_display": format_price_krw(line_total_krw),
            }
        )

    return {
        "cart_id": cart_id,
        "items": lines,
        "item_count": item_count,
        "total_krw": total_krw,
        "total_krw_display": format_price_krw(total_krw),
        "has_unpriced_items": has_unpriced_items,
    }


def _line_key(food_id: int | None, menu_text: str | None) -> tuple[int, str]:
    """카트에서 한 줄을 가리키는 신원.

    food_id만으로 묶으면 안 된다. 메뉴판에 "물만두 5,000"과 "군만두 6,000"이 따로
    있으면 화면에는 카드가 둘인데 카트에서는 "만두 2"로 합쳐진다 — 가격이 다른 둘을
    한 줄로 만들어 총계까지 틀리게 한다.

    가격으로 구분하는 것도 안 된다. "쌈싸먹는 김치찌개"와 "쌈싸먹는 꽁치김치찌개"는
    실제 메뉴판에서 둘 다 7,000원이었다. 메뉴판에 인쇄된 글자만이 둘을 가른다.

    menu_text가 없으면(좌표 없이 매칭된 옛 경로) food_id만으로 묶는다 — 그 경우엔
    애초에 줄 구분 정보가 없으므로 예전과 같게 동작하는 게 맞다.

    등록되지 않은 메뉴는 food_id가 없다(None). 설명은 못 해도 담을 수는 있어야 해서
    받아주고, 그때는 menu_text가 유일한 신원이 된다 — 그래서 food_id 자리에 0을 둔다.
    """
    return (food_id or 0, menu_text or "")


def get_cart(cart_id: str) -> dict:
    """카트 전체 상태를 돌려준다. 처음 보는 카트 ID면 빈 카트(에러 아님)."""
    return _build_state(cart_id, _carts.get(cart_id, []))


def change_quantity(
    cart_id: str,
    *,
    food_id: int | None,
    name_kr: str,
    name_en: str,
    price_krw: int | None,
    quantity_delta: int,
    menu_text: str | None = None,
) -> dict:
    """메뉴판 한 줄의 수량을 quantity_delta만큼 더하거나 빼고, 카트 전체를 돌려준다.

    이미 담긴 줄이면 새 줄을 만들지 않고 그 줄의 수량만 바꾼다. 결과 수량이 0 이하면
    줄을 지운다 — "음수 금지"와 "0이면 자동 삭제"가 같은 한 줄에서 나온다.

    카트에 없는 줄을 빼려고 하면(quantity_delta < 0) 아무 일도 일어나지 않는다.
    수량 0짜리 빈 줄을 남기지 않기 위해서다.

    묶는 기준은 food_id가 아니라 (food_id, menu_text)다 — _line_key() 설명 참고.
    """
    items = _carts.setdefault(cart_id, [])
    key = _line_key(food_id, menu_text)

    for item in items:
        if _line_key(item["food_id"], item.get("menu_text")) == key:
            item["quantity"] += quantity_delta
            # 이번에 읽은 가격이 있으면 그 값으로 갱신한다. 처음 담을 때 가격을 못 읽었더라도
            # 다른 사진에서 읽히면 그때부터 총계에 반영되도록 하기 위함.
            if price_krw is not None:
                item["price_krw"] = price_krw
            break
    else:
        items.append(
            {
                "food_id": food_id,
                "name_kr": name_kr,
                "name_en": name_en,
                "price_krw": price_krw,
                "quantity": quantity_delta,
                "menu_text": menu_text,
            }
        )

    _carts[cart_id] = [item for item in items if item["quantity"] > 0]
    return _build_state(cart_id, _carts[cart_id])


def clear_cart(cart_id: str) -> dict:
    """카트 하나를 비우고, 비워진 전체 상태를 돌려준다.

    다른 카트 ID는 건드리지 않는다. 반환 모양이 담기/조회와 같아야 프론트가 응답을
    그대로 갈아끼울 수 있다.
    """
    _carts.pop(cart_id, None)
    return _build_state(cart_id, [])


def clear_all() -> None:
    """저장된 모든 카트를 버린다 — 테스트가 서로 영향을 주지 않게 하기 위한 용도."""
    _carts.clear()
