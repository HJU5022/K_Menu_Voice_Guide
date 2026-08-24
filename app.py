"""Streamlit 진입점 — 화면만 담당하고, 계산은 FastAPI(`K_Menu_Talk.py`)를 HTTP로 부른다.

처음에는 화면과 파이프라인을 한 프로세스에 직접 연결했지만(이 파일의 이전 버전),
GPU 실측(2026-08-23) 후 계산을 GPU Space 한 곳에 몰기로 하면서 이 파일은 무료 CPU
Space에서 도는 화면 전용 클라이언트가 됐다 — `src/`를 임포트하지 않으므로 paddle·torch
없이 뜬다. 결정 배경과 계약은 docs/specs/streamlit-app.md, docs/specs/api-layer.md 참고.

모바일 앱(`mobile/lib/api.dart`)과 같은 API·같은 계약을 쓴다. API 주소는 환경변수
`API_BASE_URL`로 주입한다(앱의 `config.dart`와 같은 방식). 기본값은 로컬 개발용이다.

화면 구성도 앱(`mobile/lib/screens/candidates_screen.dart`)을 기준으로 맞춘다 — 같은
API를 쓰는 다른 화면이 이미 이 데이터를 다 그리고 있고, 그 판단 근거도 그쪽 주석에
남아 있다. 웹만 다르게 정할 이유가 없다.

디자인(CSS·테마)은 아직 입히지 않았다. 이 파일은 그 CSS가 붙을 골격 역할을 한다.
"""

import html
import io
import os
import re
import uuid

import requests
import streamlit as st
from PIL import Image, ImageDraw, ImageFont

API_BASE_URL = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

# 잠자던 Space가 깨어나는 동안도 기다릴 수 있게 넉넉히 둔다. 이 시간을 넘기면
# EC-07(연결 실패)로 처리된다.
REQUEST_TIMEOUT_SEC = 120

# 화면에 보여줄 카테고리 6개 — 순서와 영어 제목은 docs/content-style.md의 문구 통일
# 기준을 따른다. 앱(mobile/lib/screens/detail_screen.dart)도 같은 순서를 쓴다.
DETAIL_CARDS = [
    ("DESCRIPTION", "Description", False),
    ("HOW_TO_EAT", "How to eat", False),
    ("INGREDIENT", "Ingredients", False),
    ("ALLERGY", "Allergies & dietary needs", True),
    ("PRONUNCIATION", "Pronunciation", False),
    ("SPICY", "Spice level", False),
]

# 예외 화면 문구도 App.tsx의 ErrorPanel에서 그대로 가져왔다.
ERROR_MESSAGES = {
    "ocr_empty": (
        "We couldn't read this photo",
        "Try brighter lighting, hold the menu straight, and move closer to the text.",
    ),
    "unsupported_food": (
        "Not in our guide yet",
        "Try a different menu item or ask the restaurant staff.",
    ),
}

# 후보 번호에 돌려 쓰는 색 — 앱 `menu_photo_overlay.dart`와 같은 팔레트다.
# 사진 위 상자와 목록 배지가 **같은 색**이어야 눈으로 짝지을 수 있다. 후보가 6개를
# 넘으면 색이 반복되지만, 번호가 같이 붙어 있어 헷갈리지 않는다.
CANDIDATE_COLORS = ["#D32F2F", "#1976D2", "#388E3C", "#F57C00", "#7B1FA2", "#0097A7"]

st.set_page_config(page_title="K-Menu Voice Guide", page_icon="🍲", layout="centered")


def _color(index: int) -> str:
    """목록에서 index번째 줄의 색. 사진 상자와 배지가 같은 값을 써야 짝지어진다."""
    return CANDIDATE_COLORS[index % len(CANDIDATE_COLORS)]


def _label(index: int) -> str:
    """후보 번호 표기. 앱과 같게 두 자리로 채운다(`01`, `02` …)."""
    return f"{index + 1:02d}"


def _go(step: str) -> None:
    """화면을 바꾼다. Streamlit은 스크립트를 처음부터 다시 실행하므로 상태는 session_state에 둔다."""
    st.session_state["step"] = step


def _reset() -> None:
    """처음 화면으로 돌아가면서 이전 분석 결과를 모두 비운다."""
    for key in ("analysis", "guide", "image", "picked"):
        st.session_state.pop(key, None)
    _go("upload")


def _cart_id() -> str:
    """이 화면의 카트를 가리키는 값.

    로그인이 없는 서비스라 계정 대신 쓰는 최소 식별자다(`docs/specs/cart.md`).
    `session_state`에 둔다 — 앱도 실행 중에만 들고 있는 값을 쓴다(`mobile/lib/api.dart`의
    `cartId`). 새로고침하면 새 카트가 되지만, 식당에 앉아 한 번에 쓰는 화면이라 그걸로
    충분하다. localStorage에 두려면 JavaScript가 필요해 코드가 복잡해진다.
    """
    if "cart_id" not in st.session_state:
        st.session_state["cart_id"] = uuid.uuid4().hex
    return st.session_state["cart_id"]


def _cart_request(method: str, path: str, payload: dict | None = None) -> None:
    """카트 요청을 보내고 돌아온 **카트 전체**를 session_state에 담는다.

    담기·빼기·비우기 어느 요청이든 카트 전체가 돌아온다 — 화면이 부분 갱신을 짜맞추지
    않게 서버가 그렇게 정했다(`docs/specs/cart.md`).

    실패하면 **담긴 내용을 지우지 않고** 오류 문구만 남긴다(EC-06). 서버가 잠깐 안
    되는 것과 카트가 비는 것은 다른 일이다.
    """
    try:
        response = requests.request(
            method,
            f"{API_BASE_URL}{path}",
            headers={"X-Cart-Id": _cart_id()},
            json=payload,
            timeout=REQUEST_TIMEOUT_SEC,
        )
        response.raise_for_status()
    except requests.RequestException:
        st.session_state["cart_error"] = "We couldn't update your order just now."
        return

    st.session_state.pop("cart_error", None)
    st.session_state["cart"] = response.json()


def _line_key(food_id, menu_text) -> str:
    """카트에서 이 줄을 가리키는 신원 — 앱 `Candidate.lineKey`와 같은 규칙이다.

    `food_id`만으로 묶으면 안 된다. 메뉴판에 "물만두"와 "군만두"가 둘 다 있으면 화면
    카드는 둘인데 카트는 하나가 되고, 가격이 다른 둘을 합쳐 총계까지 틀린다(EC-12).
    """
    return f"{food_id}|{menu_text or ''}"


def _cart_quantities() -> dict[str, int]:
    """지금 담겨 있는 줄별 수량."""
    cart = st.session_state.get("cart") or {}
    return {
        _line_key(line.get("food_id"), line.get("menu_text")): line["quantity"]
        for line in cart.get("items", [])
    }


def _change_cart(entry: dict, delta: int) -> None:
    """메뉴 줄 하나의 수량을 바꾼다.

    안내 못 하는 줄은 이름 자리에 메뉴판 글자를 그대로 보낸다 — 설명은 못 해도 주문은
    되기 때문이다(앱 `UnsupportedMenuLine.cartNameKr`와 같다). 서버가 그 글자에서
    가격을 떼어 화면에 쓸 이름을 만들어 준다(`src/cart/store.py`).
    """
    if entry["supported"]:
        name_kr = entry["name_kr"]
        name_en = entry["name_en"]
    else:
        name_kr = entry.get("menu_text") or ""
        name_en = name_kr

    _cart_request(
        "POST",
        "/api/cart/items",
        payload={
            "food_id": entry.get("food_id"),
            "name_kr": name_kr,
            "name_en": name_en,
            "menu_text": entry.get("menu_text"),
            "price_krw": entry.get("price_krw"),
            "quantity_delta": delta,
        },
    )


def _menu_entries(analysis: dict) -> list[dict]:
    """후보와 안내 못 하는 줄을 메뉴판에 인쇄된 순서(`line_no`)로 합친다.

    서버가 둘을 따로 보내는 건 예전 웹 화면이 `candidates`만 알았기 때문이다. 합쳐서
    줄 순서대로 놓아야 화면이 실제 메뉴판과 같은 순서가 된다 — 앱의 `menuEntries`
    (`mobile/lib/api.dart`)와 같은 규칙이다.

    번호와 색은 **이 합친 목록의 순서**로 매긴다.
    """
    entries = [dict(item, supported=True) for item in analysis.get("candidates", [])]
    entries += [dict(item, supported=False) for item in analysis.get("unsupported_lines", [])]
    # 계약상 후보의 `line_no`는 없을 수도 있다(`int | None`). 그런 줄은 뒤로 보낸다 —
    # 파이썬 정렬은 순서를 유지하므로 자기들끼리는 받은 순서 그대로 남는다.
    entries.sort(key=lambda entry: (entry.get("line_no") is None, entry.get("line_no") or 0))
    return entries


