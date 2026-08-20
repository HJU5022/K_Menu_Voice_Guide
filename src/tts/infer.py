"""TTS 추론 — Qwen3-TTS 1.7B Base + LoRA 어댑터로 실제 음성을 생성한다.

베이스 모델: Qwen/Qwen3-TTS-12Hz-1.7B-Base
LoRA 어댑터: k-bite-team/k-menu-qwen3-tts-lora (박민영님 학습, 40 epoch, lr=2e-6)

이 파일의 로직은 박민영님이 실제 학습에 쓴 노트북에서 확인한, 커뮤니티 패치
(instavar/qwen3-tts-lora-finetuning, patches/0001-qwen3-tts-lora.patch가 공식
Qwen3-TTS 저장소에 추가하는 finetuning/infer_lora_custom_voice.py)를 그대로 옮긴
것이다 — 처음엔 이 패치 파일을 못 찾아서 추측(generate_voice_clone 기반)으로 짰었는데,
실제 코드를 확인하고 나서 완전히 다시 짰다:

- LoRA는 PeftModel로 감싼 뒤 기본적으로 merge_and_unload()로 베이스 모델에 합쳐진다
  (--no_merge_lora 플래그가 없으면).
- 음성 생성은 generate_voice_clone이 아니라 **generate_custom_voice**를 쓴다 — 학습된
  목소리를 "이름 있는 스피커"로 모델에 등록해두고(config.json의 talker_config.spk_id에
  이름→ID 매핑) 그 이름으로 부르는 방식이다.
- speaker_embedding.safetensors의 "target_speaker_embedding" 텐서를, 등록된 speaker_id
  위치의 core_model.talker.model.codec_embedding.weight에 직접 덮어쓴다.
- LoRA scale은 peft.tuners.lora.LoraLayer의 set_scale()으로 적용한다 (1.0이면 생략).

2026-08-20: 서버에 연결해서 첫 실제 GPU 실행 중 발화 초반(0.2~0.4초)이 무음으로 끊기는
증상 발견 — TTS팀 정식 스크립트(inference.py)와 대조해보니 이 파일이 instruct 파라미터를
아예 안 넘기고 있었음(리스펠링도 누락). LoRA가 instruct 조건으로 학습됐는데 그걸 안 주니
생성 초반이 불안정해진 것으로 보임 — apply_respelling()/INSTRUCT_MAP을 정식 스크립트와
동일하게 포팅해서 수정함. speaker_name="speaker"/lora_scale=0.3은 여전히 팀 최종
채택값과 대조 확인 필요.
"""

import re
import tempfile
from time import perf_counter

import numpy as np

VALID_STYLES = frozenset({"GUIDE", "CAUTION"})

TTS_BASE_MODEL_ID = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
TTS_ADAPTER_REPO_ID = "k-bite-team/k-menu-qwen3-tts-lora"
TTS_SPEAKER_NAME = "speaker"  # 학습·추론 노트북에서 커스텀 이름을 안 줘서 계속 기본값 사용됨
LORA_SCALE = 0.3  # 1.0은 거의 항상 깨진 결과가 나온다는 커뮤니티 가이드, 0.2~0.5 권장값 중간값. 팀 최종 확정값 확인 필요
# 0.2/0.3/0.4/0.5 비교 실험 결과: 0.2·0.4는 발화 시작부에 최대 0.8초 무음, 0.5는 327초짜리
# 폭주 생성(정상은 ~25~30초) — scale을 낮추거나 높여서 없어지는 문제가 아니라 커스텀
# 보이스클로닝(generate_custom_voice) 자체의 특성으로 보임. scale 튜닝 대신 아래
# _trim_silence()로 후처리한다.
SEED = 42  # 청크 간 음색 흔들림 방지용 고정 시드 (원본 스크립트 기본값)
MAX_NEW_TOKENS = 4096

# TTS팀 정식 스크립트(inference.py)와 동일한 표 — 음식명 발음 보정용 리스펠링.
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
_SORTED_RESPELL_NAMES = sorted(RESPELL_MAP, key=len, reverse=True)

