import unittest

from src.tts.infer import synthesize


class TtsInferTests(unittest.TestCase):
    def test_synthesize_returns_not_ready_result_for_valid_input(self):
        result = synthesize("A helpful food guide.", "GUIDE")

        self.assertIsNone(result["audio_path"])
        self.assertEqual(result["status"], "not_ready")
        self.assertGreaterEqual(result["latency_ms"], 0)

    def test_synthesize_rejects_empty_text(self):
        with self.assertRaisesRegex(ValueError, "비어 있지 않은 문자열"):
            synthesize("   ", "GUIDE")

    def test_synthesize_rejects_unknown_style(self):
        with self.assertRaisesRegex(ValueError, "GUIDE 또는 CAUTION"):
            synthesize("A helpful food guide.", "NEUTRAL")
