"""OCR 모델을 같은 조건으로 비교 측정한다.

base(파인튜닝 전)와 파인튜닝 모델을 같은 테스트셋·같은 전처리·같은 detection 박스로
돌리고 인식(recognition) 모델만 바꿔가며 잰다.

숫자 지표는 정답 라벨이 음식명뿐이라 여기서 낼 수 없다. 대신 **숫자를 얼마나 가격답게
읽었는지**를 대리 지표로 낸다(digit_token_rate·price_parse_rate). 정답 있는 숫자 정확도는
eval/measure_digits.py 가 따로 잰다.

지표를 낸다:
  match_recall — manifest의 match_count>=1인 이미지 중, 올바른 등록 음식 후보를
                 1개 이상 뽑아낸 비율. 기존 97.22%와 같은 축의 지표.
  label_hit    — 정답 라벨이 OCR 원문에 그대로 들어있는 비율.
                 기존 42.94%(exact_label_recall)와 같은 축으로 의도한 지표.
  label_cer    — 라벨별 최소 정규화 편집거리의 평균. 낮을수록 좋다.
                 학습 로그의 CER(AI Hub 검증셋 기준)과는 측정 대상이 다르다.

실행 예 (저장소 루트에서):
  python eval/measure_ocr.py --rec hf --label final
  python eval/measure_ocr.py --rec paddle-base --label base
  python eval/measure_ocr.py --rec local --weights <경로>.pdparams --dict <경로>.txt --label prev
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rapidfuzz.distance import Levenshtein

from src.ocr import infer
from src.ocr.match import match_food_candidates
from src.ocr.price import find_prices


def norm(text: str) -> str:
    """공백을 없애고 소문자로 — 비교 전에 표기 흔들림을 줄인다."""
    return "".join(text.split()).lower()


def use_local_checkpoint(weights: str, dict_path: str) -> None:
    """infer.py의 인식 모델을 로컬 체크포인트로 갈아끼운다.

    infer._load_rec_engine()과 똑같은 순서로 만들되 HF Hub 대신 로컬 파일을 쓴다.
    이렇게 해야 detection·전처리·세로쓰기 회전까지 전부 같은 경로를 탄다.
    """
    post = infer.CTCLabelDecode(character_dict_path=dict_path, use_space_char=True)
    char_num = len(post.character)

    config = dict(infer._ARCHITECTURE_CONFIG)
    config["Head"] = dict(infer._ARCHITECTURE_CONFIG["Head"])
    config["Head"]["out_channels_list"] = {
        "CTCLabelDecode": char_num,
        "SARLabelDecode": char_num + 2,
        "NRTRLabelDecode": char_num + 3,
    }

    model = infer.build_model(config)
    prefix = weights[: -len(".pdparams")] if weights.endswith(".pdparams") else weights
    infer.load_model({"Global": {"pretrained_model": prefix, "checkpoints": None}}, model)
    model.eval()

    infer._rec_model = model
    infer._rec_post_process = post
    infer._rec_ops = [
        infer.DecodeImage(img_mode="BGR", channel_first=False),
        infer.RecResizeImg(image_shape=[3, 48, 320], infer_mode=True),
        infer.KeepKeys(keep_keys=["image"]),
    ]


def recognize_paddle_base(image_path: str) -> str:
    """PaddleOCR 기본 인식 모델의 결과를 읽는다 (base 비교군).

    detection은 파인튜닝 쪽과 같은 엔진·같은 박스를 쓴다. 다만 우리가 추가한
    세로쓰기 회전 보정은 여기에 적용되지 않으므로 비교표에 그 점을 적어야 한다.
    """
    image = infer.preprocess_image(image_path)
    results = infer._load_det_engine().predict(image)
    if not results:
        return ""

    texts = results[0].get("rec_texts")
    if texts is None:
        raise KeyError("rec_texts 키가 없다. 사용 가능한 키: %s" % list(results[0].keys()))
    return " ".join(t for t in texts if t)


def measure(entry: dict, image_path: Path, recognize) -> dict:
    """이미지 한 장을 측정해서 결과 한 줄을 만든다."""
    text = recognize(str(image_path))
    normalized = norm(text)
    segments = [s for s in text.split() if s]

    hits = 0
    cers = []
    for label in entry["labels"]:
        target = norm(label)
        if target and target in normalized:
            hits += 1
        distances = [Levenshtein.normalized_distance(target, norm(s)) for s in segments]
        cers.append(min(distances) if distances else 1.0)

    correct_food = False
    if entry["match_count"] >= 1:
        targets = [norm(label) for label in entry["labels"]]
        correct_food = any(
            norm(candidate["name_kr"]) in target
            for candidate in match_food_candidates(text)
            for target in targets
        )

    # 숫자 관련 대리 지표. 정답 가격이 없으므로 "얼마나 가격답게 읽혔나"만 본다:
    # 숫자가 섞인 토큰 중 가격 파서가 실제 금액으로 받아들이는 비율.
    digit_tokens = [s for s in segments if any(c.isdigit() for c in s)]
    parsed_tokens = [s for s in digit_tokens if find_prices(s)]

    return {
        "file_name": entry["file_name"],
        "category": entry["category"],
        "match_count": entry["match_count"],
        "label_total": len(entry["labels"]),
        "label_hits": hits,
        "label_cers": cers,
        "correct_food": correct_food,
        "digit_tokens": len(digit_tokens),
        "parsed_price_tokens": len(parsed_tokens),
        "ocr_text": text,
    }


def summarize(rows: list) -> dict:
    """카테고리별·전체 집계를 낸다."""
    groups = defaultdict(list)
    for row in rows:
        groups[row["category"]].append(row)
    groups["__all__"] = rows

    summary = {}
    for name, group in groups.items():
        labels = sum(r["label_total"] for r in group)
        hits = sum(r["label_hits"] for r in group)
        cers = [c for r in group for c in r["label_cers"]]
        matchable = [r for r in group if r["match_count"] >= 1]
        correct = [r for r in matchable if r["correct_food"]]
        # 숫자 대리 지표: 숫자가 섞인 토큰 중 가격 파서가 금액으로 받아들이는 비율.
        # 낮다는 건 숫자를 읽긴 했는데 가격으로 쓸 수 없는 상태로 읽었다는 뜻이다.
        digit_tokens = sum(r.get("digit_tokens", 0) for r in group)
        parsed_tokens = sum(r.get("parsed_price_tokens", 0) for r in group)
        summary[name] = {
            "images": len(group),
            "labels": labels,
            "label_hit": round(hits / labels, 4) if labels else None,
            "label_cer": round(sum(cers) / len(cers), 4) if cers else None,
            "matchable_images": len(matchable),
            "match_recall": round(len(correct) / len(matchable), 4) if matchable else None,
            "digit_tokens": digit_tokens,
            "price_parse_rate": round(parsed_tokens / digit_tokens, 4) if digit_tokens else None,
        }
    return summary


def default_test_root() -> str:
    """테스트셋 위치 — 환경변수가 있으면 그걸, 없으면 맥 기본 경로를 쓴다."""
    return os.environ.get("OCR_TEST_SET_ROOT") or str(Path.home() / "Downloads" / "OCR_test_set_50")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rec", choices=["hf", "local", "paddle-base"], required=True)
    parser.add_argument("--weights", help="--rec local 일 때 .pdparams 경로")
    parser.add_argument("--dict", dest="dict_path", help="--rec local 일 때 dict 경로")
    parser.add_argument("--test-root", default=default_test_root())
    parser.add_argument("--label", required=True, help="결과 파일 이름에 쓸 이름")
    args = parser.parse_args()

    if args.rec == "local":
        if not (args.weights and args.dict_path):
            parser.error("--rec local 은 --weights 와 --dict 가 필요하다")
        use_local_checkpoint(args.weights, args.dict_path)

    recognize = recognize_paddle_base if args.rec == "paddle-base" else infer.recognize

    test_root = Path(args.test_root)
    manifest_path = test_root / "manifest.json"
    if not manifest_path.exists():
        parser.error("manifest.json이 없다: %s — --test-root 를 확인해라" % manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    rows = []
    for i, entry in enumerate(manifest, 1):
        image_path = test_root / entry["category"] / entry["file_name"]
        print("[%d/%d] %s" % (i, len(manifest), entry["file_name"]))
        rows.append(measure(entry, image_path, recognize))

    result = {"label": args.label, "rec": args.rec, "summary": summarize(rows), "rows": rows}
    out_path = Path(__file__).parent / ("measure_ocr_%s.json" % args.label)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n저장: %s" % out_path)
    for name, s in result["summary"].items():
        print("  %-16s match_recall=%s  label_hit=%s  label_cer=%s  price_parse_rate=%s"
              % (name, s["match_recall"], s["label_hit"], s["label_cer"], s["price_parse_rate"]))


if __name__ == "__main__":
    main()
