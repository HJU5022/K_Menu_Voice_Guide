# Spec — TTS 파인튜닝

> 뼈대만 잡아둔 상태입니다. 형식은 [`_example.md`](./_example.md)를 따르고, 다섯 섹션을 모두 채운 뒤 구현에 들어갑니다.

## Why

- **페르소나**:
- **상황**:
- **문제**:
- **측정 지표**: (예: MOS N점 이상, Perso.ai 대비 비교 우위)

## Goal

- **해결 목표**:
- **성공 기준**: (발음 정확도 / 자연스러움 MOS / TTFB)
- **Out of Scope**:

## What

**Happy Path**

1. gTTS로 학습용 음성 스크립트 생성
2. `finetune.py`로 LoRA/PEFT 파인튜닝
3. `infer.py`로 라이브 음성 생성 (기본 경로)
4. TTFB 목표 초과 시 → `pregenerate.py`로 조합 30~60개 사전 생성·캐싱 (Plan B)
5. `perso_client.py`로 동일 텍스트를 Perso.ai에도 생성 → 비교 평가

**Edge Cases** (최소 5개 + 처리 방식)

| # | 상황 | 처리 방식 |
|---|---|---|
| EC-01 | TTFB가 목표를 초과 | Plan B(사전 생성 캐시)로 전환 |
| EC-02 | 캐시에 없는 조합 요청 | |
| EC-03 | Perso.ai API 호출 실패 | |
| EC-04 | 내레이션 텍스트가 지나치게 긺 | |
| EC-05 | 음성 파일 저장 실패 | |

## How

- 베이스 모델:
- 학습 데이터: gTTS 생성분 (`data/README.md` 참고)
- TTFB 목표값: (초)
- Plan B 전환 기준: TTFB 목표 초과 시
- 사전 생성 조합 수: 30~60개
- 출력 형식: WAV

## AC (Given-When-Then)

**AC-01 ·**
- GIVEN:
- WHEN:
- THEN:
