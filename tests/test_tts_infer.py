import unittest
from unittest.mock import patch

from src.tts import infer


class FakeModel:
    """Stands in for the real Qwen3TTSModel + LoRA during tests (no GPU needed)."""

    def generate_custom_voice(self, text, speaker, language, max_new_tokens):
        import numpy as np

        return [np.zeros(100, dtype="float32")], 24000


class TtsInferTests(unittest.TestCase):
    def test_synthesize_rejects_empty_text(self):
        with self.assertRaisesRegex(ValueError, "비어 있지 않은 문자열"):
            infer.synthesize("   ", "GUIDE")

    def test_synthesize_rejects_unknown_style(self):
        with self.assertRaisesRegex(ValueError, "GUIDE 또는 CAUTION"):
            infer.synthesize("A helpful food guide.", "NEUTRAL")

    def test_synthesize_returns_audio_path_on_success(self):
        with patch.object(infer, "_load_model", return_value=FakeModel()):
            result = infer.synthesize("A helpful food guide.", "GUIDE")

        self.assertEqual(result["status"], "ok")
        self.assertIsNotNone(result["audio_path"])
        self.assertTrue(result["audio_path"].endswith(".wav"))
        self.assertGreaterEqual(result["latency_ms"], 0)
