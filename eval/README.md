# eval/

모델 성능을 재고 기록하는 곳입니다. "이 모델을 왜 골랐는지"의 근거가 여기 남습니다.

## 파일

| 파일 | 내용 |
|---|---|
| `TTS_MODULE.md` | TTS 파인튜닝 실험 기록 — 하이퍼파라미터 8차 실험, 발음 리스펠링, GUIDE/CAUTION 톤 구분(instruct), UTMOS 자동 평가 결과 |
| `training_log.csv` | 위 실험의 에폭별 Val Loss 원본 로그 (`TTS_MODULE.md` 3절 표의 근거 데이터) |
| `qwen3_tts_lora_final.ipynb` | 실제 학습에 쓴 Colab 노트북 (환경설정 → 데이터빌드 → 학습 → 업로드) |
| `mos_scores.csv` | TTS 발음·자연스러움 MOS 채점 원본 데이터 |
| `model_comparison.md` | OCR(기본·파인튜닝) · TTS 후보군 · Perso.ai 비교 · Plan B 판단 정리 |
| `measure_ocr.py` | OCR 동일 조건 비교 측정 스크립트 — base/로컬 체크포인트/최종(HF)을 같은 코드로 측정 (매칭 정확도·라벨일치·라벨 CER) |
| `measure_ocr_final.json` | 최종(4차) 모델 실측 결과 원본 (2026-08-21, 매칭 91.67% · 라벨일치 66.67%) |
| `measure_match_precision.py` | 매칭 **오탐** 측정 — `measure_ocr.py`가 재현율만 보는 사각지대를 메운다. AI Hub 관광 음식메뉴판 라벨을 정답으로 쓴다 (2026-08-23 추가) |
| `measure_digits.py` | 숫자(가격) 인식만 따로 재는 벤치마크 — 같은 박스·같은 크롭을 base와 파인튜닝에 각각 먹여 원인을 분리한다. 가격을 그려 넣은 합성 이미지를 써서 테스트셋·GPU 없이 재현된다 |
| `measure_digits.json` | 위 벤치마크 결과 원본 (2026-08-25 재측정 — base 77.78% vs 파인튜닝 5.56%, `model_comparison.md` 1-1절의 근거) |
| `pregenerate_tts_cache_colab.ipynb` | `static/tts_cache` wav 50개를 Colab GPU에서 재생성하는 절차. 문구·`LORA_SCALE`이 바뀌면 캐시가 낡으므로 전량 재생성해야 한다 |
| `tts_pregen_log.csv` | 사전 생성 배치의 항목별 생성 시간·음성 길이·RTF 기록 — **저장소에 없다.** 배치를 돌린 PC에만 생긴다 |
| `perso_comparison/` | Perso.ai 비교 원본 오디오 4개 (ours/perso × guide/caution) |

앞의 3개는 원래 `src/tts/`에 있었으나, 학습 실험 기록·산출물이라 이곳으로 옮겼습니다. `src/tts/`에는 실제 서비스가 실행하는 런타임 코드만 둡니다.

Colab에서 돌린 실험 노트북(한글 표기 스크리닝, 로마자 자기증류 등)은 저장소에 두지 않습니다. 결론과 근거만 `TTS_MODULE.md`·`model_comparison.md`에 남깁니다.

## MOS가 뭔가

**M**ean **O**pinion **S**core — 사람이 음성을 듣고 1~5점으로 매긴 점수의 평균입니다. 자동 지표로는 "자연스러운지"를 재기 어려워서 직접 듣고 채점합니다.

- 1점 = 매우 나쁨, 5점 = 매우 좋음
- 채점자 여러 명의 평균을 씁니다 (한 명이면 편향이 큽니다)
- 발음 정확도와 자연스러움을 **따로** 매깁니다

## 기록 흐름

```
음성 생성 → 채점자들이 듣고 점수 입력 → mos_scores.csv
                                          ↓
                              평균 내서 model_comparison.md에 정리
```
