# Spec — OCR 파인튜닝

> 뼈대만 잡아둔 상태입니다. 형식은 [`_example.md`](./_example.md)를 따르고, 다섯 섹션을 모두 채운 뒤 구현에 들어갑니다.

## Why

- **페르소나**: 한국 음식에 익숙하지 않은 영어권 개별 외국인 관광객
- **상황**: 한국어로만 적힌 메뉴판을 촬영해 음식명을 인식시키려 한다.
- **문제**:
  1. 기본 PaddleOCR은 범용 한국어 인식 모델이라 메뉴판 특유의 서체·작은 글자·음식명 고유명사에 오인식이 잦다.
  2. 오인식된 글자로는 등록 음식명(RapidFuzz 매칭)과 제대로 이어지지 않아 다음 단계(텍스트·음성 안내)로 못 넘어간다.
- **측정 지표**: 기본 PaddleOCR 대비 한국어 음식명 인식률 +N%p (목표 수치는 Goal 참고)

## Goal

- **해결 목표**: 커스텀 딕셔너리로 파인튜닝한 PaddleOCR(mobile)로 메뉴판 음식명 인식률을 목표치까지 끌어올린다.
- **성공 기준**: `OCR_test_set_50`(별도 구성 테스트 50장) 기준 인식률 90% 이상
- **Out of Scope**: 손글씨 메뉴 인식, 실시간 동영상 OCR, 다국어 지원(영어권 메뉴판 외), paddleslim 양자화는 90% 인식률 확보 이후 배포 최적화 단계에서 별도로 진행(이 Spec의 AC 검증 대상 아님)

## What

**Happy Path**

1. AI Hub 데이터 → `prepare_dataset.py`로 PaddleOCR 학습 포맷(`rec_gt_train.txt`) 변환
2. 커스텀 딕셔너리 생성 (등록 음식명 50개 기준)
3. `finetune.py`로 학습
4. `infer.py`로 추론 → 한국어 글자 추출
5. `match.py`로 등록 음식명과 유사도 매칭

**Edge Cases** (최소 5개 + 처리 방식)

| # | 상황 | 처리 방식 |
|---|---|---|
| EC-01 | 메뉴판이 기울어져 촬영됨 | `preprocess.py`의 `_deskew`: Otsu 이진화 + `minAreaRect`로 회전각 추정 후 `warpAffine`으로 보정 |
| EC-02 | 조명이 어둡거나 반사됨 | `preprocess.py`의 `_enhance_contrast`: LAB 색공간에서 CLAHE 적용(`clipLimit=2.0`, `tileGridSize=8x8`) |
| EC-03 | 등록되지 않은 음식명이 인식됨 | `match.py`에서 부분일치 실패 또는 RapidFuzz 점수 70점 미만 → `None` 반환 → UI에 "미지원 안내" 표시 |
| EC-04 | 글자를 하나도 못 찾음 | OCR 결과 없음 → "조명·거리·각도 안내" 메시지와 함께 재촬영 요청 |
| EC-05 | 유사도가 비슷한 후보가 여러 개 | EC-03과 동일한 카드 UI 정책 재사용: 후보들을 번호+카드 목록으로 보여주고 사용자가 하나를 직접 선택 |

## How

**학습 방식 3안 — 전환 기준을 여기서 확정한다**

| 안 | 방식 | 선택 기준 |
|---|---|---|
| 1안 | 전체 학습 | 데이터 39,000장 규모로 대형 모델을 처음부터 학습시키면 과적합·학습 시간 부담 → 미선택 |
| 2안 | LoRA · QLoRA | PaddleOCR 인식 모델은 LoRA 적용 사례가 드물고, 이미 mobile 모델 자체가 경량이라 이득이 적음 → 미선택 |
| 3안 | mobile + 양자화(paddleslim) | **선택.** `korean_PP-OCRv5_mobile_rec` 사전학습 가중치로 전체 파인튜닝(현재 `finetune.py` 구현 상태) → HF Spaces ZeroGPU 배포 환경(추론 시간·메모리 제약)에 적합. 양자화는 파인튜닝 완료 후 순서대로 진행: ① 파인튜닝만으로 90% 인식률 확보 확인 → ② paddleslim으로 양자화 → ③ 양자화 후 재측정, 90% 밑으로 떨어지면 양자화 없는 mobile 가중치로 롤백 |

- 학습 데이터 출처: AI Hub "관광 음식메뉴판 데이터" — 학습 39,000장(13개 지역 × 3,000), 검증 6,500장(13개 지역 × 500), 평가용 테스트 50장(`OCR_test_set_50`, 학습/검증과 별도 구성)
- 커스텀 딕셔너리 파일 경로/형식: `OCR_finetune_data/custom_dict.txt` — 한 줄에 문자 1개, 총 1,118자. 학습·검증 데이터에 등장한 문자 + 등록 음식명 문자의 합집합(`prepare_dataset.py`의 `build_dictionary`)
- 매칭 임계값 (RapidFuzz score): `match.py`의 `MATCH_THRESHOLD = 70` (`fuzz.partial_ratio` 기준)

## AC (Given-When-Then)

**AC-01 · 정상 촬영된 메뉴판에서 등록 음식명 인식**
- GIVEN: 사용자가 조명이 양호하고 기울기가 크지 않은 메뉴판 사진을 촬영
- WHEN: 전처리 → 파인튜닝 OCR → `match_food` 파이프라인을 실행
- THEN: `OCR_test_set_50` 기준 90% 이상의 사진에서 등록 음식명과 정확히 매칭된다

**AC-02 · 기울어진 사진 보정**
- GIVEN: 메뉴판이 기울어져 촬영됨 (EC-01)
- WHEN: `preprocess_image`가 호출됨
- THEN: deskew로 각도가 보정된 이미지가 OCR에 전달되고, 보정 전 대비 인식률이 떨어지지 않는다

**AC-03 · 등록되지 않은 음식명 처리**
- GIVEN: OCR이 등록되지 않은 음식명 글자를 추출함 (EC-03)
- WHEN: `match_food`가 호출됨
- THEN: 부분일치 실패 또는 점수 70점 미만으로 `None`을 반환하고, UI에 "미지원 안내"가 표시된다

**AC-04 · 글자 인식 완전 실패**
- GIVEN: 조명·각도 문제로 OCR이 텍스트를 전혀 추출하지 못함 (EC-04)
- WHEN: 파이프라인이 빈 OCR 결과를 받음
- THEN: "조명·거리·각도 안내" 메시지와 함께 재촬영을 요청한다