def _summary_line(entries: list[dict], has_photo: bool) -> str:
    """목록 위에 두는 한 줄 안내 — 앱 `candidates_screen.dart`의 `_summaryLine`과 같다.

    사진 위에 상자가 안 붙은 줄이 있으면 그 수를 밝힌다. 상자가 2개인데 목록이 6줄이면
    "왜 4개는 표시가 없지?"가 되는데, 이름이 여러 글자 상자에 걸쳐 잘리면 서버가 위치를
    특정하지 못해 생기는 정상 동작이다. 말없이 두면 화면이 뭔가 빠뜨린 것처럼 보인다.
    """
    dish = "dish" if len(entries) == 1 else "dishes"
    found = f"We found {len(entries)} {dish}."
    if not has_photo:
        return found

    unpinned = sum(1 for entry in entries if not entry.get("source"))
    if unpinned == 0:
        return f"{found} Each box shows what we read there."

    it = "one" if unpinned == 1 else str(unpinned)
    return (
        f"{found} Each box shows what we read there — "
        f"we could not pin {it} to a spot on the photo."
    )


def _modifier_labels(modifiers: dict | None) -> list[str]:
    """수식어를 화면에 쓸 이름으로 편다.

    메뉴판 이름 앞에 붙어 있던 재료·맵기다. 같은 "김치찌개" 두 줄을 가르는 단서가
    이것뿐일 때가 있다(꽁치김치찌개). 영어 표기가 있으면 그쪽을 쓴다 — 읽을 사람이
    한국어를 못 읽는다.
    """
    if not modifiers:
        return []

    labels = []
    for category in ("spice", "ingredient"):
        for modifier in modifiers.get(category) or []:
            labels.append(modifier.get("keyword_en") or modifier.get("keyword") or "")
    return [label for label in labels if label]


def _badge_html(index: int) -> str:
    """번호 배지. 사진 상자와 같은 색을 내려면 HTML로 그려야 한다.

    Streamlit이 기본으로 주는 색 이름(`:red[]` 등)으로는 위 팔레트의 정확한 색을 낼 수
    없어, Pillow로 그린 사진 상자와 색이 어긋난다. 색으로 짝짓는 것이 이 화면의
    핵심이라 배지만 인라인 HTML로 그린다 — 들어가는 값은 우리가 만든 상수 팔레트와
    정수 번호뿐이고 사용자 입력이 섞이지 않는다.
    """
    return (
        f'<span style="display:inline-block;min-width:28px;padding:2px 6px;'
        f"border-radius:6px;background:{_color(index)};color:#fff;font-size:12px;"
        f'font-weight:700;text-align:center">{_label(index)}</span>'
    )


def _modifier_badges_html(labels: list[str]) -> str:
    """수식어 배지들. 한 줄에 나란히 놓으려고 번호 배지와 같은 방식으로 그린다."""
    return " ".join(
        '<span style="display:inline-block;padding:1px 8px;border-radius:10px;'
        'background:rgba(128,128,128,0.18);font-size:11px">' + label + "</span>"
        for label in labels
    )


def _muted(text: str, size: str = "0.85rem") -> str:
    """보조 글자. **색을 직접 정하지 않고 흐리게만 한다.**

    밝은 모드와 어두운 모드 양쪽에서 읽혀야 하는데, 배경색을 모르는 채로 회색 값을
    박으면 한쪽에서 안 보인다. 지금 글자색을 그대로 쓰고 투명도만 낮춘다.
    """
    return f'<div style="opacity:0.65;font-size:{size};margin:0">{text}</div>'


def _pronunciation_quote(details: dict) -> str:
    """발음 안내에서 따옴표 안의 발음만 뽑는다.

    `Bossam is pronounced "bo-ssam," meaning "wrapped."` → `bo-ssam,`
    요약 블록은 스크롤 없이 다 보여야 해서 문장 전체를 넣을 자리가 없다. 본문
    Pronunciation 항목에는 문장이 그대로 남는다.
    """
    match = re.search(r'"([^"]+)"', details.get("PRONUNCIATION", "") or "")
    if match:
        # 원문이 `"bo-ssam," meaning ...` 꼴이라 쉼표가 따옴표 안에 들어 있다.
        # 그대로 두면 화면에 `"bo-ssam,"`으로 보인다.
        return match.group(1).strip(" ,.;:")
    return ""


