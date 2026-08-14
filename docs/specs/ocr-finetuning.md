# Spec — OCR 파인튜닝

> 뼈대만 잡아둔 상태입니다. 형식은 [`_example.md`](./_example.md)를 따르고, 다섯 섹션을 모두 채운 뒤 구현에 들어갑니다.

## Why

- **페르소나**:
- **상황**:
- **문제**:
- **측정 지표**: (예: 기본 PaddleOCR 대비 한국어 음식명 인식률 +N%p)

## Goal

- **해결 목표**:
- **성공 기준**: (숫자로)
- **Out of Scope**:

## What

**Happy Path**

1. AI Hub 데이터 → `prepare_dataset.py`로 PaddleOCR 학습 포맷(`rec_gt_train.txt`) 변환
2. 커스텀 딕셔너리 생성 (등록 음식명 30개 기준)
3. `finetune.py`로 학습
4. `infer.py`로 추론 → 한국어 글자 추출
5. `match.py`로 등록 음식명과 유사도 매칭

**Edge Cases** (최소 5개 + 처리 방식)

| # | 상황 | 처리 방식 |
|---|---|---|
| EC-01 | 메뉴판이 기울어져 촬영됨 | |
| EC-02 | 조명이 어둡거나 반사됨 | |
| EC-03 | 등록되지 않은 음식명이 인식됨 | |
| EC-04 | 글자를 하나도 못 찾음 | |
| EC-05 | 유사도가 비슷한 후보가 여러 개 | |

## How

**학습 방식 3안 — 전환 기준을 여기서 확정한다**

| 안 | 방식 | 선택 기준 |
|---|---|---|
| 1안 | 전체 학습 | |
| 2안 | LoRA · QLoRA | |
| 3안 | mobile + 양자화(paddleslim) | |

- 학습 데이터 출처:
- 커스텀 딕셔너리 파일 경로/형식:
- 매칭 임계값 (RapidFuzz score):

## AC (Given-When-Then)

**AC-01 ·**
- GIVEN:
- WHEN:
- THEN:
