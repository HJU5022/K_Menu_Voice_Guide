# src/db/

**Supabase 데이터 접근 계층**

DB에 직접 접근하는 코드는 전부 여기에만 둡니다. 다른 폴더에서는 이 모듈을 통해서만 데이터를 가져옵니다.

## 파일

| 파일 | 역할 |
|---|---|
| `supabase_client.py` | 읽기 전용 anon key로 접속, RLS로 SELECT만 허용 |
| `cache.py` | 서버 시작 시 전체 데이터를 메모리에 올려두기 |
| `menu_modifiers_seed.sql` | `menu_modifiers` 테이블 생성·초기 데이터 |

일회성 데이터 주입 SQL(음식 행 추가, 상세 문장 채우기 등)은 저장소에 두지 않습니다. 한 번 실행하면 값은 DB가 정본이 되고, 파일이 남아 있으면 "아직 실행해야 하는 것"으로 오해되기 때문입니다. 실행해야 할 SQL이 남아 있으면 파일이 아니라 아래 문서에 직접 적습니다.

## 접근하는 테이블

| 테이블 | 내용 |
|---|---|
| `foods` | 음식 기본 정보 (음식명, spice_level, 대표사진 URL·출처). `name_kr`은 TTS가 읽는 이름으로도 씁니다 |
| `food_details` | 카테고리 6개 상세 설명 (PRONUNCIATION·SPICY·DESCRIPTION·INGREDIENT·HOW_TO_EAT·ALLERGY) + TTS 전용 `PRONUNCIATION_TTS` |
| `food_narration` | style별 내레이션 문장 |
| `menu_modifiers` | 메뉴판 줄에서 음식명을 뺀 나머지에 붙는 수식어. `keyword_en`이 후보 카드의 **영어 태그**가 됩니다(`매운`→`Hot`, `해산물`→`Seafood`). `category`가 `spice`면 `spice_tier`(1~5)를 함께 씁니다 |

## 보안

- **anon key만** 사용합니다. service role key는 저장소에 절대 넣지 않습니다.
- RLS(Row Level Security)로 `SELECT`만 허용됩니다. INSERT/UPDATE/DELETE는 막혀 있습니다.
- 키는 `.env`에 두고, `.env.example`에는 **키 이름만** 적습니다.

## 캐싱을 쓰는 이유

안내 데이터를 갖춘 음식이 50개뿐이라 데이터가 작습니다. 서버 시작할 때 전부 메모리에 올려두면 요청마다 DB를 다녀올 필요가 없어서 응답이 빨라집니다.

첫 요청에서 4개 테이블을 한 번에 읽는 왕복이 **약 2.5초**, 그 뒤로는 메모리라 **2ms 미만**입니다 (2026-08-25 실측, `eval/model_comparison.md` 3절). 서비스 응답에서 눈에 띄는 콜드 비용은 여기 하나뿐입니다.

## TTS가 읽는 음식명 — 컬럼 추가 없이 `name_kr`을 씁니다

TTS에 넘기는 문장에서는 음식명만 **한글 표기로 바꿔서** 읽힙니다(`Tteokbokki` → `떡볶이`). 영어 문장 안의 로마자 음식명을 모델이 영어 음운으로 읽어버리는 문제를, 표기를 한글로 바꿔 한국어 음운으로 읽게 해서 푸는 방식입니다(경위: `docs/specs/tts-finetuning.md`). 치환은 `src/text_gen/narration.py`의 `_to_tts_text()`가 하고, 값은 **이미 있는 `foods.name_kr`을 그대로** 씁니다. 화면에 표시되는 텍스트는 로마자 표기 그대로입니다 — 여행자가 소리 내어 읽어야 하는 정보이기 때문입니다.

**그래서 이번 변경에는 실행할 SQL이 없습니다.** 컬럼 추가도, 데이터 주입도 필요 없습니다. `name_kr`은 이미 50행 전부 채워져 있고 `cache.py`가 예전부터 select하던 컬럼입니다.

## 취소된 것 — `foods.name_respell` 컬럼 추가 SQL

한때 영문 리스펠링 표기(`Tteokbokki` → `Duck-bok-kee`)를 담을 `foods.name_respell` 컬럼을 만들고 21개 행에 값을 넣는 SQL을 이 문서에 실행 대기로 적어뒀었습니다. **실행하지 않기로 했습니다** — 표기를 리스펠링으로 바꿔도 발음이 정확해지지 않아 TTS가 읽는 표기 자체를 한글로 바꿨기 때문입니다(경위: `docs/specs/tts-finetuning.md`).

2026-08-25 기준 DB에 이 컬럼은 **없습니다**(조회 시 `column foods.name_respell does not exist`, 42703). `src/db/cache.py`도 더 이상 이 컬럼을 select하지 않으므로, 그대로 두면 됩니다.

혹시 이미 실행해서 컬럼이 생긴 환경이 있다면 지워도 됩니다 — 읽는 코드가 없습니다. 컬럼이 남아 있어도 앱은 정상 동작하므로 급한 작업은 아닙니다.

```sql
-- 컬럼이 있으면 지운다. 없으면 아무 일도 하지 않는다
alter table foods drop column if exists name_respell;
```

리스펠링 표 21개의 값 자체는 `eval/TTS_MODULE.md` 4절(청취 스크리닝 결과)과 커밋 `8176e66`의 `RESPELL_MAP`에 남아 있습니다.

## 썸네일 저장 규칙

`foods.thumbnail_url`/`thumbnail_attribution`을 새로 채울 때 지켜야 하는 규칙입니다. 기존 50개에서 역산했고 50개 전부 이 규칙을 따릅니다.

| 항목 | 규칙 |
|---|---|
| 저장 위치 | Supabase Storage 버킷 `food-thumbnails`, 경로 `selected_photos/` |
| 파일명 | `name_en`에서 공백을 뺀 값 + `.jpg` (예: `Kimchi Jeon` → `KimchiJeon.jpg`) |
| 출처 표기 (Wikimedia) | `Source: Wikimedia Commons, {라이선스}, {저작자}` |
| 출처 표기 (AI Hub) | `Source: AI Hub Tourism Menu Board Dataset (NIA)` |

- URL은 기존 행에서 그대로 따옵니다 — 프로젝트 주소를 문서에 적어두면 나중에 갈립니다
- 업로드는 anon key로 안 됩니다. 대시보드(Storage > `food-thumbnails` > `selected_photos` > Upload)나 service_role 키가 필요합니다
- **출처를 사진과 다르게 적지 않습니다.** `docs/specs/flutter-mobile-app.md`가 "사진을 보여주는 자리에는 출처를 반드시 함께 표시한다"를 프로젝트 조건으로 정해두었습니다