# 스타일별 instruct 문구 (톤 제어) — LoRA가 이 조건으로 학습됐으므로 반드시 같이 넘겨야 함.
# instruct 없이 호출하면 학습 때 본 적 없는 입력이 되어 생성 초반이 불안정해진다
# (관찰된 증상: 발화 시작 0.2~0.4초 구간이 무음으로 끊김).
INSTRUCT_MAP = {
    "GUIDE": "Speak in a calm, informative tone, like a knowledgeable guide explaining something interesting. Keep a natural, steady pace, not slow.",
    "CAUTION": "Say it in an urgent, warning tone, as if cautioning someone.",
}

_model = None


def apply_respelling(text: str) -> str:
    """음식명 부분만 리스펠링 표기로 치환. 단어 경계 기준으로 정확히 매칭."""
    for name in _SORTED_RESPELL_NAMES:
        text = re.sub(rf"\b{re.escape(name)}\b", RESPELL_MAP[name], text)
    return text


def _resolve_core_model(model):
    """Find the sub-model that actually has a ``talker`` (the real generation model)."""
    if hasattr(model, "talker"):
        return model
    if hasattr(model, "model") and hasattr(model.model, "talker"):
        return model.model
    if hasattr(model, "base_model"):
        base = model.base_model
        if hasattr(base, "talker"):
            return base
        if hasattr(base, "model") and hasattr(base.model, "talker"):
            return base.model
    return model


