"""숫자(가격) 인식만 따로 재는 벤치마크 — base와 파인튜닝 모델을 같은 조건으로 비교한다.

**왜 별도 스크립트인가**: eval/measure_ocr.py는 음식명 기준 지표(label_hit·label_cer·
match_recall)만 낸다. 그런데 실제 메뉴판에서 이름은 잘 읽히는데 가격이 망가지는 현상이
관측됐고(eval/measure_ocr_final.json의 ocr_text에 '0I', 's0', '0.000', '14.9000 13.'
같은 토큰이 남아 있다), 전체 지표로는 그 원인이 보이지 않는다.

**어떻게 원인을 분리하나**: 이미지 한 장을 detection에 한 번만 넣고, 거기서 나온 **같은
박스·같은 크롭**을 두 인식 모델에 각각 먹인다. 전처리·검출·크롭이 완전히 동일하므로
차이가 나면 그건 인식 모델 자체의 차이다.

  - base       : PaddleOCR 기본 인식기 (detection 파이프라인이 함께 돌려주는 rec_texts)
  - finetuned  : 우리가 파인튜닝한 체크포인트 (infer._recognize_crop_with_score)
  - production : 실제 배포 경로 (infer._better_reading — 한글 없는 조각은 base 쪽을 채택)

해석 기준:
  - 파인튜닝 쪽만 나쁘면  -> 학습 과정에서 숫자 성능을 잃은 것 (catastrophic forgetting)
  - 둘 다 비슷하게 나쁘면 -> 전처리/크롭/CTC/후처리 등 구조 문제

정답을 알아야 정확도를 잴 수 있는데 실제 메뉴판 사진에는 가격 정답 라벨이 없다. 그래서
가격 문자열을 직접 그려 넣은 이미지를 만들어 쓴다 — 정답이 확실하고, 표기 형태·글자 크기·
흐림 정도를 의도적으로 흔들 수 있다. 실제 사진 기반 비교는 테스트셋이 있는 환경에서
eval/measure_ocr.py --rec paddle-base 로 따로 돌린다.

실행 (저장소 루트에서):
  python eval/measure_digits.py
  python eval/measure_digits.py --out eval/measure_digits.json
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# paddleocr -> paddlex -> modelscope 체인이 torch를 끌어오는데, 그전에 paddle이 먼저
# 로드돼 있으면 Windows에서 torch DLL 로딩이 깨진다. K_Menu_Talk.py와 같은 이유로 먼저 올린다.
import torch  # noqa: F401

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from rapidfuzz.distance import Levenshtein

from src.ocr import infer
from src.ocr.price import find_prices

# 실제 한국 메뉴판에서 쓰이는 가격 표기들. 콤마/마침표/원/₩ 유무를 섞는다.
PRICE_FORMS = ["9,000", "8000", "12,000", "4,500", "16,000원", "₩7,000", "23,000", "6.000"]
FOOD_NAMES = ["비빔밥", "김치찌개", "삼겹살", "순대", "불고기", "떡볶이", "된장찌개", "잡채"]

FONTS = ["malgun.ttf", "batang.ttc", "gulim.ttc"]
# (흐림, 글자크기, jpeg 품질) — 또렷한 사진부터 손떨림 섞인 사진까지.
CONDITIONS = [(0.0, 44, 95), (1.0, 36, 60), (1.8, 30, 40)]


def render_menu(path: Path, rows: list[tuple[str, str]], font_name: str, blur: float, size: int, quality: int) -> None:
    """메뉴판 한 장을 그린다 — 왼쪽에 음식명, 오른쪽에 가격."""
    height = 140 + 150 * len(rows)
    image = Image.new("RGB", (900, height), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("C:/Windows/Fonts/" + font_name, size)
    for index, (name, price) in enumerate(rows):
        y = 80 + 150 * index
        draw.text((70, y), name, fill=(30, 30, 30), font=font)
        draw.text((600, y), price, fill=(30, 30, 30), font=font)
    if blur:
        image = image.filter(ImageFilter.GaussianBlur(blur))
    image.save(path, quality=quality)


def read_both(image_path: Path) -> list[dict]:
    """이미지 한 장을 detection에 넣고, 각 박스를 두 인식 모델로 각각 읽는다.

    detection과 전처리를 한 번만 돌려 **완전히 같은 크롭**을 양쪽에 넘기는 것이 요점이다.
    여기가 달라지면 인식 모델 차이인지 크롭 차이인지 구분할 수 없다.
    """
    image, _mapping = infer.preprocess_image_with_mapping(str(image_path))
    results = infer._load_det_engine().predict(image)
    if not results:
        return []

    detection = results[0]
    polys = detection.get("dt_polys", [])
    base_texts = detection.get("rec_texts", [])
    base_scores = detection.get("rec_scores", [])

    readings = []
    for index, poly in enumerate(polys):
        x, y, width, height = cv2.boundingRect(np.array(poly, dtype=np.int32))
        crop = image[y : y + height, x : x + width]

        # infer.recognize_boxes()와 같은 분기 — 세로로 긴 조각은 회전해서 읽는다.
        if height > width * infer._VERTICAL_ASPECT_RATIO:
            tuned = infer._recognize_vertical_crop(crop)
        else:
            ok, buffer = cv2.imencode(".jpg", crop)
            if not ok:
                continue
            tuned = infer._recognize_crop_with_score(buffer.tobytes())

        base = (
            base_texts[index] if index < len(base_texts) else "",
            base_scores[index] if index < len(base_scores) else 0.0,
        )
        # 배포 경로가 실제로 어느 쪽을 채택하는지 그대로 재현한다.
        production_text, _score = infer._better_reading(tuned, base)

        readings.append(
            {
                "x": int(x),
                "y": int(y),
                "base": base[0],
                "finetuned": tuned[0],
                "production": production_text,
            }
        )
    return readings


def strip(text: str) -> str:
    return "".join(text.split())


def score_reading(truth: str, reading: str) -> dict:
    """가격 하나에 대해 세 가지를 잰다: 글자 일치, 편집거리, 파서가 금액을 복원하는가."""
    expected_value = find_prices(strip(truth))
    parsed = find_prices(strip(reading))
    return {
        "exact": strip(reading) == strip(truth),
        "cer": Levenshtein.normalized_distance(strip(truth), strip(reading)),
        # 글자가 조금 달라도 파서가 같은 금액을 복원하면 서비스 관점에서는 성공이다.
        "parsed_ok": bool(expected_value) and bool(parsed) and parsed[0][2] == expected_value[0][2],
    }


def run(out_path: Path) -> dict:
    scratch = Path(__file__).parent / "_digits_tmp.jpg"
    samples = []

    case_index = 0
    for font_name in FONTS:
        for blur, size, quality in CONDITIONS:
            # 한 장에 4줄씩 — 매번 다른 가격 표기를 쓴다.
            rows = [
                (FOOD_NAMES[(case_index * 4 + i) % len(FOOD_NAMES)],
                 PRICE_FORMS[(case_index * 4 + i) % len(PRICE_FORMS)])
                for i in range(4)
            ]
            render_menu(scratch, rows, font_name, blur, size, quality)
            try:
                readings = read_both(scratch)
            finally:
                scratch.unlink(missing_ok=True)

            # 오른쪽 절반 박스 = 가격 박스. 위에서 아래로 정렬해 그린 순서와 짝짓는다.
            if not readings:
                continue
            midpoint = (min(r["x"] for r in readings) + max(r["x"] for r in readings)) / 2
            price_boxes = sorted((r for r in readings if r["x"] > midpoint), key=lambda r: r["y"])

            for (name, truth), reading in zip(rows, price_boxes):
                samples.append(
                    {
                        "font": font_name,
                        "blur": blur,
                        "size": size,
                        "food": name,
                        "truth": truth,
                        "base": reading["base"],
                        "finetuned": reading["finetuned"],
                        "production": reading["production"],
                        "base_score": score_reading(truth, reading["base"]),
                        "finetuned_score": score_reading(truth, reading["finetuned"]),
                        "production_score": score_reading(truth, reading["production"]),
                    }
                )
            case_index += 1
            print("[%d] %s blur=%.1f size=%d -> 가격박스 %d개"
                  % (case_index, font_name, blur, size, len(price_boxes)))

    def aggregate(key: str) -> dict:
        scores = [s[key] for s in samples]
        total = len(scores) or 1
        return {
            "samples": len(scores),
            "digit_exact": round(sum(s["exact"] for s in scores) / total, 4),
            "digit_cer": round(sum(s["cer"] for s in scores) / total, 4),
            "price_parsed_ok": round(sum(s["parsed_ok"] for s in scores) / total, 4),
        }

    result = {
        "note": "같은 이미지·같은 detection 박스·같은 크롭을 두 인식 모델에 각각 먹인 결과",
        "base": aggregate("base_score"),
        "finetuned": aggregate("finetuned_score"),
        "production": aggregate("production_score"),
        "samples": samples,
    }
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(Path(__file__).parent / "measure_digits.json"))
    args = parser.parse_args()

    result = run(Path(args.out))

    print("\n%-12s %-10s %-10s %s" % ("모델", "글자일치", "CER", "파서가 금액 복원"))
    print("-" * 52)
    for label in ("base", "finetuned", "production"):
        s = result[label]
        print("%-12s %-10s %-10s %s"
              % (label, "%.1f%%" % (s["digit_exact"] * 100), "%.3f" % s["digit_cer"],
                 "%.1f%%" % (s["price_parsed_ok"] * 100)))

    print("\n대표 실패 사례 (파인튜닝 모델):")
    failures = [s for s in result["samples"] if not s["finetuned_score"]["exact"]]
    for s in failures[:8]:
        print("   %-9s -> %-12s (base: %-9s) %s blur=%.1f size=%d"
              % (s["truth"], repr(s["finetuned"]), repr(s["base"]), s["font"], s["blur"], s["size"]))
    print("\n저장: %s" % args.out)


if __name__ == "__main__":
    main()
