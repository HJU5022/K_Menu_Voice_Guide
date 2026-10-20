-- 0001_init_schema.sql — 새 Supabase 프로젝트에 4개 테이블과 읽기 전용 RLS를 만든다.
--
-- 근거: `src/db/cache.py`가 select하는 컬럼 + `src/db/README.md`의 테이블 설명.
-- 옛 DB에서 스키마를 직접 뽑은 것이 아니므로, CSV를 넣기 전에 옛 DB의 실제 컬럼 타입과
-- 대조해 다르면 이 파일을 고친다(특히 foods 컬럼 타입, id가 identity인지 여부).
-- 데이터는 이 파일에 없다. CSV 백업을 Table Editor로 가져온다(menu_modifiers 시드는
-- `menu_modifiers_seed.sql`이 정제 전 503행이라 쓰지 않는다).

create table if not exists foods (
  id bigint primary key,
  name_kr text not null,
  name_en text not null,
  spice_level smallint not null check (spice_level between 0 and 5),
  thumbnail_url text,
  thumbnail_attribution text
);

create table if not exists food_details (
  food_id bigint not null references foods (id) on delete cascade,
  category text not null check (
    category in (
      'PRONUNCIATION', 'SPICY', 'DESCRIPTION',
      'INGREDIENT', 'HOW_TO_EAT', 'ALLERGY'
    )
  ),
  detail_text text not null,
  primary key (food_id, category)
);

create table if not exists food_narration (
  food_id bigint not null references foods (id) on delete cascade,
  style text not null check (style in ('GUIDE', 'CAUTION')),
  narration_text text not null,
  primary key (food_id, style)
);

create table if not exists menu_modifiers (
  id bigint generated always as identity primary key,
  keyword text not null unique,
  category text not null check (category in ('spice', 'ingredient')),
  keyword_en text,
  spice_tier smallint check (spice_tier between 1 and 5)
);

-- 읽기 전용: anon key로는 SELECT만 허용한다. INSERT/UPDATE/DELETE 정책은 만들지 않는다.
alter table foods enable row level security;
alter table food_details enable row level security;
alter table food_narration enable row level security;
alter table menu_modifiers enable row level security;

create policy "anon read foods" on foods for select to anon using (true);
create policy "anon read food_details" on food_details for select to anon using (true);
create policy "anon read food_narration" on food_narration for select to anon using (true);
create policy "anon read menu_modifiers" on menu_modifiers for select to anon using (true);
