"""TTS를 별도 프로세스에서 실행하기 위한 진입점 (``python -m src.tts.worker``).

이 서비스는 같은 프로세스에서 PaddleOCR(paddle)도 로드한다. paddleocr → paddlex →
modelscope로 이어지는 임포트 체인이 내부적으로 ``import torch``를 실행하는데, 그 시점에
paddle이 이미 로드해둔 네이티브 DLL과 얽혀 torch의 ``shm.dll`` 로딩이 깨진다
(Windows, ``OSError: [WinError 127]``). ``src/pipeline.py``는 이 문제를 피하려고
TTS 추론을 이 스크립트를 통해 완전히 별도인 자식 프로세스에서 실행한다 — 그 프로세스는
paddle을 전혀 임포트하지 않으므로 torch가 깨끗하게 로드된다.

**상주 프로세스**: 요청 하나를 처리하고 끝내는 게 아니라, stdin이 닫힐 때까지 계속
살아있으면서 요청을 반복해서 받는다. 모델을 GPU에 올리는 데 대부분의 시간이 들기
때문이다(``src/tts/infer.py``의 ``_load_model()``이 전역 캐시를 쓰므로, 프로세스가
살아있는 한 두 번째 요청부터는 이미 올라간 모델을 그대로 재사용한다).

프로토콜 — **한 줄에 요청 하나, 한 줄에 응답 하나**:
    받는다: ``{"text": ..., "style": ...}`` JSON 한 줄
    보낸다: ``src.tts.infer.synthesize()``와 동일한 형태의 JSON 한 줄

주의: qwen-tts/transformers 쪽이 모델을 불러오는 동안 ``print()``로 경고를 stdout에
직접 찍는 경우가 있다(예: "flash-attn is not installed"). 그대로 두면 이 텍스트가
결과 JSON에 섞여서 호출 쪽(``src/pipeline.py``)의 ``json.loads()``가 깨진다 —
그래서 synthesize() 호출 동안은 stdout을 stderr로 돌려, 우리가 쓰는 JSON 줄만
실제 stdout에 남게 한다.
"""

import contextlib
import json
import sys

from src.tts.infer import synthesize

_FAILED = {"audio_path": None, "status": "not_ready", "latency_ms": 0.0}


def main() -> None:
    """한 줄씩 요청을 받아 음성을 만들고, 결과 JSON을 한 줄로 돌려주는 반복문.

    별도 프로세스로 도는 이유는 `paddle`(OCR)과 `torch`(TTS)를 한 프로세스에 함께
    올릴 수 없어서다. 이 파일은 paddle을 전혀 import하지 않는다.

    요청마다 프로세스를 새로 띄우지 않고 **살려두고 재사용**한다 — 모델 로딩이 이
    작업에서 제일 비싼 부분이라, 매번 띄우면 그 비용을 요청마다 다시 낸다.
    """
    # 결과 JSON을 쓸 진짜 stdout은 따로 붙들어둔다 — 아래에서 stdout을 stderr로
    # 돌리는 동안에도 이 핸들로는 정상적으로 쓸 수 있다.
    real_stdout = sys.stdout

    # readline이 ""(빈 문자열)을 주면 stdin이 닫혔다는 뜻 = 부모가 끝났거나 죽었다.
    # 그때 반복문이 끝나고 이 프로세스도 같이 정리된다.
    for line in iter(sys.stdin.readline, ""):
        line = line.strip()
        if not line:
            continue

        try:
            payload = json.loads(line)
            with contextlib.redirect_stdout(sys.stderr):
                result = synthesize(payload["text"], payload["style"])
        except Exception as exc:
            # 요청 하나가 실패해도 프로세스를 죽이지 않는다 — 죽이면 다음 요청이
            # 다시 모델 로딩(90초 이상)부터 시작해야 하기 때문이다.
            result = {**_FAILED, "error": str(exc)}

        real_stdout.write(json.dumps(result) + "\n")
        real_stdout.flush()


if __name__ == "__main__":
    main()
