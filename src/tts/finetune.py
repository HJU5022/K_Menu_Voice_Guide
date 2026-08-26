"""TTS 파인튜닝 — Qwen3-TTS 1.7B Base에 LoRA 어댑터를 학습시킨다. 학습할 때만 실행한다.

학습 데이터는 팀원이 직접 녹음한 음성이다. 준비 방법은 data/README.md 참고.

출처 — 이 파일은 박민영님이 실제 학습에 쓴 Colab 노트북
(`eval/qwen3_tts_lora_final.ipynb`, 커밋 b99009e)의 코드를 모듈로 옮긴 것이다.
노트북은 실행 기록이자 인계용 문서로 그대로 두고, 여기서는 재실행 가능한 함수만 남긴다.

GPU 전제 — 학습·코드추출 모두 CUDA가 필요하다(노트북은 Colab A100 기준). 로컬
Windows 개발 환경에서는 돌아가지 않는다. 배포 경로(`src/tts/infer.py`)와 달리 이
모듈은 서비스 런타임에서 import되지 않는다.

노트북과 달라진 점 4가지:

1. Colab 전용 코드를 걷어냈다 — `google.colab.drive`(마운트), `google.colab.userdata`
   (토큰), `IPython.display.Audio`(미리듣기), `%%bash`/`%%writefile` 매직. 작업
   디렉토리는 `--work-dir` 인자로 받고, HF 토큰은 `.env`의 `HF_TOKEN`으로 읽는다.
2. `RESPELL_MAP`·`apply_respelling()`을 옮겨오지 않았다. 2026-08-25에 영문 리스펠링
   (`Tteokbokki` → `Duck-bok-kee`)을 한글 표기(`떡볶이`)로 바꾸면서 저장소에서
   의도적으로 삭제한 코드다 — 근거는 `src/tts/infer.py` 상단 정정 항목과
   `eval/TTS_MODULE.md` 4절. 여기서 되살리면 걷어낸 방식이 학습 경로로 되돌아온다.
   대신 `build_dataset(text_transform=...)` 훅을 열어뒀고, 기본값은 원문 그대로다.
   ⚠️ 배포 중인 체크포인트는 리스펠링된 영문 라벨로 학습된 것이라, 기본값으로 새로
   학습하면 학습 텍스트 조건이 그 체크포인트와 달라진다.
3. instruct 문구와 모델 ID를 `src/tts/infer.py`에서 import한다. 노트북은 학습·추론
   양쪽에 같은 문자열을 복사해 뒀는데, 두 곳이 어긋나면 학습/추론 조건이 조용히
   갈라진다. 상수의 출처를 추론 모듈 한 곳으로 둔다.
4. 진행 로그를 `print`에서 `logging`으로 바꿨다(stdout 핸들러). AGENTS.md 로깅 원칙.

체크포인트 이력 — 노트북이 실행한 런은 `final_respelled_lr5e-6_ep40`(epoch-39)이고,
현재 배포본은 그 다음 런인 `instruct_trained_lr5e-6_ep40`(epoch-31)이다. 후자는 학습
스크립트를 고쳐 instruct를 학습에도 반영한 버전이다(`src/tts/infer.py` 참고). 이
모듈이 그대로 재현하는 것은 전자이며, 후자를 재현하려면 커뮤니티 패치 위에 얹은
instruct 학습 패치가 추가로 필요하다 — 그 패치는 노트북에 들어 있지 않다.
"""

import argparse
import csv
import json
import logging
import os
import random
import re
import subprocess
import time
import zipfile
from pathlib import Path

from src.tts.infer import INSTRUCT_MAP, TTS_ADAPTER_REPO_ID, TTS_BASE_MODEL_ID

logger = logging.getLogger(__name__)

