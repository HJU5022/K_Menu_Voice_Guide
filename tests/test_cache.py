"""캐싱 테스트 — src/db/cache.py가 DB를 한 번만 읽고, 조회 함수들이 맞는 값을 주는지 확인한다.

실제 Supabase에 접속하지 않는다. 대신 아래 FakeClient(가짜 DB)를 끼워넣어서,
네트워크·키 없이도 로직만 검사한다. 그래서 인터넷이 끊겨 있어도 돌아간다.

실행: python -m pytest tests/test_cache.py
"""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from src.db import cache


class FakeQuery:
    """supabase 쿼리 흉내 — client.table("foods").select(...).execute() 체인을 받아준다.

    진짜 supabase 라이브러리는 .select()가 또 자기 자신을 돌려주고, 마지막에 .execute()가
    결과를 주는 구조다(메서드 체이닝). 그 모양만 똑같이 흉내내서, 미리 넣어둔 데이터를
    그대로 돌려준다.
    """

    def __init__(self, data):
        self.data = data

    def select(self, *_args):
        # 어떤 컬럼을 고르든 무시하고 자기 자신을 돌려준다 (체이닝만 성립시키면 됨)
        return self

    def execute(self):
        # 진짜 supabase 응답은 .data 속성에 결과가 들어있다 — 그 모양만 맞춰준다
        return SimpleNamespace(data=self.data)


class FakeClient:
    """가짜 supabase 클라이언트 — 어느 테이블을 몇 번 읽었는지 세어둔다.

    call_counts가 핵심이다. cache.py의 목적이 "DB를 딱 한 번만 읽는 것"이라서,
    호출 횟수를 세어야 캐싱이 실제로 동작하는지 검사할 수 있다.
    """

    def __init__(self, tables):
        self.tables = tables
        self.call_counts = {name: 0 for name in tables}

    def table(self, name):
        self.call_counts[name] += 1
        return FakeQuery(self.tables[name])


class CacheTests(unittest.TestCase):
    def setUp(self):
        """각 테스트 시작 전에 매번 실행된다 — 캐시를 비우고 가짜 데이터를 새로 깐다."""
        # cache.py는 모듈 단위 전역 변수에 캐시를 들고 있어서, 앞 테스트가 남긴 값이
        # 다음 테스트로 새면 결과가 꼬인다. 그래서 매번 None으로 되돌린다.
        cache._cache = None

        # 실제 DB의 4개 테이블을 흉내낸 최소 데이터 (음식 1개짜리 축소판)
        self.tables = {
            "foods": [
                {
                    "id": 1,
                    "name_kr": "비빔밥",
                    "name_en": "Bibimbap",
                    "spice_level": 1,
                    "thumbnail_url": "https://example.com/bibimbap.jpg",
                    "thumbnail_attribution": "Source: AI Hub",
                }
            ],
            "food_details": [
                {"food_id": 1, "category": "DESCRIPTION", "detail_text": "Mixed rice."},
                {"food_id": 1, "category": "ALLERGY", "detail_text": "Contains egg."},
            ],
            "food_narration": [
                {"food_id": 1, "style": "GUIDE", "narration_text": "A mild dish."}
            ],
            "menu_modifiers": [
                {"keyword": "매운", "category": "spice", "keyword_en": "spicy", "spice_tier": 3}
            ],
        }
        self.fake_client = FakeClient(self.tables)

    def test_loads_from_db_only_once(self):
        """캐싱의 핵심 — 여러 번 조회해도 DB는 테이블당 한 번만 읽어야 한다."""
        with patch.object(cache, "client", self.fake_client):
            # 일부러 3번 조회한다 (foods 2번 + food_details 1번)
            cache.get_foods()
            cache.get_foods()
            cache.get_food_details(1)

        # 3번 불렀는데도 실제 DB 접근은 테이블당 1회여야 캐싱이 동작한 것
        self.assertEqual(self.fake_client.call_counts["foods"], 1)
        self.assertEqual(self.fake_client.call_counts["food_details"], 1)

    def test_get_food_returns_matching_row(self):
        """food_id로 음식 한 줄을 정확히 찾아오는지."""
        with patch.object(cache, "client", self.fake_client):
            result = cache.get_food(1)

        self.assertEqual(result["name_kr"], "비빔밥")
        self.assertEqual(result["name_en"], "Bibimbap")
        self.assertEqual(result["thumbnail_url"], "https://example.com/bibimbap.jpg")
        self.assertEqual(result["thumbnail_attribution"], "Source: AI Hub")

    def test_get_food_returns_none_for_unknown_id(self):
        """없는 food_id면 예외를 던지지 말고 None을 줘야 한다 (호출 쪽에서 404로 처리)."""
        with patch.object(cache, "client", self.fake_client):
            result = cache.get_food(999)

        self.assertIsNone(result)

    def test_get_food_details_filters_by_food_id_and_category(self):
        """카테고리를 지정하면 그 카테고리만 걸러서 준다 — 내레이션은 6개 중 2개만 쓰기 때문."""
        with patch.object(cache, "client", self.fake_client):
            result = cache.get_food_details(1, categories=("ALLERGY",))

        # DESCRIPTION도 데이터에 있지만, ALLERGY만 요청했으므로 그것만 나와야 한다
        self.assertEqual(result, {"ALLERGY": "Contains egg."})

    def test_get_narration_text_matches_food_id_and_style(self):
        """food_id와 style(GUIDE/CAUTION) 둘 다 맞는 줄을 찾아오는지."""
        with patch.object(cache, "client", self.fake_client):
            result = cache.get_narration_text(1, "GUIDE")

        self.assertEqual(result, "A mild dish.")

    def test_get_narration_text_returns_none_when_missing(self):
        """같은 음식이라도 해당 style이 없으면 None (여기선 GUIDE만 있고 CAUTION은 없음)."""
        with patch.object(cache, "client", self.fake_client):
            result = cache.get_narration_text(1, "CAUTION")

        self.assertIsNone(result)

    def test_get_modifiers_returns_all_rows(self):
        """수식어(매운·순한 등) 목록은 거르지 않고 통째로 준다 — 매칭 쪽에서 전부 훑어야 해서."""
        with patch.object(cache, "client", self.fake_client):
            result = cache.get_modifiers()

        self.assertEqual(result, self.tables["menu_modifiers"])


if __name__ == "__main__":
    unittest.main()
