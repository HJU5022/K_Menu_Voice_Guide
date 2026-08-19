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

**아직 실제로 실행은 못 해봤다 (로컬에 GPU가 없음).** 로직은 실제 코드를 그대로 옮긴
것이라 신뢰도가 높지만, speaker_name="speaker"/lora_scale=0.3이 팀이 실제로 최종
채택한 값인지는 확인 필요 (노트북에서 0.2/0.3/0.35/0.5를 다 뽑아서 귀로 비교하던 중이었음).
"""

import tempfile
from time import perf_counter

VALID_STYLES = frozenset({"GUIDE", "CAUTION"})

TTS_BASE_MODEL_ID = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
TTS_ADAPTER_REPO_ID = "k-bite-team/k-menu-qwen3-tts-lora"
TTS_SPEAKER_NAME = "speaker"  # 학습·추론 노트북에서 커스텀 이름을 안 줘서 계속 기본값 사용됨
LORA_SCALE = 0.3  # 1.0은 거의 항상 깨진 결과가 나온다는 커뮤니티 가이드, 0.2~0.5 권장값 중간값. 팀 최종 확정값 확인 필요
SEED = 42  # 청크 간 음색 흔들림 방지용 고정 시드 (원본 스크립트 기본값)
MAX_NEW_TOKENS = 4096

_model = None


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
    """Validate a narration request, generate speech, and return the TTS result."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("TTS text는 비어 있지 않은 문자열이어야 합니다.")
    if style not in VALID_STYLES:
        raise ValueError("TTS style은 GUIDE 또는 CAUTION이어야 합니다.")

    import soundfile as sf

    started_at = perf_counter()

    model = _load_model()
    wavs, sample_rate = model.generate_custom_voice(
        text=text,
        speaker=TTS_SPEAKER_NAME,
        language="auto",
        max_new_tokens=MAX_NEW_TOKENS,
    )

    output_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    sf.write(output_file.name, wavs[0], sample_rate)

    return {
        "audio_path": output_file.name,
        "latency_ms": (perf_counter() - started_at) * 1000,
        "status": "ok",
    }
