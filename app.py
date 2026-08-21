"""Streamlit 진입점 — 화면과 파이프라인을 한 프로세스에서 직접 연결한다.

배포를 Hugging Face Spaces(Streamlit SDK)로 옮기기로 하면서, 기존 배포 진입점
`K_Menu_Talk.py`(FastAPI) + 별도 React 웹앱 구조를 이 파일 하나로 대신한다.
HTTP 계약이 사라지므로 CORS·VITE_API_BASE_URL·오디오 정적 서빙이 모두 불필요하다.

`src/` 아래 로직(ocr·text_gen·db·tts·pipeline)은 그대로 재사용한다 — 이 파일에는
화면 구성과 상태 전환만 둔다(`K_Menu_Talk.py`가 요청/응답 변환만 뒀던 것과 같은 원칙).

디자인(CSS·테마)은 아직 입히지 않았다. `frontend/src/styles.css`를 Streamlit으로
이식하는 작업이 별도로 진행 중이며, 이 파일은 그 CSS가 붙을 골격 역할을 한다.
"""

# 다른 어떤 import보다도 먼저 torch를 로드해야 한다 — 아래 src.pipeline이 쓰는
# paddleocr을 import하면 내부적으로 paddlex -> modelscope로 이어지는 체인이 torch를
# 끌어오는데, 그 시점에 paddle이 이미 로드해둔 네이티브 DLL과 얽혀 torch의 shm.dll
# 로딩이 깨진다(Windows, OSError: [WinError 127]). K_Menu_Talk.py와 같은 이유·같은 처방.
import torch  # noqa: F401

import tempfile

import streamlit as st

from src.db import cache
from src.pipeline import analyze_image, create_tts_response
from src.text_gen.detail import get_details, get_food_info

# 화면에 보여줄 카테고리 6개 — 순서와 영어 제목은 frontend/src/App.tsx의 DETAIL_CARDS를
# 그대로 옮겼다(frontend/docs/content-style.md의 문구 통일 기준을 따르기 위함).
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

    # analyze_image()는 파일 경로를 받으므로 업로드된 바이트를 임시 파일로 떨군다
    # (K_Menu_Talk.py의 /api/analyze가 하던 것과 동일).
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_file:
        tmp_file.write(image.getvalue())
        tmp_path = tmp_file.name

    with st.spinner("Reading the menu..."):
        st.session_state["analysis"] = analyze_image(tmp_path)
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
    """고른 음식의 설명·음성을 한 번만 만들어 session_state에 담는다.

    Streamlit은 버튼 하나 누를 때마다 스크립트를 처음부터 다시 실행한다. 결과를 여기
    담아두지 않으면 화면이 갱신될 때마다 TTS가 다시 돌아간다(캐시 미스면 요청당 33초).
    """
    food = cache.get_food(food_id)
    with st.spinner("Preparing your guide..."):
        tts = create_tts_response(food_id)

    st.session_state["guide"] = {
        **get_food_info(food_id),
        "spice_level": food["spice_level"],
        "details": get_details(food_id),
        **tts,
    }
    _go("result")


def screen_result() -> None:
    """3번 화면 — 카테고리 6개 상세 카드와 내레이션 음성을 보여준다."""
    guide = st.session_state["guide"]

    st.title(guide["name_kr"])
    st.caption(guide["name_en"])
    # 맵기 단계를 불꽃 5개로 표시한다(README 3절 "불꽃 아이콘 5개 채움").
    st.write("🌶️" * guide["spice_level"] + "·" * (5 - guide["spice_level"]))

    if guide["narration_audio_path"]:
        st.audio(guide["narration_audio_path"])
    else:
        # TTS가 실패해도 상세 텍스트는 그대로 보여준다(README 9절 위험 대응).
        st.warning("Audio guide is unavailable right now.")
        st.write(guide["narration_text"])

    for category, title, is_warning in DETAIL_CARDS:
        with st.container(border=True):
            st.markdown(f"**{title}**")
            text = guide["details"].get(category, "")
            st.warning(text) if is_warning else st.write(text)

    st.button("Take a new photo", on_click=_reset)


SCREENS = {"upload": screen_upload, "select": screen_select, "result": screen_result}

SCREENS[st.session_state.setdefault("step", "upload")]()
