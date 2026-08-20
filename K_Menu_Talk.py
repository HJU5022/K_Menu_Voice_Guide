"""배포 진입점 — FastAPI로 analyze/foods API를 노출하고 src/pipeline.py만 호출한다.

Gradio 대신 FastAPI를 쓴다: 프론트엔드가 별도 웹앱(React)이라 Gradio 화면이 아니라
HTTP API 계약이 필요하기 때문이다(docs/specs/api-layer.md 참고). 이 파일에는
요청/응답 변환만 두고, OCR·텍스트·TTS 로직은 그대로 src/ 아래에 둔다.
"""

# 다른 어떤 import보다도 먼저 torch를 로드해야 한다 — src/pipeline.py가 쓰는 paddleocr을
# import하면 내부적으로 paddlex -> modelscope로 이어지는 체인이 torch를 끌어오는데, 그
# 시점에 paddle이 이미 로드해둔 네이티브 DLL과 얽혀 torch의 shm.dll 로딩이 깨진다
# (Windows, OSError: [WinError 127]). src/pipeline.py가 TTS 추론 자체는 별도 venv의
# 자식 프로세스로 분리했지만(src/tts/worker.py), 이 문제는 그것과 무관하게 paddleocr
# 초기화 시점에 또 발생한다 — 실측 재현·검증 완료(2026-08-20).
import torch  # noqa: F401

import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

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


class Candidate(BaseModel):
    food_id: int
    name_kr: str
    name_en: str
    score: int
    modifiers: dict


class AnalyzeResponse(BaseModel):
    status: str
    ocr_text: str
    candidates: list[Candidate]


class FoodDetailResponse(BaseModel):
    food_id: int
    name_kr: str
    name_en: str
    details: dict[str, str]
    narration_text: str
    style: str
    tts_status: str
    narration_audio_path: str | None
    tts_latency_ms: float


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


@app.get("/api/foods/{food_id}", response_model=FoodDetailResponse)
def get_food(food_id: int):
    try:
        details = get_details(food_id)
        food_info = get_food_info(food_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"food_id {food_id}를 찾을 수 없습니다.")

    tts_response = create_tts_response(food_id)
    tts_response["narration_audio_path"] = _publish_audio(tts_response["narration_audio_path"])
    return {**food_info, "details": details, **tts_response}
