"""API 테스트 — K_Menu_Talk.py의 두 엔드포인트가 약속한 모양대로 응답하는지 확인한다.

FastAPI의 TestClient를 쓴다. 서버를 진짜로 띄우지 않고, 코드 안에서 가짜 HTTP 요청을
보내서 응답을 받아보는 도구다(uvicorn 실행 불필요).

OCR·TTS 같은 무거운 로직은 전부 patch로 가짜 값으로 바꾼다. 여기서 검사하는 건
"모델이 잘 동작하나"가 아니라 "URL·상태코드·응답 필드명이 프론트와 맞나"이기 때문이다.

실행: python -m pytest tests/test_api.py
"""

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import K_Menu_Talk
from K_Menu_Talk import app


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
        self.assertEqual(response.json(), {"status": "ocr_empty", "ocr_text": "", "candidates": []})


class FoodDetailEndpointTests(unittest.TestCase):
    """GET /api/foods/{id} — 음식 하나의 상세 6개 + 내레이션 + 음성을 돌려주는 엔드포인트."""

    def setUp(self):
        self.client = TestClient(app)

    @patch.object(K_Menu_Talk, "create_tts_response")
    @patch.object(K_Menu_Talk, "get_food_info")
    @patch.object(K_Menu_Talk, "get_details")
    def test_get_food_returns_details_and_narration(
        self, mock_get_details, mock_get_food_info, mock_create_tts_response
    ):
        """응답에 상세·이름·style·tts_status가 다 들어있는지 — 프론트 결과 화면이 쓰는 필드들."""
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
        # 음식 이름은 결과 화면 제목으로 쓰이므로 반드시 응답에 있어야 한다
        self.assertEqual(body["name_kr"], "비빔밥")
        self.assertEqual(body["name_en"], "Bibimbap")
        self.assertEqual(body["style"], "GUIDE")
        self.assertEqual(body["tts_status"], "not_ready")
        self.assertIsNone(body["narration_audio_path"])
        # 세 함수 모두 같은 food_id로 딱 한 번씩 불렸는지 (중복 호출은 곧 중복 DB/GPU 비용)
        mock_get_details.assert_called_once_with(1)
        mock_get_food_info.assert_called_once_with(1)
        mock_create_tts_response.assert_called_once_with(1)

    @patch.object(K_Menu_Talk, "create_tts_response")
    @patch.object(K_Menu_Talk, "get_food_info")
    @patch.object(K_Menu_Talk, "get_details")
    def test_get_food_publishes_audio_under_audio_url(
        self, mock_get_details, mock_get_food_info, mock_create_tts_response
    ):
        """TTS가 만든 서버 파일경로가, 브라우저가 재생할 수 있는 /audio/ URL로 바뀌어 나가는지.

        이게 안 되면 프론트 <audio src>에 서버 디스크 경로가 그대로 들어가서 소리가 안 난다.
        """
        mock_get_details.return_value = {"DESCRIPTION": "설명"}
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


if __name__ == "__main__":
    unittest.main()