def _apply_speaker_config(core_model, adapter_dir, speaker_name):
    import json
    import os

    config_path = os.path.join(adapter_dir, "config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config_dict = json.load(f)
    talker_config = config_dict.get("talker_config", {})
    spk_id_map = talker_config.get("spk_id", {})
    spk_is_dialect = talker_config.get("spk_is_dialect", {})
    if isinstance(spk_id_map, dict):
        core_model.config.talker_config.spk_id.update(spk_id_map)
    if isinstance(spk_is_dialect, dict):
        core_model.config.talker_config.spk_is_dialect.update(spk_is_dialect)

    core_model.config.tts_model_type = "custom_voice"
    core_model.tts_model_type = "custom_voice"
    core_model.supported_speakers = core_model.config.talker_config.spk_id.keys()

    if speaker_name not in core_model.config.talker_config.spk_id:
        raise ValueError(
            f"speaker_name '{speaker_name}'이 어댑터의 config.json에 등록돼 있지 않습니다."
        )


def _apply_speaker_embedding(core_model, adapter_dir, speaker_name):
    import os

    from safetensors.torch import load_file

    embedding_path = os.path.join(adapter_dir, "speaker_embedding.safetensors")
    payload = load_file(embedding_path)
    if "target_speaker_embedding" not in payload:
        raise KeyError(f"'target_speaker_embedding'이 {embedding_path}에 없습니다.")

    spk_id = core_model.config.talker_config.spk_id[speaker_name]
    weight = core_model.talker.model.codec_embedding.weight
    weight.data[spk_id] = payload["target_speaker_embedding"].to(device=weight.device, dtype=weight.dtype)


def _set_lora_scale(peft_model, scale):
    from peft.tuners.lora import LoraLayer

    if scale == 1.0:
        return
    adapter = getattr(peft_model, "active_adapter", None)
    for module in peft_model.modules():
        if isinstance(module, LoraLayer):
            if adapter is None:
                module.scale_layer(scale)
            elif isinstance(adapter, (list, tuple)):
                for name in adapter:
                    module.set_scale(name, scale)
            else:
                module.set_scale(adapter, scale)


def _load_model():
    """Load the base model once, merge the LoRA adapter, register the custom speaker, and cache it."""
    global _model
    if _model is not None:
        return _model

    import torch
    from huggingface_hub import snapshot_download
    from peft import PeftModel
    from qwen_tts import Qwen3TTSModel

    adapter_dir = snapshot_download(repo_id=TTS_ADAPTER_REPO_ID)

    tts = Qwen3TTSModel.from_pretrained(
        TTS_BASE_MODEL_ID,
        device_map="cuda:0",
        torch_dtype=torch.bfloat16,
        attn_implementation="sdpa",
    )

    peft_model = PeftModel.from_pretrained(tts.model, adapter_dir)
    _set_lora_scale(peft_model, LORA_SCALE)
    tts.model = peft_model.merge_and_unload()

    core_model = _resolve_core_model(tts.model)
    _apply_speaker_config(core_model, adapter_dir, TTS_SPEAKER_NAME)
    _apply_speaker_embedding(core_model, adapter_dir, TTS_SPEAKER_NAME)
    core_model.eval()

    if SEED is not None:
        torch.manual_seed(SEED)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(SEED)

    _model = tts
    return _model


def _trim_silence(
    wav: np.ndarray,
    sample_rate: int,
    silence_threshold: float = 0.02,
    min_gap_ms: int = 200,
    keep_gap_ms: int = 100,
    edge_pad_ms: int = 40,
) -> np.ndarray:
    """generate_custom_voice() 출력에서 비정상적인 무음 구간을 잘라낸다.

    실측(0.2/0.3/0.4/0.5 LoRA scale 비교, instruct 파라미터 추가 후에도 재현):
    발화 시작부에 최대 0.8초짜리 무음이 붙거나, 문장 중간에 200~600ms짜리 부자연스러운
    끊김이 생긴다 — scale이나 instruct로는 없어지지 않는, 이 방식(codec embedding을
    직접 덮어쓰는 커스텀 보이스클로닝) 자체의 워밍업 특성으로 보임. 그래서 생성 후
    무음 구간을 감지해서 잘라낸다 — 앞/뒤는 완전히, 중간은 자연스러운 쉼표 길이로 압축한다
    (완전히 이어붙이면 부자연스럽게 뚝 끊긴 느낌이 나서, 짧게는 남겨둔다).
    """
    win = max(int(sample_rate * 0.02), 1)  # 20ms 창
    n_win = int(np.ceil(len(wav) / win))
    rms = np.array(
        [
            np.sqrt(np.mean(wav[i * win : (i + 1) * win].astype(np.float64) ** 2))
            for i in range(n_win)
        ]
    )
    voiced = rms > silence_threshold

    if not voiced.any():
        return wav  # 전부 무음이면 (드문 실패 케이스) 손대지 않고 호출자가 판단하게 둔다

    edge_pad = max(int(sample_rate * edge_pad_ms / 1000), 0)

    # 1) 앞/뒤 무음 트리밍 — 발화의 자연스러운 어택/디케이가 잘리지 않도록 약간 여유를 둔다
    first = int(np.argmax(voiced))
    last = len(voiced) - 1 - int(np.argmax(voiced[::-1]))
    start = max(first * win - edge_pad, 0)
    end = min((last + 1) * win + edge_pad, len(wav))
    wav = wav[start:end]

    # 2) 문장 중간의 비정상적으로 긴 무음을 자연스러운 쉼표 길이로 압축
    n_win = int(np.ceil(len(wav) / win))
    rms = np.array(
        [
            np.sqrt(np.mean(wav[i * win : (i + 1) * win].astype(np.float64) ** 2))
            for i in range(n_win)
        ]
    )
    voiced = rms > silence_threshold
    min_gap_windows = max(int(min_gap_ms / 20), 1)
    keep_gap_samples = int(sample_rate * keep_gap_ms / 1000)

    segments = []
    pos = 0
    i = 0
    while i < len(voiced):
        if voiced[i]:
            i += 1
            continue
        j = i
        while j < len(voiced) and not voiced[j]:
            j += 1
        if j - i >= min_gap_windows:
            segments.append(wav[pos : i * win])
            gap_start = i * win
            segments.append(wav[gap_start : gap_start + keep_gap_samples])
            pos = j * win
        i = j

    segments.append(wav[pos:])
    return np.concatenate(segments) if len(segments) > 1 else wav


def synthesize(text: str, style: str) -> dict[str, object]:
    """Validate a narration request, generate speech, and return the TTS result."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("TTS text는 비어 있지 않은 문자열이어야 합니다.")
    if style not in VALID_STYLES:
        raise ValueError("TTS style은 GUIDE 또는 CAUTION이어야 합니다.")

    import soundfile as sf

    started_at = perf_counter()

    tts_text = apply_respelling(text)
    instruct = INSTRUCT_MAP[style]

    model = _load_model()
    wavs, sample_rate = model.generate_custom_voice(
        text=tts_text,
        speaker=TTS_SPEAKER_NAME,
        language="auto",
        max_new_tokens=MAX_NEW_TOKENS,
        instruct=instruct,
    )

    trimmed = _trim_silence(wavs[0], sample_rate)

    output_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    sf.write(output_file.name, trimmed, sample_rate)

    return {
        "audio_path": output_file.name,
        "latency_ms": (perf_counter() - started_at) * 1000,
        "status": "ok",
    }