def _translucent(hex_color: str) -> tuple[int, int, int, int]:
    """상자 안쪽을 덮을 색. 아주 옅게만 채운다 — 진하게 채우면 무엇을 읽었는지 못 본다."""
    red, green, blue = (int(hex_color[start : start + 2], 16) for start in (1, 3, 5))
    return red, green, blue, 31


def _photo_with_boxes(image_bytes: bytes, entries: list[dict]) -> Image.Image:
    """올린 사진 위에 각 줄이 나온 자리를 번호 상자로 그린 **사본**을 돌려준다.

    왜 필요한가: 목록만 보면 "왜 이게 나왔지?"를 확인할 방법이 없다. 실제로 사진에 없는
    음식이 후보로 뜬 적이 있는데(`막국수` → `칼국수`), 그때 사용자가 스스로 판단할 근거가
    화면에 하나도 없었다.

    좌표(`source`)는 원본 사진 기준 0~1 비율이라 원본 크기만 곱하면 자리가 맞는다.
    """
    canvas = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    # RGBA로 그려야 상자 안쪽을 반투명하게 채울 수 있다.
    draw = ImageDraw.Draw(canvas, "RGBA")
    width, height = canvas.size

    # 사진 크기가 제각각이라 선 굵기와 글자 크기를 사진에 비례해서 정한다.
    line_width = max(2, round(min(width, height) / 400))
    font = ImageFont.load_default(size=max(12, round(min(width, height) / 45)))

    for index, entry in enumerate(entries):
        source = entry.get("source")
        if not source:
            continue  # 자리를 못 찾은 줄 — 목록에는 남지만 사진에는 못 그린다(EC-09)

        left = source["left"] * width
        top = source["top"] * height
        right = left + source["width"] * width
        bottom = top + source["height"] * height

        color = _color(index)
        draw.rectangle(
            (left, top, right, bottom),
            outline=color,
            width=line_width,
            fill=_translucent(color),
        )
        _draw_number(draw, index, left, top, bottom, height, font, color)

    return canvas


def _draw_number(
    draw: ImageDraw.ImageDraw,
    index: int,
    left: float,
    top: float,
    bottom: float,
    image_height: int,
    font: ImageFont.ImageFont,
    color: str,
) -> None:
    """상자에 번호를 붙인다. 위쪽에 자리가 없으면 아래에 붙인다(앱과 같은 규칙)."""
    text = _label(index)
    text_left, text_top, text_right, text_bottom = draw.textbbox((0, 0), text, font=font)
    padding = 2
    box_width = text_right - text_left + padding * 2
    box_height = text_bottom - text_top + padding * 2

    number_top = top - box_height - 1
    if number_top < 0:
        number_top = min(bottom + 1, image_height - box_height)

    draw.rectangle(
        (left, number_top, left + box_width, number_top + box_height), fill=color
    )
    draw.text(
        (left + padding - text_left, number_top + padding - text_top),
        text,
        font=font,
        fill="#FFFFFF",
    )


def screen_upload() -> None:
    """1번 화면 — 메뉴 사진을 촬영하거나 업로드한다."""
    st.title("K-Menu Voice Guide")
    st.caption("Photograph a Korean menu and get an English guide with audio.")
    # 링크만 받고 들어온 사람에게는 설명해줄 사람이 없다. 무엇을 하는 서비스인지
    # 한 줄로 먼저 알려준다.
    st.markdown(
        _muted("Take a photo &rarr; pick a dish &rarr; hear what it is, "
               "how it tastes, and how to eat it."),
        unsafe_allow_html=True,
    )

    photo = st.camera_input("Take a photo of the menu")
    uploaded = st.file_uploader("or upload a photo", type=["jpg", "jpeg", "png"])
    image = photo or uploaded
    if image is None:
        return

    # 보낸 바이트는 남겨둔다 — 다음 화면에서 이 사진 위에 상자를 그린다.
    image_bytes = image.getvalue()
    st.session_state["image"] = image_bytes

    # 계약은 api-layer.md의 POST /api/analyze — multipart, 필드명 "image".
    with st.spinner("Reading the menu..."):
        try:
            response = requests.post(
                f"{API_BASE_URL}/api/analyze",
                files={"image": (image.name or "menu.jpg", image_bytes)},
                timeout=REQUEST_TIMEOUT_SEC,
            )
            response.raise_for_status()
        except requests.RequestException:
            _go("api_error")
            st.rerun()
    analysis = response.json()
    st.session_state["analysis"] = analysis
    # 새 메뉴판을 성공적으로 읽었으면 카트를 비운다 — A식당에서 담아둔 것이 B식당
    # 메뉴판을 찍은 뒤에도 남으면 안 된다(EC-09). 흐리게 찍어 실패한 경우는 새 식당이
    # 아니라 실패한 시도이므로 담아둔 것을 그대로 둔다(EC-10).
    if analysis.get("status") == "candidates_found":
        _cart_request("DELETE", "/api/cart")
    _go("select")
    st.rerun()


