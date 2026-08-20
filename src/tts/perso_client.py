"""Perso.ai API 호출 — 비교 평가용 음성 생성.

우리 파인튜닝 모델과 같은 내레이션 텍스트를 넣어 MOS(UTMOS)로 비교한다.
배포 경로에는 들어가지 않는다. API 키는 .env의 PERSO_API_KEY에서 읽는다.

API 스펙 출처: https://platform.perso.ai/docs (Speech 제품)
- 인증: 헤더 `PersoPlatform-APIKey: <key>`
- 음성 목록: GET /api/speech/v2/voices
- 합성: POST /api/speech/v1/text-to-speech/{voice_id}?output_format=wav_24000
  body: {"text": "..."} -> 응답이 바이너리 오디오(200)
"""

import os

import requests

BASE_URL = "https://platform.perso.ai/api"
DEFAULT_OUTPUT_FORMAT = "wav_24000"  # infer.py/UTMOS 평가와 동일하게 24kHz로 맞춤


def _api_key() -> str:
    key = os.environ.get("PERSO_API_KEY")
    if not key:
        raise RuntimeError(
            "PERSO_API_KEY가 .env에 없습니다. https://platform.perso.ai/settings/apikey/ 에서 발급받아 추가하세요."
        )
    return key


def _headers() -> dict[str, str]:
    return {"PersoPlatform-APIKey": _api_key(), "Content-Type": "application/json"}


def create_voice(name: str, audio_paths: list[str], description: str | None = None) -> str:
    """오디오 샘플(들)로 음성을 클로닝해서 voice_id를 반환한다 (비동기, 202).

    audio_paths: MP3/WAV/M4A 파일 경로 목록. 합쳐서 30초~3분 권장.
    """
    if not audio_paths:
        raise ValueError("audio_paths가 비어 있습니다.")

    files = [("files", (os.path.basename(p), open(p, "rb"))) for p in audio_paths]
    data = {"name": name}
    if description:
        data["description"] = description
    try:
        resp = requests.post(
            f"{BASE_URL}/speech/v1/voices/add",
            headers={"PersoPlatform-APIKey": _api_key()},  # multipart라 Content-Type은 requests가 자동 설정
            data=data,
            files=files,
            timeout=120,
        )
    finally:
        for _, (_, fh) in files:
            fh.close()
    resp.raise_for_status()
    return resp.json()["voice_id"]


def list_voices(search: str | None = None, page_size: int = 30) -> list[dict[str, object]]:
    """사용 가능한 voice_id 목록을 가져온다. text-to-speech 호출 전에 한 번 확인해야 함."""
    params: dict[str, object] = {"page_size": page_size}
    if search:
        params["search"] = search
    resp = requests.get(f"{BASE_URL}/speech/v2/voices", headers=_headers(), params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()["voices"]


def synthesize(text: str, voice_id: str, output_format: str = DEFAULT_OUTPUT_FORMAT) -> bytes:
    """text를 지정한 voice_id로 합성해서 오디오 바이트를 반환한다."""
    if not text or not text.strip():
        raise ValueError("text는 비어 있지 않은 문자열이어야 합니다.")
    if not voice_id:
        raise ValueError("voice_id가 필요합니다. list_voices()로 먼저 확인하세요.")

    resp = requests.post(
        f"{BASE_URL}/speech/v1/text-to-speech/{voice_id}",
        headers=_headers(),
        params={"output_format": output_format},
        json={"text": text},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.content


def synthesize_to_file(text: str, voice_id: str, output_path: str, output_format: str = DEFAULT_OUTPUT_FORMAT) -> str:
    """synthesize()의 결과를 파일로 저장하고 경로를 반환한다."""
    audio_bytes = synthesize(text, voice_id, output_format=output_format)
    with open(output_path, "wb") as f:
        f.write(audio_bytes)
    return output_path
