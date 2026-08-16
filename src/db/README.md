# src/db/

**Supabase 데이터 접근 계층**

DB에 직접 접근하는 코드는 전부 여기에만 둡니다. 다른 폴더에서는 이 모듈을 통해서만 데이터를 가져옵니다.

## 파일

| 파일 | 역할 |
|---|---|
| `supabase_client.py` | 읽기 전용 anon key로 접속, RLS로 SELECT만 허용 |
| `cache.py` | 서버 시작 시 전체 데이터를 메모리에 올려두기 |

## 접근하는 테이블

| 테이블 | 내용 |
|---|---|
| `foods` | 음식 기본 정보 (음식명, spice_level) |
| `food_details` | 카테고리 6개 상세 설명 (PRONUNCIATION·SPICY·DESCRIPTION·INGREDIENT·HOW_TO_EAT·ALLERGY) |
| `food_narration` | style별 내레이션 문장 |

## 보안

- **anon key만** 사용합니다. service role key는 저장소에 절대 넣지 않습니다.
- RLS(Row Level Security)로 `SELECT`만 허용됩니다. INSERT/UPDATE/DELETE는 막혀 있습니다.
- 키는 `.env`에 두고, `.env.example`에는 **키 이름만** 적습니다.

## 캐싱을 쓰는 이유

등록된 음식이 50개뿐이라 데이터가 작습니다. 서버 시작할 때 전부 메모리에 올려두면 요청마다 DB를 다녀올 필요가 없어서 응답이 빨라집니다.
