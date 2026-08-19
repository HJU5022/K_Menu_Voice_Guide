import unittest
from unittest.mock import patch

from src import pipeline


class PipelineTests(unittest.TestCase):
    @patch("src.pipeline.synthesize")
    @patch("src.pipeline.get_narration")
    def test_create_tts_response_combines_text_and_tts_results(
        self, mock_get_narration, mock_synthesize
    ):
        mock_get_narration.return_value = {
            "text": "This is Bibimbap.",
            "style": "GUIDE",
        }
        mock_synthesize.return_value = {
            "audio_path": None,
            "status": "not_ready",
            "latency_ms": 1.25,
        }

        result = pipeline.create_tts_response(1)

        mock_get_narration.assert_called_once_with(1)
        mock_synthesize.assert_called_once_with("This is Bibimbap.", "GUIDE")
        self.assertEqual(
            result,
            {
                "narration_text": "This is Bibimbap.",
                "style": "GUIDE",
                "narration_audio_path": None,
                "tts_status": "not_ready",
                "tts_latency_ms": 1.25,
            },
        )

    @patch("src.pipeline.synthesize")
    @patch("src.pipeline.get_narration")
    def test_create_tts_response_falls_back_when_synthesize_raises(
        self, mock_get_narration, mock_synthesize
    ):
        mock_get_narration.return_value = {
            "text": "This is Bibimbap.",
            "style": "GUIDE",
        }
        mock_synthesize.side_effect = RuntimeError("GPU를 사용할 수 없습니다.")

        result = pipeline.create_tts_response(1)

        self.assertEqual(
            result,
            {
                "narration_text": "This is Bibimbap.",
                "style": "GUIDE",
                "narration_audio_path": None,
                "tts_status": "not_ready",
                "tts_latency_ms": 0.0,
            },
        )

    @patch("src.pipeline.get_details")
    @patch("src.pipeline.create_tts_response")
    @patch("src.pipeline.match_food")
    @patch("src.pipeline.recognize")
    def test_run_returns_full_response_when_matched(
        self, mock_recognize, mock_match_food, mock_create_tts_response, mock_get_details
    ):
        mock_recognize.return_value = "비빔밥 8000원"
        mock_match_food.return_value = {"food_id": 1, "name_kr": "비빔밥", "score": 100.0}
        mock_create_tts_response.return_value = {
            "narration_text": "This is Bibimbap.",
            "style": "GUIDE",
            "narration_audio_path": None,
            "tts_status": "not_ready",
            "tts_latency_ms": 1.25,
        }
        mock_get_details.return_value = {"DESCRIPTION": "A bowl of rice."}

        result = pipeline.run("dummy.jpg")

        mock_recognize.assert_called_once_with("dummy.jpg")
        mock_match_food.assert_called_once_with("비빔밥 8000원")
        mock_create_tts_response.assert_called_once_with(1)
        mock_get_details.assert_called_once_with(1)
        self.assertEqual(result["matched_food"], {"food_id": 1, "name_kr": "비빔밥", "score": 100.0})
        self.assertEqual(result["details"], {"DESCRIPTION": "A bowl of rice."})
        self.assertEqual(result["narration_text"], "This is Bibimbap.")

    @patch("src.pipeline.get_details")
    @patch("src.pipeline.create_tts_response")
    @patch("src.pipeline.match_food")
    @patch("src.pipeline.recognize")
    def test_run_returns_none_matched_food_when_no_match(
        self, mock_recognize, mock_match_food, mock_create_tts_response, mock_get_details
    ):
        mock_recognize.return_value = "알수없는글자"
        mock_match_food.return_value = None

        result = pipeline.run("dummy.jpg")

        self.assertEqual(result, {"matched_food": None})
        mock_create_tts_response.assert_not_called()
        mock_get_details.assert_not_called()

    @patch("src.pipeline.match_food_candidates")
    @patch("src.pipeline.recognize")
    def test_analyze_image_returns_ocr_empty_without_matching(self, mock_recognize, mock_match_candidates):
        mock_recognize.return_value = "   "

        result = pipeline.analyze_image("dummy.jpg")

        self.assertEqual(
            result,
            {"status": "ocr_empty", "ocr_text": "", "candidates": []},
        )
        mock_match_candidates.assert_not_called()

    @patch("src.pipeline.match_food_candidates")
    @patch("src.pipeline.recognize")
    def test_analyze_image_returns_unsupported_food_with_ocr_text(
        self, mock_recognize, mock_match_candidates
    ):
        mock_recognize.return_value = "미지원음식"
        mock_match_candidates.return_value = []

        result = pipeline.analyze_image("dummy.jpg")

        self.assertEqual(
            result,
            {"status": "unsupported_food", "ocr_text": "미지원음식", "candidates": []},
        )
        mock_match_candidates.assert_called_once_with("미지원음식")

    @patch("src.pipeline.synthesize")
    @patch("src.pipeline.get_details")
    @patch("src.pipeline.match_food_candidates")
    @patch("src.pipeline.recognize")
    def test_analyze_image_returns_candidates_without_creating_response(
        self, mock_recognize, mock_match_candidates, mock_get_details, mock_synthesize
    ):
        candidates = [
            {"food_id": 2, "name_kr": "닭갈비", "score": 100, "modifiers": {}},
            {"food_id": 1, "name_kr": "갈비", "score": 95, "modifiers": {}},
        ]
        mock_recognize.return_value = "닭갈비 갈비"
        mock_match_candidates.return_value = candidates

        result = pipeline.analyze_image("dummy.jpg")

        self.assertEqual(
            result,
            {"status": "candidates_found", "ocr_text": "닭갈비 갈비", "candidates": candidates},
        )
        mock_get_details.assert_not_called()
        mock_synthesize.assert_not_called()
