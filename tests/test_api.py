"""API 테스트 — K_Menu_Talk.py의 두 엔드포인트가 약속한 모양대로 응답하는지 확인한다.

FastAPI의 TestClient를 쓴다. 서버를 진짜로 띄우지 않고, 코드 안에서 가짜 HTTP 요청을
보내서 응답을 받아보는 도구다(uvicorn 실행 불필요).

OCR·TTS 같은 무거운 로직은 전부 patch로 가짜 값으로 바꾼다. 여기서 검사하는 건
"모델이 잘 동작하나"가 아니라 "URL·상태코드·응답 필드명이 프론트와 맞나"이기 때문이다.

실행: python -m pytest tests/test_api.py
"""

import io
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import K_Menu_Talk
from K_Menu_Talk import app
from src.cart import store as cart_store


class AnalyzeEndpointTests(unittest.TestCase):
    """POST /api/analyze — 메뉴판 사진을 올리면 음식 후보 목록을 돌려주는 엔드포인트."""

    def setUp(self):
        self.client = TestClient(app)

    @patch.object(K_Menu_Talk, "analyze_image")
    def test_analyze_returns_candidates(self, mock_analyze_image):
        """사진을 올리면 200과 함께 후보 목록이 그대로 전달되는지."""
        # 실제 OCR 대신 이 값이 돌아온다 (OCR은 GPU·모델이 필요해서 테스트에서 제외)
        mock_analyze_image.return_value = {
            "status": "candidates_found",
            "ocr_text": "비빔밥",
            "candidates": [
                {"food_id": 1, "name_kr": "비빔밥", "name_en": "Bibimbap", "score": 95, "modifiers": {}}
            ],
        }

        # 진짜 이미지 파일이 필요 없다 — 아무 바이트나 파일인 척 올리면 된다
        response = self.client.post(
            "/api/analyze",
            files={"image": ("menu.jpg", io.BytesIO(b"fake-image-bytes"), "image/jpeg")},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "candidates_found")
        mock_analyze_image.assert_called_once()

    @patch.object(K_Menu_Talk, "analyze_image")
    def test_analyze_candidate_includes_price_fields(self, mock_analyze_image):
        """메뉴판에서 읽은 가격(price_krw/price_krw_display)이 후보 응답에 그대로 실리는지."""
        mock_analyze_image.return_value = {
            "status": "candidates_found",
            "ocr_text": "비빔밥 9,000원",
            "candidates": [
                {
                    "food_id": 1,
                    "name_kr": "비빔밥",
                    "name_en": "Bibimbap",
                    "score": 95,
                    "modifiers": {},
                    "price_krw": 9000,
                    "price_krw_display": "₩9,000",
                }
            ],
        }

        response = self.client.post(
            "/api/analyze",
            files={"image": ("menu.jpg", io.BytesIO(b"fake-image-bytes"), "image/jpeg")},
        )

        candidate = response.json()["candidates"][0]
        self.assertEqual(candidate["price_krw"], 9000)
        self.assertEqual(candidate["price_krw_display"], "₩9,000")

    @patch.object(K_Menu_Talk, "analyze_image")
    def test_analyze_candidate_price_defaults_to_none_when_absent(self, mock_analyze_image):
        """가격 필드를 안 준 후보 dict(가격 없는 메뉴)도 200으로 응답하고 null이어야 한다."""
        mock_analyze_image.return_value = {
            "status": "candidates_found",
            "ocr_text": "비빔밥",
            "candidates": [
                {"food_id": 1, "name_kr": "비빔밥", "name_en": "Bibimbap", "score": 95, "modifiers": {}}
            ],
        }

        response = self.client.post(
            "/api/analyze",
            files={"image": ("menu.jpg", io.BytesIO(b"fake-image-bytes"), "image/jpeg")},
        )

        candidate = response.json()["candidates"][0]
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(candidate["price_krw"])
        self.assertIsNone(candidate["price_krw_display"])

    @patch.object(K_Menu_Talk, "analyze_image")
    def test_analyze_candidate_includes_source_position(self, mock_analyze_image):
        """후보가 사진 어디의 어떤 글자에서 나왔는지가 응답에 실려야 한다 — 프론트가 그 자리에 상자를 그린다."""
        mock_analyze_image.return_value = {
            "status": "candidates_found",
            "ocr_text": "비빔밥 9,000",
            "candidates": [
                {
                    "food_id": 1,
                    "name_kr": "비빔밥",
                    "name_en": "Bibimbap",
                    "score": 95,
                    "modifiers": {},
                    "source": {"text": "비빔밥 9,000", "left": 0.1, "top": 0.2, "width": 0.3, "height": 0.08},
                }
            ],
        }

        response = self.client.post(
            "/api/analyze",
            files={"image": ("menu.jpg", io.BytesIO(b"fake-image-bytes"), "image/jpeg")},
        )

        source = response.json()["candidates"][0]["source"]
        self.assertEqual(source["text"], "비빔밥 9,000")
        self.assertEqual((source["left"], source["top"]), (0.1, 0.2))

    @patch.object(K_Menu_Talk, "analyze_image")
    def test_analyze_candidate_source_is_null_when_position_is_unknown(self, mock_analyze_image):
        """위치를 못 찾은 후보도 200으로 나가야 한다 — 사진 위 상자만 생략된다."""
        mock_analyze_image.return_value = {
            "status": "candidates_found",
            "ocr_text": "비빔밥",
            "candidates": [
                {"food_id": 1, "name_kr": "비빔밥", "name_en": "Bibimbap", "score": 95, "modifiers": {}}
            ],
        }

        response = self.client.post(
            "/api/analyze",
            files={"image": ("menu.jpg", io.BytesIO(b"fake-image-bytes"), "image/jpeg")},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["candidates"][0]["source"])

    @patch.object(K_Menu_Talk, "analyze_image")
    def test_analyze_passes_through_ocr_empty(self, mock_analyze_image):
        """글자를 못 읽었을 때(ocr_empty)도 에러가 아니라 200으로 상태를 알려줘야 한다.

        프론트가 이 status를 보고 "다시 찍어주세요" 안내 화면을 띄우기 때문에,
        여기서 500 에러를 내면 안내를 못 한다.
        """
        mock_analyze_image.return_value = {
            "status": "ocr_empty",
            "ocr_text": "",
            "candidates": [],
        }

        response = self.client.post(
            "/api/analyze",
            files={"image": ("menu.jpg", io.BytesIO(b"fake-image-bytes"), "image/jpeg")},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"status": "ocr_empty", "ocr_text": "", "candidates": []},
        )


