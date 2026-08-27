# Spec — 텍스트 생성

## Why

- **페르소나**: 한국 음식에 익숙하지 않은 영어권 개별 외국인 관광객
- **상황**: OCR로 음식을 인식/선택한 뒤, 화면 텍스트와 음성 나레이션으로 그 음식 정보를 확인하려 한다.
- **문제**:
  1. 화면용 상세 텍스트(`food_details` 6개 카테고리)는 발음·알레르기 정보까지 다 있지만, 음성 나레이션(`food_narration.narration_text`)에는 설명·먹는법·맵기 정도만 담겨있고 **발음·알레르기 정보가 빠져있다.**
  2. 외국인 관광객에게 발음·알레르기는 특히 중요한 정보라 텍스트에만 있고 음성으로 안 나가면 실질적으로 놓치기 쉽다.
- **측정 지표**: 나레이션에 발음·알레르기 정보가 포함된 음식 비율 (목표는 Goal 참고)

## Goal

- **해결 목표**: 음성 나레이션이 설명·먹는법(기존 `food_narration`)에 더해, 발음·알레르기 정보(`food_details`의 PRONUNCIATION·ALLERGY)까지 자동으로 포함하도록 한다.
- **성공 기준**: 등록된 50개 음식 전부, `get_narration()` 결과 텍스트에 PRONUNCIATION·ALLERGY 문장이 빠짐없이 포함된다.
- **Out of Scope**:
  - DESCRIPTION·HOW_TO_EAT 자동 생성 — 음식마다 개성이 담긴 부분이라 계속 사람이 직접 씀
  - 다국어(중국어 등) 지원 — 별도 로드맵
  - 새 카테고리 추가, 음식 개수 확장 — 별도 로드맵

## What

**Happy Path**

1. 선택된 음식 → `food_details`에서 6개 카테고리 조회 (화면용 상세 텍스트, 기존과 동일)
2. 해당 음식의 `spice_level` 조회
3. `spice_level` → `style`(GUIDE / CAUTION) 자동 결정 (기존과 동일)
4. `food_narration`에서 결정된 style에 맞는 `narration_text`(설명·먹는법 문장) 조회
5. `food_details`에서 같은 음식의 PRONUNCIATION·ALLERGY 문장 조회
6. 3, 4, 5에서 조회한 문장 3개를 순서대로(narration_text → PRONUNCIATION → ALLERGY) 이어붙여 최종 나레이션 텍스트를 만든다 — **셋 다 이미 완성된 문장이라 새로 생성하지 않고 그대로 이어붙이기만 한다.**

**카테고리 6개 (화면용)**

| # | 카테고리 | 설명 |
|---|---|---|
| 1 | DESCRIPTION | 음식 설명(맛·특징) |
| 2 | PRONUNCIATION | 음식명 영어 발음 안내 |
| 3 | INGREDIENT | 주요 재료 |
| 4 | HOW_TO_EAT | 먹는 법 |
| 5 | SPICY | 맵기 설명(서술형) |
| 6 | ALLERGY | 알레르기 유발 재료 안내 |

**음성 전용 1개 (2026-08-25 추가)** — `food_details`에 같은 방식으로 들어 있고, 화면에는 그리지 않는다.

| # | 카테고리 | 왜 따로 있나 |
|---|---|---|
| 7 | PRONUNCIATION_TTS | 화면용 `PRONUNCIATION`은 `Bibimbap is pronounced "bee-bim-bap."`처럼 이름을 말한 뒤 발음 표기를 다시 알려준다. 그런데 TTS 입력에서는 음식명이 한글로 치환되므로 `비빔밥 is pronounced "bee-bim-bap."`이 되어 **같은 이름을 한국어 발음으로 한 번, 로마자로 한 번 연달아 읽는다.** 음성에서는 한글로 읽어주는 이름 자체가 발음 안내이므로, 이름을 한 번만 말하는 문장(`Say it like this: 떡볶이.`)으로 갈아끼운다. 이 행이 없으면 화면용 문장을 그대로 쓴다 — 코드를 먼저 배포하고 DB 행을 나중에 넣어도 안내가 끊기지 않게 |

**Edge Cases** (최소 5개 + 처리 방식)

