import unittest
from unittest.mock import patch

import numpy as np

from src.tts import infer


class FakeModel:
    """Stands in for the real Qwen3TTSModel + LoRA during tests (no GPU needed)."""

    def __init__(self):
        self.last_call = None

    def generate_custom_voice(self, text, speaker, language, max_new_tokens, instruct=""):
        import numpy as np

        self.last_call = {
            "text": text,
            "speaker": speaker,
            "language": language,
            "max_new_tokens": max_new_tokens,
            "instruct": instruct,
        }
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

    def test_synthesize_passes_instruct_for_style(self):
        """instruct 없이 호출하면 LoRA가 학습 때 못 본 입력을 받게 되어 발화 초반이
        불안정해진다 (실제로 관찰된 증상: 0.2~0.4초 무음 끊김) — 회귀 방지용 테스트."""
        fake = FakeModel()
        with patch.object(infer, "_load_model", return_value=fake):
            infer.synthesize("A helpful food guide.", "GUIDE")

        self.assertEqual(fake.last_call["instruct"], infer.INSTRUCT_MAP["GUIDE"])

    def test_synthesize_respells_food_name_before_calling_model(self):
        fake = FakeModel()
        with patch.object(infer, "_load_model", return_value=fake):
            infer.synthesize("This dish is called Tteokbokki.", "CAUTION")

        self.assertEqual(fake.last_call["text"], "This dish is called Duck-bok-kee.")
        self.assertEqual(fake.last_call["instruct"], infer.INSTRUCT_MAP["CAUTION"])


def _tone(duration_s, sample_rate=24000, amplitude=0.3):
    """무음이 아닌 '발화'처럼 보이는 구간(순수 톤)을 만든다."""
    t = np.linspace(0, duration_s, int(sample_rate * duration_s), endpoint=False)
    return (amplitude * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def _silence(duration_s, sample_rate=24000):
    return np.zeros(int(sample_rate * duration_s), dtype=np.float32)


class TrimSilenceTests(unittest.TestCase):
    """_trim_silence() 회귀 테스트 — 실측(0.2~0.5 LoRA scale 비교, instruct 추가 후에도
    재현)된 '발화 시작부 최대 0.8초 무음 / 문장 중간 200~600ms 끊김' 문제의 후처리 방어선."""

    SR = 24000

    def test_trims_leading_and_trailing_silence(self):
        wav = np.concatenate([_silence(0.8, self.SR), _tone(1.0, self.SR), _silence(0.6, self.SR)])

        result = infer._trim_silence(wav, self.SR)

        # 앞뒤 무음은 거의 다 잘려나가고(약간의 edge_pad만 남음), 발화 구간 길이(1.0s) 근처로 수렴한다
        self.assertLess(len(result) / self.SR, 1.3)
        self.assertGreater(len(result) / self.SR, 0.9)

    def test_compresses_long_internal_gap_to_keep_gap_ms(self):
        wav = np.concatenate([_tone(0.5, self.SR), _silence(0.6, self.SR), _tone(0.5, self.SR)])

        result = infer._trim_silence(wav, self.SR, min_gap_ms=200, keep_gap_ms=100)

        # 600ms짜리 무음이 100ms로 압축되어 전체 길이가 크게 줄어든다
        self.assertLess(len(result) / self.SR, 1.3)
        self.assertGreater(len(result) / self.SR, 1.0)

    def test_leaves_short_internal_gap_untouched(self):
        wav = np.concatenate([_tone(0.5, self.SR), _silence(0.1, self.SR), _tone(0.5, self.SR)])

        result = infer._trim_silence(wav, self.SR, min_gap_ms=200, keep_gap_ms=100)

        # 100ms짜리 무음(기준선 200ms 미만)은 압축 대상이 아니라 원본 길이가 거의 그대로 유지된다
        self.assertAlmostEqual(len(result) / self.SR, len(wav) / self.SR, delta=0.05)

    def test_returns_input_unchanged_when_entirely_silent(self):
        wav = _silence(1.0, self.SR)

        result = infer._trim_silence(wav, self.SR)

        self.assertEqual(len(result), len(wav))
