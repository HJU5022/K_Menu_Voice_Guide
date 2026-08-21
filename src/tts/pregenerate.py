"""Plan B — 등록 음식 전체의 내레이션 음성을 미리 생성해 캐싱한다.

실측 결과 라이브 TTS 생성이 워밍업 후에도 약 33초로 TTFB 목표(5~7초)를 크게 넘어,
요청 시점 생성 대신 미리 만들어둔 파일을 꺼내 쓰는 방식(Plan B)으로 전환한다
(README 9절 위험 대응 "초과 시 사전 생성 캐싱으로 전환" 참고).

사용법 — 서비스와 같은 환경(ocr_env)에서, 저장소 루트 기준:
    python -m src.tts.pregenerate            # 없는 조합만 생성 (중단돼도 이어하기 안전)
    python -m src.tts.pregenerate --force    # 전부 다시 생성 (내레이션 문구가 바뀐 뒤)

생성 파일: static/tts_cache/food_{food_id}_{STYLE}.wav — src/pipeline.py의
_load_cached_tts()가 같은 이름 규칙으로 조회한다. 실제 합성은 파이프라인과 동일한
경로(별도 venv의 상주 워커, TTS_VENV_PYTHON 환경변수 지원)로 실행되므로, 여기서 만든
파일과 라이브 생성 결과는 같은 모델·같은 설정을 쓴다.

조합은 닫힌 집합이다: 음식 50개 × 스타일 1개(spice_level로 GUIDE/CAUTION이 자동
결정되므로 음식당 하나). 개당 약 33초 × 50개 ≈ 30분 안팎의 일회성 배치.
"""

# K_Menu_Talk.py와 같은 이유로 torch를 다른 어떤 import보다 먼저 로드한다 — 아래
# src.pipeline이 paddleocr을 모듈 수준에서 임포트하는데, 그 뒤에 torch가 로드되면
# Windows에서 shm.dll 로딩이 깨진다(WinError 127, 커밋 c06cb4d 참고).
import torch  # noqa: F401

import argparse
import csv
import shutil
import sys
from pathlib import Path

from src import pipeline
from src.db import cache
from src.text_gen.narration import get_narration


# 배치가 곧 RTF 측정이기도 하다: RTF = 생성 시간 ÷ 생성된 음성 길이 (1.0 미만이면 실시간).
# 결과를 eval/ 아래 CSV로 남겨 모델 비교표의 근거 데이터로 쓴다.
LOG_PATH = Path(__file__).resolve().parent.parent.parent / "eval" / "tts_pregen_log.csv"


def _wav_duration_sec(path: Path) -> float | None:
    """wav 길이(초). soundfile이 있으면 그걸, 없으면 표준 wave 모듈을 쓴다.

    (soundfile은 float 포맷 wav도 읽지만 TTS venv에만 있을 수 있고, 표준 wave는
    어디서나 되지만 PCM만 읽는다 — 둘 다 실패하면 RTF 없이 진행한다.)
    """
    try:
        import soundfile as sf
        info = sf.info(str(path))
        return info.frames / info.samplerate
    except Exception:
        pass
    try:
        import wave
        with wave.open(str(path), "rb") as w:
            return w.getnframes() / w.getframerate()
    except Exception:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="등록 음식 전체의 TTS 음성을 미리 생성한다.")
    parser.add_argument("--force", action="store_true", help="이미 있는 파일도 다시 생성")
    args = parser.parse_args()

    pipeline._TTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    foods = cache.get_foods()
    done = skipped = failed = 0
    log_rows: list[dict] = []

    for i, food in enumerate(foods, 1):
        try:
            narration = get_narration(food["id"])
        except ValueError as exc:
            # 내레이션 데이터가 빠진 음식은 기록만 남기고 계속 간다 — 한 음식 때문에
            # 나머지 49개의 배치를 중단할 이유가 없다.
            print(f"[{i}/{len(foods)}] {food['name_kr']} — 내레이션 없음, 건너뜀 ({exc})")
            failed += 1
            continue

        target = pipeline._TTS_CACHE_DIR / f"food_{food['id']}_{narration['style']}.wav"
        label = f"[{i}/{len(foods)}] {food['name_kr']} ({narration['style']})"

        if target.exists() and not args.force:
            print(f"{label} — 있음, 건너뜀")
            skipped += 1
            continue

        result = pipeline._synthesize_via_subprocess(narration["text"], narration["style"])
        if result.get("status") != "ok" or not result.get("audio_path"):
            print(f"{label} — 실패 (status={result.get('status')})")
            failed += 1
            continue

        # synthesize()가 시스템 임시 폴더에 쓴 wav를 캐시 위치로 옮긴다.
        shutil.move(result["audio_path"], target)

        latency_sec = result["latency_ms"] / 1000
        duration = _wav_duration_sec(target)
        rtf = (latency_sec / duration) if duration else None
        log_rows.append({
            "food_id": food["id"],
            "name_kr": food["name_kr"],
            "style": narration["style"],
            "latency_sec": round(latency_sec, 2),
            "audio_sec": round(duration, 2) if duration else "",
            "rtf": round(rtf, 3) if rtf else "",
        })

        rtf_note = f" · 음성 {duration:.1f}초 · RTF {rtf:.2f}" if rtf else ""
        print(f"{label} — 생성 {latency_sec:.1f}초{rtf_note}")
        done += 1

    if log_rows:
        write_header = not LOG_PATH.exists()
        with open(LOG_PATH, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(log_rows[0].keys()))
            if write_header:
                writer.writeheader()
            writer.writerows(log_rows)
        rtfs = [r["rtf"] for r in log_rows if r["rtf"] != ""]
        if rtfs:
            print(f"\n평균 RTF {sum(rtfs) / len(rtfs):.2f} (n={len(rtfs)}) → {LOG_PATH}")

    print(f"\n완료 {done} · 건너뜀 {skipped} · 실패 {failed} → {pipeline._TTS_CACHE_DIR}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
