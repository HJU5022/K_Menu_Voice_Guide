"""배포 진입점 — FastAPI로 analyze/foods API를 노출하고 src/pipeline.py만 호출한다.

Gradio 대신 FastAPI를 쓴다: 프론트엔드가 별도 웹앱(React)이라 Gradio 화면이 아니라
HTTP API 계약이 필요하기 때문이다(docs/specs/api-layer.md 참고). 이 파일에는
요청/응답 변환만 두고, OCR·텍스트·TTS 로직은 그대로 src/ 아래에 둔다.
"""

import tempfile

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.pipeline import analyze_image, create_tts_response
from src.text_gen.detail import get_details

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


class Candidate(BaseModel):
    food_id: int
    name_kr: str
    score: int
    modifiers: dict


class AnalyzeResponse(BaseModel):
    status: str
    ocr_text: str
    candidates: list[Candidate]


class FoodDetailResponse(BaseModel):
    details: dict[str, str]
    narration_text: str
    style: str
    tts_status: str
    narration_audio_path: str | None
    tts_latency_ms: float


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
    except ValueError:
        raise HTTPException(status_code=404, detail=f"food_id {food_id}를 찾을 수 없습니다.")

    tts_response = create_tts_response(food_id)
    return {"details": details, **tts_response}