class FoodDetailEndpointTests(unittest.TestCase):
    """GET /api/foods/{id} — 음식 하나의 상세 6개 + 내레이션 + 음성을 돌려주는 엔드포인트."""

    def setUp(self):
        self.client = TestClient(app)

    @patch.object(K_Menu_Talk, "get_food_row")
    @patch.object(K_Menu_Talk, "create_tts_response")
    @patch.object(K_Menu_Talk, "get_food_info")
    @patch.object(K_Menu_Talk, "get_details")
    def test_get_food_returns_details_and_narration(
        self, mock_get_details, mock_get_food_info, mock_create_tts_response, mock_get_food_row
    ):
        """응답에 상세·이름·style·tts_status가 다 들어있는지 — 프론트 결과 화면이 쓰는 필드들."""
        mock_get_details.return_value = {"DESCRIPTION": "설명", "SPICY": "1단계"}
        # 맵기는 cache에서 따로 읽어오므로 여기서도 막아준다 — 안 막으면 실제 Supabase를 부른다
        mock_get_food_row.return_value = {"spice_level": 3}
        mock_get_food_info.return_value = {"food_id": 1, "name_kr": "비빔밥", "name_en": "Bibimbap"}
        mock_create_tts_response.return_value = {
            "narration_text": "설명입니다.",
            "style": "GUIDE",
            "narration_audio_path": None,
            "tts_status": "not_ready",
            "tts_latency_ms": 0.0,
        }

        response = self.client.get("/api/foods/1")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["details"], {"DESCRIPTION": "설명", "SPICY": "1단계"})
        # 음식 이름은 결과 화면 제목으로 쓰이므로 반드시 응답에 있어야 한다
        self.assertEqual(body["name_kr"], "비빔밥")
        self.assertEqual(body["name_en"], "Bibimbap")
        self.assertEqual(body["style"], "GUIDE")
        self.assertEqual(body["tts_status"], "not_ready")
        # 결과 화면 맵기 눈금이 쓰는 값 — 응답에서 빠지면 화면이 못 그린다
        self.assertEqual(body["spice_level"], 3)
        self.assertIsNone(body["narration_audio_path"])
        # 세 함수 모두 같은 food_id로 딱 한 번씩 불렸는지 (중복 호출은 곧 중복 DB/GPU 비용)
        mock_get_details.assert_called_once_with(1)
        mock_get_food_info.assert_called_once_with(1)
        mock_create_tts_response.assert_called_once_with(1)

    @patch.object(K_Menu_Talk, "get_food_row")
    @patch.object(K_Menu_Talk, "create_tts_response")
    @patch.object(K_Menu_Talk, "get_food_info")
    @patch.object(K_Menu_Talk, "get_details")
    def test_get_food_publishes_audio_under_audio_url(
        self, mock_get_details, mock_get_food_info, mock_create_tts_response, mock_get_food_row
    ):
        """TTS가 만든 서버 파일경로가, 브라우저가 재생할 수 있는 /audio/ URL로 바뀌어 나가는지.

        이게 안 되면 프론트 <audio src>에 서버 디스크 경로가 그대로 들어가서 소리가 안 난다.
        """
        mock_get_details.return_value = {"DESCRIPTION": "설명"}
        mock_get_food_row.return_value = {"spice_level": 1}
        mock_get_food_info.return_value = {"food_id": 1, "name_kr": "비빔밥", "name_en": "Bibimbap"}
        # TTS가 임시폴더에 wav를 만든 상황을 흉내낸다 (실제 음성 생성은 안 함)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(b"fake-wav-bytes")
            source_path = tmp.name
        mock_create_tts_response.return_value = {
            "narration_text": "설명입니다.",
            "style": "GUIDE",
            "narration_audio_path": source_path,
            "tts_status": "ok",
            "tts_latency_ms": 12.5,
        }

        try:
            response = self.client.get("/api/foods/1")
        finally:
            # 테스트가 실패해도 static/audio에 쓰레기 파일이 남지 않도록 반드시 치운다
            (K_Menu_Talk.AUDIO_DIR / Path(source_path).name).unlink(missing_ok=True)
            Path(source_path).unlink(missing_ok=True)

        self.assertEqual(response.status_code, 200)
        audio_path = response.json()["narration_audio_path"]
        self.assertTrue(audio_path.startswith("/audio/"))

    @patch.object(K_Menu_Talk, "get_details")
    def test_get_food_returns_404_for_unknown_food(self, mock_get_details):
        """등록 안 된 음식이면 404 — 내부 ValueError가 500으로 새어나가면 안 된다."""
        mock_get_details.side_effect = ValueError("food_id 999에 대한 food_details가 없습니다.")

        response = self.client.get("/api/foods/999")

        self.assertEqual(response.status_code, 404)


