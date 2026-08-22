"""매칭기의 **오탐**을 잰다 — 기존 지표가 보지 못하던 쪽.

## 왜 필요했나

여태 쓰던 지표(`eval/measure_ocr.py`의 `match_recall`, 그리고 문서의 97.22%)는
"올바른 음식 후보를 뽑아냈나"만 본다. **"사진에 없는 음식을 내놓지는 않았나"는
아무도 재지 않았다.** 그 사각지대 때문에, 재현율이 99%인 상태로 정밀도가 46%까지
떨어져 있는 걸 오래 모르고 있었다(2026-08-23 실측).

실제 증상: `여름막국수`가 적힌 메뉴판에서 등록되지 않은 `막국수` 대신 `칼국수`와
`콩국수`가 후보로 올라왔다. 3글자 이름은 두 글자만 맞아도 80점이 나오기 때문이다.

## 데이터

AI Hub "관광 음식메뉴판 데이터"(222) 검증셋. 라벨 JSON에
`annotations[].menu_information.ko`(메뉴판에 인쇄된 이름)와
`annotations[].ocr.text`(그 자리에서 읽히는 글자)가 들어 있어 정답으로 쓸 수 있다.

## 정오 판정

후보로 나온 등록 음식 이름이 **그 메뉴판의 어떤 메뉴명에든 부분 문자열로 들어 있으면**
정답으로 본다(`김치찌개` ⊂ `쌈싸먹는김치찌개`). 어디에도 없으면 오탐이다.

## 두 가지 모드

    --source label   라벨의 정답 글자를 그대로 입력 (OCR 오류 배제, 매칭 로직만 평가)
    --source ocr     실제 이미지에 OCR을 돌려 입력 (실사용에 가까움, 느림)

`--source ocr`은 OCR 결과를 `--cache`에 저장해두고 재사용한다. 임계값만 바꿔가며
다시 재는 일이 잦은데, 그때마다 OCR을 다시 돌리면 장당 8초씩 낭비된다.

## 실행 예 (저장소 루트에서)

    python eval/measure_match_precision.py --source label \\
        --labels "~/Downloads/222.관광 음식메뉴판 데이터/.../02.라벨링데이터_풀린곳" --limit 400

    python eval/measure_match_precision.py --source ocr \\
        --labels <라벨폴더> --images <원천이미지폴더> --limit 100 \\
        --cache eval/.match_precision_ocr_cache.json
"""

import argparse
import glob
import json
import os
import random
from pathlib import Path

import src.ocr.match as match
from src.db.cache import get_foods

# 스윕할 임계값. 실측에서 80과 85 사이에 절벽이 있어 그 구간을 촘촘히 본다.
THRESHOLDS = (55, 60, 65, 70, 75, 80, 85, 90)


