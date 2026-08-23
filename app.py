"""Streamlit 진입점 — 화면만 담당하고, 계산은 FastAPI(`K_Menu_Talk.py`)를 HTTP로 부른다.

처음에는 화면과 파이프라인을 한 프로세스에 직접 연결했지만(이 파일의 이전 버전),
GPU 실측(2026-08-23) 후 계산을 GPU Space 한 곳에 몰기로 하면서 이 파일은 무료 CPU
Space에서 도는 화면 전용 클라이언트가 됐다 — `src/`를 임포트하지 않으므로 paddle·torch
없이 뜬다. 결정 배경과 계약은 docs/specs/streamlit-app.md, docs/specs/api-layer.md 참고.

모바일 앱(`mobile/lib/api.dart`)과 같은 API·같은 계약을 쓴다. API 주소는 환경변수
`API_BASE_URL`로 주입한다(앱의 `config.dart`와 같은 방식). 기본값은 로컬 개발용이다.

디자인(CSS·테마)은 아직 입히지 않았다. 이 파일은 그 CSS가 붙을 골격 역할을 한다.
"""

import os

import requests
import streamlit as st

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

st.set_page_config(page_title="K-Menu Voice Guide", page_icon="🍲", layout="centered")


def _go(step: str) -> None:
    """화면을 바꾼다. Streamlit은 스크립트를 처음부터 다시 실행하므로 상태는 session_state에 둔다."""
    st.session_state["step"] = step


def _reset() -> None:
    """처음 화면으로 돌아가면서 이전 분석 결과를 모두 비운다."""
    for key in ("analysis", "guide"):
        st.session_state.pop(key, None)
    _go("upload")


def screen_upload() -> None:
    """1번 화면 — 메뉴 사진을 촬영하거나 업로드한다."""
    st.title("K-Menu Voice Guide")
    st.caption("Photograph a Korean menu and get an English guide with audio.")

    photo = st.camera_input("Take a photo of the menu")
    uploaded = st.file_uploader("or upload a photo", type=["jpg", "jpeg", "png"])
    image = photo or uploaded
    if image is None:
        return

    # 계약은 api-layer.md의 POST /api/analyze — multipart, 필드명 "image".
    with st.spinner("Reading the menu..."):
        try:
            response = requests.post(
                f"{API_BASE_URL}/api/analyze",
                files={"image": (image.name or "menu.jpg", image.getvalue())},
                timeout=REQUEST_TIMEOUT_SEC,
            )
            response.raise_for_status()
        except requests.RequestException:
            _go("api_error")
            st.rerun()
    st.session_state["analysis"] = response.json()
    _go("select")
    st.rerun()


def screen_select() -> None:
    """2번 화면 — 인식된 음식 후보를 보여주고 하나를 고르게 한다."""
    analysis = st.session_state["analysis"]
    status = analysis["status"]

    if status in ERROR_MESSAGES:
        heading, hint = ERROR_MESSAGES[status]
        st.subheader(heading)
        st.write(hint)
        st.button("Take a new photo", on_click=_reset)
        return

    candidates = analysis["candidates"]
    st.subheader("Which dish is it?")

    # 후보가 하나뿐이면 고르게 할 이유가 없어 바로 결과로 넘긴다.
    if len(candidates) == 1:
        _select_food(candidates[0]["food_id"])
        st.rerun()
        return

    for candidate in candidates:
        label = f"{candidate['name_kr']} · {candidate['name_en']}"
        if st.button(label, key=f"candidate_{candidate['food_id']}", use_container_width=True):
            _select_food(candidate["food_id"])
            st.rerun()

    st.button("Take a new photo", on_click=_reset)


def _select_food(food_id: int) -> None:
    """고른 음식의 설명·음성을 한 번만 받아 session_state에 담는다.

    Streamlit은 버튼 하나 누를 때마다 스크립트를 처음부터 다시 실행한다. 결과를 여기
    담아두지 않으면 화면이 갱신될 때마다 서버가 TTS를 다시 돌린다(캐시 미스면 요청당 33초).
    """
    # 계약은 api-layer.md의 GET /api/foods/{food_id} — 상세·나레이션·맵기가 한 응답에 다 있다.
    with st.spinner("Preparing your guide..."):
        try:
            response = requests.get(
                f"{API_BASE_URL}/api/foods/{food_id}", timeout=REQUEST_TIMEOUT_SEC
            )
            response.raise_for_status()
        except requests.RequestException:
            _go("api_error")
            return

    st.session_state["guide"] = response.json()
    _go("result")


def screen_result() -> None:
    """3번 화면 — 카테고리 6개 상세 카드와 내레이션 음성을 보여준다."""
    guide = st.session_state["guide"]

    st.title(guide["name_kr"])
    st.caption(guide["name_en"])
    # 맵기 단계를 불꽃 5개로 표시한다(README 3절 "불꽃 아이콘 5개 채움").
    st.write("🌶️" * guide["spice_level"] + "·" * (5 - guide["spice_level"]))

    if guide["narration_audio_path"]:
        # 응답의 경로는 상대 경로(/audio/...)다 — 파일은 API 서버에 있으므로 주소를 붙인다.
        st.audio(f"{API_BASE_URL}{guide['narration_audio_path']}")
    else:
        # TTS가 실패해도 상세 텍스트는 그대로 보여준다(README 9절 위험 대응).
        st.warning("Audio guide is unavailable right now.")
        st.write(guide["narration_text"])

    for category, title, is_warning in DETAIL_CARDS:
        with st.container(border=True):
            st.markdown(f"**{title}**")
            text = guide["details"].get(category, "")
            # if문으로 쓴다 — 삼항 표현식으로 두면 Streamlit의 magic(한 줄에 남은 값을
            # 자동 출력하는 기능)이 그 반환값까지 화면에 그린다. st.write()는 None이라
            # "None" 배지가, st.warning()은 내부 객체라 Streamlit API 설명서 표가 통째로
            # 카드 안에 렌더링됐다(실측 2026-08-24).
            if is_warning:
                st.warning(text)
            else:
                st.write(text)

    st.button("Take a new photo", on_click=_reset)


def screen_api_error() -> None:
    """예외 화면 — API 서버에 연결하지 못했다(EC-07). 잠자던 Space가 깨는 중일 수도 있다."""
    st.subheader("We couldn't reach the service")
    st.write("The server may be waking up. Please try again in a moment.")
    st.button("Try again", on_click=_reset)


SCREENS = {
    "upload": screen_upload,
    "select": screen_select,
    "result": screen_result,
    "api_error": screen_api_error,
}

SCREENS[st.session_state.setdefault("step", "upload")]()