# --- 외부 리포 (커뮤니티 패치) -----------------------------------------------
# 공식 Qwen3-TTS 저장소에는 LoRA 파인튜닝 스크립트가 없다. instavar 저장소의 패치를
# 공식 저장소에 적용해서 finetuning/sft_12hz_lora.py 등을 만들어 쓴다.
QWEN_REPO_URL = "https://github.com/QwenLM/Qwen3-TTS.git"
QWEN_REPO_COMMIT = "0c6a7cbb6c8421a46332f8c2434c7825c4c855ef"  # 패치가 맞물리는 시점 고정
PATCH_REPO_URL = "https://github.com/instavar/qwen3-tts-lora-finetuning.git"
TOKENIZER_MODEL_ID = "Qwen/Qwen3-TTS-Tokenizer-12Hz"

# --- 데이터셋 빌드 파라미터 ---------------------------------------------------
SEED = 42
VAL_RATIO = 0.1
# CAUTION 녹음이 전체의 8%뿐이라 학습 시 3배로 복제해 균형을 맞춘다.
OVERSAMPLE_CAUTION = 3
SAMPLE_RATE = 24000

# 녹음 라벨 CSV의 text 열이 잘려 들어간 2건. 원본 녹음을 듣고 사람이 채운 값이다.
TEXT_FIXES = {
    "케리어/케리어 80.m4a": "A traditional spicy beef soup Yukgaejang is widely enjoyed.",
    "케리어/케리어 215.m4a": "For a light seafood meal choose Mulhoe.",
}

# --- 학습 하이퍼파라미터 (5개 조합 비교에서 채택된 값) -------------------------
# 비교 기록: eval/TTS_MODULE.md 3절, eval/training_log.csv
DEFAULT_LR = "5e-6"
DEFAULT_EPOCHS = 40
DEFAULT_LORA_RANK = 16
DEFAULT_LORA_ALPHA = 32
DEFAULT_BATCH_SIZE = 4
DEFAULT_MIXED_PRECISION = "bf16"
# 학습 후 미리듣기 생성에만 쓰는 값. 배포 값은 infer.py의 LORA_SCALE(0.15)이며,
# 여기 0.3은 노트북이 미리듣기를 뽑을 때 쓴 값 그대로다.
PREVIEW_LORA_SCALE = 0.3

# 학습 직후 톤 구분이 실제로 들리는지 확인하는 고정 문장.
PREVIEW_TEXTS = {
    "GUIDE": (
        "Bibimbap is a colorful bowl of warm rice topped with seasoned "
        "vegetables, meat, and a fried egg."
    ),
    "CAUTION": (
        "Careful, this one is spicy! Tteokbokki is chewy rice cakes simmered "
        "in a thick, spicy chili sauce."
    ),
}

CSV_FIELDS = [
    "run_id", "epoch", "val_loss", "lr", "epochs_total", "lora_rank", "lora_alpha",
    "batch_size", "mixed_precision", "duration_sec", "returncode",
    "guide_sample_path", "caution_sample_path", "notes", "timestamp",
]

_EPOCH_LINE = re.compile(r"Epoch (\d+) \| Val Loss: ([\d.]+)")
_M4A_INDEX = re.compile(r"(\d+)\.m4a$")


# --- 1. 환경 준비 -------------------------------------------------------------

def unpack_recordings(zip_path: Path, raw_dir: Path) -> Path:
    """녹음 zip을 푼다. 이미 풀려 있으면 건너뛴다.

    zip이 Windows에서 만들어져 파일명이 cp949로 들어있는 경우가 있어, UTF-8 플래그
    (0x800)가 없는 항목은 cp437 → cp949로 되돌린다. 안 하면 한글 폴더명이 깨진다.
    """
    root = raw_dir / "제발"
    if (root / "naration_labels.csv").exists():
        logger.info("녹음 이미 해제됨: %s", root)
        return root

    raw_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            name = info.filename
            if not (info.flag_bits & 0x800):
                try:
                    name = name.encode("cp437").decode("cp949")
                except UnicodeDecodeError:
                    logger.warning("파일명 디코딩 실패, 원본 유지: %r", info.filename)
            target = raw_dir / name
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(target, "wb") as dst:
                dst.write(src.read())
    logger.info("압축 해제 완료: %s", root)
    return root


