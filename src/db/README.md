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
| `foods` | 음식 기본 정보 (음식명, TTS용 리스펠링 표기, spice_level, 대표사진 URL·출처) |
| `food_details` | 카테고리 6개 상세 설명 (PRONUNCIATION·SPICY·DESCRIPTION·INGREDIENT·HOW_TO_EAT·ALLERGY) + TTS 전용 `PRONUNCIATION_TTS` |
| `food_narration` | style별 내레이션 문장 |
| `menu_modifiers` | 메뉴에 붙는 수식어 (예: "매운") — 매칭 후 따로 뽑아내는 데 씀 |

## 보안

- **anon key만** 사용합니다. service role key는 저장소에 절대 넣지 않습니다.
- RLS(Row Level Security)로 `SELECT`만 허용됩니다. INSERT/UPDATE/DELETE는 막혀 있습니다.
- 키는 `.env`에 두고, `.env.example`에는 **키 이름만** 적습니다.

## 캐싱을 쓰는 이유

안내 데이터를 갖춘 음식이 50개뿐이라 데이터가 작습니다. 서버 시작할 때 전부 메모리에 올려두면 요청마다 DB를 다녀올 필요가 없어서 응답이 빨라집니다.

첫 요청에서 4개 테이블을 한 번에 읽는 왕복이 **약 2.5초**, 그 뒤로는 메모리라 **2ms 미만**입니다 (2026-08-25 실측, `eval/model_comparison.md` 3절). 서비스 응답에서 눈에 띄는 콜드 비용은 여기 하나뿐입니다.

## ⚠️ 현재 어긋나 있는 것 — foods 200행

메뉴판 빈도 상위 200개 시드(일회성 SQL, 저장소 밖)가 이미 실행돼 `foods`가 **200행**인데, `food_narration`·`food_details`·`thumbnail_url`은 기존 **50개분만** 있습니다. 그 결과:

- `GET /api/foods`가 안내 불가능한 음식 150개까지 "지원 목록"으로 내보냅니다
- `src/ocr/match.py`도 그 150개를 매칭 후보로 씁니다
- 그런데 누르면 `GET /api/foods/{id}`가 404를 돌려줍니다

**대응 — 아직 실행 안 됨. 조장이 Supabase SQL Editor에서 실행합니다.** 앱의 anon key는 RLS로 SELECT만 허용되므로 대시보드(또는 service_role) 권한이 필요합니다.

```sql
-- 1) 지울 대상을 먼저 눈으로 확인한다 (지우지 않는다)
select f.id, f.name_kr, f.name_en, f.spice_level
from foods f
where not exists (select 1 from food_narration n where n.food_id = f.id)
  and not exists (select 1 from food_details  d where d.food_id = f.id)
order by f.id;

-- 2) 확인했으면 실행한다. 재실행해도 안전하다(지울 게 없으면 0행)
delete from foods f
where not exists (select 1 from food_narration n where n.food_id = f.id)
  and not exists (select 1 from food_details  d where d.food_id = f.id);

-- 3) 결과 확인 — foods 50 / narration 50 / details 350(50 x 7종)이면 정상
select (select count(*) from foods)          as foods,
       (select count(*) from food_narration) as narration,
       (select count(*) from food_details)   as details;
```

판정 기준을 `id 51~200`으로 잡지 않은 이유: `foods.id`는 identity 컬럼이라 재시드하면 값이 달라집니다. 기존 50개는 내레이션·상세를 둘 다 갖고 있어 이 조건에 걸리지 않습니다. 카트는 영향이 없습니다 — `src/cart/store.py`는 메모리 딕셔너리라 DB 외래키가 없습니다.

다시 넣을 때는 **상세 6종·내레이션·썸네일을 먼저 준비하고 음식 행을 넣는 순서**를 권합니다. 순서가 반대면 지금과 같은 상태가 반복됩니다.

## ⚠️ 아직 실행 안 된 것 — `foods.name_respell` 컬럼

