import shutil
from pathlib import Path

DATA_DIR = Path("OCR_finetune_data")  # 옮긴 폴더 경로에 맞게 수정

images_dir = DATA_DIR / "images"
images_dir.mkdir(exist_ok=True)

for split, old_folder in [("train", "train_images"), ("val", "val_images")]:
    src_folder = DATA_DIR / old_folder
    for img_path in src_folder.glob("*.jpg"):
        shutil.copy(img_path, images_dir / img_path.name)

    old_gt = DATA_DIR / f"rec_gt_{split}.txt"
    new_gt = DATA_DIR / f"{split}.txt"
    with open(old_gt, encoding="utf-8") as f_in, open(new_gt, "w", encoding="utf-8") as f_out:
        for line in f_in:
            path, text = line.rstrip("\n").split("\t", 1)
            filename = path.split("/")[-1]
            f_out.write(f"images/{filename}\t{text}\n")

shutil.copy(DATA_DIR / "custom_dict.txt", DATA_DIR / "dict.txt")

print("정리 완료:", DATA_DIR)
print("images/ 안 파일 수:", len(list(images_dir.glob("*.jpg"))))
