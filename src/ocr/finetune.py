"""OCR 파인튜닝 — 1안 전체학습 / 2안 LoRA·QLoRA / 3안 mobile+양자화.

세 가지 안 중 무엇을 쓸지와 전환 기준은 docs/specs/ocr-finetuning.md에서 정한다.
학습할 때만 실행한다.
"""

import subprocess
from pathlib import Path

import yaml

# 아래 두 경로를 원격 데스크톱 실제 위치에 맞게 수정하세요
DATASET_DIR = Path("OCR_finetune_data").resolve()
PADDLEX_REPO_DIR = Path("PaddleX").resolve()  # git clone한 위치

BASE_CONFIG = {
    "Global": {
        "model": "korean_PP-OCRv5_mobile_rec",
        "mode": "train",
        "dataset_dir": str(DATASET_DIR),
        "device": "gpu:0",
        "output": "output",
    },
    "CheckDataset": {
        "convert": {"enable": False, "src_dataset_type": None},
        "split": {"enable": False, "train_percent": None, "val_percent": None},
    },
    "Train": {
        "epochs_iters": 20,
        "batch_size": 8,
        "learning_rate": 0.001,
        "pretrain_weight_path": "https://paddle-model-ecology.bj.bcebos.com/paddlex/official_pretrained_model/korean_PP-OCRv5_mobile_rec_pretrained.pdparams",
        "resume_path": None,
        "log_interval": 20,
        "eval_interval": 1,
        "save_interval": 1,
    },
    "Evaluate": {
        "weight_path": "output/best_accuracy/best_accuracy.pdparams",
        "log_interval": 1,
    },
}


def write_config(path: Path = Path("finetune_config.yaml")) -> Path:
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(BASE_CONFIG, f, allow_unicode=True, sort_keys=False)
    return path


def run_training(config_path: Path):
    subprocess.run(
        [
            "python", str(PADDLEX_REPO_DIR / "main.py"),
            "-c", str(config_path),
            "-o", "Global.mode=train",
            "-o", f"Global.dataset_dir={DATASET_DIR}",
        ],
        check=True,
    )


if __name__ == "__main__":
    config_path = write_config()
    print(f"설정 파일 생성됨: {config_path}")
    run_training(config_path)