def screen_select() -> None:
    """2번 화면 — 읽어낸 메뉴 줄을 사진과 함께 보여주고 하나를 고르게 한다."""
    analysis = st.session_state["analysis"]
    status = analysis["status"]

    if status in ERROR_MESSAGES:
        heading, hint = ERROR_MESSAGES[status]
        st.subheader(heading)
        st.write(hint)
        st.button("Take a new photo", on_click=_reset)
        return

    # 고를 것이 하나뿐이면 선택 화면을 건너뛴다. 다만 안내 못 하는 줄이 하나라도 있으면
    # 건너뛰지 않는다 — 건너뛰면 그 줄들이 화면에서 통째로 사라진다(EC-03).
    candidates = analysis.get("candidates", [])
    if len(candidates) == 1 and not analysis.get("unsupported_lines"):
        _select_food(candidates[0])
        st.rerun()
        return

    entries = _menu_entries(analysis)
    image_bytes = st.session_state.get("image")

    st.subheader("Which dish is it?")
    if image_bytes:
        st.image(_photo_with_boxes(image_bytes, entries), width="stretch")
    st.caption(_summary_line(entries, image_bytes is not None))

    quantities = _cart_quantities()
    for index, entry in enumerate(entries):
        key = _line_key(entry.get("food_id"), entry.get("menu_text"))
        _render_entry(entry, index, quantities.get(key, 0))

    _render_cart_bar()
    st.button("Take a new photo", on_click=_reset)


def _clear_cart() -> None:
    _cart_request("DELETE", "/api/cart")


def _render_cart_bar() -> None:
    """목록 아래 카트 요약 — 담긴 수와 총계, 주문 확인 화면으로 가는 길."""
    cart = st.session_state.get("cart") or {}
    count = cart.get("item_count", 0)

    st.divider()

    error = st.session_state.get("cart_error")
    if error:
        # 담긴 내용은 그대로 두고 문구만 알린다 — 서버가 잠깐 안 되는 것과 카트가
        # 비는 것은 다른 일이다(EC-06).
        st.warning(error)

    if count == 0:
        # 빈 카트에서는 두 버튼 모두 누를 수 없다(EC-07).
        st.caption("Nothing in your order yet.")
    else:
        st.markdown(
            f'<div style="font-size:1.05rem;font-weight:700">{count} in your order'
            f'<span style="margin-left:12px">'
            f'{html.escape(cart.get("total_krw_display") or "")}</span></div>',
            unsafe_allow_html=True,
        )

    order_column, clear_column = st.columns(2)
    with order_column:
        st.button(
            "Order",
            key="open_cart",
            disabled=count == 0,
            width="stretch",
            on_click=_go,
            args=("cart",),
        )
    with clear_column:
        st.button(
            "Clear cart",
            key="clear_cart",
            disabled=count == 0,
            width="stretch",
            on_click=_clear_cart,
        )