| # | 상황 | 처리 방식 |
|---|---|---|
| EC-01 | `food_details` 6개 카테고리 중 일부가 비어 있음 | `detail.py`는 있는 카테고리만 dict로 반환 (방어코드 없음 — 현재 50개 전부 채워져 있어 실제로 발생 안 함) |
| EC-02 | `spice_level`이 NULL이거나 숫자가 아님 | `get_narration()`이 `ValueError` 발생 |
| EC-03 | 해당 style의 `narration_text`가 없음 | `get_narration()`이 `ValueError` 발생 |
| EC-04 | 등록되지 않은 음식 (`food_id` 없음) | `get_narration()`이 `ValueError` 발생 |
| EC-05 | PRONUNCIATION 또는 ALLERGY가 없음 | `get_narration()`이 `ValueError` 발생 (narration_text 없을 때와 동일하게 처리) |

## How

**spice_level → style 결정 로직**

| spice_level | style |
|---|---|
| 1, 2, 3 | GUIDE |
| 4, 5 | CAUTION |

- 참조 테이블: `foods`, `food_details`, `food_narration`

**나레이션 조합 로직**

`get_narration(food_id)`는 **키 4개**를 돌려준다 — `text`(화면용) · `tts_text`(음성용) ·
`style` · `name_kr`(이름 단독 음성용). 화면용과 음성용을 나누는 이유는 두 가지다.

| | `text` (화면) | `tts_text` (음성) |
|---|---|---|
| 음식명 표기 | 로마자 그대로 (`Tteokbokki`) — 여행자가 소리 내어 읽어야 한다 | **한글로 치환** (`떡볶이`) — 로마자를 주면 모델이 영어 음운으로 읽는다. 값은 `foods.name_kr`, 치환은 `_to_tts_text()`가 단어 경계로 한다 |
| 발음 안내 문장 | `PRONUNCIATION` | **`PRONUNCIATION_TTS`** (없으면 `PRONUNCIATION`으로 폴백) |

`name_kr`을 함께 싣는 이유는 이 함수가 이미 `foods` 행을 조회하고 있어서다 — 이름만 읽는 별도
음성(`name_{id}.wav`)이 그 값을 쓴다. 전환 경위는 `docs/specs/tts-finetuning.md`.

- `text`는 다음 3개 문장을 공백으로 이어붙인 것이다:
  1. `food_narration.narration_text` (해당 food_id·style)
  2. `food_details.PRONUNCIATION` (해당 food_id)
  3. `food_details.ALLERGY` (해당 food_id)
- 세 값 모두 Supabase에 사람이 미리 작성해 둔 완성된 문장이며, 이 함수는 **새 문장을 생성하지 않고 조회 후 이어붙이기만 한다** (외부 LLM API도 쓰지 않음).
- INGREDIENT·SPICY는 이미 `food_narration.narration_text` 안에 자연스럽게 녹아 있는 경우가 많아 별도로 이어붙이지 않는다 (지금 빠져있던 건 PRONUNCIATION·ALLERGY뿐이었음).

## AC (Given-When-Then)

**AC-05 · 화면용과 음성용이 갈린다**
- GIVEN: `food_id`가 유효하고 `PRONUNCIATION_TTS` 행이 있다
- WHEN: `get_narration(food_id)`를 호출
- THEN: `text`에는 로마자 음식명과 `PRONUNCIATION`이, `tts_text`에는 한글 음식명과 `PRONUNCIATION_TTS`가 들어간다. `PRONUNCIATION_TTS`가 없으면 `tts_text`도 `PRONUNCIATION`을 쓴다

**AC-01 · 정상 조회 시 발음·알레르기 포함**
- GIVEN: `food_id`가 유효하고 narration_text·PRONUNCIATION·ALLERGY가 모두 존재
- WHEN: `get_narration(food_id)`를 호출
- THEN: 반환된 `text`에 세 문장이 모두 순서대로(narration → 발음 → 알레르기) 포함된다

**AC-02 · spice_level에 따른 style 결정**
- GIVEN: 음식의 `spice_level`이 1~5 사이 정수
- WHEN: `get_narration(food_id)`를 호출
- THEN: 1~3이면 GUIDE, 4~5면 CAUTION style의 narration_text가 사용된다

**AC-03 · 필요한 문장 중 하나라도 없으면 예외**
- GIVEN: narration_text·PRONUNCIATION·ALLERGY 중 하나가 없음
- WHEN: `get_narration(food_id)`를 호출
- THEN: `ValueError`가 발생한다 (방어코드로 조용히 넘어가지 않음)

