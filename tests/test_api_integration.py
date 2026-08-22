"""프론트엔드가 실제로 호출하는 순서(analyze -> foods/{id})를 그대로 재현해,
두 엔드포인트를 이어붙였을 때 응답 스키마가 프론트가 기대하는 필드를 계속
유지하는지 확인하는 통합테스트. 개별 엔드포인트 단위 테스트는 test_api.py 참고.

**단위 테스트와 뭐가 다른가**: test_api.py는 엔드포인트를 하나씩 따로 본다.
여기서는 사진 업로드 → 후보 받기 → 그 후보의 food_id로 상세 요청까지, 실제 사용자가
거치는 두 단계를 한 테스트 안에서 연달아 호출한다. 각각은 멀쩡한데 이어붙이면 깨지는
경우(예: analyze가 주는 필드명과 상세 요청이 기대하는 필드명이 다름)를 잡기 위한 것이다.
이런 계약 불일치가 실제로 한 번 있었기 때문에 이 테스트가 생겼다.

실행: python -m pytest tests/test_api_integration.py
"""

import io
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import K_Menu_Talk
from K_Menu_Talk import app


class AnalyzeToFoodDetailFlowTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @patch.object(K_Menu_Talk, "get_food_row")
    @patch.object(K_Menu_Talk, "create_tts_response")
    @patch.object(K_Menu_Talk, "get_food_info")
    @patch.object(K_Menu_Talk, "get_details")
    @patch.object(K_Menu_Talk, "analyze_image")
    def test_full_analyze_then_food_detail_flow(
        self,
        mock_analyze_image,
        mock_get_details,
        mock_get_food_info,
        mock_create_tts_response,
        mock_get_food_row,
    ):
        """사진 업로드 → 후보 받기 → 그 후보로 상세 요청까지, 프론트와 같은 순서로 호출한다."""
        mock_analyze_image.return_value = {
            "status": "candidates_found",
            "ocr_text": "비빔밥",
            "candidates": [
                {"food_id": 1, "name_kr": "비빔밥", "name_en": "Bibimbap", "score": 95, "modifiers": {}}
            ],
        }
        mock_get_food_info.return_value = {"food_id": 1, "name_kr": "비빔밥", "name_en": "Bibimbap"}
        mock_get_food_row.return_value = {"spice_level": 2}
        mock_get_details.return_value = {
            "DESCRIPTION": "설명",
            "PRONUNCIATION": "비빔밥",
            "INGREDIENT": "밥, 나물",
            "HOW_TO_EAT": "비벼서 먹는다",
            "SPICY": "순함",
            "ALLERGY": "달걀",
        }
        mock_create_tts_response.return_value = {
            "narration_text": "비빔밥은...",
            "style": "GUIDE",
            "narration_audio_path": "/audio/1.wav",
            "tts_status": "ready",
            "tts_latency_ms": 120.0,
        }

        # --- 1단계: 사진 업로드 → 후보 목록 ---
        analyze_res = self.client.post(
            "/api/analyze",
            files={"image": ("menu.jpg", io.BytesIO(b"fake-image-bytes"), "image/jpeg")},
        )
        self.assertEqual(analyze_res.status_code, 200)
        analyze_body = analyze_res.json()
        self.assertEqual(analyze_body["status"], "candidates_found")
        candidate = analyze_body["candidates"][0]
        # 후보 카드 UI가 쓰는 필드가 하나라도 빠지면 화면이 깨진다
        for field in ("food_id", "name_kr", "name_en", "score", "modifiers"):
            self.assertIn(field, candidate)

        # --- 2단계: 1단계에서 받은 food_id를 그대로 써서 상세 요청 ---
        # 값을 직접 적지 않고 candidate에서 꺼내 쓰는 게 핵심 — 두 응답이 실제로
        # 이어지는지(필드명이 맞는지) 검사하는 게 이 테스트의 목적이기 때문이다.
        detail_res = self.client.get(f"/api/foods/{candidate['food_id']}")
        self.assertEqual(detail_res.status_code, 200)
        detail_body = detail_res.json()
        for field in (
            "spice_level",
            "details",
            "narration_text",
            "style",
            "tts_status",
            "narration_audio_path",
            "tts_latency_ms",
        ):
            self.assertIn(field, detail_body)
        # 6개 카테고리가 전부 와야 결과 화면의 카드 6장이 채워진다 (기획서 필수 요건)
        for category in (
            "DESCRIPTION",
            "PRONUNCIATION",
            "INGREDIENT",
            "HOW_TO_EAT",
            "SPICY",
            "ALLERGY",
        ):
            self.assertIn(category, detail_body["details"])


if __name__ == "__main__":
    unittest.main()
