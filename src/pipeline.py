"""Narration and TTS pipeline skeleton.

The OCR and UI layers are deliberately outside this module. Given a matched
``food_id``, this module connects text generation to TTS and returns one
UI-friendly response.
"""

import json
import os
import queue
import subprocess
import threading
from pathlib import Path

from src.text_gen.narration import get_narration
from src.ocr.infer import recognize
from src.ocr.match import match_food, match_food_candidates
from src.text_gen.detail import get_details

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
_TTS_TIMEOUT_SEC = 300

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
            pass
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
            # 파이프가 어긋났을 수 있으므로(요청만 들어가고 응답이 안 온 상태 등)
            # 그냥 두면 다음 요청까지 계속 밀린다. 버리고 새로 시작하게 한다.
            _kill_worker()
            return dict(_TTS_FAILED)


def create_tts_response(food_id: int) -> dict[str, object]:
    """Create the text-and-audio response for one already-matched food.

    TTS 합성이 실패해도(GPU 없음, 모델 로딩 실패, 자식 프로세스 크래시 등) 텍스트 응답까지
    막지 않는다 — narration_text/style은 그대로 반환하고 tts_status만 "not_ready"로 남긴다
    (README 9절 "TTS 생성 실패 | 상세 텍스트 우선 출력" 참고).
    """
    narration = get_narration(food_id)
    tts_result = _synthesize_via_subprocess(narration["text"], narration["style"])

    return {
        "narration_text": narration["text"],
        "style": narration["style"],
        "narration_audio_path": tts_result.get("audio_path"),
        "tts_status": tts_result.get("status", "not_ready"),
        "tts_latency_ms": tts_result.get("latency_ms", 0.0),
    }


def analyze_image(image_path: str) -> dict:
    """Return OCR analysis status and food candidates without creating a response."""
    ocr_text = recognize(image_path).strip()
    if not ocr_text:
        return {"status": "ocr_empty", "ocr_text": "", "candidates": []}

    candidates = match_food_candidates(ocr_text)
    if not candidates:
        return {"status": "unsupported_food", "ocr_text": ocr_text, "candidates": []}

    return {"status": "candidates_found", "ocr_text": ocr_text, "candidates": candidates}


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
