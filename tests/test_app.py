"""app.py 화면 테스트 — `docs/specs/streamlit-app.md`의 AC를 그대로 옮겼다.

Streamlit이 주는 `AppTest`로 스크립트를 실제로 실행하고 그려진 요소를 확인한다.
브라우저는 뜨지 않는다. 서버가 필요한 자리(자동 이동)만 `requests`를 가짜로 바꾼다.

화면 상태는 `session_state`에 직접 넣는다 — 업로드부터 시작하면 매번 서버가 필요해서
검사하려는 화면과 상관없는 것까지 끌어들이게 된다.
"""

import importlib.util
import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests
from PIL import Image
from streamlit.testing.v1 import AppTest

APP_PATH = str(Path(__file__).resolve().parents[1] / "app.py")


def _candidate(**overrides) -> dict:
    """안내 가능한 메뉴 줄 하나. 필드 이름은 api-layer.md의 `Candidate`를 따른다."""
    candidate = {
        "food_id": 1,
        "name_kr": "갈비탕",
        "name_en": "Galbitang",
        "score": 95,
        "modifiers": {"spice": [], "ingredient": []},
        "line_no": 0,
        "thumbnail_url": None,
        "thumbnail_attribution": None,
        "source": None,
        "price_krw": None,
        "price_krw_display": None,
    }
    candidate.update(overrides)
    # 메뉴판 글자는 등록 이름을 따라가는 것이 기본이다. 이름만 바꾸고 이 둘을 그대로
    # 두면 "김치찌개인데 메뉴판에는 갈비탕"이라는, 실제로는 나올 수 없는 재료가 된다.
    candidate.setdefault("menu_text", candidate["name_kr"])
    candidate.setdefault("name_text", candidate["name_kr"])
    return candidate


def _unsupported(**overrides) -> dict:
    """안내는 못 하지만 이름·가격은 읽힌 줄 (`UnsupportedMenuLine`)."""
    line = {
        "line_no": 1,
        "menu_text": "공기밥 1,000",
        "name_text": "공기밥",
        "price_krw": 1000,
        "price_krw_display": "₩1,000",
        "source": None,
    }
    line.update(overrides)
    return line


def _select_screen(candidates, unsupported=(), image=None, cart=None) -> AppTest:
    """후보 선택 화면을 그린 상태로 돌려준다."""
    app = AppTest.from_file(APP_PATH)
    app.session_state["step"] = "select"
    app.session_state["analysis"] = {
        "status": "candidates_found",
        "ocr_text": "갈비탕",
        "candidates": list(candidates),
        "unsupported_lines": list(unsupported),
    }
    if image is not None:
        app.session_state["image"] = image
    if cart is not None:
        app.session_state["cart"] = cart
    return app.run()


def _cart_line(**overrides) -> dict:
    """`CartResponse.items`의 한 줄."""
    line = {
        "food_id": 1,
        "name_kr": "갈비탕",
        "name_en": "Galbitang",
        "menu_text": "갈비탕",
        "name_text": "갈비탕",
        "price_krw": 15000,
        "price_krw_display": "₩15,000",
        "quantity": 1,
        "line_total_krw": 15000,
        "line_total_display": "₩15,000",
    }
    line.update(overrides)
    return line


def _cart(items=(), **overrides) -> dict:
    """`CartResponse` 전체 — 담기·빼기·비우기 어느 요청이든 이 모양이 돌아온다."""
    items = list(items)
    cart = {
        "cart_id": "test",
        "items": items,
        "item_count": sum(line["quantity"] for line in items),
        "total_krw": sum(line["line_total_krw"] or 0 for line in items),
        "total_krw_display": "₩15,000",
        "has_unpriced_items": False,
    }
    cart.update(overrides)
    return cart


def _button(app: AppTest, label: str):
    [button] = [element for element in app.button if element.label == label]
    return button


def _texts(app: AppTest) -> list[str]:
    """화면에 글자로 나온 것들을 한데 모은다 — 어느 요소로 그렸는지는 검사 대상이 아니다."""
    return [element.value for element in app.markdown] + [
        element.value for element in app.caption
    ]


