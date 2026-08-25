"""배포 진입점 — FastAPI로 analyze/foods API를 노출하고 src/pipeline.py만 호출한다.

화면을 갖지 않는다: 모바일 앱이 별도 클라이언트라 화면이 아니라 HTTP API 계약이
필요하기 때문이다(docs/specs/api-layer.md 참고). 이 파일에는 요청/응답 변환만 두고,
OCR·텍스트·TTS 로직은 그대로 src/ 아래에 둔다.

웹 화면은 `frontend/`(React)가 맡는다 — 이 API를 HTTP로 부르는 별도 클라이언트이며,
src/를 직접 임포트하지 않는다.
"""

# 다른 어떤 import보다도 먼저 torch를 로드해야 한다 — src/pipeline.py가 쓰는 paddleocr을
# import하면 내부적으로 paddlex -> modelscope로 이어지는 체인이 torch를 끌어오는데, 그
# 시점에 paddle이 이미 로드해둔 네이티브 DLL과 얽혀 torch의 shm.dll 로딩이 깨진다
# (Windows, OSError: [WinError 127]). src/pipeline.py가 TTS 추론 자체는 별도 venv의
# 자식 프로세스로 분리했지만(src/tts/worker.py), 이 문제는 그것과 무관하게 paddleocr
# 초기화 시점에 또 발생한다 — 실측 재현·검증 완료(2026-08-20).
import torch  # noqa: F401

# torch 다음, 다른 src.* import보다 먼저 로깅을 설정한다 — 순서가 밀리면 다른 라이브러리가
# 먼저 logging.basicConfig()를 호출해(흔한 일이다) 이 설정이 무시된다. stdout으로 보내는
# 이유는 배포된 Space에 셸 접근이 없어, Container 로그 화면에서 보이는 게 stdout뿐이기
# 때문이다(docs/specs/error-logging.md).
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
# httpx(Supabase 클라이언트가 내부적으로 씀)가 요청 URL을 INFO로 찍어 공개 Space 로그에
# 그대로 노출된다(실측 2026-08-24) — WARNING 이상만 남긴다.
logging.getLogger("httpx").setLevel(logging.WARNING)

import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.cart.store import change_quantity, clear_cart, get_cart
from src.db.cache import get_food as get_food_row, get_foods
from src.pipeline import analyze_image, create_tts_response
from src.text_gen.detail import get_details, get_food_info

app = FastAPI(title="K-Menu Voice Guide API")

# 프론트엔드가 별도 포트(예: Vite 개발 서버 :5173)에서 이 API(:8000)를 호출하므로
# CORS 허용이 필요하다. 지금은 쿠키/인증 헤더를 안 쓰는 구조라 "*"로 열어두되,
# 나중에 인증이 붙으면 allow_origins를 실제 프론트 배포 주소로 좁혀야 한다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# src/tts/infer.py의 synthesize()는 시스템 임시 폴더에 wav를 쓴다 — 브라우저가 못 읽는
# 서버 로컬 경로이므로, 여기서 이 정적 폴더로 옮기고 /audio/{filename} URL로 노출한다.
AUDIO_DIR = Path(__file__).resolve().parent / "static" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/audio", StaticFiles(directory=str(AUDIO_DIR)), name="audio")


class CandidateSource(BaseModel):
    """이 후보가 메뉴판 사진의 어디에서, 어떤 글자에서 나왔는지 — 추적용.

    좌표는 **업로드한 원본 사진 기준 0~1 비율**이다(px가 아니다). 프론트가 사진을 어떤
    크기로 그리든 그대로 얹을 수 있게 하기 위함이며, 서버 쪽 전처리(회전·크기 조정)는
    이미 되돌린 값이다.
    """

    # OCR이 그 자리에서 실제로 읽은 글자. 음식명과 다를 수 있고(오인식·가격이 같이 붙음 등),
    # 그 차이 자체가 "왜 이 후보가 나왔는지"를 보여주는 정보다.
    text: str
    left: float
    top: float
    width: float
    height: float