def _entry_html(entry: dict, index: int) -> str:
    """메뉴 줄 하나의 글자 부분을 **한 덩어리 HTML로** 만든다.

    Streamlit 요소를 여러 개 쌓으면 요소마다 기본 여백이 붙어 항목 하나가 화면을 거의
    다 먹는다(실측 2026-08-24). 한 덩어리로 그리면 줄 간격을 우리가 정할 수 있다.

    메뉴판에서 읽어온 글자가 그대로 들어가므로 **반드시 이스케이프한다** — `<`나 `&`가
    섞이면 화면이 깨진다.

    항목 순서는 앱 `candidates_screen.dart`와 같다.
    """
    supported = entry["supported"]
    rows = []

    if supported:
        # 읽을 사람이 영어권이라 영어 이름을 크게, 한글은 보조로 둔다.
        rows.append(_title_html(entry["name_en"]))
        rows.append(_muted(html.escape(entry["name_kr"])))
    else:
        rows.append(_title_html(entry.get("name_text") or entry.get("menu_text", "")))
        rows.append(_muted("Not in our guide yet"))

    # 메뉴판에 실제로 인쇄된 글자. 등록 이름과 다를 때만 보여준다 — 같으면 같은 말을
    # 두 번 적는 꼴이다(EC-12).
    name_text = entry.get("name_text")
    if supported and name_text and name_text != entry.get("name_kr"):
        rows.append(_muted("Menu: " + html.escape(name_text)))

    labels = _modifier_labels(entry.get("modifiers"))
    if labels:
        rows.append(f'<div style="margin-top:4px">{_modifier_badges_html(labels)}</div>')

    # 가격은 있을 때만. 서버가 못 읽었으면 자리를 비운다(EC-11).
    price = entry.get("price_krw_display")
    if price:
        rows.append(
            f'<div style="font-size:1rem;font-weight:700;margin-top:4px">'
            f"{html.escape(price)}</div>"
        )

    # 사진 출처. 사진을 보여주는 자리에는 반드시 함께 둔다.
    if entry.get("thumbnail_url") and entry.get("thumbnail_attribution"):
        rows.append(_muted(html.escape(entry["thumbnail_attribution"]), size="0.7rem"))

    return '<div style="display:flex;flex-direction:column;gap:2px">' + "".join(rows) + "</div>"


def _title_html(text: str) -> str:
    """목록 항목의 이름 줄."""
    return (
        '<div style="font-size:1.05rem;font-weight:700;margin:0">'
        f"{html.escape(text)}</div>"
    )


def _render_entry(entry: dict, index: int, quantity: int = 0) -> None:
    """메뉴 줄 하나를 그린다."""
    with st.container(border=True):
        number_column, text_column = st.columns([1, 5], vertical_alignment="top")

        with number_column:
            # 사진 위 상자와 같은 번호·같은 색. 어느 줄이 어느 자리인지 잇는다.
            st.markdown(_badge_html(index), unsafe_allow_html=True)
            if entry.get("thumbnail_url"):
                # 폭 고정 — 폰에서 칸이 쌓일 때 사진만 커지는 것을 막는다.
                st.image(entry["thumbnail_url"], width=72)

        with text_column:
            st.markdown(_entry_html(entry, index), unsafe_allow_html=True)

            # 설명을 볼 수 있는 줄만 누를 수 있게 둔다 — 안내할 내용이 없는데 눌리면
            # 고장으로 읽힌다(EC-13). 담기는 안내 못 하는 줄에도 열어둔다: 설명은 못
            # 해도 주문은 되기 때문이다(공기밥 같은 줄).
            if entry["supported"]:
                # key는 합친 목록에서의 순서로 만든다. `food_id`도 `line_no`도 유일하지
                # 않다 — 같은 음식이 두 줄에 나올 수 있고(물만두·군만두), 한 줄에서 서로
                # 다른 음식이 매칭되기도 한다(EC-08).
                if st.button("Select", key=f"pick_{index}", width="stretch"):
                    _select_food(entry)
                    st.rerun()

            _render_stepper(entry, index, quantity)


def _render_stepper(entry: dict, index: int, quantity: int) -> None:
    """담기·빼기 버튼 — 앱 `_QuantityStepper`와 같은 규칙이다.

    아직 안 담긴 줄에는 `+`만 보여준다. 0인데 `−`가 있으면 누를 수 있어 보이지만 아무
    일도 일어나지 않아서 고장처럼 읽힌다(EC-02).
    """
    if quantity == 0:
        if st.button("Add to order", key=f"add_{index}", width="stretch"):
            _change_cart(entry, 1)
            st.rerun()
        return

    minus_column, count_column, plus_column = st.columns(
        [1, 1, 1], vertical_alignment="center"
    )
    with minus_column:
        if st.button("−", key=f"minus_{index}", width="stretch"):
            _change_cart(entry, -1)
            st.rerun()
    with count_column:
        st.markdown(
            f'<div style="text-align:center;font-weight:700">{quantity}</div>',
            unsafe_allow_html=True,
        )
    with plus_column:
        if st.button("+", key=f"plus_{index}", width="stretch"):
            _change_cart(entry, 1)
            st.rerun()


