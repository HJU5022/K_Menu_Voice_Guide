"""배포 진입점 — FastAPI로 analyze/foods API를 노출하고 src/pipeline.py만 호출한다.

Gradio 대신 FastAPI를 쓴다: 프론트엔드가 별도 웹앱(React)이라 Gradio 화면이 아니라
HTTP API 계약이 필요하기 때문이다(docs/specs/api-layer.md 참고). 이 파일에는
요청/응답 변환만 두고, OCR·텍스트·TTS 로직은 그대로 src/ 아래에 둔다.
"""

import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.pipeline import analyze_image, create_tts_response
from src.text_gen.detail import get_details, get_food_info

app = FastAPI(title="K-Menu Voice Guide API")

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
