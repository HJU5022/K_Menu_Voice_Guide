"""Narration and TTS pipeline skeleton.

The OCR and UI layers are deliberately outside this module. Given a matched
``food_id``, this module connects text generation to TTS and returns one
UI-friendly response.
"""

import json
import logging
import os
import queue
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from time import perf_counter

from src.text_gen.narration import get_narration
from src.ocr.infer import group_boxes_into_rows, recognize, recognize_boxes_with_mapping
from src.ocr.preprocess import to_original_bbox
from src.ocr.match import match_food, scan_menu_lines
from src.text_gen.detail import get_details

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# torch(TTS)는 이 프로세스가 이미 로드한 paddle(OCR)과 같은 venv/프로세스에 못 올라간다 —
# paddleocr → paddlex → modelscope가 내부적으로 torch를 끌어오는데, paddle이 먼저 로드한
# 네이티브 DLL과 얽혀 torch의 shm.dll 로딩이 깨진다(Windows, WinError 127). 그래서 TTS는
# torch만 깔린 별도 venv(.venv-tts)의 파이썬으로 완전히 다른 자식 프로세스에서 실행한다.
# 이 환경변수로 실제 경로를 다르게 지정할 수 있다(팀원마다 venv 위치가 다를 수 있어서).
_TTS_PYTHON = os.environ.get("TTS_VENV_PYTHON") or str(_PROJECT_ROOT / ".venv-tts" / "Scripts" / "python.exe")

# 워커가 stderr로 흘리는 라이브러리 경고·에러를 모아두는 곳. 파이프로 받아두면 버퍼가
# 가득 찼을 때 워커가 멈춰버리므로(고전적인 파이프 교착), 파일로 바로 흘려보낸다.
_TTS_LOG_PATH = _PROJECT_ROOT / "logs" / "tts_worker.log"

# 응답 대기 상한. 첫 요청은 모델을 GPU에 올리는 시간(실측 90~160초)이 포함되므로 넉넉히 준다.
# main에서 자식 프로세스 타임아웃을 300초 -> 600초로 늘린 것과 같은 값으로 맞춘다.
_TTS_TIMEOUT_SEC = 600

# Plan B — 사전 생성 캐시(src/tts/pregenerate.py가 만든 파일)가 있으면 라이브 생성 대신
# 그걸 쓴다. 실측 결과 라이브 생성이 워밍업 후에도 약 33초로 TTFB 목표(5~7초)를 크게
# 넘기 때문이다(README 9절 위험 대응 "초과 시 사전 생성 캐싱으로 전환").
_TTS_CACHE_DIR = _PROJECT_ROOT / "static" / "tts_cache"

_TTS_FAILED: dict[str, object] = {"audio_path": None, "status": "not_ready", "latency_ms": 0.0}

# 상주 워커 프로세스 하나를 계속 재사용한다(요청마다 새로 띄우면 매번 모델을 다시 올려야 한다).
# 파이프는 요청/응답이 한 줄씩 오가는 구조라 두 요청이 겹치면 서로 섞인다 — 그래서 아래
# 잠금으로 한 번에 하나씩만 통과시킨다.
_worker: subprocess.Popen | None = None
_worker_log = None
_worker_lock = threading.Lock()


def _open_worker_log():
    global _worker_log
    if _worker_log is None or _worker_log.closed:
        _TTS_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _worker_log = open(_TTS_LOG_PATH, "a", encoding="utf-8", buffering=1)
    return _worker_log