def _select_food(entry: dict) -> None:
    """고른 줄의 설명·음성을 한 번만 받아 session_state에 담는다.

    Streamlit은 버튼 하나 누를 때마다 스크립트를 처음부터 다시 실행한다. 결과를 여기
    담아두지 않으면 화면이 갱신될 때마다 서버가 TTS를 다시 돌린다(캐시 미스면 요청당 33초).
    """
    # 계약은 api-layer.md의 GET /api/foods/{food_id} — 상세·나레이션·맵기가 한 응답에 다 있다.
    with st.spinner("Preparing your guide..."):
        try:
            response = requests.get(
                f"{API_BASE_URL}/api/foods/{entry['food_id']}", timeout=REQUEST_TIMEOUT_SEC
            )
            response.raise_for_status()
        except requests.RequestException:
            _go("api_error")
            return

    st.session_state["guide"] = response.json()
    # 상세 응답에는 메뉴판 글자·가격·대표 사진이 없다(api-layer.md의 FoodDetailResponse).
    # 결과 화면에서 다시 찾을 방법이 없으므로 고른 시점에 같이 담아둔다.
    # 출처는 사진과 **한 쌍으로** 담는다 — 사진만 옮기고 출처를 빠뜨리면 안 된다.
    st.session_state["picked"] = {
        "name_text": entry.get("name_text"),
        "price_krw_display": entry.get("price_krw_display"),
        "thumbnail_url": entry.get("thumbnail_url"),
        "thumbnail_attribution": entry.get("thumbnail_attribution"),
    }
    _go("result")


def _summary_html(guide: dict, picked: dict) -> str:
    """요약 블록의 글자 부분. 이름·가격·맵기·발음을 한 덩어리로 묶는다."""
    rows = [
        '<div style="font-size:1.6rem;font-weight:800;margin:0">'
        f'{html.escape(guide["name_kr"])}</div>',
        _muted(html.escape(guide["name_en"]), size="0.95rem"),
    ]

    name_text = picked.get("name_text")
    if name_text and name_text != guide["name_kr"]:
        rows.append(_muted("Menu: " + html.escape(name_text)))

    # 맵기 단계를 불꽃 5개로 표시한다(README 3절 "불꽃 아이콘 5개 채움").
    level = guide["spice_level"]
    spice = "🌶️" * level + "·" * (5 - level)
    price = picked.get("price_krw_display")
    if price:
        line = (
            f'{spice}<span style="margin-left:14px;font-weight:700">'
            f"{html.escape(price)}</span>"
        )
    else:
        line = spice
    rows.append(f'<div style="margin-top:8px;font-size:1rem">{line}</div>')

    quote = _pronunciation_quote(guide["details"])
    if quote:
        rows.append(_muted("&ldquo;" + html.escape(quote) + "&rdquo;", size="0.95rem"))

    return '<div style="display:flex;flex-direction:column;gap:2px">' + "".join(rows) + "</div>"


def _render_summary(guide: dict, picked: dict) -> None:
    """상단 요약 블록 — 스크롤하지 않아도 이름·가격·맵기·발음·음성이 다 보이게 모은다."""
    thumbnail = picked.get("thumbnail_url")
    if thumbnail:
        image_column, text_column = st.columns([1, 2], vertical_alignment="top")
        with image_column:
            # 폭을 고정한다. `stretch`로 두면 폰에서 칸이 위아래로 쌓이면서 사진이
            # 화면 폭을 다 먹어 요약이 접힌 아래로 밀려난다(실측 2026-08-24).
            st.image(thumbnail, width=140)
            attribution = picked.get("thumbnail_attribution")
            if attribution:
                st.markdown(
                    _muted(html.escape(attribution), size="0.7rem"),
                    unsafe_allow_html=True,
                )
        with text_column:
            st.markdown(_summary_html(guide, picked), unsafe_allow_html=True)
    else:
        st.markdown(_summary_html(guide, picked), unsafe_allow_html=True)

    if guide["narration_audio_path"]:
        # 응답의 경로는 상대 경로(/audio/...)다 — 파일은 API 서버에 있으므로 주소를 붙인다.
        st.audio(f"{API_BASE_URL}{guide['narration_audio_path']}")
    else:
        # TTS가 실패해도 상세 텍스트는 그대로 보여준다(README 9절 위험 대응).
        st.warning("Audio guide is unavailable right now.")
        st.write(guide["narration_text"])


