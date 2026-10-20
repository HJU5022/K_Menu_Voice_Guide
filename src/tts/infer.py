"""TTS 추론 — Qwen3-TTS 1.7B Base + LoRA 어댑터로 실제 음성을 생성한다.

베이스 모델: Qwen/Qwen3-TTS-12Hz-1.7B-Base
LoRA 어댑터: hajeongun/k-menu-qwen3-tts-lora (2026-10-20 k-bite-team에서 그대로 복사)
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
# [왜] 팀 저장소(k-bite-team/k-menu-qwen3-tts-lora)에 기대지 않도록 개인 계정에 그대로 복사했다.
# 파일 7개의 sha256이 원본과 같다.
TTS_ADAPTER_REPO_ID = "hajeongun/k-menu-qwen3-tts-lora"
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
    """실제로 음성을 만드는 속 모델(`talker`를 가진 쪽)을 찾아 돌려준다.

    모델이 여러 겹으로 싸여 있어서 필요하다. PEFT로 감싸면 `base_model`이 한 겹 더 생기고,
    라이브러리 버전에 따라 `.model`이 한 번 더 들어가기도 한다. 우리가 건드려야 하는
    speaker 설정과 codec embedding은 **가장 안쪽**에 있어서, 겉껍데기에 그대로 쓰면
    조용히 아무 일도 일어나지 않는다(예외도 안 난다).

    그래서 있을 수 있는 껍질 조합을 바깥에서 안쪽 순으로 하나씩 확인한다.
    """
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
    """학습된 목소리를 "이름 있는 화자"로 모델에 등록한다.

    이 방식은 참조 음성 파일을 매번 넣어주는 voice clone이 아니라, 어댑터에 함께 저장된
    화자 이름→ID 표(`config.json`의 `talker_config.spk_id`)를 모델 설정에 합쳐 넣고
    그 이름으로 부르는 방식이다. 그래서 요청마다 참조 음성을 읽을 필요가 없다.

    합쳐 넣기(update)이지 통째로 바꾸기가 아니다 — 베이스 모델이 원래 갖고 있던 화자
    목록을 지우면 안 되기 때문이다.
    """
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

    # 이름이 등록되지 않았으면 여기서 멈춘다. 그냥 넘어가면 나중에 생성 단계에서
    # 엉뚱한 기본 화자 목소리로 음성이 만들어지는데, 소리는 정상적으로 나와서
    # 듣기 전까지 잘못된 줄 모른다.
    if speaker_name not in core_model.config.talker_config.spk_id:
        raise ValueError(
            f"speaker_name '{speaker_name}'이 어댑터의 config.json에 등록돼 있지 않습니다."
        )


def _apply_speaker_embedding(core_model, adapter_dir, speaker_name):
    """학습된 목소리의 특징 벡터를, 등록한 화자 자리에 직접 덮어쓴다.

    위 `_apply_speaker_config()`가 "이 이름은 몇 번 자리"라는 표만 넣었다면, 여기서
    그 번호 자리의 실제 값을 우리 목소리로 바꾼다. 둘은 반드시 짝으로 불러야 한다 —
    표만 넣고 값을 안 바꾸면 이름은 인식되는데 목소리는 베이스 모델 것이 나온다.

    이 주입은 LoRA를 합친(`merge_and_unload`) **뒤에** 일어나므로 `LORA_SCALE`의
    영향을 받지 않는다. 어댑터 세기를 낮춰도 음색이 유지되는 이유가 이것이다.
    """
    import os

    from safetensors.torch import load_file

    embedding_path = os.path.join(adapter_dir, "speaker_embedding.safetensors")
    payload = load_file(embedding_path)
    if "target_speaker_embedding" not in payload:
        raise KeyError(f"'target_speaker_embedding'이 {embedding_path}에 없습니다.")

    spk_id = core_model.config.talker_config.spk_id[speaker_name]
    weight = core_model.talker.model.codec_embedding.weight
    # 모델이 올라간 장치(GPU)와 자료형(bfloat16)에 맞춰 옮긴 뒤 덮어쓴다.
    # 맞추지 않으면 대입 시점에 타입 오류가 나거나 CPU-GPU 사이에서 조용히 느려진다.
    weight.data[spk_id] = payload["target_speaker_embedding"].to(device=weight.device, dtype=weight.dtype)


def _set_lora_scale(peft_model, scale):
    """LoRA를 얼마나 세게 걸지 정한다. 값의 근거는 위 `LORA_SCALE` 주석에 있다.

    합치기(`merge_and_unload`) **전에** 불러야 한다. 합치고 나면 어댑터 계층이 사라져
    이 함수가 바꿀 대상이 없다.

    PEFT 버전에 따라 활성 어댑터가 없을 수도, 이름 하나일 수도, 목록일 수도 있어서
    세 경우를 모두 처리한다.
    """
    from peft.tuners.lora import LoraLayer

    # 1.0은 "그대로"라는 뜻이라 건드릴 이유가 없다. 굳이 모든 계층을 훑지 않는다.
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
    """베이스 모델을 한 번만 올리고, 어댑터를 합치고, 화자를 등록해 캐시한다.

    모델 로딩이 이 모듈에서 제일 비싼 일이라 **프로세스당 한 번만** 한다. 두 번째
    호출부터는 올려둔 것을 그대로 쓴다.

    import를 함수 안에서 하는 이유가 있다. `torch`는 무겁고, `paddle`(OCR)과 같은
    프로세스에 함께 올라가면 충돌한다. 이 모듈은 TTS 전용 자식 프로세스에서만 실행되므로
    (`src/tts/worker.py`), 파일을 읽는 것만으로 torch가 딸려 오지 않게 안쪽으로 미뤄둔다.
    """
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

    # 순서가 중요하다: 세기를 정한 뒤에 합친다.
    # 합치면 어댑터 계층이 사라지므로, 뒤집으면 scale이 아무 효과가 없다.
    peft_model = PeftModel.from_pretrained(tts.model, adapter_dir)
    _set_lora_scale(peft_model, LORA_SCALE)
    tts.model = peft_model.merge_and_unload()

    core_model = _resolve_core_model(tts.model)
    _apply_speaker_config(core_model, adapter_dir, TTS_SPEAKER_NAME)
    _apply_speaker_embedding(core_model, adapter_dir, TTS_SPEAKER_NAME)
    core_model.eval()

    # 시드를 고정한다. 긴 문장은 여러 조각으로 나뉘어 생성되는데, 조각마다 난수가
    # 달라지면 같은 문장 안에서 음색이 미묘하게 흔들린다.
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

    # 소리가 나는 구간을 그대로 두고, **너무 긴 무음만** 짧게 줄여 이어붙인다.
    # segments에 조각을 순서대로 쌓아 마지막에 한 번에 붙인다 — 배열을 매번 이어붙이면
    # 그때마다 통째로 복사되기 때문이다.
    segments = []
    pos = 0   # 아직 segments에 넣지 않은 구간의 시작 위치
    i = 0
    while i < len(voiced):
        if voiced[i]:
            i += 1
            continue
        # 여기부터 무음이다. 어디까지 이어지는지 j로 끝을 찾는다.
        j = i
        while j < len(voiced) and not voiced[j]:
            j += 1
        # 짧은 무음은 말의 자연스러운 쉼이라 손대지 않는다.
        # 기준(min_gap_ms)보다 긴 것만 줄인다.
        if j - i >= min_gap_windows:
            segments.append(wav[pos : i * win])          # 무음 직전까지의 소리
            gap_start = i * win
            segments.append(wav[gap_start : gap_start + keep_gap_samples])  # 쉼을 조금만 남긴다
            pos = j * win                                 # 나머지 무음은 건너뛴다
        i = j

    segments.append(wav[pos:])   # 마지막 무음 이후 남은 소리
    return np.concatenate(segments) if len(segments) > 1 else wav


def synthesize(text: str, style: str) -> dict[str, object]:
    """문장 하나를 받아 음성 파일을 만들고, 경로·걸린 시간·상태를 돌려준다.

    style에 맞는 instruct(톤 구분)를 붙여 모델에 넘긴다. 음식명 표기는 이미 한글로
    바뀐 상태로 들어온다(`src/text_gen/narration.py`의 `tts_text`).

    입력 검사를 모델 로딩보다 **먼저** 한다. 빈 문장이나 잘못된 style 때문에 수 초짜리
    로딩을 하고 나서 실패하면 시간만 버린다.

    돌려주는 `audio_path`는 임시 파일이다. 지우는 책임은 호출부(`src/pipeline.py`)에
    있다 — 여기서 지우면 아직 읽지도 않은 파일이 사라진다.
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