def clone_repos(work_dir: Path) -> None:
    """Qwen3-TTS 본체와 LoRA 패치 저장소를 받고, 패치를 적용한다."""
    qwen_dir = work_dir / "Qwen3-TTS"
    patch_dir = work_dir / "qwen3-tts-lora-finetuning"

    if not qwen_dir.exists():
        subprocess.run(["git", "clone", QWEN_REPO_URL, str(qwen_dir)], check=True)
        subprocess.run(["git", "checkout", QWEN_REPO_COMMIT], cwd=qwen_dir, check=True)
    if not patch_dir.exists():
        subprocess.run(["git", "clone", PATCH_REPO_URL, str(patch_dir)], check=True)

    if not (qwen_dir / "finetuning" / "sft_12hz_lora.py").exists():
        subprocess.run(
            ["bash", str(patch_dir / "scripts" / "apply_patches.sh")],
            cwd=work_dir, env={**os.environ, "QWEN_DIR": str(qwen_dir)}, check=True,
        )
    logger.info("리포 준비 완료: %s", qwen_dir)


def apply_upstream_fixes(work_dir: Path) -> None:
    """패치된 학습·추론 스크립트에 남아 있는 버그 4개를 고친다. 재실행 안전하다.

    커뮤니티 패치가 적용된 직후 상태에서 그대로 돌리면 실패하거나 기능이 빠지는
    지점들이다. 업스트림에 반영되면 이 함수는 통째로 없어져야 한다.
    """
    qwen_dir = work_dir / "Qwen3-TTS"
    sft_path = qwen_dir / "finetuning" / "sft_12hz_lora.py"
    infer_path = qwen_dir / "finetuning" / "infer_lora_custom_voice.py"
    infer_sh = work_dir / "qwen3-tts-lora-finetuning" / "scripts" / "run_lora_infer.sh"

    # 1. accelerate가 tensorboard 로그를 쓸 위치를 못 받아 학습 시작 시 죽는다.
    content = sft_path.read_text(encoding="utf-8")
    if "project_dir=args.output_model_path" not in content:
        patched, n = re.subn(
            r'(log_with="tensorboard",)(\s*\))',
            r"\1\n        project_dir=args.output_model_path,\2",
            content, count=1,
        )
        if n == 0:
            raise RuntimeError(f"패치 1 대상 코드를 못 찾음: {sft_path}")
        sft_path.write_text(patched, encoding="utf-8")
        logger.info("패치 1 적용: tensorboard project_dir")

    # 2. 추론 스크립트에 main() 호출이 빠져 있어 실행해도 아무 일도 안 일어난다.
    infer_src = infer_path.read_text(encoding="utf-8")
    if not infer_src.rstrip().endswith("main()"):
        with open(infer_path, "a", encoding="utf-8") as f:
            f.write("    main()\n")
        infer_src = infer_path.read_text(encoding="utf-8")
        logger.info("패치 2 적용: main() 호출")

    # 3. --instruct 인자가 없어 톤 조절(GUIDE/CAUTION)을 쓸 수 없다.
    if "--instruct" not in infer_src:
        lang_arg = '    parser.add_argument("--language", default="auto")\n'
        lang_pass = "        language=args.language,\n"
        if lang_arg not in infer_src or lang_pass not in infer_src:
            raise RuntimeError(f"패치 3 대상 코드를 못 찾음: {infer_path}")
        infer_src = infer_src.replace(
            lang_arg, lang_arg + '    parser.add_argument("--instruct", default="")\n'
        ).replace(lang_pass, lang_pass + "        instruct=args.instruct,\n")
        infer_path.write_text(infer_src, encoding="utf-8")
        logger.info("패치 3 적용: --instruct 인자")

    # 4. 셸 래퍼가 INSTRUCT를 넘겨주지 않아 3번 패치가 무용지물이 된다.
    sh_src = infer_sh.read_text(encoding="utf-8")
    if "INSTRUCT" not in sh_src:
        sh_src = sh_src.replace(
            'MAX_NEW_TOKENS="${MAX_NEW_TOKENS:-4096}"',
            'MAX_NEW_TOKENS="${MAX_NEW_TOKENS:-4096}"\nINSTRUCT="${INSTRUCT:-}"',
        ).replace(
            '  --output_wav "${OUT_WAV}"',
            '  --output_wav "${OUT_WAV}" \\\n  --instruct "${INSTRUCT}"',
        )
        infer_sh.write_text(sh_src, encoding="utf-8")
        logger.info("패치 4 적용: 셸 스크립트 INSTRUCT 전달")