class Candidate(BaseModel):
    food_id: int
    name_kr: str
    name_en: str
    score: int
    modifiers: dict
    # 메뉴판에서 위에서부터 센 줄 번호. 화면이 메뉴판에 인쇄된 순서대로 늘어놓을 때 쓴다.
    line_no: int | None = None
    thumbnail_url: str | None = None
    thumbnail_attribution: str | None = None
    # 이름이 여러 글자 상자에 걸쳐 잘리면 위치를 특정할 수 없어 null이 된다 —
    # 그때 프론트는 사진 위 상자 없이 후보 카드만 보여준다.
    source: CandidateSource | None = None
    # 메뉴판 사진 OCR 텍스트에서 이 음식명 근처에 있던 "OOO원" 값을 읽어온 것이다
    # (src/ocr/price.py) — DB나 임의 산정 값이 아니라 실제 사진에 적힌 가격이다.
    price_krw: int | None = None
    price_krw_display: str | None = None
    # 이 후보가 나온 메뉴판 줄의 글자 그대로. 같은 음식이 여러 줄에 있으면 후보도
    # 여러 개 나오는데(물만두/군만두 → 둘 다 "만두"), 그때 무엇이 다른지 알려주는
    # 유일한 단서다. 종업원에게 보여줄 때도 등록 이름보다 이쪽이 정확하다.
    menu_text: str | None = None
    # 같은 줄에서 가격만 뗀 것(src/ocr/price.py의 strip_prices). 화면은 가격을 이미
    # 따로 보여주므로, 줄 글자를 그대로 쓰면 같은 값이 두 번 보인다.
    name_text: str | None = None


class AnalyzeResponse(BaseModel):
    # candidates_found | unsupported_food | not_a_menu
    # not_a_menu는 글자는 읽혔지만 가격 붙은 메뉴 줄이 하나도 없을 때다(메뉴판이 아닌
    # 사진). 다시 찍으면 해결되는 상황과 그렇지 않은 상황을 화면이 구별하기 위한 값이다.
    status: str
    ocr_text: str
    candidates: list[Candidate]


class FoodDetailResponse(BaseModel):
    food_id: int
    name_kr: str
    name_en: str
    # 맵기 1~5. 상세 텍스트(details["SPICY"])와 별개로, 결과 화면 위쪽에 눈금을 그리는 데 쓴다.
    # get_food_info()가 이름 3개만 돌려주므로 아래 get_food()에서 cache를 한 번 더 읽어 채운다.
    spice_level: int
    details: dict[str, str]
    narration_text: str
    style: str
    tts_status: str
    narration_audio_path: str | None
    tts_latency_ms: float
    # 음식 이름만 읽은 음성. 화면은 이름 옆 스피커에 이것을, 아래 재생바에 나레이션을 건다.
    # 둘을 나눠 둬야 이름을 눌렀을 때 설명까지 같이 나오지 않는다.
    name_audio_path: str | None
    name_tts_status: str


class SupportedFood(BaseModel):
    """설정 화면의 "이 서비스가 지원하는 음식" 목록에 쓰는 한 줄 (docs/specs/supported-foods.md)."""

    food_id: int
    name_kr: str
    name_en: str


class CartItemChange(BaseModel):
    # 등록되지 않은 메뉴는 food_id가 없다. 설명은 못 해도 담을 수는 있어야 한다.
    food_id: int | None = None
    name_kr: str
    name_en: str
    # 메뉴판에 인쇄된 그 줄 글자(/api/analyze의 candidate.menu_text). 카트가 줄을
    # 구분하는 기준이라, 안 보내면 같은 음식의 서로 다른 줄이 한 줄로 합쳐진다.
    menu_text: str | None = None
    # 메뉴판 사진에서 읽은 가격을 프론트가 그대로 실어 보낸다 — 사진마다 값이 다르므로
    # 서버가 food_id로 되찾아올 수 있는 값이 아니다. 못 읽었으면 null.
    price_krw: int | None = None
    quantity_delta: int


