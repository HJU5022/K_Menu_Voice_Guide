"""Supabase 접속 — 읽기 전용 anon key를 쓰고, RLS로 SELECT만 허용한다.

대상 테이블: foods / food_details / food_narration / menu_modifiers
키는 .env에서 읽는다. 코드에 직접 적지 않는다.
"""

import os

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])
