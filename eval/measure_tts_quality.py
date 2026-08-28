"""TTS 음성의 명료도(WER)·자연스러움(UTMOS)·생성 속도(RTF)를 한 자리에서 잰다.

사용법 — 저장소 루트에서:

    python -m eval.measure_tts_quality --score-cache
        지금 배포에 실려 있는 static/tts_cache 나레이션 50개를 그대로 채점한다.
        생성을 하지 않으므로 GPU 없이도 돌지만, ASR은 GPU가 있어야 빠르다.

    python -m eval.measure_tts_quality --ablate --n 10
        같은 문장을 (1) 배포 구성(LoRA 9차, scale 0.15) (2) LoRA를 뺀 베이스로
        각각 새로 생성해 같은 잣대로 채점한다. 파인튜닝이 무엇을 바꿨는지 보는 절제 실험.

왜 이 세 가지인가 — 심사 기준이 WER·MOS·RTF를 지목한다. MOS는 사람 채점이 정본이고
UTMOS는 그 대체가 아니라 사람 채점 전에 회귀를 잡는 자동 지표로 쓴다.

WER 기준선에 대해 — 참조 문장은 화면에 보이는 나레이션(`text`, 음식명이 로마자)이다.
음성이 읽는 문장(`tts_text`)은 음식명만 한글로 바뀌어 있는데, ASR을 영어로 돌리면 그
한 낱말은 거의 항상 틀리게 받아 적힌다. 그래서 두 값을 같이 낸다:

    WER          전체 낱말 기준 (음식명 포함)
    WER_core     음식명 낱말을 뺀 나머지 — 안내 문장 자체가 알아들리는가

음식명이 한국어 음운으로 읽히는 것은 의도한 동작이므로(src/text_gen/narration.py),
그 낱말의 ASR 불일치를 품질 저하로 읽으면 안 된다. 이름 발음이 맞는지는 별도로
eval/verify_name_audio.py가 한국어 ASR로 본다.
"""

import argparse
import csv
import json
import os
import re
import sys
import unicodedata
from pathlib import Path
from time import perf_counter

_ROOT = Path(__file__).resolve().parent.parent
_CACHE_DIR = _ROOT / "static" / "tts_cache"
_OUT_DIR = _ROOT / "eval" / "tts_quality"

_PUNCT = re.compile(r"[^\w'가-힣]+", re.UNICODE)


def _words(text: str) -> list[str]:
    """WER 비교용으로 문장을 낱말 목록으로 다듬는다.

    ASR은 문장부호와 대소문자를 제 마음대로 붙이므로 둘 다 버린다. 하이픈과 대시는
    낱말 경계로 본다 — "meat-free"를 한 낱말로 볼지 두 낱말로 볼지는 참조와 가설에
    같은 규칙만 적용하면 결과가 흔들리지 않는다.
    """
    text = unicodedata.normalize("NFC", text).lower()
    text = text.replace("—", " ").replace("–", " ").replace("-", " ")
    text = _PUNCT.sub(" ", text)
    return [w for w in text.split() if w]


