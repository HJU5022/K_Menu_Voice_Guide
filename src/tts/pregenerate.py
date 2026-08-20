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
import shutil
import sys

from src import pipeline
from src.db import cache
from src.text_gen.narration import get_narration


def main() -> None:
    parser = argparse.ArgumentParser(description="등록 음식 전체의 TTS 음성을 미리 생성한다.")
    parser.add_argument("--force", action="store_true", help="이미 있는 파일도 다시 생성")
    args = parser.parse_args()

    pipeline._TTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    foods = cache.get_foods()
    done = skipped = failed = 0

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
        print(f"{label} — 생성 {result['latency_ms'] / 1000:.1f}초")
        done += 1

    print(f"\n완료 {done} · 건너뜀 {skipped} · 실패 {failed} → {pipeline._TTS_CACHE_DIR}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
