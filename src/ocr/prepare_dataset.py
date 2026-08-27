"""AI Hub 라벨을 PaddleOCR 학습 포맷으로 변환하고 커스텀 딕셔너리를 만든다.

학습할 때만 실행한다. 배포 경로에는 들어가지 않는다.
사용법은 data/README.md 참고.

**하는 일 세 가지.**

1. AI Hub 원본은 "메뉴판 사진 한 장 + 그 안 글자들의 좌표·정답" 형태다. 인식 모델(rec)은
   글자 한 덩어리만 담긴 작은 이미지로 학습하므로, 좌표를 따라 사진을 **잘라낸다**.
2. 잘라낸 조각과 정답 텍스트를 `이미지경로<TAB>정답` 한 줄씩으로 적는다(PaddleOCR 형식).
3. 그 과정에서 본 모든 글자를 모아 **커스텀 딕셔너리**를 만든다. 모델이 고를 수 있는 글자
   후보를 실제로 나오는 것만으로 좁히면, 헷갈릴 선택지가 줄어 정확도가 올라간다.

원본은 zip 안에 든 채로 읽는다 — 39,000장을 풀어놓으면 디스크가 몇 배로 든다.
"""

import json
import os
import random
import zipfile
from collections import Counter

import cv2
import numpy as np
from dotenv import load_dotenv

load_dotenv()
    
RAW_ROOT = os.environ["OCR_RAW_DATA_ROOT"]
OUT_DIR = "data/processed"

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
    """글자 상자 하나를 사진에서 잘라낸다. 상자보다 조금 넓게 잘라준다.

    좌표가 픽셀이 아니라 **퍼센트**로 들어온다(AI Hub 라벨 형식). 사진 크기가 제각각이라
    비율로 적어둔 것이므로, 실제 픽셀로 바꾸려면 이 사진의 폭·높이를 곱해야 한다.

    `pad_ratio`만큼 여유를 두고 자르는 이유는, 상자에 딱 맞춰 자르면 글자의 끝부분(받침의
    아래, 획의 삐침)이 잘려 나가기 때문이다. 잘린 글자로 학습하면 모델이 온전한 글자를
    못 알아본다.

    상자가 사진 밖으로 나가거나 크기가 0이면 None을 돌려주고, 호출부가 그 조각을 건너뛴다.
    """
    h, w = img.shape[:2]
    x1 = x_pct / 100 * w
    y1 = y_pct / 100 * h
    bw = w_pct / 100 * w
    bh = h_pct / 100 * h
    pad_x = bw * pad_ratio
    pad_y = bh * pad_ratio
    # x1을 pad_x만큼 앞으로 당겼으므로, 끝점에 2*pad_x를 더해야 양쪽에 pad_x씩 남는다.
    # (x1이 이미 당겨진 값이라는 점에 주의 — 원래 좌표 기준으로는 +pad_x다.)
    x1 = max(0, int(x1 - pad_x))
    y1 = max(0, int(y1 - pad_y))
    x2 = min(w, int(x1 + bw + 2 * pad_x))
    y2 = min(h, int(y1 + bh + 2 * pad_y))
    if x2 <= x1 or y2 <= y1:
        return None
    return img[y1:y2, x1:x2]


def process_split(split, per_region_limit, regions_to_run):
    """한 갈래(train 또는 val)를 지역별로 훑어 크롭 이미지와 라벨 파일을 만든다.

    지역마다 상한(`per_region_limit`)을 두고 **무작위로 섞어서** 뽑는다. 앞에서부터
    순서대로 3,000장을 가져오면 파일명 순서에 몰린 특정 가게·특정 메뉴판만 학습하게 된다.

    돌려주는 값은 (본 글자들의 빈도, 만든 조각 수)다. 글자 빈도는 딕셔너리를 만드는 데 쓴다.
    """
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

                    # 라벨 파일과 사진 파일은 이름 규칙으로 짝지어진다(`-tf.jpg` 접미사).
                    # 짝이 없는 라벨이 실제로 섞여 있어서, 없으면 조용히 건너뛴다.
                    file_stem = data["meta"]["file_name"].rsplit(".", 1)[0]
                    source_name = f"/{file_stem}-tf.jpg"
                    if source_name not in source_names:
                        continue

                    with source_zf.open(source_name) as f:
                        img_bytes = f.read()
                    # zip에서 읽은 바이트를 파일로 저장하지 않고 바로 이미지로 푼다.
                    # cv2.imread는 경로만 받으므로 imdecode를 쓴다.
                    img_array = np.frombuffer(img_bytes, dtype=np.uint8)
                    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                    if img is None:   # 깨진 파일 — 건너뛴다
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
    """모델이 고를 수 있는 글자 목록(커스텀 딕셔너리)을 만든다.

    학습·검증 데이터에서 실제로 본 글자에 더해, **등록 음식 50개의 이름 글자를 반드시
    넣는다.** 서비스가 맞혀야 하는 것이 그 50개인데, 우연히 표본에 안 잡힌 글자가 하나라도
    빠지면 그 글자가 든 음식은 아예 인식될 수 없다.

    정렬해서 쓰는 이유는 매번 같은 순서를 얻기 위해서다 — 순서가 바뀌면 글자↔번호 대응이
    달라져 예전 체크포인트를 못 쓴다.
    """
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
    # 라벨 파일을 빈 채로 새로 만든다. 아래 process_split이 "a"(이어쓰기)로 열기 때문에,
    # 지우지 않으면 다시 돌릴 때마다 앞선 실행의 줄 위에 계속 쌓인다.
    open(f"{OUT_DIR}/rec_gt_train.txt", "w").close()
    open(f"{OUT_DIR}/rec_gt_val.txt", "w").close()

    train_chars, train_total = process_split("train", PER_REGION_TRAIN, REGIONS)
    print(f"\n=== train 전체 완료: {train_total}개 ===")

    val_chars, val_total = process_split("val", PER_REGION_VAL, REGIONS)
    print(f"=== val 전체 완료: {val_total}개 ===")

    dict_chars = build_dictionary(train_chars, val_chars)
    print(f"\n=== 커스텀 딕셔너리 완료: 고유 문자 {len(dict_chars)}개 ===")
    print(f"저장 위치: {OUT_DIR}")