class SupportedFoodsEndpointTests(unittest.TestCase):
    """GET /api/foods — 설정 화면의 "지원 음식" 목록 (docs/specs/supported-foods.md).

    사진을 찍기 전에 지원 여부를 확인하는 용도라, 일부만 추려 보내면 안 된다.
    """

    def setUp(self):
        self.client = TestClient(app)

    @patch.object(K_Menu_Talk, "get_foods")
    def test_returns_every_registered_food(self, mock_get_foods):
        """AC-01 · 등록된 음식을 전부 돌려준다."""
        mock_get_foods.return_value = [
            {"id": 1, "name_kr": "비빔밥", "name_en": "Bibimbap"},
            {"id": 2, "name_kr": "불고기", "name_en": "Bulgogi"},
            {"id": 3, "name_kr": "떡볶이", "name_en": "Tteokbokki"},
        ]

        response = self.client.get("/api/foods")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body), 3)
        self.assertEqual(body[0], {"food_id": 1, "name_kr": "비빔밥", "name_en": "Bibimbap"})

    @patch.object(K_Menu_Talk, "get_foods")
    def test_sorts_by_english_name(self, mock_get_foods):
        """AC-02 · 여행자가 영문으로 훑기 때문에 영문명 오름차순이어야 한다."""
        mock_get_foods.return_value = [
            {"id": 3, "name_kr": "떡볶이", "name_en": "Tteokbokki"},
            {"id": 1, "name_kr": "비빔밥", "name_en": "Bibimbap"},
            {"id": 2, "name_kr": "불고기", "name_en": "Bulgogi"},
        ]

        response = self.client.get("/api/foods")

        self.assertEqual(
            [food["name_en"] for food in response.json()],
            ["Bibimbap", "Bulgogi", "Tteokbokki"],
        )

    @patch.object(K_Menu_Talk, "get_foods")
    def test_returns_empty_list_instead_of_404(self, mock_get_foods):
        """AC-03 · 등록된 음식이 없어도 오류가 아니다 — 프론트가 "아직 없음"으로 안내한다."""
        mock_get_foods.return_value = []

        response = self.client.get("/api/foods")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    @patch.object(K_Menu_Talk, "get_foods")
    def test_does_not_leak_photo_or_spice_columns(self, mock_get_foods):
        """이 화면의 질문은 "무엇을 지원하나"이지 "무엇을 먹을까"가 아니다 — 이름만 내보낸다."""
        mock_get_foods.return_value = [
            {
                "id": 1,
                "name_kr": "비빔밥",
                "name_en": "Bibimbap",
                "spice_level": 2,
                "thumbnail_url": "https://example.com/bibimbap.jpg",
            }
        ]

        response = self.client.get("/api/foods")

        self.assertEqual(sorted(response.json()[0]), ["food_id", "name_en", "name_kr"])

    def test_food_list_route_does_not_shadow_the_detail_route(self):
        """/api/foods와 /api/foods/{id}가 공존해야 한다 — 목록 라우트가 상세를 가로채면 안 된다."""
        with (
            patch.object(K_Menu_Talk, "get_details", return_value={"DESCRIPTION": "설명"}),
            patch.object(
                K_Menu_Talk,
                "get_food_info",
                return_value={"food_id": 1, "name_kr": "비빔밥", "name_en": "Bibimbap"},
            ),
            patch.object(
                K_Menu_Talk,
                "create_tts_response",
                return_value={
                    "narration_text": "설명입니다.",
                    "style": "GUIDE",
                    "narration_audio_path": None,
                    "tts_status": "not_ready",
                    "tts_latency_ms": 0.0,
                },
            ),
        ):
            response = self.client.get("/api/foods/1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name_en"], "Bibimbap")


