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