class CartLine(BaseModel):
    food_id: int | None = None
    name_kr: str
    name_en: str
    menu_text: str | None = None
    # menu_text에서 가격만 뗀 것. 화면이 가격을 따로 보여주는 자리에서 이름까지
    # 가격을 달고 있으면 같은 값이 두 번 보인다.
    name_text: str | None = None
    price_krw: int | None
    price_krw_display: str | None
    quantity: int
    line_total_krw: int | None
    line_total_display: str | None


class CartResponse(BaseModel):
    """카트 전체 상태 — 담기/빼기/조회 어느 요청이든 이 모양 그대로 돌려준다."""

    cart_id: str
    items: list[CartLine]
    item_count: int
    total_krw: int
    total_krw_display: str
    # 가격을 못 읽은 메뉴가 담겨 있으면 true — 총계가 일부만 반영된 값이라는 표시.
    has_unpriced_items: bool


def _publish_audio(local_path: str | None) -> str | None:
    """TTS가 쓴 임시 wav 파일을 AUDIO_DIR로 옮기고 프론트가 쓸 상대 URL을 돌려준다."""
    if not local_path:
        return None
    source = Path(local_path)
    if not source.exists():
        return None
    dest = AUDIO_DIR / source.name
    shutil.move(str(source), str(dest))
    return f"/audio/{dest.name}"


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze(image: UploadFile = File(...)):
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_file:
        tmp_file.write(await image.read())
        tmp_path = tmp_file.name

    return analyze_image(tmp_path)


@app.get("/api/foods", response_model=list[SupportedFood])
def list_foods():
    """안내할 수 있는 음식 전체를 영문명 순으로 돌려준다.

    사진을 찍기 전에 "내 앞의 메뉴를 이 앱이 알아볼 수 있나"를 확인하는 용도라, 일부만
    추리지 않고 등록된 것을 전부 보낸다. 사진·맵기·가격은 싣지 않는다 — 이 화면의 질문은
    "무엇을 지원하나"이지 "무엇을 먹을까"가 아니다.
    """
    foods = get_foods()
    return sorted(
        ({"food_id": food["id"], "name_kr": food["name_kr"], "name_en": food["name_en"]} for food in foods),
        key=lambda food: food["name_en"],
    )


@app.get("/api/foods/{food_id}", response_model=FoodDetailResponse)
def get_food(food_id: int):
    try:
        details = get_details(food_id)
        food_info = get_food_info(food_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"food_id {food_id}를 찾을 수 없습니다.")

    # 위 get_food_info()가 통과했으므로 이 food_id의 행은 반드시 있다.
    spice_level = get_food_row(food_id)["spice_level"]

    tts_response = create_tts_response(food_id)
    tts_response["narration_audio_path"] = _publish_audio(tts_response["narration_audio_path"])
    tts_response["name_audio_path"] = _publish_audio(tts_response["name_audio_path"])
    return {**food_info, "spice_level": spice_level, "details": details, **tts_response}


# 로그인이 없는 서비스라, 카트는 브라우저가 만들어 localStorage에 보관하는 UUID로 구분한다.
# 처음 보는 ID면 빈 카트를 돌려준다 — 별도의 "카트 생성" 요청이 필요 없게.
@app.get("/api/cart", response_model=CartResponse)
def read_cart(x_cart_id: str = Header(..., alias="X-Cart-Id")):
    return get_cart(x_cart_id)


@app.delete("/api/cart", response_model=CartResponse)
def empty_cart(x_cart_id: str = Header(..., alias="X-Cart-Id")):
    return clear_cart(x_cart_id)


@app.post("/api/cart/items", response_model=CartResponse)
def change_cart_item(change: CartItemChange, x_cart_id: str = Header(..., alias="X-Cart-Id")):
    return change_quantity(
        x_cart_id,
        food_id=change.food_id,
        name_kr=change.name_kr,
        name_en=change.name_en,
        price_krw=change.price_krw,
        quantity_delta=change.quantity_delta,
        menu_text=change.menu_text,
    )
