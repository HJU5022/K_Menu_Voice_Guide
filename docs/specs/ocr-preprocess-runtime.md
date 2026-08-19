# Spec — OCR 런타임 전처리 연결

## Why

- **페르소나**: 한국어 메뉴판을 촬영해 음식 정보를 확인하려는 영어권 관광객
- **상황**: 기울었거나 조명이 균일하지 않은 메뉴 사진을 업로드한다.
- **문제**: `preprocess_image()`에는 기울기·대비·크기 보정이 구현되어 있지만, 현재 `recognize()`의 실제 OCR 경로에서는 호출되지 않아 보정 효과가 적용되지 않는다.
- **측정 지표**: `recognize()` 호출 시 전처리가 OCR detection 이전에 한 번 실행되고, detection이 전처리된 이미지 배열을 받는지 단위 테스트로 검증한다.

## Goal

- **해결 목표**: `recognize(image_path)`가 전처리된 이미지 배열을 OCR detection과 이후 crop recognition에 사용하도록 연결한다.
- **성공 기준**:
  1. `recognize()`가 `preprocess_image(image_path)`를 호출한다.
  2. OCR detection과 crop이 전처리 결과 배열을 사용한다.
  3. 읽을 수 없는 이미지 경로에서는 `preprocess_image()`의 `ValueError`가 그대로 호출자에게 전달된다.
- **Out of Scope**: 후보 선택, Gradio UI, TTS, Supabase 스키마, OCR 모델·가중치·학습 방식 변경, 전처리 알고리즘 변경.

## What

**Happy Path**

1. `recognize(image_path)`가 `preprocess_image(image_path)`를 호출한다.
2. 전처리 함수가 메모리의 이미지 배열을 반환한다.
3. OCR detection이 그 배열을 입력으로 사용한다.
4. detection polygon으로 잘라낸 crop도 같은 전처리 이미지 배열에서 만든다.
5. recognition 결과를 기존과 동일하게 공백으로 합쳐 반환한다.

**Edge Cases**

| # | 상황 | 처리 방식 |
|---|---|---|
| EC-01 | 이미지 경로가 존재하지 않음 | `preprocess_image()`의 `ValueError`를 `recognize()`가 그대로 전달한다. |
| EC-02 | 이미지 파일을 읽을 수 없음 | `preprocess_image()`의 `ValueError`를 `recognize()`가 그대로 전달한다. |
| EC-03 | detection 결과가 없음 | 기존과 같이 빈 문자열을 반환한다. |
| EC-04 | detection crop을 JPEG로 인코딩할 수 없음 | 기존과 같이 해당 crop을 건너뛴다. |
| EC-05 | 일부 crop recognition 결과가 빈 문자열 | 기존과 같이 빈 결과를 제외하고 나머지 텍스트만 합친다. |

## How

- 대상 함수: `src/ocr/infer.py`의 `recognize(image_path: str) -> str`
- 입력 검증과 이미지 로드는 `src/ocr/preprocess.py`의 `preprocess_image(image_path)`에 맡긴다.
- `recognize()`는 원본을 `cv2.imread()`로 다시 읽지 않는다.
- 임시 이미지 파일을 만들지 않고, `preprocess_image()`가 반환한 `numpy.ndarray`를 detection과 crop의 공통 입력으로 쓴다.
- `src/ocr/preprocess.py`의 deskew, 대비 보정, 리사이즈 알고리즘은 수정하지 않는다.

## AC

**AC-01 · 전처리 후 detection 실행**
- GIVEN: 읽을 수 있는 메뉴 이미지 경로와 전처리 결과 이미지 배열이 있다.
- WHEN: `recognize(image_path)`를 호출한다.
- THEN: `preprocess_image(image_path)`가 한 번 호출되고, detection은 그 반환 배열을 입력으로 받는다.

**AC-02 · crop의 전처리 이미지 사용**
- GIVEN: detection이 글자 영역 polygon을 하나 반환한다.
- WHEN: `recognize(image_path)`를 호출한다.
- THEN: recognition에 전달되는 JPEG crop은 전처리 결과 이미지 배열에서 잘라낸 것이다.

**AC-03 · 잘못된 이미지 경로 전달**
- GIVEN: 존재하지 않거나 읽을 수 없는 이미지 경로가 있다.
- WHEN: `recognize(image_path)`를 호출한다.
- THEN: `preprocess_image()`가 발생시킨 `ValueError`가 변경되지 않고 호출자에게 전달된다.
