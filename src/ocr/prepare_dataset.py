"""AI Hub 라벨을 PaddleOCR 학습 포맷으로 변환하고 커스텀 딕셔너리를 만든다.

학습할 때만 실행한다. 배포 경로에는 들어가지 않는다.
사용법은 data/README.md 참고.
"""

import json
import os
import random
import zipfile
from collections import Counter

import cv2
import numpy as np

RAW_ROOT = "/Users/jeong-un/Downloads/222.관광 음식메뉴판 데이터/01-1.정식개방데이터"
OUT_DIR = "/Users/jeong-un/Downloads/OCR_finetune_data"

REGIONS = [
    ("01. 서울", "SL"), ("02. 부산", "BS"), ("03. 대구", "DG"), ("04. 인천", "IC"),
    ("05. 광주", "GJ"), ("06. 대전", "DJ"), ("07. 울산", "US"), ("08. 경기", "GG"),
    ("09. 강원", "KW"), ("10. 충청", "CC"), ("11. 전라", "JR"), ("12. 경상", "KS"),
    ("13. 제주", "JJ"),
]

FOOD_NAMES = [
    "비빔밥", "불고기", "떡볶이", "김치찌개", "된장찌개", "삼겹살", "갈비탕", "물냉면",
    "비빔냉면", "잡채", "김밥", "순두부찌개", "삼계탕", "제육볶음", "곱창전골", "육개장",
    "감자탕", "칼국수", "잔치국수", "순대", "족발", "보쌈", "낙지볶음", "아귀찜", "매운탕",
    "갈비찜", "해물파전", "갈비", "콩국수", "육회", "간장게장", "양념게장", "닭갈비", "찜닭",
    "김치볶음밥", "오징어볶음", "순댓국", "콩나물국밥", "만두", "비빔국수", "떡국", "수제비",
    "물회", "두부김치", "계란찜", "감자전", "떡갈비", "청국장", "갈치조림", "동태찌개",
]

PER_REGION_TRAIN = 3000
PER_REGION_VAL = 500


def crop_text_region(img, x_pct, y_pct, w_pct, h_pct, pad_ratio=0.1):
    h, w = img.shape[:2]
    x1 = x_pct / 100 * w
    y1 = y_pct / 100 * h
    bw = w_pct / 100 * w
    bh = h_pct / 100 * h
    pad_x = bw * pad_ratio
    pad_y = bh * pad_ratio
    x1 = max(0, int(x1 - pad_x))
    y1 = max(0, int(y1 - pad_y))
    x2 = min(w, int(x1 + bw + 2 * pad_x))
    y2 = min(h, int(y1 + bh + 2 * pad_y))
    if x2 <= x1 or y2 <= y1:
        return None
    return img[y1:y2, x1:x2]


def process_split(split, per_region_limit, regions_to_run):
    label_prefix = "TL_" if split == "train" else "VL_"
    source_prefix = "TS_" if split == "train" else "VS_"
    label_dir = f"{RAW_ROOT}/{'Training' if split == 'train' else 'Validation'}/02.라벨링데이터"
    source_dir = f"{RAW_ROOT}/{'Training' if split == 'train' else 'Validation'}/01.원천데이터"

    out_img_dir = f"{OUT_DIR}/{split}_images"
    os.makedirs(out_img_dir, exist_ok=True)
    gt_path = f"{OUT_DIR}/rec_gt_{split}.txt"

    all_chars = Counter()
    total = 0

    with open(gt_path, "a", encoding="utf-8") as gt:
        for region_full, region_code in regions_to_run:
            label_zip_path = f"{label_dir}/{label_prefix}{region_full}.zip"
            source_zip_path = f"{source_dir}/{source_prefix}{region_full}.zip"

            with zipfile.ZipFile(label_zip_path) as label_zf, zipfile.ZipFile(source_zip_path) as source_zf:
                source_names = set(source_zf.namelist())
                label_names = [n for n in label_zf.namelist() if n.endswith(".json")]
                random.shuffle(label_names)

                count = 0
                for label_name in label_names:
                    if count >= per_region_limit:
                        break
                    with label_zf.open(label_name) as f:
                        data = json.load(f)

                    file_stem = data["meta"]["file_name"].rsplit(".", 1)[0]
                    source_name = f"/{file_stem}-tf.jpg"
                    if source_name not in source_names:
                        continue

                    with source_zf.open(source_name) as f:
                        img_bytes = f.read()
                    img_array = np.frombuffer(img_bytes, dtype=np.uint8)
                    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                    if img is None:
                        continue

                    for ann in data.get("annotations", []):
                        if count >= per_region_limit:
                            break
                        ocr = ann.get("ocr", {})
                        text = ocr.get("text", "").strip()
                        if not text:
                            continue
                        crop = crop_text_region(img, ocr["x"], ocr["y"], ocr["width"], ocr["height"])
                        if crop is None or crop.size == 0:
                            continue

                        crop_filename = f"{region_code}_{split}_{count:06d}.jpg"
                        cv2.imwrite(f"{out_img_dir}/{crop_filename}", crop)
                        gt.write(f"{split}_images/{crop_filename}\t{text}\n")
                        all_chars.update(text)
                        count += 1

                print(f"[{split}] {region_full}: {count}개 크롭 완료")
                total += count

    return all_chars, total


def build_dictionary(train_chars, val_chars):
    all_chars = Counter()
    all_chars.update(train_chars)
    all_chars.update(val_chars)
    for name in FOOD_NAMES:
        all_chars.update(name)

    dict_chars = sorted(all_chars.keys())
    with open(f"{OUT_DIR}/custom_dict.txt", "w", encoding="utf-8") as f:
        for ch in dict_chars:
            f.write(ch + "\n")
    return dict_chars


if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    open(f"{OUT_DIR}/rec_gt_train.txt", "w").close()
    open(f"{OUT_DIR}/rec_gt_val.txt", "w").close()

    train_chars, train_total = process_split("train", PER_REGION_TRAIN, REGIONS)
    print(f"\n=== train 전체 완료: {train_total}개 ===")

    val_chars, val_total = process_split("val", PER_REGION_VAL, REGIONS)
    print(f"=== val 전체 완료: {val_total}개 ===")

    dict_chars = build_dictionary(train_chars, val_chars)
    print(f"\n=== 커스텀 딕셔너리 완료: 고유 문자 {len(dict_chars)}개 ===")
    print(f"저장 위치: {OUT_DIR}")
