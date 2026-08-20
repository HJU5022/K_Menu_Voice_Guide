"""프론트엔드가 실제로 호출하는 순서(analyze -> foods/{id})를 그대로 재현해,
두 엔드포인트를 이어붙였을 때 응답 스키마가 프론트가 기대하는 필드를 계속
유지하는지 확인하는 통합테스트. 개별 엔드포인트 단위 테스트는 test_api.py 참고.
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

    @patch.object(K_Menu_Talk, "create_tts_response")
    @patch.object(K_Menu_Talk, "get_food_info")
    @patch.object(K_Menu_Talk, "get_details")
    @patch.object(K_Menu_Talk, "analyze_image")
    def test_full_analyze_then_food_detail_flow(
        self, mock_analyze_image, mock_get_details, mock_get_food_info, mock_create_tts_response
    ):
        mock_analyze_image.return_value = {
            "status": "candidates_found",
            "ocr_text": "비빔밥",
            "candidates": [
                {"food_id": 1, "name_kr": "비빔밥", "name_en": "Bibimbap", "score": 95, "modifiers": {}}
            ],
        }
        mock_get_food_info.return_value = {"food_id": 1, "name_kr": "비빔밥", "name_en": "Bibimbap"}
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

        analyze_res = self.client.post(
            "/api/analyze",
            files={"image": ("menu.jpg", io.BytesIO(b"fake-image-bytes"), "image/jpeg")},
        )
        self.assertEqual(analyze_res.status_code, 200)
        analyze_body = analyze_res.json()
        self.assertEqual(analyze_body["status"], "candidates_found")
        candidate = analyze_body["candidates"][0]
        for field in ("food_id", "name_kr", "name_en", "score", "modifiers"):
            self.assertIn(field, candidate)

        detail_res = self.client.get(f"/api/foods/{candidate['food_id']}")
        self.assertEqual(detail_res.status_code, 200)
        detail_body = detail_res.json()
        for field in (
            "details",
            "narration_text",
            "style",
            "tts_status",
            "narration_audio_path",
            "tts_latency_ms",
        ):
            self.assertIn(field, detail_body)
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
