"""TTS 추론 테스트 — src/tts/infer.py의 synthesize()와 무음 제거 후처리를 확인한다.

실제 Qwen3-TTS 모델은 부르지 않는다(GPU·수 GB 모델 다운로드가 필요하므로).
아래 FakeModel이 모델 자리에 들어가서, **모델에 무엇을 넘겼는지**를 기록해준다.
즉 "음성이 좋은가"가 아니라 "입력을 올바르게 가공해서 넘겼는가"를 검사한다.

검사하는 두 가지 가공:
- **리스펠링**: 음식명을 발음하기 쉬운 영어 표기로 바꿔서 넘긴다
  (예: Tteokbokki → Duck-bok-kee). 화면 텍스트는 원본 그대로 두고 TTS 입력만 바꾼다.
- **instruct**: GUIDE/CAUTION에 맞는 톤 지시문을 함께 넘긴다.

뒤쪽 TrimSilenceTests는 생성된 음성에서 불필요한 무음을 잘라내는 후처리 테스트다.
자세한 배경은 eval/TTS_MODULE.md 4·5절 참고.

실행: python -m pytest tests/test_tts_infer.py
"""

import unittest
from unittest.mock import patch

import numpy as np

from src.tts import infer


class FakeModel:
    """Stands in for the real Qwen3TTSModel + LoRA during tests (no GPU needed).

    last_call에 "마지막으로 어떤 인자를 받았는지"를 저장해둔다. 테스트는 이걸 꺼내서
    리스펠링·instruct가 제대로 적용된 채로 넘어왔는지 확인한다.
    """

    def __init__(self):
        self.last_call = None

    def generate_custom_voice(self, text, speaker, language, max_new_tokens, instruct=""):
        import numpy as np

        # 진짜 모델이 받는 인자를 그대로 받아서 기록만 하고, 가짜 음성 데이터를 돌려준다
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
        """빈 텍스트면 모델을 띄우기 전에 막는다 — 무거운 모델 로딩을 헛되이 하지 않기 위해."""
        with self.assertRaisesRegex(ValueError, "비어 있지 않은 문자열"):
            infer.synthesize("   ", "GUIDE")

    def test_synthesize_rejects_unknown_style(self):
        """style은 GUIDE/CAUTION 둘 중 하나만 — 오타가 조용히 통과하면 톤이 엉뚱해진다."""
        with self.assertRaisesRegex(ValueError, "GUIDE 또는 CAUTION"):
            infer.synthesize("A helpful food guide.", "NEUTRAL")

    def test_synthesize_returns_audio_path_on_success(self):
        """정상 경로 — wav 파일 경로와 status='ok'를 돌려주는지."""
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
        """음식명이 리스펠링 표기로 바뀐 뒤 모델에 들어가는지 (Tteokbokki → Duck-bok-kee).

        문장 안에 섞여 있어도 그 단어만 정확히 바뀌어야 한다. 화면에 표시되는 원본
        텍스트는 그대로 두고, TTS 입력만 바꾸는 게 이 기능의 핵심이다.
        """
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

    SR = 24000  # 샘플레이트 24kHz — 1초 = 24000개 숫자

    def test_trims_leading_and_trailing_silence(self):
        """앞뒤에 붙은 무음을 잘라낸다 — 재생 버튼을 눌러도 한참 조용한 문제를 막기 위해."""
        # [0.8초 무음] + [1.0초 발화] + [0.6초 무음] 짜리 가짜 음성을 만든다
        wav = np.concatenate([_silence(0.8, self.SR), _tone(1.0, self.SR), _silence(0.6, self.SR)])

        result = infer._trim_silence(wav, self.SR)

        # 앞뒤 무음은 거의 다 잘려나가고(약간의 edge_pad만 남음), 발화 구간 길이(1.0s) 근처로 수렴한다
        self.assertLess(len(result) / self.SR, 1.3)
        self.assertGreater(len(result) / self.SR, 0.9)

    def test_compresses_long_internal_gap_to_keep_gap_ms(self):
        """문장 중간의 긴 끊김은 짧게 줄인다 (600ms → 100ms) — 말이 뚝뚝 끊겨 들리지 않도록."""
        wav = np.concatenate([_tone(0.5, self.SR), _silence(0.6, self.SR), _tone(0.5, self.SR)])

        result = infer._trim_silence(wav, self.SR, min_gap_ms=200, keep_gap_ms=100)

        # 600ms짜리 무음이 100ms로 압축되어 전체 길이가 크게 줄어든다
        self.assertLess(len(result) / self.SR, 1.3)
        self.assertGreater(len(result) / self.SR, 1.0)

    def test_leaves_short_internal_gap_untouched(self):
        """짧은 쉼(100ms)은 건드리지 않는다 — 자연스러운 말의 호흡까지 없애면 안 되므로."""
        wav = np.concatenate([_tone(0.5, self.SR), _silence(0.1, self.SR), _tone(0.5, self.SR)])

        result = infer._trim_silence(wav, self.SR, min_gap_ms=200, keep_gap_ms=100)

        # 100ms짜리 무음(기준선 200ms 미만)은 압축 대상이 아니라 원본 길이가 거의 그대로 유지된다
        self.assertAlmostEqual(len(result) / self.SR, len(wav) / self.SR, delta=0.05)

    def test_returns_input_unchanged_when_entirely_silent(self):
        """전부 무음이면 그대로 둔다 — 다 잘라내서 길이 0짜리 파일을 만들면 재생이 깨진다."""
        wav = _silence(1.0, self.SR)

        result = infer._trim_silence(wav, self.SR)

        self.assertEqual(len(result), len(wav))