def load_truth(label_path: Path) -> list[str] | None:
    """라벨 하나에서 메뉴명 목록을 꺼낸다. 메뉴 항목이 없으면 None."""
    try:
        data = json.loads(label_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    names = []
    for annotation in data.get("annotations", []):
        name = ((annotation.get("menu_information") or {}).get("ko") or "").strip()
        if name:
            names.append(name.replace(" ", ""))
    return names or None


def load_label_text(label_path: Path) -> str:
    """라벨에 적힌 글자를 이어붙여 '완벽한 OCR 결과'를 만든다."""
    data = json.loads(label_path.read_text(encoding="utf-8"))
    bits = []
    for annotation in data.get("annotations", []):
        text = ((annotation.get("ocr") or {}).get("text") or "").strip()
        if text:
            bits.append(text)
    return " ".join(bits)


def collect_from_labels(label_dir: str, limit: int) -> list[tuple[str, list[str]]]:
    paths = sorted(glob.glob(os.path.join(label_dir, "*.json")))
    random.shuffle(paths)
    cases = []
    for path in paths:
        if len(cases) >= limit:
            break
        names = load_truth(Path(path))
        if not names:
            continue
        text = load_label_text(Path(path))
        if text:
            cases.append((text, names))
    return cases


def collect_from_images(label_dir: str, image_dir: str, limit: int, cache_path: Path):
    """실제 OCR을 돌린다. 이미 캐시에 있는 이미지는 건너뛴다."""
    # 무거운 import라 이 모드에서만 한다.
    from src.ocr.infer import group_boxes_into_rows, recognize_boxes_with_mapping

    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    images = sorted(glob.glob(os.path.join(image_dir, "*.jpg")))
    random.shuffle(images)

    for index, image in enumerate(images[:limit], 1):
        stem = Path(image).stem
        if stem in cache:
            continue
        # 원천 파일명은 "-tf"가 붙어 있고 라벨 파일명에는 없다.
        label = Path(label_dir) / (stem.replace("-tf", "") + ".json")
        names = load_truth(label) if label.exists() else None
        if not names:
            continue
        try:
            boxes, _mapping = recognize_boxes_with_mapping(image)
        except Exception as error:  # 한 장이 깨져도 배치 전체를 멈추지 않는다
            print("[%d] %s OCR 실패: %s" % (index, stem, error), flush=True)
            continue
        cache[stem] = {"text": " ".join(group_boxes_into_rows(boxes)).strip(), "names": names}
        cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        print("[%d/%d] %s" % (index, min(limit, len(images)), stem), flush=True)

    return [(entry["text"], entry["names"]) for entry in cache.values()]


def sweep(cases: list[tuple[str, list[str]]]) -> None:
    registered = [food["name_kr"] for food in get_foods()]
    original = match.MATCH_THRESHOLD

    print("\n메뉴판 %d장" % len(cases))
    print("%6s %8s %8s %7s %7s" % ("임계값", "정밀도", "재현율", "오탐", "놓침"))
    try:
        for threshold in THRESHOLDS:
            match.MATCH_THRESHOLD = threshold
            hit = wrong = missed = 0
            for text, names in cases:
                truth = {name for name in registered if any(name in menu for menu in names)}
                got = {c["name_kr"] for c in match.match_food_candidates(text)}
                hit += len(truth & got)
                wrong += len(got - truth)
                missed += len(truth - got)
            precision = hit / (hit + wrong) if hit + wrong else 0.0
            recall = hit / (hit + missed) if hit + missed else 0.0
            mark = "  ← 현재" if threshold == original else ""
            print("%6d %7.1f%% %7.1f%% %7d %7d%s" % (
                threshold, precision * 100, recall * 100, wrong, missed, mark))
    finally:
        match.MATCH_THRESHOLD = original


def report_score_buckets(cases: list[tuple[str, list[str]]]) -> None:
    """점수대별 정탐/오탐 분포 — 임계값을 어디에 둘지 판단하는 근거.

    실측에서 정탐의 93%가 100점이었고 80점대는 정탐 1 : 오탐 38이었다. 이 표가
    "유사도 관용이 값을 못 하고 있다"는 결론의 직접 근거다.
    """
    registered = [food["name_kr"] for food in get_foods()]
    original = match.MATCH_THRESHOLD
    match.MATCH_THRESHOLD = min(THRESHOLDS)
    buckets: dict[int, list[int]] = {}
    try:
        for text, names in cases:
            truth = {name for name in registered if any(name in menu for menu in names)}
            for candidate in match.match_food_candidates(text):
                bucket = (candidate["score"] // 5) * 5
                counts = buckets.setdefault(bucket, [0, 0])
                counts[0 if candidate["name_kr"] in truth else 1] += 1
    finally:
        match.MATCH_THRESHOLD = original

    print("\n점수 구간별 정탐/오탐")
    print("%10s %7s %7s %9s" % ("점수", "정탐", "오탐", "정탐비율"))
    for bucket in sorted(buckets, reverse=True):
        ok, bad = buckets[bucket]
        print("%5d~%-4d %7d %7d %8.0f%%" % (bucket, bucket + 4, ok, bad, ok / (ok + bad) * 100))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=("label", "ocr"), default="label")
    parser.add_argument("--labels", required=True, help="라벨 json이 있는 폴더")
    parser.add_argument("--images", help="--source ocr 일 때 원천 이미지 폴더")
    parser.add_argument("--limit", type=int, default=400)
    parser.add_argument("--cache", default="eval/.match_precision_ocr_cache.json")
    parser.add_argument("--seed", type=int, default=0, help="표본을 고정해 비교 가능하게 한다")
    args = parser.parse_args()

    random.seed(args.seed)
    if args.source == "ocr":
        if not args.images:
            parser.error("--source ocr 에는 --images 가 필요하다")
        cases = collect_from_images(args.labels, args.images, args.limit, Path(args.cache))
    else:
        cases = collect_from_labels(args.labels, args.limit)

    if not cases:
        parser.error("측정할 메뉴판이 없다 — --labels 경로를 확인해라")

    sweep(cases)
    report_score_buckets(cases)


if __name__ == "__main__":
    main()
