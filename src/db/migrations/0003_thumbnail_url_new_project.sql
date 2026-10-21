-- 0003_thumbnail_url_new_project.sql — foods.thumbnail_url의 Storage 주소를 새 프로젝트로 바꾼다.
-- 0002 실행 후에 한 번만 실행한다. 사진 50장은 새 프로젝트의 public 버킷
-- food-thumbnails/selected_photos/에 같은 파일명으로 올렸다(2026-10-20).
update foods
set thumbnail_url = replace(
  thumbnail_url,
  'https://qrxxxtwcrwiizpmsrpxi.supabase.co/',
  'https://jpdhmguwlvruugobafdy.supabase.co/'
)
where thumbnail_url like 'https://qrxxxtwcrwiizpmsrpxi.supabase.co/%';