def download_base_model(work_dir: Path) -> Path:
    """베이스 모델을 로컬에 내려받는다. 이미 있으면 건너뛴다."""
    from huggingface_hub import snapshot_download

    local_dir = work_dir / TTS_BASE_MODEL_ID.replace("/", os.sep)
    if (local_dir / "config.json").exists():
        logger.info("베이스 모델 이미 있음: %s", local_dir)
        return local_dir
    snapshot_download(repo_id=TTS_BASE_MODEL_ID, local_dir=str(local_dir))
    logger.info("베이스 모델 다운로드 완료: %s", local_dir)
    return local_dir


# --- 2. 학습 데이터 빌드 ------------------------------------------------------

def _load_label_csv(path: Path) -> list[dict]:
    # utf-8-sig: Excel에서 저장된 CSV에 BOM이 붙어 있다.
    with open(path, encoding="utf-8-sig") as f:
        return [row for row in csv.DictReader(f) if row.get("audio_path")]


def _convert_to_wav(src: Path, dst: Path) -> bool:
    """m4a 녹음을 학습용 wav(24kHz/mono/s16)로 변환한다. 이미 있으면 건너뛴다."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return True
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", str(src), "-ar", str(SAMPLE_RATE),
         "-ac", "1", "-sample_fmt", "s16", str(dst)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        logger.error("ffmpeg 변환 실패 %s: %s", src, result.stderr[-300:])
        return False
    return True


def build_dataset(raw_root: Path, data_dir: Path, text_transform=None) -> dict[str, Path]:
    """녹음과 라벨을 train/val jsonl로 만든다.

    text_transform: 학습 텍스트에 적용할 변환 함수. 기본값은 원문 그대로다.
        노트북은 여기서 영문 리스펠링을 적용했지만, 표기 방식이 한글로 바뀌면서
        저장소에서 삭제된 코드다(모듈 docstring 2번 항목 참고).

    분할은 (food_id, style) 그룹 단위로 하고 시드를 고정한다 — 같은 음식의 녹음이
    train/val 양쪽에 섞이면 val_loss가 실제보다 낙관적으로 나온다.
    """
    transform = text_transform or (lambda text: text)
    random.seed(SEED)

    style_by_food: dict[int, str] = {}
    with open(raw_root / "naration.txt", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        next(reader)  # 헤더
        for parts in reader:
            if parts:
                style_by_food[int(parts[1])] = parts[2].strip().upper()

    samples = []
    for row in _load_label_csv(raw_root / "naration_labels.csv"):
        food_id = int(_M4A_INDEX.search(row["audio_path"]).group(1))
        text = TEXT_FIXES.get(row["audio_path"], row["text"]).strip()
        samples.append({"audio_path": row["audio_path"], "text": transform(text),
                        "food_id": food_id, "kind": "narration"})
    for row in _load_label_csv(raw_root / "carry_labels.csv"):
        idx = int(_M4A_INDEX.search(row["audio_path"]).group(1))
        text = TEXT_FIXES.get(row["audio_path"], row["text"]).strip()
        # 케리어 녹음은 음식 하나당 5개씩 이어져 있다.
        samples.append({"audio_path": row["audio_path"], "text": transform(text),
                        "food_id": (idx - 1) // 5 + 1, "kind": "carry"})

    for s in samples:
        s["style"] = style_by_food.get(s["food_id"], "GUIDE")
    n_caution = sum(1 for s in samples if s["style"] == "CAUTION")
    logger.info("스타일 분포 — GUIDE %d / CAUTION %d (%.1f%%)",
                len(samples) - n_caution, n_caution, n_caution / len(samples) * 100)

    ok, failed = [], []
    for s in samples:
        dst = data_dir / "wav" / Path(s["audio_path"]).with_suffix(".wav")
        if _convert_to_wav(raw_root / s["audio_path"], dst):
            s["wav_path"] = str(dst)
            ok.append(s)
        else:
            failed.append(s["audio_path"])
    logger.info("wav 변환 성공 %d / 실패 %d", len(ok), len(failed))
    if failed:
        logger.warning("변환 실패 목록: %s", failed)
    samples = ok

    # 전 샘플이 같은 참조 음성을 쓴다 — 화자가 한 명이라 화자별로 나눌 게 없다.
    guide_narration = [s for s in samples if s["kind"] == "narration" and s["style"] == "GUIDE"]
    ref_audio = (guide_narration or samples)[0]["wav_path"]
    logger.info("ref_audio (전 샘플 공통) = %s", ref_audio)

    expanded = []
    for s in samples:
        expanded.extend([s] * (OVERSAMPLE_CAUTION if s["style"] == "CAUTION" else 1))

    by_group: dict[tuple, list] = {}
    for s in expanded:
        by_group.setdefault((s["food_id"], s["style"]), []).append(s)

    train, val = [], []
    for items in by_group.values():
        random.shuffle(items)
        n_val = max(1, round(len(items) * VAL_RATIO)) if len(items) > 1 else 0
        val.extend(items[:n_val])
        train.extend(items[n_val:])

    data_dir.mkdir(parents=True, exist_ok=True)
    written = {}
    for name, rows in [("train_raw.jsonl", train), ("val_raw.jsonl", val)]:
        path = data_dir / name
        with open(path, "w", encoding="utf-8") as f:
            for s in rows:
                f.write(json.dumps(
                    {"audio": s["wav_path"], "text": s["text"], "ref_audio": ref_audio},
                    ensure_ascii=False,
                ) + "\n")
        logger.info("%d행 기록 -> %s", len(rows), path)
        written[name.split("_")[0]] = path
    return written


def encode_audio_codes(work_dir: Path, data_dir: Path, device: str = "cuda:0") -> None:
    """오디오를 코덱 토큰으로 미리 변환한다. 학습 스크립트가 이 파일을 먹는다."""
    prepare = work_dir / "Qwen3-TTS" / "finetuning" / "prepare_data.py"
    for split in ("train", "val"):
        subprocess.run(
            ["python", str(prepare), "--device", device,
             "--tokenizer_model_path", TOKENIZER_MODEL_ID,
             "--input_jsonl", str(data_dir / f"{split}_raw.jsonl"),
             "--output_jsonl", str(data_dir / f"{split}_with_codes.jsonl")],
            cwd=work_dir, check=True,
        )
        logger.info("%s 코드 추출 완료", split)


# --- 3. 학습 ------------------------------------------------------------------

def _append_log_rows(log_csv: Path, rows: list[dict]) -> None:
    exists = log_csv.exists()
    log_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(log_csv, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerows(rows)


def _render_preview(work_dir: Path, base_model: Path, ckpt: Path,
                    style: str, out_wav: Path, lora_scale: float) -> bool:
    """학습된 체크포인트로 미리듣기 wav 하나를 만든다."""
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "QWEN_DIR": str(work_dir / "Qwen3-TTS"),
        "BASE_MODEL": str(base_model),
        "ADAPTER_DIR": str(ckpt),
        "LORA_SCALE": str(lora_scale),
        "ATTN_IMPL": "sdpa",
        "TEXT": PREVIEW_TEXTS[style],
        "INSTRUCT": INSTRUCT_MAP[style],
        "OUT_WAV": str(out_wav),
    }
    script = work_dir / "qwen3-tts-lora-finetuning" / "scripts" / "run_lora_infer.sh"
    result = subprocess.run(["bash", str(script)], cwd=work_dir, env=env,
                            capture_output=True, text=True)
    if result.returncode != 0:
        logger.error("미리듣기 생성 실패 (%s): %s", style, result.stderr[-500:])
        return False
    return True


def run_training(run_id: str, work_dir: Path, data_dir: Path, base_model: Path,
                 log_csv: Path, samples_dir: Path, *,
                 epochs: int = DEFAULT_EPOCHS, lr: str = DEFAULT_LR,
                 lora_rank: int = DEFAULT_LORA_RANK, lora_alpha: int = DEFAULT_LORA_ALPHA,
                 batch_size: int = DEFAULT_BATCH_SIZE,
                 mixed_precision: str = DEFAULT_MIXED_PRECISION,
                 lora_scale: float = PREVIEW_LORA_SCALE,
                 notes: str = "") -> tuple[int, Path, list[tuple[int, float]]]:
    """학습을 돌리고 에폭별 val_loss를 CSV에 남긴 뒤, 마지막 체크포인트로 미리듣기를 뽑는다.

    반환: (returncode, 출력 디렉토리, [(epoch, val_loss), ...])
    """
    output_dir = work_dir / f"output_{run_id}"
    env = {
        **os.environ,
        "QWEN_DIR": str(work_dir / "Qwen3-TTS"),
        "TRAIN_JSONL": str(data_dir / "train_with_codes.jsonl"),
        "VAL_JSONL": str(data_dir / "val_with_codes.jsonl"),
        "OUTPUT_DIR": str(output_dir),
        "LR": lr,
        "EPOCHS": str(epochs),
        "LORA_RANK": str(lora_rank),
        "LORA_ALPHA": str(lora_alpha),
        "BATCH_SIZE": str(batch_size),
        "MIXED_PRECISION": mixed_precision,
        "ATTN_IMPL": "sdpa",
    }
    script = work_dir / "qwen3-tts-lora-finetuning" / "scripts" / "run_lora_train.sh"

    rows: list[tuple[int, float]] = []
    start = time.time()
    # 학습 로그를 흘려보면서 에폭별 val_loss를 주워담는다. 스크립트가 몇 시간 돌기
    # 때문에 끝난 뒤 한꺼번에 읽으면 진행 상황을 볼 수 없다.
    proc = subprocess.Popen(["bash", str(script)], cwd=work_dir, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, bufsize=1)
    for line in proc.stdout:
        logger.info("%s", line.rstrip())
        m = _EPOCH_LINE.search(line)
        if m:
            rows.append((int(m.group(1)), float(m.group(2))))
    proc.wait()
    duration = time.time() - start

    preview_paths = {"GUIDE": "", "CAUTION": ""}
    if rows and proc.returncode == 0:
        ckpt = output_dir / f"checkpoint-epoch-{rows[-1][0]}"
        for style in ("GUIDE", "CAUTION"):
            out_wav = samples_dir / f"{run_id}_{style.lower()}.wav"
            if _render_preview(work_dir, base_model, ckpt, style, out_wav, lora_scale):
                preview_paths[style] = str(out_wav)

    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    _append_log_rows(log_csv, [{
        "run_id": run_id, "epoch": epoch, "val_loss": val_loss, "lr": lr,
        "epochs_total": epochs, "lora_rank": lora_rank, "lora_alpha": lora_alpha,
        "batch_size": batch_size, "mixed_precision": mixed_precision,
        "duration_sec": round(duration, 1), "returncode": proc.returncode,
        "guide_sample_path": preview_paths["GUIDE"],
        "caution_sample_path": preview_paths["CAUTION"],
        "notes": notes, "timestamp": timestamp,
    } for epoch, val_loss in rows])

    final = rows[-1][1] if rows else "N/A"
    logger.info("[%s] 종료 (rc=%s, %.1f초, final val_loss=%s)",
                run_id, proc.returncode, duration, final)
    if rows:
        best_epoch, best_loss = min(rows, key=lambda r: r[1])
        logger.info("최저 val_loss: epoch %d (%.4f)", best_epoch, best_loss)
    return proc.returncode, output_dir, rows


# --- 4. 어댑터 업로드 ---------------------------------------------------------

def upload_adapter(ckpt: Path, repo_id: str = TTS_ADAPTER_REPO_ID,
                   commit_message: str = "Update LoRA adapter") -> str:
    """학습된 어댑터를 Hugging Face에 올린다. 토큰은 .env의 HF_TOKEN에서 읽는다."""
    from huggingface_hub import HfApi

    token = os.environ.get("HF_TOKEN")
    if not token:
        raise RuntimeError("HF_TOKEN이 없다 — .env에 추가하세요 (.env.example 참고)")
    api = HfApi(token=token)
    api.create_repo(repo_id=repo_id, repo_type="model", exist_ok=True, private=False)
    api.upload_folder(folder_path=str(ckpt), repo_id=repo_id, repo_type="model",
                      commit_message=commit_message)
    url = f"https://huggingface.co/{repo_id}"
    logger.info("업로드 완료: %s", url)
    return url


# --- 실행 ---------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Qwen3-TTS LoRA 파인튜닝")
    parser.add_argument("--zip-path", type=Path, required=True,
                        help="녹음 원본 zip 경로")
    parser.add_argument("--work-dir", type=Path, required=True,
                        help="리포·모델·학습 산출물을 두는 작업 디렉토리")
    parser.add_argument("--run-id", default="lora_run",
                        help="학습 로그 CSV에서 이 런을 식별할 이름")
    parser.add_argument("--epochs", type=int, default=DEFAULT_EPOCHS)
    parser.add_argument("--lr", default=DEFAULT_LR)
    parser.add_argument("--lora-rank", type=int, default=DEFAULT_LORA_RANK)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--notes", default="")
    parser.add_argument("--upload", action="store_true",
                        help="학습 후 마지막 체크포인트를 Hugging Face에 올린다")
    args = parser.parse_args()

    # 로그는 stdout으로 — 셸 접근이 없는 환경에서도 바로 보이게 (AGENTS.md 로깅 원칙).
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    work_dir: Path = args.work_dir.resolve()
    data_dir = work_dir / "data"
    work_dir.mkdir(parents=True, exist_ok=True)

    raw_root = unpack_recordings(args.zip_path, work_dir / "raw")
    clone_repos(work_dir)
    apply_upstream_fixes(work_dir)
    base_model = download_base_model(work_dir)

    build_dataset(raw_root, data_dir)
    encode_audio_codes(work_dir, data_dir)

    rc, output_dir, rows = run_training(
        run_id=args.run_id, work_dir=work_dir, data_dir=data_dir,
        base_model=base_model, log_csv=work_dir / "training_log.csv",
        samples_dir=work_dir / "samples",
        epochs=args.epochs, lr=args.lr, lora_rank=args.lora_rank,
        batch_size=args.batch_size, notes=args.notes,
    )
    if rc != 0:
        raise SystemExit(f"학습 실패 (rc={rc})")

    if args.upload:
        upload_adapter(output_dir / f"checkpoint-epoch-{rows[-1][0]}",
                       commit_message=f"Adapter from run {args.run_id}")


if __name__ == "__main__":
    main()