def _align(ref: list[str], hyp: list[str]) -> list[tuple[str, int, int]]:
    """레벤슈타인 정렬. (연산, ref 인덱스, hyp 인덱스) 목록을 돌려준다.

    직접 구현하는 이유는 의존성 하나를 아끼려는 것이 아니라, 어느 낱말에서 틀렸는지
    알아야 음식명 낱말을 따로 떼어낼 수 있기 때문이다.
    """
    n, m = len(ref), len(hyp)
    dist = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dist[i][0] = i
    for j in range(m + 1):
        dist[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = 0 if ref[i - 1] == hyp[j - 1] else 1
            dist[i][j] = min(
                dist[i - 1][j] + 1, dist[i][j - 1] + 1, dist[i - 1][j - 1] + cost
            )

    ops: list[tuple[str, int, int]] = []
    i, j = n, m
    while i > 0 or j > 0:
        same = i > 0 and j > 0 and ref[i - 1] == hyp[j - 1]
        if i > 0 and j > 0 and dist[i][j] == dist[i - 1][j - 1] + (0 if same else 1):
            ops.append(("ok" if same else "sub", i - 1, j - 1))
            i, j = i - 1, j - 1
        elif i > 0 and dist[i][j] == dist[i - 1][j] + 1:
            ops.append(("del", i - 1, -1))
            i -= 1
        else:
            ops.append(("ins", -1, j - 1))
            j -= 1
    ops.reverse()
    return ops


def _score_text(reference: str, hypothesis: str, name_en: str) -> dict:
    """참조 문장과 ASR 전사를 견줘 WER과 음식명 인식 여부를 낸다."""
    ref, hyp = _words(reference), _words(hypothesis)
    name = _words(name_en)
    # 참조 문장에서 음식명이 놓인 자리를 표시해 둔다 — 그 자리의 오류는 따로 센다.
    name_idx: set[int] = set()
    if name:
        for i in range(len(ref) - len(name) + 1):
            if ref[i : i + len(name)] == name:
                name_idx.update(range(i, i + len(name)))

    ops = _align(ref, hyp)
    sub = sum(1 for op, _, _ in ops if op == "sub")
    dele = sum(1 for op, _, _ in ops if op == "del")
    ins = sum(1 for op, _, _ in ops if op == "ins")
    core_err = sum(
        1 for op, ri, _ in ops if op in ("sub", "del") and ri not in name_idx
    ) + ins
    core_n = max(len(ref) - len(name_idx), 1)
    name_hit = None
    if name_idx:
        name_hit = all(op == "ok" for op, ri, _ in ops if ri in name_idx)

    return {
        "ref_words": len(ref),
        "sub": sub,
        "del": dele,
        "ins": ins,
        "wer": (sub + dele + ins) / max(len(ref), 1),
        "wer_core": core_err / core_n,
        "name_hit": name_hit,
    }


def _load_asr():
    """faster-whisper large-v3. GPU가 되면 GPU로, 안 되면 CPU로 떨어진다.

    DLL 경로 손질은 eval/verify_name_audio.py와 같은 이유다 — ctranslate2가 찾는
    cuBLAS/cuDNN이 이 환경에서는 torch 패키지 안에만 있다.
    """
    from faster_whisper import WhisperModel

    try:
        import torch

        if hasattr(os, "add_dll_directory"):
            os.add_dll_directory(str(Path(torch.__file__).parent / "lib"))
        if torch.cuda.is_available():
            return WhisperModel("large-v3", device="cuda", compute_type="float16")
    except Exception as exc:  # noqa: BLE001 - 왜 CPU로 떨어졌는지는 남겨야 한다
        print(f"GPU ASR 준비 실패({exc}) — CPU로 돈다", file=sys.stderr)
    return WhisperModel("large-v3", device="cpu", compute_type="int8")


def _transcribe(model, path: Path) -> str:
    """영어 나레이션을 전사한다.

    language를 "en"으로 고정하는 이유 — 문장 안에 한글 음식명이 하나 섞여 있어서
    자동 판별에 맡기면 파일마다 언어가 갈리고, 그러면 같은 잣대로 견줄 수 없다.
    """
    segments, _ = model.transcribe(
        str(path), language="en", beam_size=5, without_timestamps=True
    )
    return "".join(s.text for s in segments)


def _load_utmos():
    import torch

    model = torch.hub.load("tarepan/SpeechMOS", "utmos22_strong", trust_repo=True)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    return model.to(device).eval(), device


def _utmos_score(bundle, path: Path) -> float:
    import librosa
    import torch

    model, device = bundle
    wave, sr = librosa.load(str(path), sr=None, mono=True)
    with torch.no_grad():
        return float(model(torch.from_numpy(wave).unsqueeze(0).to(device), sr).item())


def _duration(path: Path) -> float:
    import soundfile as sf

    info = sf.info(str(path))
    return info.frames / info.samplerate


def _summarize(rows: list[dict], label: str) -> dict:
    if not rows:
        return {}
    total_ref = sum(r["ref_words"] for r in rows)
    total_err = sum(r["sub"] + r["del"] + r["ins"] for r in rows)
    utmos = [r["utmos"] for r in rows if r.get("utmos") is not None]
    rtf = [r["rtf"] for r in rows if r.get("rtf") is not None]
    hits = [r["name_hit"] for r in rows if r.get("name_hit") is not None]
    return {
        "label": label,
        "n": len(rows),
        # 파일별 WER의 평균이 아니라 낱말을 다 합쳐서 낸 값이다 — 짧은 파일이 과대
        # 대표되지 않게 하려는 것으로, ASR 평가의 관행이기도 하다.
        "wer": total_err / max(total_ref, 1),
        "wer_core": sum(r["wer_core"] * (r["ref_words"] or 1) for r in rows)
        / max(total_ref, 1),
        "utmos_mean": sum(utmos) / len(utmos) if utmos else None,
        "utmos_min": min(utmos) if utmos else None,
        "utmos_max": max(utmos) if utmos else None,
        "rtf_mean": sum(rtf) / len(rtf) if rtf else None,
        "audio_sec_total": sum(r["dur_sec"] for r in rows),
        "name_hit_rate": (sum(1 for h in hits if h) / len(hits)) if hits else None,
    }


def _write(rows: list[dict], summary: dict, variant: str) -> None:
    if not rows:
        print("채점할 파일이 없었다.")
        return
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = _OUT_DIR / f"{variant}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    with open(_OUT_DIR / f"{variant}.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\n=> {csv_path}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def _pick(foods, n: int, ids: list[int] | None):
    """채점 대상 고르기. 맵기 4 이상(CAUTION) 음식은 4개뿐이라 반드시 넣는다."""
    if ids:
        return [f for f in foods if f["id"] in ids]
    caution = [f for f in foods if (f.get("spice_level") or 0) >= 4]
    guide = [f for f in foods if (f.get("spice_level") or 0) < 4]
    return (caution + guide)[:n]


def _load_base_model():
    """LoRA를 붙이지 않은 베이스 모델. 화자 임베딩만 같게 맞춘다.

    화자 임베딩을 그대로 두는 이유 — 목소리까지 달라지면 "LoRA가 무엇을 바꿨나"가
    아니라 "다른 사람 목소리와 견줬다"가 된다. 어댑터 델타만 빼는 절제 실험이어야
    비교가 성립한다. 화자 임베딩은 merge_and_unload() 이후에 codec_embedding에
    직접 덮어쓰는 값이라 LoRA와 독립이다(src/tts/infer.py의 _apply_speaker_embedding).
    """
    import torch
    from huggingface_hub import snapshot_download
    from qwen_tts import Qwen3TTSModel

    from src.tts import infer

    adapter_dir = snapshot_download(repo_id=infer.TTS_ADAPTER_REPO_ID)
    tts = Qwen3TTSModel.from_pretrained(
        infer.TTS_BASE_MODEL_ID,
        device_map="cuda:0",
        torch_dtype=torch.bfloat16,
        attn_implementation="sdpa",
    )
    core = infer._resolve_core_model(tts.model)
    infer._apply_speaker_config(core, adapter_dir, infer.TTS_SPEAKER_NAME)
    infer._apply_speaker_embedding(core, adapter_dir, infer.TTS_SPEAKER_NAME)
    core.eval()
    return tts


def _generate(tts, text: str, style: str, out_path: Path) -> float:
    """한 문장을 생성해 파일로 남기고 걸린 시간(초)을 돌려준다."""
    import soundfile as sf

    from src.tts import infer
    from src.tts.audio_checks import normalize_loudness

    started = perf_counter()
    infer._seed_everything(infer.SEED)
    wavs, sr = tts.generate_custom_voice(
        text=text,
        speaker=infer.TTS_SPEAKER_NAME,
        language="auto",
        max_new_tokens=infer.MAX_NEW_TOKENS,
        instruct=infer.INSTRUCT_MAP[style],
    )
    elapsed = perf_counter() - started
    sf.write(str(out_path), normalize_loudness(infer._trim_silence(wavs[0], sr)), sr)
    return elapsed


def _row(food, narration, path, gen_sec, asr, utmos) -> dict:
    dur = _duration(path)
    hyp = _transcribe(asr, path)
    row = {
        "food_id": food["id"],
        "name_kr": food.get("name_kr", ""),
        "style": narration["style"],
        "dur_sec": round(dur, 2),
        "gen_sec": round(gen_sec, 2) if gen_sec else None,
        "rtf": round(gen_sec / dur, 3) if gen_sec and dur else None,
        "utmos": round(_utmos_score(utmos, path), 4) if utmos else None,
    }
    row.update(_score_text(narration["text"], hyp, food.get("name_en", "")))
    row["hyp"] = hyp.strip()
    return row


def _report(row) -> None:
    print(
        f"{row['food_id']:>3} {row['name_kr']:<8} {row['style']:<8} "
        f"WER {row['wer']:.1%} · core {row['wer_core']:.1%} "
        f"· UTMOS {row['utmos'] if row['utmos'] is not None else '-'} "
        f"· RTF {row['rtf'] if row['rtf'] is not None else '-'}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="TTS 음성의 WER·UTMOS·RTF를 잰다.")
    parser.add_argument("--score-cache", action="store_true", help="배포 캐시를 그대로 채점")
    parser.add_argument("--ablate", action="store_true", help="배포 구성 vs LoRA 제거 비교")
    parser.add_argument("--n", type=int, default=10, help="--ablate에서 쓸 음식 수")
    parser.add_argument("--ids", type=int, nargs="*", help="음식 id 직접 지정")
    parser.add_argument("--no-utmos", action="store_true", help="UTMOS를 건너뛴다")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    from src.db import cache
    from src.text_gen.narration import get_narration

    foods = cache.get_foods()
    asr = _load_asr()
    utmos = None if args.no_utmos else _load_utmos()

    if args.score_cache:
        rows = []
        for food in foods:
            narration = get_narration(food["id"])
            path = _CACHE_DIR / f"food_{food['id']}_{narration['style']}.wav"
            if not path.exists():
                print(f"{food['id']:>3} 파일 없음 — 건너뜀")
                continue
            row = _row(food, narration, path, None, asr, utmos)
            _report(row)
            rows.append(row)
        _write(rows, _summarize(rows, "deployed-cache"), "deployed")
        return

    if args.ablate:
        targets = _pick(foods, args.n, args.ids)
        for variant in ("finetuned", "base"):
            audio_dir = _OUT_DIR / variant
            audio_dir.mkdir(parents=True, exist_ok=True)
            print(f"\n=== {variant} ({len(targets)}개) ===")
            if variant == "finetuned":
                from src.tts import infer

                tts = infer._load_model()
            else:
                # 앞 변형의 모델을 GPU에서 내려야 두 번째가 올라간다.
                import gc

                import torch

                from src.tts import infer

                infer._model = None
                tts = None
                gc.collect()
                torch.cuda.empty_cache()
                tts = _load_base_model()

            rows = []
            for food in targets:
                narration = get_narration(food["id"])
                out = audio_dir / f"food_{food['id']}_{narration['style']}.wav"
                gen_sec = _generate(tts, narration["tts_text"], narration["style"], out)
                row = _row(food, narration, out, gen_sec, asr, utmos)
                _report(row)
                rows.append(row)
            _write(rows, _summarize(rows, variant), variant)
        return

    parser.error("--score-cache 또는 --ablate 중 하나를 골라야 한다.")


if __name__ == "__main__":
    main()
