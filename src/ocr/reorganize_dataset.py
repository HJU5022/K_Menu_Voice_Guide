"""OCR 학습 데이터 폴더를 PaddleOCR 학습 스크립트가 기대하는 모양으로 한 번 정리한다.

`src/ocr/prepare_dataset.py`가 AI Hub 원본을 "이미지경로<TAB>정답텍스트" 형식으로 바꿔주는
데까지 하고, 이 스크립트가 그 결과를 **학습을 돌리기 직전 배치**로 옮긴다. 두 단계를 나눈
이유는 앞 단계가 라벨 내용을 만드는 일이고, 이 단계는 파일을 어느 폴더에 어떤 이름으로 두느냐만
바꾸는 일이라서다 — 라벨을 다시 만들지 않고 폴더 배치만 다시 하고 싶을 때가 있다.

바뀌는 것은 세 가지다.

1. `train_images/`·`val_images/`로 나뉘어 있던 이미지를 `images/` 한 곳으로 모은다.
   PaddleOCR 학습 설정은 이미지 루트를 하나만 받으므로, 학습/검증을 폴더로 가르면
   같은 설정에서 둘을 함께 못 읽는다.
2. 라벨 파일 안의 경로를 `images/파일명`으로 다시 쓴다. 1번에서 이미지를 옮겼으니
   라벨이 가리키는 경로도 같이 안 고치면 학습이 첫 줄부터 파일을 못 찾는다.
3. `custom_dict.txt`를 `dict.txt`라는 이름으로 한 벌 더 만든다. 학습 설정이
   `dict.txt`라는 이름으로 사전을 찾기 때문이다(사전 내용은 그대로다).

**1회성 스크립트다.** 서비스 실행 경로에 들어가지 않는다 — 데이터를 처음 준비할 때만
사람이 손으로 한 번 돌린다. 절차 전체는 `data/README.md` 2절을 참고할 것.

실행:
    python -m src.ocr.reorganize_dataset
"""

import shutil
from pathlib import Path

# 정리 대상 폴더. 데이터를 받아둔 위치에 맞게 고쳐서 쓴다.
# (인자로 받지 않는 이유: 한 번 돌리고 마는 스크립트라 CLI를 붙일 값어치가 없었다)
DATA_DIR = Path("OCR_finetune_data")


def main(data_dir: Path = DATA_DIR) -> None:
    """위 세 가지 정리를 순서대로 수행한다. 자세한 이유는 파일 맨 위 설명 참고."""
    images_dir = data_dir / "images"
    images_dir.mkdir(exist_ok=True)

    for split, old_folder in [("train", "train_images"), ("val", "val_images")]:
        # 이미지를 옮기지 않고 복사(copy)한다 — 중간에 잘못돼도 원본이 남아 있어야
        # 처음부터 다시 돌릴 수 있다. 데이터가 39,000장이라 다시 받는 비용이 크다.
        src_folder = data_dir / old_folder
        for img_path in src_folder.glob("*.jpg"):
            shutil.copy(img_path, images_dir / img_path.name)

        # 라벨 파일의 경로 칸만 새 위치로 다시 쓴다. 정답 텍스트 칸은 손대지 않는다 —
        # 음식 이름에 탭이 들어갈 일은 없지만, split("\t", 1)로 첫 탭에서만 잘라
        # 뒤쪽 텍스트가 통째로 보존되게 한다.
        old_gt = data_dir / f"rec_gt_{split}.txt"
        new_gt = data_dir / f"{split}.txt"
        with open(old_gt, encoding="utf-8") as f_in, open(new_gt, "w", encoding="utf-8") as f_out:
            for line in f_in:
                path, text = line.rstrip("\n").split("\t", 1)
                filename = path.split("/")[-1]
                f_out.write(f"images/{filename}\t{text}\n")

    shutil.copy(data_dir / "custom_dict.txt", data_dir / "dict.txt")

    print("정리 완료:", data_dir)
    print("images/ 안 파일 수:", len(list(images_dir.glob("*.jpg"))))


if __name__ == "__main__":
    main()
