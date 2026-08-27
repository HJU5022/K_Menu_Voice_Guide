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

## 상세 카드 6개 — 순서와 영어 제목

웹과 앱이 **같은 순서·같은 제목**을 쓴다. 서버가 주는 `details`는 순서 없는 묶음이라 무엇을 어떤
순서로 보여줄지는 화면이 정하는데, 같은 서비스인데 웹과 앱이 다르면 안 된다. 정본은 이 표이고,
구현은 `frontend/client/src/pages/Home.tsx`의 `DETAIL_CARDS`와 앱의 상세 화면이 따른다.

| # | `details` 키 | 화면 제목 |
|---|---|---|
| 1 | `DESCRIPTION` | Description |
| 2 | `HOW_TO_EAT` | How to eat |
| 3 | `INGREDIENT` | Ingredients |
| 4 | `ALLERGY` | Allergies & dietary needs |
| 5 | `PRONUNCIATION` | Pronunciation |
| 6 | `SPICY` | Spice level |

- 알레르기 항목만 경고 스타일로 그린다 — 안전 정보다. 나머지는 같은 모양으로 둔다.
- 서버가 특정 카테고리를 비워 보내면 그 카드는 건너뛴다. 빈 카드가 있으면 정보가 누락된 것처럼 보인다.
- `details`에는 음성 전용 `PRONUNCIATION_TTS`가 섞여 올 수 있다 — **이 표에 없는 키는 그리지 않는다.**

## 맵기 5단계 — `spice_level` 값을 정하는 기준

`foods.spice_level`(1~5)에 어떤 값을 넣을지 정할 때 쓰는 **데이터 작성 기준**이다. 사람마다
"맵다"의 기준이 달라서, 값을 넣는 사람이 바뀌면 같은 음식이 다른 단계로 들어간다.

| `spice_level` | 기준 (작성자용) | 참고 수치 |
|---|---|---|
| 1 (순함) | Bell Pepper 수준 | 0 SHU |
| 2 (약간 매움) | Poblano 수준 | 약 1,000~2,000 SHU |
| 3 (보통) | Jalapeño 수준 | 약 2,500~8,000 SHU |
| 4 (매움) | 청양고추 수준 | 약 4,000~12,000 SHU |
| 5 (아주 매움) | 불닭볶음면 수준 | 4,404 SHU |

**화면에는 이 표가 나오지 않는다.** 사용자가 보는 것은 두 가지다.

- 불꽃 아이콘 5칸을 `spice_level`만큼 채운 눈금 (웹 `Home.tsx`, 앱 `spice_gauge.dart`)
- `SPICY` 상세 카드의 문장 — DB에 사람이 써 넣은 영어 설명이다
  (예: `Moderately spicy — the broth is bright red from chili oil and gochugaru.`)

스코빌 수치와 고추 비유를 화면에 띄우는 것은 기획 단계 안이었고 **구현하지 않았다.**
새로 쓰는 `SPICY` 문장에 숫자를 넣지 말 것 — 조리법과 가게마다 실제 매움이 달라 단정할 수 없고,
지금 50개 문장 중 숫자를 쓴 것이 하나도 없어 혼자만 다른 모양이 된다.

4단계 이상이면 음성 스타일도 `CAUTION`으로 갈린다(`src/text_gen/narration.py`). 화면의 불꽃
개수와 음성의 톤이 같은 값에서 나오므로 서로 어긋나지 않는다.

## 예외 화면 문구

원인이 다르면 문구도 달라야 한다. 같은 문구를 쓰면 사진만 고치면 되는 사용자가 포기한다.

| 상황 (`status`) | 제목 | 다음 행동 안내 |
|---|---|---|
| `ocr_empty` | We couldn't read this photo | Try brighter lighting, hold the menu straight, and move closer to the text. |
| `not_a_menu` | We couldn't find a menu here | Point the camera at a printed menu with prices, then take the photo again. |
| `unsupported_food` | Not in our guide yet | Try a different menu item or ask the restaurant staff. |

- 앞의 둘은 **다시 찍으면 해결된다**, 마지막 하나는 다시 찍어도 같다 — 그래서 갈라 쓴다.
- 잘못된 파일 업로드(400·413)에는 "다시 찍으세요"를 쓰지 않는다. 12MB는 다시 찍어도 12MB다.
- 문구의 실제 값은 `frontend/client/src/i18n.ts`에 있다. 새로 짓지 말고 여기서 가져다 쓴다.

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
