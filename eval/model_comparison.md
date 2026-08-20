# 모델 비교

> 실험이 끝날 때마다 표를 채운다. 측정하지 않은 칸은 "미측정"으로 명시한다. (최종 갱신: 2026-08-21, D5 체크포인트)

## 1. OCR 비교

한국어 음식명 인식률 기준. 테스트셋은 동일하게 쓴다.

| 모델 | 매칭 정확도 | 라벨 완전일치 | 검증 정확도 | 비고 |
|---|---|---|---|---|
| 기본 PaddleOCR (base) | 측정 예정 | 측정 예정 | — | 비교 기준. `eval/measure_ocr.py --rec paddle-base`로 동일 조건 측정 예정 |
| 파인튜닝 4차 (최종 배포본) | **91.67%** | **66.67%** | 90.98% | 2026-08-21 실측, 세로쓰기 회전 보정 등 후처리 반영 |
| (참고) 후처리 반영 전 기존 측정 | 97.22% | 42.94% | — | 측정 스크립트 미보존 — 판정 기준 재확인 불가 |

- 테스트셋: `OCR_test_set_50` — 실제 메뉴판 사진 50장 (01_normal 20 · 02_multi_food 15 · 03_low_quality 10 · 04_unregistered 5), 정답 라벨 `manifest.json`
- 매칭 정확도 정의: match_count>=1인 36장 중, `match.py`가 정답 라벨과 일치하는 등록 음식 후보를 1개 이상 반환한 비율
- 라벨 완전일치 정의: 전체 정답 라벨 중 OCR 원문에 그대로 포함된 비율
- CER(글자 오류율): 2.50% — AI Hub 검증셋 6,500장·절단된 글자박스 기준 (`train.log`의 `norm_edit_dis 0.9750`)
- 측정 스크립트: `eval/measure_ocr.py` (커밋됨 — base/이전 회차/최종을 같은 코드로 측정 가능), 결과 원본: `eval/measure_ocr_final.json`
- **최종 선택**: 파인튜닝 4차 (20 epoch / batch 8 / lr 0.001, 검증 90.98%) — 학습 경위는 `docs/specs/ocr-finetuning.md` 참고

## 2. TTS 후보군 비교

| 모델 | UTMOS (자동 MOS 예측) | 사람 MOS | Latency | 비고 |
|---|---|---|---|---|
| 베이스 모델 (Qwen3-TTS 1.7B Base) | 미측정 | 미측정 | — | Val Loss 기준선 10.87(1차 학습) |
| 파인튜닝 (LoRA, 8차 최종) | **3.92 ~ 4.07** (n=76) | 진행 중 (평가자 2/5명) | 콜드 61.3초 / 워밍업 33초 | Val Loss 8.91 (−18%) · 리스펠링 21/50 · instruct 톤 구분 |
| Perso.ai (상용 비교군) | GUIDE 4.1135 / CAUTION 4.1556 | — | — | 같은 화자 클로닝·같은 문장 비교 |

- **파인튜닝 vs Perso.ai (2026-08-21, 1차)**: GUIDE **104.3%** · CAUTION **106.9%** — 성공 기준(≥85%) 상회. 단 스타일당 1문장(n=1), 76문장 확대 재평가 예정. 원본 오디오: `eval/perso_comparison/`
- UTMOS는 UTMOS22(`utmos22_strong`) 자동 예측값 — 사람 MOS를 대체하지 않음 (상세: `eval/TTS_MODULE.md` 6절)
- Latency 측정 조건: 원격 RTX 3080 Ti · 상주 워커(PR #45) · 3회 실측
- **최종 선택**: Qwen3-TTS 1.7B Base + LoRA 파인튜닝 (경위: `eval/TTS_MODULE.md` 1절)

## 3. Plan B 판단 — **전환 결정 (2026-08-21)**

| 항목 | 값 |
|---|---|
| TTFB 목표 | 5~7초 |
| 라이브 생성 실측 TTFB | 워밍업 후 약 33초 (콜드 61.3초) |
| Plan B(사전 생성) 전환 여부 | **전환** — 목표 대비 구조적 미달 |

- 구현: `src/tts/pregenerate.py`(배치 사전 생성 + RTF 로그) + `src/pipeline.py` 캐시 조회. 캐시 히트 시 1초 미만
- RTF: 사전 생성 배치에서 50개 표본으로 실측 → `eval/tts_pregen_log.csv` (배치 실행 후 기록)
- 기준·경위: `docs/specs/tts-finetuning.md` "구현 변경 이력 (2026-08-21)" 참고
