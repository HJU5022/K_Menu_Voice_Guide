"""Supabase 접속 — 읽기 전용 anon key를 쓰고, RLS로 SELECT만 허용한다.

대상 테이블: foods / food_details / food_narration / menu_modifiers
키는 .env에서 읽는다. 코드에 직접 적지 않는다.

**왜 anon key만 쓰나.** 이 서비스는 DB에 아무것도 쓰지 않는다 — 음식 설명은 사람이 미리
넣어둔 것을 읽기만 한다. 쓸 일이 없는데 쓰기 권한이 있는 키를 배포 서버에 두면, 키가 새는
날 데이터가 지워질 수 있다. 권한을 처음부터 안 주는 편이 새지 않게 지키는 것보다 확실하다.
"""

import os

from dotenv import load_dotenv
from supabase import create_client

# .env를 읽어 os.environ에 올린다. 이미 환경변수로 값이 들어와 있으면(배포 Space가 그렇다)
# load_dotenv는 그 값을 덮어쓰지 않는다.
load_dotenv()

# 키가 없으면 여기서 KeyError로 즉시 멈춘다 — 일부러 .get()을 쓰지 않았다.
# 키 없이 넘어가면 첫 조회에서야 알 수 없는 인증 오류로 터지는데, 그때는 원인이
# "키를 안 넣었다"라는 것이 드러나지 않는다.
client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])
