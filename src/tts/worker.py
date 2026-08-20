"""TTS를 별도 프로세스에서 실행하기 위한 진입점 (``python -m src.tts.worker``).

이 서비스는 같은 프로세스에서 PaddleOCR(paddle)도 로드한다. paddleocr → paddlex →
modelscope로 이어지는 임포트 체인이 내부적으로 ``import torch``를 실행하는데, 그 시점에
paddle이 이미 로드해둔 네이티브 DLL과 얽혀 torch의 ``shm.dll`` 로딩이 깨진다
(Windows, ``OSError: [WinError 127]``). ``src/pipeline.py``는 이 문제를 피하려고
TTS 추론을 이 스크립트를 통해 완전히 별도인 자식 프로세스에서 실행한다 — 그 프로세스는
paddle을 전혀 임포트하지 않으므로 torch가 깨끗하게 로드된다.

stdin으로 ``{"text": ..., "style": ...}`` JSON 한 덩어리를 받아, stdout에 결과 JSON
한 줄(``src.tts.infer.synthesize()``와 동일한 형태)을 찍는다.

주의: qwen-tts/transformers 쪽이 모델을 불러오는 동안 ``print()``로 경고를 stdout에
직접 찍는 경우가 있다(예: "flash-attn is not installed"). 그대로 두면 이 텍스트가
결과 JSON 앞에 섞여서 호출 쪽(``src/pipeline.py``)의 ``json.loads()``가 깨진다 —
그래서 synthesize() 호출 동안은 stdout을 stderr로 돌려, 우리가 마지막에 쓰는
JSON 한 줄만 실제 stdout에 남게 한다.
"""

import contextlib
import json
import sys

from src.tts.infer import synthesize


def main() -> None:
    payload = json.loads(sys.stdin.read())
    real_stdout = sys.stdout
    try:
        with contextlib.redirect_stdout(sys.stderr):
            result = synthesize(payload["text"], payload["style"])
    except Exception as exc:
        result = {"audio_path": None, "status": "not_ready", "latency_ms": 0.0, "error": str(exc)}
    real_stdout.write(json.dumps(result))


if __name__ == "__main__":
    main()