def _select_buttons(app: AppTest) -> list:
    return [button for button in app.button if button.label == "Select"]


def _sample_photo(size: tuple[int, int] = (400, 300)) -> bytes:
    """상자를 그릴 대상이 되는 작은 사진."""
    buffer = io.BytesIO()
    Image.new("RGB", size, "white").save(buffer, format="PNG")
    return buffer.getvalue()


def _app_module():
    """`_photo_with_boxes`를 직접 부르려고 app.py를 모듈로 읽는다.

    상자가 정말 그려졌는지는 픽셀을 봐야 알 수 있는데, `AppTest`는 그려진 이미지의
    내용까지는 돌려주지 않는다. 화면 요소를 만드는 함수들은 Streamlit 실행 밖에서는
    아무 일도 하지 않으므로(경고만 남는다) 이렇게 불러도 안전하다.
    """
    spec = importlib.util.spec_from_file_location("kmenu_app", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- AC-08 ------------------------------------------------------------------


def test_ac08_같은_food_id가_두_줄이어도_화면이_죽지_않는다():
    app = _select_screen(
        [
            _candidate(food_id=7, name_kr="만두", name_en="Dumplings", line_no=0,
                       menu_text="물만두", name_text="물만두"),
            _candidate(food_id=7, name_kr="만두", name_en="Dumplings", line_no=1,
                       menu_text="군만두", name_text="군만두"),
        ]
    )

    assert not app.exception
    assert len(_select_buttons(app)) == 2


def test_ac08_같은_line_no를_가진_후보_둘도_따로_그려진다():
    # 한 줄에서 서로 다른 음식이 매칭되면 line_no가 겹친다(src/ocr/match.py).
    app = _select_screen(
        [
            _candidate(food_id=1, name_en="Galbitang", line_no=3),
            _candidate(food_id=2, name_en="Kimchi Stew", name_kr="김치찌개", line_no=3),
        ]
    )

    assert not app.exception
    assert len(_select_buttons(app)) == 2


# --- AC-09 ------------------------------------------------------------------


def test_ac09_메뉴판_글자와_가격이_보인다():
    app = _select_screen(
        [
            _candidate(name_kr="갈비탕", name_text="황기갈비탕", price_krw_display="₩15,000"),
            _candidate(food_id=2, name_en="Kimchi Stew", name_kr="김치찌개"),
        ]
    )

    texts = _texts(app)
    assert any("황기갈비탕" in text for text in texts)
    assert any("₩15,000" in text for text in texts)


def test_ac09_메뉴판_글자가_등록_이름과_같으면_따로_적지_않는다():
    app = _select_screen(
        [
            _candidate(name_kr="갈비탕", name_text="갈비탕"),
            _candidate(food_id=2, name_en="Kimchi Stew", name_kr="김치찌개"),
        ]
    )

    assert not any("Menu: " in text for text in _texts(app))


# --- AC-10 ------------------------------------------------------------------


def test_ac10_썸네일에는_출처가_따라붙는다():
    app = _select_screen(
        [
            _candidate(
                thumbnail_url="https://example.com/galbitang.jpg",
                thumbnail_attribution="Photo by 아무개 (CC BY 2.0)",
            ),
            _candidate(food_id=2, name_en="Kimchi Stew", name_kr="김치찌개"),
        ]
    )

    assert any("Photo by 아무개" in text for text in _texts(app))


def test_ac10_썸네일이_없으면_출처도_그리지_않는다():
    app = _select_screen(
        [
            _candidate(thumbnail_url=None, thumbnail_attribution="Photo by 아무개"),
            _candidate(food_id=2, name_en="Kimchi Stew", name_kr="김치찌개"),
        ]
    )

    assert not any("Photo by 아무개" in text for text in _texts(app))
    assert len(app.image) == 0


# --- AC-11 ------------------------------------------------------------------


def test_ac11_미지원_줄도_목록에_남고_누를_수_없다():
    app = _select_screen(
        [_candidate(line_no=2, name_text="갈비탕")],
        [
            _unsupported(line_no=1, name_text="공기밥"),
            _unsupported(line_no=3, name_text="음료수", price_krw_display="₩2,000"),
        ],
    )

    texts = _texts(app)
    assert any("공기밥" in text for text in texts)
    assert any("음료수" in text for text in texts)
    # 고를 수 있는 줄은 후보 하나뿐이다.
    assert len(_select_buttons(app)) == 1


def test_ac11_목록이_메뉴판에_인쇄된_순서로_늘어선다():
    app = _select_screen(
        [_candidate(line_no=2, name_en="Galbitang")],
        [
            _unsupported(line_no=1, name_text="공기밥"),
            _unsupported(line_no=3, name_text="음료수"),
        ],
    )

    joined = "\n".join(_texts(app))
    assert joined.index("공기밥") < joined.index("Galbitang") < joined.index("음료수")


# --- AC-12 ------------------------------------------------------------------


def test_ac12_사진이_있으면_상자를_얹은_사진을_그린다():
    app = _select_screen(
        [
            _candidate(source={"text": "갈비탕", "left": 0.1, "top": 0.1,
                               "width": 0.3, "height": 0.1}),
            _candidate(food_id=2, name_en="Kimchi Stew", name_kr="김치찌개", source=None),
        ],
        image=_sample_photo(),
    )

    assert not app.exception
    # 썸네일이 없으므로 그려진 이미지는 메뉴판 사진 하나뿐이다.
    assert len(app.image) == 1
    # 자리를 못 찾은 줄도 목록에는 남는다(EC-09).
    assert len(_select_buttons(app)) == 2


def test_ac12_상자가_실제로_그려진다():
    module = _app_module()
    entries = [
        {"source": {"text": "갈비탕", "left": 0.25, "top": 0.25,
                    "width": 0.5, "height": 0.5}},
        {"source": None},
    ]

    drawn = module._photo_with_boxes(_sample_photo((400, 400)), entries)

    # 상자 왼쪽 위 모서리(0.25 × 400 = 100)는 팔레트 첫 색으로 칠해진다.
    assert drawn.getpixel((100, 100)) == (211, 47, 47)  # #D32F2F
    # 상자 밖은 원본 그대로다.
    assert drawn.getpixel((10, 10)) == (255, 255, 255)
    # 안쪽은 아주 옅게만 덮인다 — 진하게 채우면 무엇을 읽었는지 못 본다.
    inside = drawn.getpixel((200, 200))
    assert inside != (255, 255, 255)
    assert all(channel >= 200 for channel in inside)


def test_ac12_좌표가_없는_줄은_상자를_그리지_않는다():
    module = _app_module()
    photo = _sample_photo((400, 400))

    untouched = module._photo_with_boxes(photo, [{"source": None}])

    assert untouched.getpixel((100, 100)) == (255, 255, 255)


def test_ac12_사진이_없으면_이미지를_그리지_않는다():
    app = _select_screen(
        [_candidate(), _candidate(food_id=2, name_en="Kimchi Stew", name_kr="김치찌개")]
    )

    assert len(app.image) == 0


# --- AC-13 ------------------------------------------------------------------


def test_ac13_후보가_하나라도_미지원_줄이_있으면_건너뛰지_않는다():
    app = _select_screen([_candidate()], [_unsupported()])

    assert not app.exception
    assert [element.value for element in app.subheader] == ["Which dish is it?"]


def test_ac02_후보가_하나뿐이고_미지원_줄이_없으면_결과로_바로_간다():
    response = MagicMock()
    response.json.return_value = {
        "food_id": 1,
        "name_kr": "갈비탕",
        "name_en": "Galbitang",
        "spice_level": 1,
        "details": {"DESCRIPTION": "A beef short rib soup."},
        "narration_text": "A beef short rib soup.",
        "style": "GUIDE",
        "tts_status": "not_ready",
        "narration_audio_path": None,
        "tts_latency_ms": 0,
    }

    with patch("requests.get", return_value=response):
        app = _select_screen([_candidate()])

    # 이름은 요약 블록 안에 있다(st.title이 아니다 — 요약을 한 덩어리로 그린다).
    assert any("갈비탕" in text for text in _texts(app))


# --- AC-14 ------------------------------------------------------------------


def _guide(**overrides) -> dict:
    """`GET /api/foods/{id}` 응답 (`FoodDetailResponse`)."""
    guide = {
        "food_id": 1,
        "name_kr": "갈비탕",
        "name_en": "Galbitang",
        "spice_level": 2,
        "details": {
            "DESCRIPTION": "A beef short rib soup.",
            "HOW_TO_EAT": "Sip the broth first.",
            "INGREDIENT": "Beef short ribs, radish.",
            "ALLERGY": "Contains soy.",
            "PRONUNCIATION": 'Galbitang is pronounced "gal-bi-tang."',
            "SPICY": "Not spicy.",
        },
        "narration_text": "A beef short rib soup.",
        "style": "GUIDE",
        "tts_status": "ok",
        "narration_audio_path": "/audio/tmp.wav",
        "tts_latency_ms": 1,
    }
    guide.update(overrides)
    return guide


def _result_screen(guide=None, picked=None, analysis=None) -> AppTest:
    """상세 화면을 그린 상태로 돌려준다."""
    app = AppTest.from_file(APP_PATH)
    app.session_state["step"] = "result"
    app.session_state["guide"] = guide or _guide()
    app.session_state["picked"] = picked or {}
    if analysis is not None:
        app.session_state["analysis"] = analysis
    return app.run()


def test_ac14_결과_화면이_고른_줄의_가격을_이어받는다():
    app = _result_screen(picked={
        "name_text": "황기갈비탕",
        "price_krw_display": "₩15,000",
    })

    texts = _texts(app)
    assert any("₩15,000" in text for text in texts)
    assert any("황기갈비탕" in text for text in texts)


# --- AC-15 ------------------------------------------------------------------


def test_ac15_한_줄_안내가_찾은_줄과_자리를_못_찾은_줄을_밝힌다():
    app = _select_screen(
        [
            _candidate(source={"text": "갈비탕", "left": 0.1, "top": 0.1,
                               "width": 0.3, "height": 0.1}),
            _candidate(food_id=2, name_en="Kimchi Stew", name_kr="김치찌개"),
            _candidate(food_id=3, name_en="Bulgogi", name_kr="불고기"),
        ],
        image=_sample_photo(),
    )

    summary = [text for text in _texts(app) if text.startswith("We found")]
    assert summary == ["We found 3 dishes. Each box shows what we read there — "
                       "we could not pin 2 to a spot on the photo."]


def test_ac15_사진이_없으면_상자_이야기를_하지_않는다():
    app = _select_screen(
        [_candidate(), _candidate(food_id=2, name_en="Kimchi Stew", name_kr="김치찌개")]
    )

    summary = [text for text in _texts(app) if text.startswith("We found")]
    assert summary == ["We found 2 dishes."]


# --- AC-06 (기존 AC, 비우는 열쇠가 늘어나 함께 확인한다) --------------------


def test_ac06_처음으로_돌아가면_이전_결과가_남지_않는다():
    app = _select_screen(
        [_candidate(), _candidate(food_id=2, name_en="Kimchi Stew", name_kr="김치찌개")],
        image=_sample_photo(),
    )

    [button] = [button for button in app.button if button.label == "Take a new photo"]
    button.click().run()

    for key in ("analysis", "guide", "image", "picked"):
        assert key not in app.session_state
    assert app.session_state["step"] == "upload"


# --- 상세 화면 개편 (요약 블록 · 노트형 본문 · 대표 사진 · 뒤로가기) ---------


def test_요약_블록에_발음은_따옴표_안쪽만_보인다():
    app = _result_screen()

    texts = _texts(app)
    # 요약 블록은 스크롤 없이 다 보여야 해서 발음만 뽑아 쓴다. 원문이
    # `"gal-bi-tang."` 꼴이라 따옴표 안에 마침표가 들어 있는데, 그것까지 그대로
    # 두면 화면에 `"gal-bi-tang."`으로 보인다 — 문장부호를 떼고 인용부호로 감싼다.
    assert any("&ldquo;gal-bi-tang&rdquo;" in text for text in texts)
    # 문장 전체는 본문 Pronunciation 항목에 그대로 남는다.
    assert any("is pronounced" in text for text in texts)


def test_발음_안내에_따옴표가_없으면_요약에서_생략한다():
    guide = _guide()
    guide["details"]["PRONUNCIATION"] = "Say it as it looks."

    app = _result_screen(guide=guide)

    assert not app.exception
    assert any("Say it as it looks." in text for text in _texts(app))


def test_상세_화면에_대표_사진과_출처가_함께_나온다():
    app = _result_screen(picked={
        "thumbnail_url": "https://example.com/galbitang.jpg",
        "thumbnail_attribution": "Source: AI Hub Tourism Menu Board Dataset (NIA)",
    })

    assert len(app.image) == 1
    # 사진을 보여주는 자리에는 출처가 반드시 함께 있어야 한다.
    assert any("AI Hub Tourism Menu Board Dataset" in text for text in _texts(app))


def test_대표_사진이_없으면_사진도_출처도_그리지_않는다():
    app = _result_screen(picked={"thumbnail_attribution": "Source: 아무개"})

    assert len(app.image) == 0
    assert not any("아무개" in text for text in _texts(app))


def test_본문에서_경고_스타일은_알레르기_하나뿐이다():
    app = _result_screen()

    # 노트 형식이라 항목마다 상자를 두르지 않는다. 알레르기만 경고로 남긴다 —
    # 안전 정보라 눈에 띄어야 한다.
    warnings = [element.value for element in app.warning]
    assert warnings == ["Contains soy."]


def test_음성이_없으면_경고와_내레이션_글이_대신_나온다():
    app = _result_screen(guide=_guide(tts_status="not_ready", narration_audio_path=None))

    warnings = [element.value for element in app.warning]
    # 오디오 실패 경고 + 알레르기 경고 두 개다.
    assert "Audio guide is unavailable right now." in warnings
    assert "Contains soy." in warnings
    assert any("A beef short rib soup." in text for text in _texts(app))


def test_목록으로_돌아가도_분석_결과가_남아있다():
    analysis = {
        "status": "candidates_found",
        "ocr_text": "갈비탕",
        "candidates": [_candidate(), _candidate(food_id=2, name_en="Kimchi Stew",
                                                name_kr="김치찌개")],
        "unsupported_lines": [],
    }
    app = _result_screen(analysis=analysis)

    [button] = [b for b in app.button if b.label == "Back to the list"]
    button.click().run()

    assert app.session_state["step"] == "select"
    # 서버를 다시 부르지 않으려면 분석 결과가 그대로 남아 있어야 한다.
    assert app.session_state["analysis"] == analysis
    assert [element.value for element in app.subheader] == ["Which dish is it?"]


# --- 장바구니 (docs/specs/cart.md) -------------------------------------------


def test_담기_전에는_더하기만_담긴_뒤에는_빼기와_수량이_보인다():
    # 0인데 `−`가 있으면 눌러도 아무 일이 없어 고장처럼 읽힌다(cart.md EC-02).
    empty = _select_screen([_candidate(), _candidate(food_id=2, name_en="K", name_kr="김치찌개")])
    labels = [element.label for element in empty.button]
    assert labels.count("Add to order") == 2
    assert "−" not in labels

    filled = _select_screen(
        [_candidate(), _candidate(food_id=2, name_en="K", name_kr="김치찌개")],
        cart=_cart([_cart_line(quantity=2)]),
    )
    labels = [element.label for element in filled.button]
    assert labels.count("−") == 1
    assert labels.count("Add to order") == 1  # 아직 안 담은 줄만
    assert any("2" == text.strip() or ">2<" in text for text in _texts(filled))


def test_담기_요청은_줄을_가리키는_값을_함께_보낸다():
    app = _select_screen([
        _candidate(food_id=7, name_kr="만두", name_en="Dumplings",
                   menu_text="물만두 8,000", name_text="물만두", price_krw=8000),
        _candidate(food_id=2, name_en="K", name_kr="김치찌개"),
    ])

    response = MagicMock()
    response.json.return_value = _cart([_cart_line()])
    with patch("requests.request", return_value=response) as request:
        # 첫 줄(물만두)의 담기 버튼
        [first_add, _] = [e for e in app.button if e.label == "Add to order"]
        first_add.click().run()

    sent = request.call_args.kwargs["json"]
    assert sent["food_id"] == 7
    # `food_id`만으로는 물만두와 군만두를 가를 수 없다(cart.md EC-12).
    assert sent["menu_text"] == "물만두 8,000"
    assert sent["price_krw"] == 8000
    assert sent["quantity_delta"] == 1


def test_안내_못_하는_줄도_담을_수_있고_이름_자리에_메뉴판_글자를_보낸다():
    app = _select_screen(
        [_candidate()],
        [_unsupported(menu_text="공기밥 1,000", name_text="공기밥")],
    )

    # 설명은 못 해도 주문은 된다 — 담기 버튼은 열어둔다.
    assert [element.label for element in app.button].count("Add to order") == 2
    # 설명 보기는 여전히 막는다.
    assert len(_select_buttons(app)) == 1

    response = MagicMock()
    response.json.return_value = _cart()
    with patch("requests.request", return_value=response) as request:
        # 두 번째 "Add to order"가 미지원 줄이다.
        [_, unsupported_add] = [e for e in app.button if e.label == "Add to order"]
        unsupported_add.click().run()

    sent = request.call_args.kwargs["json"]
    assert sent["food_id"] is None
    assert sent["name_kr"] == "공기밥 1,000"


def test_같은_food_id_두_줄은_각각_따로_담긴다():
    # 카트에는 물만두만 담겨 있다. 군만두 줄은 아직 안 담긴 상태로 보여야 한다.
    app = _select_screen(
        [
            _candidate(food_id=7, name_kr="만두", name_en="Dumplings",
                       menu_text="물만두 8,000", name_text="물만두"),
            _candidate(food_id=7, name_kr="만두", name_en="Dumplings",
                       menu_text="군만두 8,000", name_text="군만두"),
        ],
        cart=_cart([_cart_line(food_id=7, menu_text="물만두 8,000", quantity=1)]),
    )

    labels = [element.label for element in app.button]
    assert labels.count("−") == 1
    assert labels.count("Add to order") == 1


def test_빈_카트에서는_주문과_비우기를_누를_수_없다():
    app = _select_screen([_candidate(), _candidate(food_id=2, name_en="K", name_kr="김치찌개")])

    # 빈 주문 확인 화면으로 넘어가지 않는다(cart.md EC-07).
    assert _button(app, "Order").proto.disabled
    assert _button(app, "Clear cart").proto.disabled


def test_담긴_것이_있으면_주문과_비우기를_누를_수_있다():
    app = _select_screen(
        [_candidate(), _candidate(food_id=2, name_en="K", name_kr="김치찌개")],
        cart=_cart([_cart_line()]),
    )

    assert not _button(app, "Order").proto.disabled
    assert not _button(app, "Clear cart").proto.disabled


def test_카트_요청이_실패해도_담긴_내용을_지우지_않는다():
    cart = _cart([_cart_line(quantity=2)])
    app = _select_screen(
        [_candidate(), _candidate(food_id=2, name_en="K", name_kr="김치찌개")],
        cart=cart,
    )

    with patch("requests.request", side_effect=requests.RequestException):
        _button(app, "+").click().run()

    # 서버가 잠깐 안 되는 것과 카트가 비는 것은 다른 일이다(cart.md EC-06).
    assert app.session_state["cart"] == cart
    assert "We couldn't update your order just now." in [e.value for e in app.warning]


def test_주문_확인_화면은_한글_이름과_수량과_총계를_보여준다():
    app = AppTest.from_file(APP_PATH)
    app.session_state["step"] = "cart"
    app.session_state["cart"] = _cart(
        [_cart_line(name_text="황기갈비탕", quantity=2, line_total_display="₩30,000")],
        total_krw_display="₩30,000",
    )
    app.run()

    texts = _texts(app)
    # 이 화면을 읽는 사람은 종업원이다 — 한국어 이름이 크게 나와야 한다.
    assert any("황기갈비탕" in text for text in texts)
    assert any("&times;2" in text for text in texts)
    assert any("₩30,000" in text for text in texts)
    # 어디로도 주문을 보내지 않는다 — 접수된 것처럼 읽히는 문구를 쓰지 않는다.
    assert not any("received" in text.lower() or "접수" in text for text in texts)


def test_가격을_못_읽은_메뉴가_있으면_총계가_일부라고_밝힌다():
    app = AppTest.from_file(APP_PATH)
    app.session_state["step"] = "cart"
    app.session_state["cart"] = _cart([_cart_line()], has_unpriced_items=True)
    app.run()

    assert any("this total is partial" in text for text in _texts(app))


def test_주문_확인에서_돌아가도_카트가_남아있다():
    cart = _cart([_cart_line()])
    app = AppTest.from_file(APP_PATH)
    app.session_state["step"] = "cart"
    app.session_state["cart"] = cart
    app.session_state["analysis"] = {
        "status": "candidates_found",
        "ocr_text": "",
        "candidates": [_candidate(), _candidate(food_id=2, name_en="K", name_kr="김치찌개")],
        "unsupported_lines": [],
    }
    app.run()

    _button(app, "Back to the list").click().run()

    # 보여주고 돌아와 수량을 고칠 수 있어야 한다(cart.md EC-08).
    assert app.session_state["step"] == "select"
    assert app.session_state["cart"] == cart


def _upload(app: AppTest) -> AppTest:
    """업로드 화면에 사진 한 장을 올린다."""
    return app.file_uploader[0].set_value(("menu.jpg", _sample_photo(), "image/jpeg")).run()


def _analyze_response(status: str = "candidates_found") -> MagicMock:
    response = MagicMock()
    response.json.return_value = {
        "status": status,
        "ocr_text": "갈비탕",
        "candidates": [
            _candidate(),
            _candidate(food_id=2, name_en="K", name_kr="김치찌개"),
        ] if status == "candidates_found" else [],
        "unsupported_lines": [],
    }
    return response


def test_새_메뉴판을_읽으면_카트를_비운다():
    app = AppTest.from_file(APP_PATH)
    app.session_state["cart"] = _cart([_cart_line()])
    app.run()

    cart_response = MagicMock()
    cart_response.json.return_value = _cart()
    with patch("requests.post", return_value=_analyze_response()), \
         patch("requests.request", return_value=cart_response) as request:
        _upload(app)

    # A식당에서 담아둔 것이 B식당 메뉴판을 찍은 뒤에도 남으면 안 된다(cart.md EC-09).
    method, url = request.call_args.args
    assert method == "DELETE"
    assert url.endswith("/api/cart")
    assert app.session_state["cart"]["item_count"] == 0


def test_사진_인식에_실패하면_카트를_그대로_둔다():
    cart = _cart([_cart_line()])
    app = AppTest.from_file(APP_PATH)
    app.session_state["cart"] = cart
    app.run()

    with patch("requests.post", return_value=_analyze_response("ocr_empty")), \
         patch("requests.request") as request:
        _upload(app)

    # 흐리게 찍어 다시 찍는 흔한 흐름에서 담아둔 것을 잃지 않게 한다(cart.md EC-10).
    request.assert_not_called()
    assert app.session_state["cart"] == cart


def test_안내_못_하는_줄은_주문_확인에서_영문_줄을_그리지_않는다():
    app = AppTest.from_file(APP_PATH)
    app.session_state["step"] = "cart"
    app.session_state["cart"] = _cart([
        _cart_line(food_id=None, name_kr="공기밥 1,000", name_en="공기밥 1,000",
                   menu_text="공기밥 1,000", name_text="공기밥"),
    ])
    app.run()

    texts = _texts(app)
    assert any("공기밥" in text for text in texts)
    # 영어 이름이 없어 메뉴판 글자를 담아 보낸 줄이다. 그대로 찍으면 같은 말이 두 번
    # 나오고 가격도 두 번 보인다.
    assert not any("공기밥 1,000" in text for text in texts)
