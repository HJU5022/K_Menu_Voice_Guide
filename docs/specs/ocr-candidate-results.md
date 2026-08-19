# Spec — OCR 후보 결과 계약

## Why

- **페르소나**: 메뉴판 사진에서 인식된 음식 중 자신이 알고 싶은 음식을 선택하려는 영어권 관광객
- **상황**: OCR이 텍스트를 읽었지만, 메뉴판에는 여러 음식이 적혀 있거나 등록되지 않은 음식만 있을 수 있다.
- **문제**: 현재 매칭 함수는 가장 높은 점수의 음식 하나 또는 `None`만 반환한다. OCR 텍스트가 없는 경우와 지원하지 않는 음식만 인식한 경우가 구분되지 않고, 여러 후보를 사용자에게 제시할 수 없다.
- **측정 지표**: 분석 결과가 OCR 실패·미지원·후보 발견을 구분하고, 후보가 정해진 정렬 규칙으로 반환되는지 단위 테스트로 검증한다.

## Goal

- **해결 목표**: OCR 텍스트를 UI가 사용할 수 있는 상태 코드와 음식 후보 목록으로 변환한다.
- **성공 기준**:
  1. 빈 OCR 텍스트는 `ocr_empty` 상태를 반환한다.
  2. OCR 텍스트는 있으나 임계값 이상 후보가 없으면 `unsupported_food` 상태를 반환한다.
  3. 후보가 있으면 `candidates_found` 상태와 점수순 후보 목록을 반환한다.
- **Out of Scope**: Gradio UI, 후보 카드 렌더링, 사용자의 음식 선택 처리, 상세 정보 조회, TTS 생성, Supabase 스키마 변경, 매칭 임계값 변경.

## What

**Happy Path**

1. `analyze_image(image_path)`가 OCR 텍스트를 읽는다.
2. `match_food_candidates(text)`가 등록 음식 중 임계값 이상 후보를 수집한다.
3. 후보를 점수 내림차순, 동점 시 한글 음식명 길이 내림차순으로 정렬한다.
4. `analyze_image()`가 `candidates_found`, OCR 텍스트, 후보 목록을 반환한다.

**Edge Cases**

| # | 상황 | 처리 방식 |
|---|---|---|
| EC-01 | OCR 결과가 빈 문자열 또는 공백뿐임 | `ocr_empty` 상태와 빈 OCR 텍스트를 반환한다. |
| EC-02 | OCR 텍스트는 있으나 임계값 이상 후보가 없음 | `unsupported_food` 상태와 OCR 텍스트, 빈 후보 목록을 반환한다. |
| EC-03 | 여러 음식이 임계값 이상임 | 모든 후보를 정렬해 반환하고 하나를 임의로 확정하지 않는다. |
| EC-04 | 후보 점수가 같음 | 더 긴 한글 음식명을 먼저 반환한다. |
| EC-05 | OCR 또는 DB 조회가 실패함 | 기존과 같이 예외를 숨기지 않고 호출자에게 전달한다. |

## How

- `src/ocr/match.py`에 `match_food_candidates(text: str) -> list[dict]`를 추가한다.
- 후보의 반환 키는 기존 매칭 결과와 같은 `food_id`, `name_kr`, `score`, `modifiers`를 사용한다.
- 후보 수집은 기존 `MATCH_THRESHOLD = 70`, `fuzz.partial_ratio`, 공백 제거 규칙을 그대로 사용한다.
- 기존 `match_food(text)`는 기존 호출부의 호환성을 위해 가장 높은 후보 하나 또는 `None`을 반환하도록 유지한다.
- `src/pipeline.py`에 `analyze_image(image_path: str) -> dict`를 추가한다.
- `analyze_image()` 반환 키는 `status`, `ocr_text`, `candidates`로 고정한다.
- 이번 작업에서 기존 `run()`과 `create_tts_response()`의 동작은 바꾸지 않는다.

## AC

**AC-01 · OCR 텍스트 없음**
- GIVEN: `recognize()`가 빈 문자열 또는 공백 문자열을 반환한다.
- WHEN: `analyze_image(image_path)`를 호출한다.
- THEN: `status`가 `ocr_empty`이고 `ocr_text`와 `candidates`가 모두 빈 값이다.

**AC-02 · 미지원 음식**
- GIVEN: `recognize()`가 텍스트를 반환하지만 `match_food_candidates()`는 빈 목록을 반환한다.
- WHEN: `analyze_image(image_path)`를 호출한다.
- THEN: `status`가 `unsupported_food`이고 OCR 텍스트는 유지하며 후보 목록은 비어 있다.

**AC-03 · 후보 목록 반환**
- GIVEN: `recognize()`가 텍스트를 반환하고 둘 이상의 음식 후보가 있다.
- WHEN: `analyze_image(image_path)`를 호출한다.
- THEN: `status`가 `candidates_found`이고 OCR 텍스트와 정렬된 후보 목록을 반환하며 상세 조회와 TTS 생성은 호출하지 않는다.

**AC-04 · 후보 정렬**
- GIVEN: 임계값 이상 후보가 여러 개이고 일부 점수가 같다.
- WHEN: `match_food_candidates(text)`를 호출한다.
- THEN: 점수 내림차순, 동점 시 한글 음식명 길이 내림차순으로 정렬된다.

**AC-05 · 기존 단일 후보 호출 호환성**
- GIVEN: 기존 호출부가 `match_food(text)`를 사용한다.
- WHEN: 하나 이상의 후보가 매칭된다.
- THEN: 정렬된 후보 중 첫 번째 후보 하나를 반환한다.
