"""TTS 추론 — Qwen3-TTS 1.7B Base + LoRA 어댑터로 실제 음성을 생성한다.

베이스 모델: Qwen/Qwen3-TTS-12Hz-1.7B-Base
LoRA 어댑터: k-bite-team/k-menu-qwen3-tts-lora
  - 최종 체크포인트: checkpoint-epoch-31 (`instruct_trained_lr5e-6_ep40` 런,
    lr=5e-6, rank=16, alpha=32, 40 epoch, batch=4, val_loss=8.8919로 전체 에폭 중 최저)
  - 2026-08-20: 이전 체크포인트(epoch-39, `final_respelled_lr5e-6_ep40`)는 리스펠링만
    학습 데이터에 반영돼 있고 instruct는 추론 시점에만 적용되던 버전이었음. 이번 런은
    학습 스크립트(dataset.py/sft_12hz_lora.py)를 고쳐서 instruct 임베딩을 시퀀스 앞에
    이어붙이는 방식으로 실제 학습에도 반영함 — 학습/추론 조건이 일치하도록 함.
  - 하이퍼파라미터 자체(LR=5e-6, rank=16)는 기존 5개 조합 비교에서 채택된 값 그대로 재사용.
    상세 실험 기록: eval/TTS_MODULE.md 3절, eval/training_log.csv (구 체크포인트 기준)

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

발음 개선(음식명 표기)과 톤 구분(instruct)이 이 모듈의 두 축이다 — 상세 근거는
eval/TTS_MODULE.md 4·5절 참고. 다만 표기 쪽은 더 이상 여기서 처리하지 않는다(아래 정정).

2026-08-25 정정 — 음식명 표기 치환을 이 파일에서 걷어냈고, 표기 방식도 한글로 바꿨음:

- 표기 방식: 영문 리스펠링(`Tteokbokki` → `Duck-bok-kee`)에서 **한글 표기**(`Tteokbokki` →
  `떡볶이`)로 바꿨다. 리스펠링은 된소리(ㄸ, ㅃ, ㄲ, ㅆ, ㅉ)에 대응하는 알파벳 신호가 없어
  근사치로 타협해야 했고, 리스펠링한 21개뿐 아니라 원본 표기가 적절하다고 판정했던 29개까지
  발음이 부정확했다 — 철자를 바꿔도 결과가 같다면 원인은 철자가 아니라 모델이 그 이름을 영어
  음운으로 읽는다는 것이다. 한글로 적으면 한국어 음운으로 읽는다.
- 값과 치환 위치: 값은 이미 있는 `foods.name_kr` 컬럼이고(표기용 컬럼을 따로 두지 않는다),
  치환은 `src/text_gen/narration.py`가 한다. 거기서 `foods` 행을 이미 조회하므로
  `name_en`/`name_kr` 쌍이 손에 있다. 이 모듈은 `tts_text`를 받아 그대로 넘긴다 — 여기서 또
  건드리면 이미 바뀐 이름을 두 번 처리하게 된다.
- 삭제한 것: `RESPELL_MAP`·`_SORTED_RESPELL_NAMES`·`apply_respelling()`. 21개 표의 값과
  스크리닝 경위는 `eval/TTS_MODULE.md` 4절에 남아 있다.
- ⚠️ 청취 확인 전이다. `eval/TTS_MODULE.md` 4절은 "영어 문장 중간에 한글 삽입"을 실패한
  접근으로 적어뒀다(`"...called 떡볶이 (tteokbokki)."` 형태, 결과가 부자연스러웠음). 지금
  방식은 로마자를 괄호로 병기하지 않고 이름 자체를 한글로 대체하는 것이라 조건이 다르지만,
  GPU 환경에서 들어보기 전까지 확정은 아니다.

2026-08-20 정정: 위 TTS_MODULE.md 5절은 "instruct는 LoRA 학습 조건이 아니라 베이스 모델
추론 시점 기능"이라고 설명하는데, 이건 **epoch-39(구) 체크포인트에만 해당**하던 얘기였음.
확인해보니 그 체크포인트를 학습한 스크립트(sft_12hz_lora.py)엔 애초에 instruct를 받는
경로 자체가 없었음 — instruct 효과는 베이스 모델의 zero-shot instruct-following 능력에서
나온 것. epoch-31(신규) 체크포인트부터는 학습 스크립트를 고쳐서 instruct를 실제 학습에도
반영했으므로, 이제는 학습 조건이 맞다. GUIDE/CAUTION 톤 구분용이며, 아래 발화 안정성
문제와는 무관하다.

2026-08-20: 실제 GPU로 처음 돌려보니 발화 시작부에 최대 0.8초 무음이 붙거나 문장 중간에
200~600ms 끊김이 생기는 증상 확인 — LoRA scale(0.2/0.3/0.4/0.5)이나 instruct 유무와
무관하게 재현됨(0.5는 327초짜리 폭주 생성까지 발생, 정상은 ~25~30초). scale 튜닝으로
없어지는 문제가 아니라 generate_custom_voice 자체의 워밍업 특성으로 보고, 아래
_trim_silence()로 생성 후 후처리한다.
"""