**AC-04 · 등록되지 않은 음식**
- GIVEN: 존재하지 않는 `food_id`
- WHEN: `get_narration(food_id)`를 호출
- THEN: `ValueError`가 발생한다

## 구현 변경 이력 (2026-08-18)

### 계획 대비 달라진 점 — "템플릿 조합"이 아니라 "문장 이어붙이기"였음

**원래 계획**: 브레인스토밍 단계에서는 PRONUNCIATION·ALLERGY를 짧은 원자료(예: "밀가루, 어묵")로 보고, "이 음식엔 ~가 들어있으니 알레르기 있으신 분은 참고하세요" 같은 **문구 템플릿 3~4개 변형**을 만들어 값을 끼워넣는 방식을 검토했음. 음식마다 같은 템플릿을 재사용하면 "이름만 다르고 다 똑같은 문장"이 될 위험이 있어서 변형을 여러 개 두기로 했었음.

**실제 코드 작성 전 DB를 다시 확인한 결과**: `food_details`의 PRONUNCIATION·ALLERGY 값이 **이미 그 자체로 완성된 문장**이었음(빈칸 채우기용 단어 목록이 아니었음). 예:
- PRONUNCIATION(떡볶이): `"Tteokbokki is pronounced \"ddeok-bo-kki.\""`
- ALLERGY(떡볶이): `"Contains gluten (rice cake and fish cake) and soy. Not suitable for those avoiding spicy food."`

**결론**: 템플릿 문구를 코드에 하드코딩할 필요가 없어짐. `get_narration()`은 `narration_text` + `PRONUNCIATION` + `ALLERGY` **세 문장을 그대로 이어붙이기만** 하면 됨 — 새 문장을 생성하는 로직이 아예 없어짐.

### "정형화(뻔한 문장)" 우려가 근본적으로 해결됨

애초 우려는 "음식마다 같은 템플릿 문구를 재사용하면 이름만 다르고 다 똑같아 보인다"는 것이었음. 근데 실제로는 **템플릿 자체가 없음** — PRONUNCIATION·ALLERGY가 음식마다 이미 다르게 손으로 쓰여 있어서, 재사용되는 고정 문구가 하나도 없음. 아래 실제 테스트 결과에서 세 음식의 발음·알레르기 문장이 전부 다른 표현으로 돼있는 걸 확인할 수 있음 — 우려했던 "뻔해짐" 문제는 애초에 발생할 수 없는 구조가 됨.

### 실제 데이터로 검증 (Supabase 실 데이터, 2026-08-18)

`get_narration()`을 실제 DB에 대해 실행한 결과 (커밋 전, 로컬 임시 테스트):

```
떡볶이 (style=CAUTION):
Tteokbokki is chewy rice cakes simmered in a thick, spicy chili sauce, and it can be
quite hot. If you're sensitive to spice, ask for a milder version or have a cold drink
nearby. It's a beloved Korean street food worth trying carefully. Tteokbokki is
pronounced "ddeok-bo-kki." Contains gluten (rice cake and fish cake) and soy. Not
suitable for those avoiding spicy food.

비빔밥 (style=GUIDE):
Bibimbap is a colorful bowl of warm rice topped with seasoned vegetables, meat, and a
fried egg. It's only mildly spicy, and mixing everything together with your spoon is
part of the fun. A great choice if you want something wholesome and easy to enjoy.
Bibimbap is pronounced "bee-bim-bap." The name literally means "mixed rice." Contains
egg and soy. A vegetarian version without meat is often available on request.

불고기 (style=GUIDE):
Bulgogi is thin slices of beef marinated in a sweet soy sauce and grilled until
tender. It's not spicy at all, with a savory-sweet flavor that pairs perfectly with
rice. A safe, delicious pick for first-time visitors. Bulgogi is pronounced
"bul-go-gi," meaning "fire meat." Contains soy and sesame. Gluten may be present
depending on the soy sauce used.
```

세 문장 모두 자연스럽게 이어지고, 발음·알레르기 표현이 음식마다 다름을 확인함.

### 테스트

- `pytest tests/` 전체 11개 통과 (`test_narration.py` 5개 — 신규 2개 포함, `test_pipeline.py` 3개, `test_tts_infer.py` 3개)
- DB 스키마·데이터는 변경하지 않음 — `narration.py` 로직만 수정
