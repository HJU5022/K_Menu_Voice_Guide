"""
K-Menu Voice Guide - TTS 프로덕션 통합 모듈.

narration_text(화면 표시용 원문)와 style(GUIDE/CAUTION)만 넘기면
음식명 리스펠링 + 톤 instruct가 자동으로 처리되어 음성 파일이 생성된다.

사용:
    from inference import generate_narration_audio
    generate_narration_audio(
        narration_text="Careful, this one's spicy! Tteokbokki is chewy rice cakes...",
        style="CAUTION",
        output_wav="output.wav",
    )

요구 사항: pip install qwen-tts peft soundfile torch
"""
import re
import torch
from qwen_tts import Qwen3TTSModel
from peft import PeftModel
import soundfile as sf

BASE_MODEL = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
ADAPTER_REPO = "k-bite-team/k-menu-qwen3-tts-lora"

# 청취 테스트로 확정한 리스펠링 표 (원본 발음이 부정확했던 음식 21개만 포함)
RESPELL_MAP = {
    "Tteokbokki": "Duck-bok-kee",
    "Bibimbap": "Bee-bim-bahp",
    "Nakji Bokkeum": "Nahk-jee Boh-kum",
    "Agujjim": "Ah-goo-jim",
    "Maeuntang": "May-oon-tang",
    "Bibim Naengmyeon": "Bee-bim Nang-myun",
    "Cheonggukjang": "Chung-gook-jang",
    "Doenjang Jjigae": "Dwen-jang Jee-geh",
    "Dongtae Jjigae": "Dong-teh Jee-geh",
    "Dubu Kimchi": "Doo-boo Kim-chee",
    "Jeyuk Bokkeum": "Jeh-yook Bok-kum",
    "Kimchi Bokkeumbap": "Kim-chee Bok-kum-bap",
    "Kimchi Jjigae": "Kim-chee Jee-geh",
    "Kongguksu": "Kong-gook-soo",
    "Mulhoe": "Mul-hweh",
    "Ojingeo Bokkeum": "Oh-jing-uh Bok-kum",
    "Sundae": "Soon-deh",
    "Sundubu Jjigae": "Soon-doo-boo Jee-geh",
    "Tteokgalbi": "Duck-gal-bee",
    "Tteokguk": "Duck-gook",
    "Yukhoe": "Yook-hweh",
}
# 긴 이름부터 먼저 치환해야 부분 문자열 충돌(예: Tteokguk vs Tteokgalbi) 방지
_SORTED_NAMES = sorted(RESPELL_MAP, key=len, reverse=True)

# 스타일별 instruct 문구 (톤 제어) - 강도/언어 비교 청취 테스트로 확정
INSTRUCT_MAP = {
    "GUIDE": "Speak in a calm, informative tone, like a knowledgeable guide explaining something interesting. Keep a natural, steady pace, not slow.",
    "CAUTION": "Say it in an urgent, warning tone, as if cautioning someone.",
}

_model = None  # lazy singleton, 첫 호출 시에만 모델 로드


def apply_respelling(text):
    """음식명 부분만 리스펠링 표기로 치환. 단어 경계 기준으로 정확히 매칭."""
    for name in _SORTED_NAMES:
        text = re.sub(rf"\b{re.escape(name)}\b", RESPELL_MAP[name], text)
    return text


def _load_model():
    global _model
    if _model is None:
        tts = Qwen3TTSModel.from_pretrained(
            BASE_MODEL,
            device_map="cuda:0",
            torch_dtype=torch.bfloat16,
            attn_implementation="sdpa",
        )
        peft_model = PeftModel.from_pretrained(tts.model, ADAPTER_REPO)
        tts.model = peft_model.merge_and_unload()
        tts.model.eval()
        _model = tts
    return _model


def generate_narration_audio(narration_text, style, output_wav="output.wav", lora_scale=0.3):
    """narration_text(화면 표시용 원문)와 style(GUIDE/CAUTION)을 받아서,
    음식명 리스펠링 + 톤 instruct를 자동 적용해 음성 파일을 생성한다."""
    style = style.upper()
    if style not in INSTRUCT_MAP:
        raise ValueError(f"style은 GUIDE 또는 CAUTION이어야 함, 받은 값: {style}")

    tts_text = apply_respelling(narration_text)
    instruct = INSTRUCT_MAP[style]

    tts = _load_model()
    wavs, sr = tts.generate_custom_voice(
        text=tts_text,
        speaker="speaker",
        language="auto",
        instruct=instruct,
    )
    sf.write(output_wav, wavs[0], sr)
    return output_wav


if __name__ == "__main__":
    import sys
    text = sys.argv[1] if len(sys.argv) > 1 else "Bibimbap is a colorful bowl of warm rice."
    style = sys.argv[2] if len(sys.argv) > 2 else "GUIDE"
    out = sys.argv[3] if len(sys.argv) > 3 else "output.wav"
    generate_narration_audio(text, style, out)
    print(f"saved: {out}")
