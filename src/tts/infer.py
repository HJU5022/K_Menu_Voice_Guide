"""TTS 추론 스켈레톤.

현재는 TTS 모델을 로드하지 않는다. 다음 단계에서 XTTS-v2 또는 F5-TTS
추론을 이 함수 안에 연결하더라도, pipeline과 UI의 입출력 계약은 유지한다.
"""

from time import perf_counter


VALID_STYLES = frozenset({"GUIDE", "CAUTION"})


def synthesize(text: str, style: str) -> dict[str, object]:
    """Validate a narration request and return the pre-model TTS result."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("TTS text는 비어 있지 않은 문자열이어야 합니다.")
    if style not in VALID_STYLES:
        raise ValueError("TTS style은 GUIDE 또는 CAUTION이어야 합니다.")

    started_at = perf_counter()
    # TODO: Step 5에서 여기서 실제 TTS 모델을 호출하고 WAV 경로를 반환한다.
    return {
        "audio_path": None,
        "latency_ms": (perf_counter() - started_at) * 1000,
        "status": "not_ready",
    }
