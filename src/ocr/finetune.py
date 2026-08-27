"""OCR 파인튜닝 — 1안 전체학습 / 2안 LoRA·QLoRA / 3안 mobile+양자화.

세 가지 안 중 무엇을 쓸지와 전환 기준은 docs/specs/ocr-finetuning.md에서 정한다.
학습할 때만 실행한다. 배포 경로에는 들어가지 않는다.

**이 파일이 직접 학습하지는 않는다.** 학습은 PaddleX가 한다. 여기서 하는 일은 두 가지뿐이다.

1. 학습 설정을 yaml 파일로 써낸다(`write_config`)
2. 그 설정으로 PaddleX를 자식 프로세스로 실행한다(`run_training`)

설정을 파이썬 dict로 들고 있다가 파일로 내보내는 이유는, yaml을 손으로 고치다 보면
어떤 값으로 학습했는지가 기록에 안 남기 때문이다. 값이 코드에 있으면 git이 변경 이력을
대신 남겨준다.

실행 전에 아래 `DATASET_DIR`·`PADDLEX_REPO_DIR` 두 경로를 자기 컴퓨터에 맞게 고쳐야 한다.
"""

import subprocess
from pathlib import Path

import yaml

# 아래 두 경로를 원격 데스크톱 실제 위치에 맞게 수정하세요
DATASET_DIR = Path("OCR_finetune_data").resolve()
PADDLEX_REPO_DIR = Path("PaddleX").resolve()  # git clone한 위치

# PaddleX가 요구하는 설정 구조 그대로다. 값의 근거는 아래 주석과
# docs/specs/ocr-finetuning.md에 있다.
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
        # 매 에폭 검증하고 매 에폭 저장한다(eval_interval·save_interval = 1). 학습이
        # 길어서, 중간에 끊기거나 과적합이 시작돼도 가장 좋았던 지점으로 되돌아갈 수
        # 있어야 하기 때문이다.
        "epochs_iters": 20,
        "batch_size": 8,          # 12GB VRAM에 맞춘 값 — 키우면 메모리 부족으로 죽는다
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
    """위 설정을 yaml 파일로 써내고 그 경로를 돌려준다.

    `allow_unicode=True`는 한글 경로가 유니코드 이스케이프 꼴로 깨져 나가지 않게 한다.
    `sort_keys=False`는 위 dict에 적은 순서를 그대로 유지한다 — 알파벳순으로 섞이면
    사람이 읽기 어렵고, 원본 PaddleX 예제와 대조하기도 힘들어진다.
    """
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(BASE_CONFIG, f, allow_unicode=True, sort_keys=False)
    return path


def run_training(config_path: Path):
    """PaddleX를 자식 프로세스로 띄워 학습을 시작한다.

    yaml에 이미 들어 있는 값을 `-o`로 한 번 더 넘기는 이유는, PaddleX가 명령줄 값을
    파일보다 우선하기 때문이다. 예전 설정 파일이 남아 있어도 이번에 의도한 경로로
    학습되도록 못 박는 것이다.

    `check=True`라서 학습이 실패하면 여기서 예외가 난다 — 실패했는데 "끝났다"고
    표시되면 잘못된 체크포인트를 그대로 쓰게 된다.
    """
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