TTS에 넘기는 문장에서 음식명을 리스펠링 표기로 바꾸기 위한 컬럼입니다(`Tteokbokki` → `Duck-bok-kee`). 예전에는 이 표가 `src/tts/infer.py`에 파이썬 dict로 하드코딩돼 있었는데, 음식이 늘 때마다 코드를 고쳐야 했고 DB와 어긋나도 알 방법이 없어서 컬럼으로 옮겼습니다. 화면에 표시되는 텍스트는 원본 로마자 표기를 그대로 유지하고, 치환은 TTS 입력에만 적용합니다(`src/text_gen/narration.py`의 `_to_tts_text()`).

**컬럼이 없으면 `cache.py`의 `foods` SELECT가 통째로 실패해 앱 전체가 죽습니다.** 행이 없을 때 폴백하는 `PRONUNCIATION_TTS`와 달리, 이건 코드보다 **먼저** 실행돼야 합니다.

**대응 — 아직 실행 안 됨. 조장이 Supabase SQL Editor에서 실행합니다.** 앱의 anon key는 RLS로 SELECT만 허용되므로 대시보드(또는 service_role) 권한이 필요합니다. 위 `foods` 200행 정리와는 순서를 가리지 않습니다 — 아래는 `id`가 아니라 `name_en`으로 매칭하기 때문입니다.

```sql
-- 1) 컬럼을 추가한다. 이미 있으면 넘어간다
alter table foods add column if not exists name_respell text;

-- 2) 리스펠링이 필요하다고 판정된 21개에만 값을 넣는다.
--    id가 아니라 name_en으로 매칭한다 — foods.id는 identity 컬럼이라 재시드하면 값이 달라진다
update foods as f
set name_respell = v.name_respell
from (values
  ('Agujjim',           'Ah-goo-jim'),
  ('Bibim Naengmyeon',  'Bee-bim Nang-myun'),
  ('Bibimbap',          'Bee-bim-bahp'),
  ('Cheonggukjang',     'Chung-gook-jang'),
  ('Doenjang Jjigae',   'Dwen-jang Jee-geh'),
  ('Dongtae Jjigae',    'Dong-teh Jee-geh'),
  ('Dubu Kimchi',       'Doo-boo Kim-chee'),
  ('Jeyuk Bokkeum',     'Jeh-yook Bok-kum'),
  ('Kimchi Bokkeumbap', 'Kim-chee Bok-kum-bap'),
  ('Kimchi Jjigae',     'Kim-chee Jee-geh'),
  ('Kongguksu',         'Kong-gook-soo'),
  ('Maeuntang',         'May-oon-tang'),
  ('Mulhoe',            'Mul-hweh'),
  ('Nakji Bokkeum',     'Nahk-jee Boh-kum'),
  ('Ojingeo Bokkeum',   'Oh-jing-uh Bok-kum'),
  ('Sundae',            'Soon-deh'),
  ('Sundubu Jjigae',    'Soon-doo-boo Jee-geh'),
  ('Tteokbokki',        'Duck-bok-kee'),
  ('Tteokgalbi',        'Duck-gal-bee'),
  ('Tteokguk',          'Duck-gook'),
  ('Yukhoe',            'Yook-hweh')
) as v(name_en, name_respell)
where f.name_en = v.name_en;

-- 3) 결과 확인 — 21이면 정상
select count(*) as respelled from foods where name_respell is not null;
```

값의 출처는 커밋 `8176e66`의 `src/tts/infer.py` `RESPELL_MAP` 21개입니다. 학습 완료된 어댑터로 원본 표기 vs 리스펠링 표기를 각각 생성해 청취 비교한 결과이며, 50개 중 21개만 리스펠링이 필요하고 29개는 원본 표기가 이미 적절하다고 판정했습니다(경위: `eval/TTS_MODULE.md` 4절).

**29개는 일부러 NULL로 둡니다.** `_to_tts_text()`가 값이 비어 있으면 치환하지 않으므로, NULL은 실패가 아니라 "원본 로마자 표기로 읽는다"는 뜻입니다. 상위 200개 시드로 들어온 음식도 같은 이유로 NULL이며, 청취 스크리닝을 거친 뒤에만 값을 채웁니다.

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
