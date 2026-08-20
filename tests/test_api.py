import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import K_Menu_Talk
from K_Menu_Talk import app


class AnalyzeEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @patch.object(K_Menu_Talk, "analyze_image")
    def test_analyze_returns_candidates(self, mock_analyze_image):
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
        self.assertEqual(response.json()["status"], "candidates_found")
        mock_analyze_image.assert_called_once()

    @patch.object(K_Menu_Talk, "analyze_image")
    def test_analyze_passes_through_ocr_empty(self, mock_analyze_image):
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
        self.assertEqual(response.json(), {"status": "ocr_empty", "ocr_text": "", "candidates": []})


class FoodDetailEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @patch.object(K_Menu_Talk, "create_tts_response")
    @patch.object(K_Menu_Talk, "get_food_info")
    @patch.object(K_Menu_Talk, "get_details")
    def test_get_food_returns_details_and_narration(
        self, mock_get_details, mock_get_food_info, mock_create_tts_response
    ):
        mock_get_details.return_value = {"DESCRIPTION": "설명", "SPICY": "1단계"}
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
        self.assertEqual(body["name_kr"], "비빔밥")
        self.assertEqual(body["name_en"], "Bibimbap")
        self.assertEqual(body["style"], "GUIDE")
        self.assertEqual(body["tts_status"], "not_ready")
        self.assertIsNone(body["narration_audio_path"])
        mock_get_details.assert_called_once_with(1)
        mock_get_food_info.assert_called_once_with(1)
        mock_create_tts_response.assert_called_once_with(1)

    @patch.object(K_Menu_Talk, "create_tts_response")
    @patch.object(K_Menu_Talk, "get_food_info")
    @patch.object(K_Menu_Talk, "get_details")
    def test_get_food_publishes_audio_under_audio_url(
        self, mock_get_details, mock_get_food_info, mock_create_tts_response
    ):
        mock_get_details.return_value = {"DESCRIPTION": "설명"}
        mock_get_food_info.return_value = {"food_id": 1, "name_kr": "비빔밥", "name_en": "Bibimbap"}
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
            (K_Menu_Talk.AUDIO_DIR / Path(source_path).name).unlink(missing_ok=True)
            Path(source_path).unlink(missing_ok=True)

        self.assertEqual(response.status_code, 200)
        audio_path = response.json()["narration_audio_path"]
        self.assertTrue(audio_path.startswith("/audio/"))

    @patch.object(K_Menu_Talk, "get_details")
    def test_get_food_returns_404_for_unknown_food(self, mock_get_details):
        mock_get_details.side_effect = ValueError("food_id 999에 대한 food_details가 없습니다.")

        response = self.client.get("/api/foods/999")

        self.assertEqual(response.status_code, 404)


class PublishAudioTests(unittest.TestCase):
    def test_publish_audio_returns_none_when_no_path(self):
        self.assertIsNone(K_Menu_Talk._publish_audio(None))

    def test_publish_audio_moves_file_and_returns_relative_url(self):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(b"fake-wav-bytes")
            source_path = tmp.name

        url = K_Menu_Talk._publish_audio(source_path)
        published_path = K_Menu_Talk.AUDIO_DIR / Path(url).name
        try:
            self.assertEqual(url, f"/audio/{Path(source_path).name}")
            self.assertTrue(published_path.exists())
            self.assertFalse(Path(source_path).exists())
        finally:
            published_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