import tempfile
from time import perf_counter

import numpy as np

VALID_STYLES = frozenset({"GUIDE", "CAUTION"})

TTS_BASE_MODEL_ID = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
TTS_ADAPTER_REPO_ID = "k-bite-team/k-menu-qwen3-tts-lora"
TTS_SPEAKER_NAME = "speaker"  # 학습·추론 노트북에서 커스텀 이름을 안 줘서 계속 기본값 사용됨
LORA_SCALE = 0.15  # GUIDE/CAUTION 톤 구분용. 어댑터를 세게 걸수록 학습된 단일 화자 톤이
# instruct를 눌러 두 스타일이 비슷하게 들려서 0.3 -> 0.15로 낮춘다 (기존 0.2/0.3/0.35/0.5
# 청취 비교는 톤이 아니라 음질 기준이었음. 1.0은 거의 항상 깨진 결과가 나옴 — 커뮤니티 가이드).
# 낮춰도 화자 음색은 유지된다 — 음색은 speaker_embedding을 codec_embedding.weight에 직접
# 덮어쓰는 방식이고(아래 _apply_speaker_embedding), 그 주입은 merge_and_unload() 이후라
# scale이 곱해지는 LoRA 델타와 무관하다. 음식명은 이제 한글로 넘어가는데(narration.py가 치환),
# 배포 체크포인트는 리스펠링된 영문 라벨로 학습된 것이라 한글 읽기는 어댑터가 아니라 베이스
# 모델의 한국어 능력에 기댄다 — 그래서 scale을 낮추는 것이 표기 쪽에 불리하지만은 않다.
# 발화 안정성도 scale에 영향받으므로 값을 바꿀 땐 청취 확인이 필요하다.
# 참고: 0.2/0.3/0.4/0.5 재비교 시 발화 시작부/중간 무음이 scale과 무관하게 나타났고
# (0.5는 327초짜리 폭주 생성까지 발생) — 그래서 scale 튜닝 대신 아래 _trim_silence()로
# 생성 후 후처리한다.
SEED = 42  # 청크 간 음색 흔들림 방지용 고정 시드 (원본 스크립트 기본값)
MAX_NEW_TOKENS = 4096

# --- 톤 구분: instruct (eval/TTS_MODULE.md 5절) ------------------------------
# 강도 단계별(약함~극단) + 언어(영어 vs 중국어) 비교 청취로 확정.
# 재학습 없이 추론 시점에서 즉시 적용되는 방식 — CAUTION 학습 데이터 부족(8%) 문제를
# 우회하는 해법. 톤 구분용이며, 발화 초반 무음 문제와는 무관함(아래 _trim_silence 참고).
INSTRUCT_MAP = {
    "GUIDE": (
        "Speak in a calm, informative tone, like a knowledgeable guide "
        "explaining something interesting. Keep a natural, steady pace, not slow."
    ),
    "CAUTION": "Say it in an urgent, warning tone, as if cautioning someone.",
}

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
    """Validate a narration request, generate speech, and return the TTS result.

    style에 맞는 instruct(톤 구분)를 붙여 모델에 넘긴다. 음식명 표기는 이미 한글로
    바뀐 상태로 들어온다(src/text_gen/narration.py의 tts_text).
    """
    if not isinstance(text, str) or not text.strip():
        raise ValueError("TTS text는 비어 있지 않은 문자열이어야 합니다.")
    if style not in VALID_STYLES:
        raise ValueError("TTS style은 GUIDE 또는 CAUTION이어야 합니다.")

    import soundfile as sf

    started_at = perf_counter()

    # 음식명 한글 치환은 narration.py에서 이미 끝났다 — 여기 오는 text가 그 결과다.
    instruct = INSTRUCT_MAP[style]

    model = _load_model()
    wavs, sample_rate = model.generate_custom_voice(
        text=text,
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