def screen_result() -> None:
    """3번 화면 — 요약 블록과 노트형 본문을 보여준다."""
    guide = st.session_state["guide"]
    picked = st.session_state.get("picked") or {}

    _render_summary(guide, picked)
    st.divider()

    for category, title, is_warning in DETAIL_CARDS:
        text = guide["details"].get(category, "")
        # 카드 테두리를 두지 않는다 — 소제목과 본문이 이어지는 노트 형식이다.
        # 알레르기만 경고 스타일을 남긴다. 안전 정보라 눈에 띄어야 한다.
        if is_warning:
            st.markdown(f"**{title}**")
            st.warning(text)
        else:
            # 제목과 본문을 한 요소로 그린다 — 나누면 요소마다 여백이 붙어 길어진다.
            # if문으로 쓴다(삼항 표현식을 쓰면 Streamlit magic이 반환값까지 그린다).
            st.markdown(f"**{title}**\n\n{text}")

    back_column, restart_column = st.columns(2)
    with back_column:
        # 목록으로 돌아가는 길. 분석 결과는 session_state에 그대로 있으므로 서버를
        # 다시 부르지 않는다 — 이 버튼이 없으면 다른 메뉴를 보려고 사진부터 다시
        # 올려야 했다(재분석 6~7초).
        st.button("Back to the list", on_click=_go, args=("select",), width="stretch")
    with restart_column:
        st.button("Take a new photo", on_click=_reset, width="stretch")


def _cart_line_html(line: dict) -> str:
    """주문 확인 화면의 한 줄.

    여기서는 **한국어 이름을 크게** 쓴다 — 이 화면을 읽는 사람은 종업원이다. 후보
    목록이 영어를 크게 쓰는 것과 방향이 반대인데, 보는 사람이 다르기 때문이다.
    """
    name = line.get("name_text") or line.get("name_kr") or ""
    rows = [
        '<div style="display:flex;justify-content:space-between;align-items:baseline">'
        f'<span style="font-size:1.25rem;font-weight:700">{html.escape(name)}</span>'
        f'<span style="font-size:1.1rem;font-weight:700">&times;{line["quantity"]}</span>'
        "</div>"
    ]
    # 영문 이름은 **진짜 영어 이름일 때만** 보여준다. 안내 못 하는 줄은 영어 이름이
    # 없어서 메뉴판 글자를 그대로 담아 보내는데, 그대로 찍으면 "공기밥" 아래 "공기밥
    # 1,000"이 또 나오고 가격도 두 번 보인다.
    name_en = line.get("name_en")
    if name_en and name_en != name and name_en != line.get("menu_text"):
        rows.append(_muted(html.escape(name_en)))
    total = line.get("line_total_display")
    if total:
        rows.append(_muted(html.escape(total), size="0.95rem"))
    return '<div style="display:flex;flex-direction:column;gap:2px">' + "".join(rows) + "</div>"


def screen_cart() -> None:
    """주문 확인 화면.

    **어디로도 주문을 보내지 않는다.** 여행자가 종업원에게 보여주는 화면이다. 그래서
    "주문이 접수되었습니다" 같은 문구를 쓰지 않는다 — 접수되지 않았는데 접수된 것처럼
    보이면 여행자가 자리에 앉아 오지 않을 음식을 기다리게 된다(`docs/specs/cart.md`).
    """
    cart = st.session_state.get("cart") or {}
    items = cart.get("items", [])

    st.subheader("Show this to the staff")
    st.caption(
        'This says "I would like to order these." Show this screen to the staff.'
    )

    for line in items:
        with st.container(border=True):
            st.markdown(_cart_line_html(line), unsafe_allow_html=True)

    st.divider()
    st.markdown(
        f'<div style="font-size:1.2rem;font-weight:800">Total '
        f'<span style="margin-left:8px">'
        f'{html.escape(cart.get("total_krw_display") or "")}</span></div>',
        unsafe_allow_html=True,
    )
    if cart.get("has_unpriced_items"):
        # 총계를 그냥 보여주면 실제보다 싸 보인다. 왜 모자란지 밝힌다.
        st.caption("Some dishes had no price on the menu, so this total is partial.")

    # 카트는 그대로 남긴다 — 보여주고 돌아와 수량을 고칠 수 있어야 한다(EC-08).
    st.button("Back to the list", on_click=_go, args=("select",), width="stretch")


def screen_api_error() -> None:
    """예외 화면 — API 서버에 연결하지 못했다(EC-07). 잠자던 Space가 깨는 중일 수도 있다."""
    st.subheader("We couldn't reach the service")
    st.write("The server may be waking up. Please try again in a moment.")
    st.button("Try again", on_click=_reset)


SCREENS = {
    "upload": screen_upload,
    "select": screen_select,
    "result": screen_result,
    "cart": screen_cart,
    "api_error": screen_api_error,
}

SCREENS[st.session_state.setdefault("step", "upload")]()
