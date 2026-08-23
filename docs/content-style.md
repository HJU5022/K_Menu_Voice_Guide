# Content Style Guide

## Why

영어권 관광객은 한국 음식과 한글 메뉴판이 낯설 수 있으므로 짧고 일관된 문구가 필요하다.

## Goal

개발자 내부 용어 대신 사용자가 즉시 이해할 수 있는 영어를 사용한다.

## What

| 의미 | 사용할 표현 | 피할 표현 |
|---|---|---|
| 사진 | `menu photo` | image, file을 무작위로 혼용 |
| 음식 | `dish` | candidate, food item |
| 분석 중 | `Reading your menu`, `Finding dishes` | OCR processing |
| 업로드 | `Upload a menu photo` | Upload만 단독 사용 |
| 다시 촬영 | `Scan another menu` | Try again만 단독 사용 |
| 미지원 | `This dish isn't in our guide yet.` | database error |
| 음성 재시도 | `Try audio again` | TTS retry |

## How

- 제목은 짧게 쓴다. 가능한 한 2~5단어로 현재 화면의 목적만 말한다.
- 제목 아래 안내는 사용자가 다음에 무엇을 하면 되는지 알려 주는 한 문장으로 쓴다.
- 버튼은 동사로 시작한다: `Take a photo`, `Choose a dish`, `Scan another menu`.
- 오류는 사용자를 탓하지 않고 원인 한 줄과 다음 행동을 제공한다.
- 한 화면에서는 음식의 기본 용어를 `dish`로 통일한다.
- 음식명은 가능하면 한글 원문과 로마자 표기를 함께 제공한다.
- 알레르기 정보는 명확하게 쓴다. 예: `May contain soy and sesame.`

## AC (Given-When-Then)

- GIVEN: 새 버튼을 추가한다. WHEN: 영어 문구를 작성한다. THEN: 누른 뒤 일어날 행동을 알 수 있는 동사형 문구를 사용한다.
- GIVEN: 미지원 음식을 표시한다. WHEN: 오류 화면을 작성한다. THEN: 기술 용어 없이 상황과 다음 행동을 안내한다.
