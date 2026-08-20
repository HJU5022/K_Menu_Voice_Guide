"""TTS 추론 — Qwen3-TTS 1.7B Base + LoRA 어댑터로 실제 음성을 생성한다.

베이스 모델: Qwen/Qwen3-TTS-12Hz-1.7B-Base
LoRA 어댑터: k-bite-team/k-menu-qwen3-tts-lora
  - 최종 체크포인트: checkpoint-epoch-39 (8차 실험 `final_respelled_lr5e-6_ep40`,
    lr=5e-6, rank=16, alpha=32, 40 epoch, batch=4)
  - 하이퍼파라미터 5개 조합(LR 5e-6/1e-5/2e-5 x rank 16/32) 비교 후 채택된 값.
    상세 실험 기록: tts/TTS_MODULE.md 3절, tts/training_log.csv

이 파일의 로직은 박민영님이 실제 학습에 쓴 노트북에서 확인한, 커뮤니티 패치
(instavar/qwen3-tts-lora-finetuning, patches/0001-qwen3-tts-lora.patch가 공식
Qwen3-TTS 저장소에 추가하는 finetuning/infer_lora_custom_voice.py)를 그대로 옮긴
것이다.

- LoRA는 PeftModel로 감싼 뒤 기본적으로 merge_and_unload()로 베이스 모델에 합쳐진다
  (--no_merge_lora 플래그가 없으면).
- 음성 생성은 generate_voice_clone이 아니라 **generate_custom_voice**를 쓴다 — 학습된
  목소리를 "이름 있는 스피커"로 모델에 등록해두고(config.json의 talker_config.spk_id에
  이름→ID 매핑) 그 이름으로 부르는 방식이다.
- speaker_embedding.safetensors의 "target_speaker_embedding" 텐서를, 등록된 speaker_id
  위치의 core_model.talker.model.codec_embedding.weight에 직접 덮어쓴다.
- LoRA scale은 peft.tuners.lora.LoraLayer의 set_scale()으로 적용한다 (1.0이면 생략).

발음 개선(리스펠링)과 톤 구분(instruct)은 2026-08-19 최종 업데이트로 synthesize()에
추가됨 — 상세 근거는 tts/TTS_MODULE.md 4·5절 참고.
"""

import re
import tempfile
from time import perf_counter

VALID_STYLES = frozenset({"GUIDE", "CAUTION"})

TTS_BASE_MODEL_ID = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
TTS_ADAPTER_REPO_ID = "k-bite-team/k-menu-qwen3-tts-lora"
TTS_SPEAKER_NAME = "speaker"  # 학습·추론 노트북에서 커스텀 이름을 안 줘서 계속 기본값 사용됨
LORA_SCALE = 0.3  # 0.2/0.3/0.35/0.5 청취 비교 후 확정. 1.0은 거의 항상 깨진 결과가 나옴(커뮤니티 가이드)
SEED = 42  # 청크 간 음색 흔들림 방지용 고정 시드 (원본 스크립트 기본값)
MAX_NEW_TOKENS = 4096

# --- 발음 개선: 음식명 리스펠링 (tts/TTS_MODULE.md 4절) ---------------------
# 청취 테스트로 확정. 화면 표시용 narration_text는 원본 로마자 표기를 그대로 쓰고,
# TTS 입력 시에만 이 표로 치환한다. 8차 최종 재학습부터는 이 치환된 텍스트를
# 학습 데이터 라벨에도 반영해, 모델이 리스펠링 표기 자체를 학습하도록 했다.
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

# --- 톤 구분: instruct (tts/TTS_MODULE.md 5절) ------------------------------
# 강도 단계별(약함~극단) + 언어(영어 vs 중국어) 비교 청취로 확정.
# 재학습 없이 추론 시점에서 즉시 적용되는 방식 — CAUTION 학습 데이터 부족(8%) 문제를
# 우회하는 해법.
INSTRUCT_MAP = {
    "GUIDE": (
        "Speak in a calm, informative tone, like a knowledgeable guide "
        "explaining something interesting. Keep a natural, steady pace, not slow."
    ),
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


def synthesize(text: str, style: str) -> dict[str, object]:
    """Validate a narration request, generate speech, and return the TTS result.

    음식명 리스펠링(발음 개선)과 style별 instruct(톤 구분)를 자동 적용한다.
    narration_text(화면 표시용 원문)는 그대로 두고, 여기서만 변환해서 모델에 넘긴다.
    """
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

    output_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    sf.write(output_file.name, wavs[0], sample_rate)

    return {
        "audio_path": output_file.name,
        "latency_ms": (perf_counter() - started_at) * 1000,
        "status": "ok",
    }