def _start_worker() -> subprocess.Popen:
    """워커를 새로 띄운다. 이 시점에는 아직 모델을 안 올리고, 첫 요청이 들어와야 올린다."""
    return subprocess.Popen(
        [_TTS_PYTHON, "-u", "-m", "src.tts.worker"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=_open_worker_log(),
        text=True,
        encoding="utf-8",
        cwd=_PROJECT_ROOT,
        # Windows 기본 인코딩(cp949)으로 열리면 한글이 섞였을 때 깨진다.
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )


def _kill_worker() -> None:
    """이상해진 워커를 버린다. 다음 요청 때 _start_worker()가 새로 띄운다."""
    global _worker
    if _worker is not None:
        try:
            _worker.kill()
        except Exception:
            # 이미 죽었거나 죽어가는 프로세스에 흔한 경로다(docs/specs/error-logging.md
            # EC-01) — ERROR로 올리지 않는다.
            logger.warning("TTS 워커 종료 실패", exc_info=True)
        _worker = None


def _readline_with_timeout(proc: subprocess.Popen, timeout: float) -> str | None:
    """proc.stdout.readline()에는 타임아웃이 없어서, 별도 스레드로 읽고 여기서 시간을 잰다.

    시간 안에 못 받으면 None을 돌려준다. 이 경우 호출 쪽이 워커를 죽이는데, 그러면
    막혀 있던 readline이 ""를 받고 스레드도 알아서 끝난다.
    """
    answer: queue.Queue = queue.Queue(maxsize=1)

    def _read() -> None:
        try:
            answer.put(proc.stdout.readline())
        except Exception:
            # _kill_worker()가 파이프를 닫으면서 정상적으로도 발생할 수 있는 경로다
            # (docs/specs/error-logging.md EC-02) — ERROR로 올리지 않는다.
            logger.warning("TTS 워커 응답 읽기 실패", exc_info=True)
            answer.put("")

    threading.Thread(target=_read, daemon=True).start()
    try:
        return answer.get(timeout=timeout)
    except queue.Empty:
        return None


def _synthesize_via_subprocess(text: str, style: str) -> dict[str, object]:
    """상주 중인 TTS 워커(``src/tts/worker.py``)에 한 줄을 보내고 한 줄을 받는다.

    워커가 아직 없거나(첫 요청) 죽어 있으면 새로 띄운다. 어떤 이유로든 실패하면
    예외를 올리지 않고 not_ready를 돌려준다 — 음성이 없어도 텍스트 응답은 나가야 한다.
    """
    global _worker
    with _worker_lock:
        try:
            # poll()이 None이 아니면 이미 종료된 프로세스다.
            if _worker is None or _worker.poll() is not None:
                _worker = _start_worker()

            _worker.stdin.write(json.dumps({"text": text, "style": style}) + "\n")
            _worker.stdin.flush()

            line = _readline_with_timeout(_worker, _TTS_TIMEOUT_SEC)
            if not line:
                raise RuntimeError("TTS 워커가 응답하지 않았습니다.")
            return json.loads(line)
        except Exception:
            # 여기서 예외를 그냥 삼키면 서로 다른 실패 원인(라이브러리 버전 충돌,
            # 컴파일러 부재, venv 없음 등)이 전부 API 응답의 "not_ready" 한 단어로
            # 뭉개진다 — 배포 환경에서 원인 파악에 재배포를 여러 번 반복하게 만든
            # 실제 사례가 있다(docs/specs/error-logging.md A-1~A-3). 반드시 로그로
            # 남긴다.
            logger.error(
                "TTS 합성 실패 (style=%s, text=%r)", style, text[:80], exc_info=True
            )
            # 파이프가 어긋났을 수 있으므로(요청만 들어가고 응답이 안 온 상태 등)
            # 그냥 두면 다음 요청까지 계속 밀린다. 버리고 새로 시작하게 한다.
            _kill_worker()
            return dict(_TTS_FAILED)


def _load_cached_tts(food_id: int, style: str) -> dict[str, object] | None:
    """사전 생성 캐시가 있으면 그 **복사본**의 경로를 synthesize()와 같은 형태로 돌려준다.

    복사본을 만드는 이유: K_Menu_Talk.py의 _publish_audio()가 받은 파일을 정적 폴더로
    이동(move)시키므로, 캐시 원본을 그대로 넘기면 첫 요청이 캐시를 소모해버린다.
    """
    cached = _TTS_CACHE_DIR / f"food_{food_id}_{style}.wav"
    if not cached.is_file():
        return None

    started_at = perf_counter()
    copy = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    copy.close()
    shutil.copyfile(cached, copy.name)
    return {
        "audio_path": copy.name,
        "status": "ok",
        "latency_ms": (perf_counter() - started_at) * 1000,
    }


def create_tts_response(food_id: int) -> dict[str, object]:
    """Create the text-and-audio response for one already-matched food.

    TTS 합성이 실패해도(GPU 없음, 모델 로딩 실패, 자식 프로세스 크래시 등) 텍스트 응답까지
    막지 않는다 — narration_text/style은 그대로 반환하고 tts_status만 "not_ready"로 남긴다
    (README 9절 "TTS 생성 실패 | 상세 텍스트 우선 출력" 참고).
    """
    narration = get_narration(food_id)
    # 화면에는 로마자 원문(text), 모델에는 음식명이 한글 표기로 바뀐 tts_text를 넘긴다.
    tts_result = _load_cached_tts(food_id, narration["style"]) or _synthesize_via_subprocess(
        narration["tts_text"], narration["style"]
    )

    return {
        "narration_text": narration["text"],
        "style": narration["style"],
        "narration_audio_path": tts_result.get("audio_path"),
        "tts_status": tts_result.get("status", "not_ready"),
        "tts_latency_ms": tts_result.get("latency_ms", 0.0),
    }


def analyze_image(image_path: str) -> dict:
    """Return OCR analysis status and food candidates without creating a response."""
    # 좌표까지 살려서 받는다 — 가격이 음식명 아래 줄에 적혀 있어도 위치로 짝지어야 하고,
    # 각 후보가 사진 어디에서 나왔는지도 표시해야 한다.
    ocr_boxes, mapping = recognize_boxes_with_mapping(image_path)
    ocr_text = " ".join(group_boxes_into_rows(ocr_boxes)).strip()
    if not ocr_text:
        return {"status": "ocr_empty", "ocr_text": "", "candidates": []}

    # 줄 단위로 매칭한다 — 같은 음식이 여러 줄에 있으면 줄마다 후보가 나온다.
    # 통짜 텍스트로 매칭하면 "물만두"와 "군만두"가 만두 후보 하나로 합쳐지고,
    # 수식어도 메뉴판 전체에서 긁어와 엉뚱한 메뉴에 붙는다
    # (match_food_candidates_by_line 설명 참고).
    candidates, unsupported = scan_menu_lines(ocr_boxes)

    # 안내 못 하는 줄도 함께 내보낸다. 등록 음식이 50개뿐이라 메뉴판의 대부분이
    # 매칭되지 않는데(실측 22.9%만 매칭), 그걸 버리면 여행자는 그 메뉴가 아예
    # 없는 것처럼 본다. 설명은 못 해도 이름과 가격은 보여줄 수 있다.
    unsupported_lines = [_attach_source(line, mapping) for line in unsupported]

    # status는 예전 뜻 그대로 둔다 — candidates가 비면 unsupported_food다.
    # 웹앱은 unsupported_lines를 모르므로, 바꾸면 그쪽 화면이 어긋난다.
    status = "candidates_found" if candidates else "unsupported_food"
    return {
        "status": status,
        "ocr_text": ocr_text,
        "candidates": [_attach_source(candidate, mapping) for candidate in candidates],
        "unsupported_lines": unsupported_lines,
    }


def _attach_source(candidate: dict, mapping) -> dict:
    """후보의 글자 상자 좌표를 원본 사진 기준 비율로 옮겨 source 필드로 만든다.

    match 단계의 좌표는 전처리(회전·크기 조정)를 거친 이미지 기준이라, 사용자가 올린
    사진 위에 그대로 그리면 어긋난다. 비율(0~1)로 바꿔두면 프론트가 사진을 어떤 크기로
    보여주든 그대로 얹을 수 있다.
    """
    source_text = candidate.pop("source_text", None)
    source_box = candidate.pop("source_box", None)

    if source_box is None or source_text is None:
        candidate["source"] = None
        return candidate

    left, top, width, height = to_original_bbox(mapping, *source_box)
    candidate["source"] = {
        "text": source_text,
        "left": left,
        "top": top,
        "width": width,
        "height": height,
    }
    return candidate


def run(image_path: str) -> dict:
    """이미지 하나를 받아 OCR → 매칭 → 텍스트생성 → TTS까지 이어서 최종 응답을 만든다."""
    text = recognize(image_path)
    match_result = match_food(text)
    if match_result is None:
        return {"matched_food": None}

    food_id = match_result["food_id"]
    response = create_tts_response(food_id)
    response["matched_food"] = match_result
    response["details"] = get_details(food_id)
    return response