class CartEndpointTests(unittest.TestCase):
    """/api/cart — 담기/조회 어느 쪽이든 카트 전체 상태를 돌려주는 엔드포인트.

    카트 로직 자체는 tests/test_cart.py가 검사한다. 여기서는 HTTP 계약만 본다:
    헤더로 카트를 구분하는지, 응답 필드명이 프론트와 맞는지.
    """

    def setUp(self):
        self.client = TestClient(app)
        cart_store.clear_all()
        self.headers = {"X-Cart-Id": "api-test-cart"}

    def test_get_cart_returns_empty_cart_for_a_new_id(self):
        response = self.client.get("/api/cart", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "cart_id": "api-test-cart",
                "items": [],
                "item_count": 0,
                "total_krw": 0,
                "total_krw_display": "₩0",
                "has_unpriced_items": False,
            },
        )

    def test_post_item_returns_the_whole_cart_with_a_total(self):
        response = self.client.post(
            "/api/cart/items",
            headers=self.headers,
            json={
                "food_id": 1,
                "name_kr": "비빔밥",
                "name_en": "Bibimbap",
                "price_krw": 9000,
                "quantity_delta": 2,
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["items"][0]["quantity"], 2)
        self.assertEqual(body["items"][0]["line_total_display"], "₩18,000")
        self.assertEqual(body["total_krw"], 18000)
        self.assertEqual(body["total_krw_display"], "₩18,000")

    def test_delete_cart_returns_the_emptied_cart(self):
        self.client.post(
            "/api/cart/items",
            headers=self.headers,
            json={
                "food_id": 1,
                "name_kr": "비빔밥",
                "name_en": "Bibimbap",
                "price_krw": 9000,
                "quantity_delta": 2,
            },
        )

        response = self.client.delete("/api/cart", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["items"], [])
        self.assertEqual(body["total_krw"], 0)
        # 서버에도 실제로 비워졌는지 (응답만 비어 보이는 게 아니라)
        self.assertEqual(self.client.get("/api/cart", headers=self.headers).json()["items"], [])

    def test_delete_cart_requires_the_cart_id_header(self):
        self.assertEqual(self.client.delete("/api/cart").status_code, 422)

    def test_cart_requires_the_cart_id_header(self):
        """헤더가 없으면 남의 카트를 돌려주는 대신 422로 거절해야 한다."""
        self.assertEqual(self.client.get("/api/cart").status_code, 422)

    def test_cart_state_persists_between_requests_for_the_same_id(self):
        """"매 요청마다 최신 전체 상태" — 두 번 담으면 두 번째 응답에 합쳐진 결과가 나온다."""
        payload = {
            "food_id": 1,
            "name_kr": "비빔밥",
            "name_en": "Bibimbap",
            "price_krw": 9000,
            "quantity_delta": 1,
        }
        self.client.post("/api/cart/items", headers=self.headers, json=payload)
        self.client.post("/api/cart/items", headers=self.headers, json=payload)

        body = self.client.get("/api/cart", headers=self.headers).json()
        self.assertEqual(len(body["items"]), 1)
        self.assertEqual(body["items"][0]["quantity"], 2)


class PublishAudioTests(unittest.TestCase):
    """_publish_audio() 단독 테스트 — 임시 wav를 공개 폴더로 옮기고 URL을 만드는 함수."""

    def test_publish_audio_returns_none_when_no_path(self):
        """TTS가 실패해서 경로가 없으면(None) 그냥 None — 텍스트만이라도 응답해야 하므로."""
        self.assertIsNone(K_Menu_Talk._publish_audio(None))

    def test_publish_audio_moves_file_and_returns_relative_url(self):
        """파일이 static/audio로 '이동'되고(복사 아님) 상대 URL이 나오는지."""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(b"fake-wav-bytes")
            source_path = tmp.name

        url = K_Menu_Talk._publish_audio(source_path)
        published_path = K_Menu_Talk.AUDIO_DIR / Path(url).name
        try:
            self.assertEqual(url, f"/audio/{Path(source_path).name}")
            self.assertTrue(published_path.exists())      # 새 위치에 있고
            self.assertFalse(Path(source_path).exists())  # 원래 위치엔 없어야 함(=이동)
        finally:
            published_path.unlink(missing_ok=True)


class LoggingConfigTests(unittest.TestCase):
    """docs/specs/error-logging.md — httpx가 Supabase 요청 URL을 INFO로 찍어 공개 Space
    로그 화면에 그대로 노출되던 문제(실측 2026-08-24)를 억제하는지 확인한다.

    K_Menu_Talk.py를 임포트하는 시점에 이미 실행되는 모듈 최상단 설정이라, 값이
    이미 적용된 상태를 확인한다(다시 임포트해서 재현하지 않는다).
    """

    def test_httpx_logger_is_suppressed_below_warning(self):
        self.assertGreaterEqual(logging.getLogger("httpx").level, logging.WARNING)


if __name__ == "__main__":
    unittest.main()
