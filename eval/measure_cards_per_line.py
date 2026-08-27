"""메뉴판 **줄 하나에서 카드가 몇 장 나오는지**를 잰다 — 후보 중복을 보는 지표.

## 왜 필요했나

`eval/measure_match_precision.py`로는 후보 중복을 잴 수 없다. 두 가지 이유다.

1. 그 스크립트는 메뉴판 글자를 한 덩어리로 이어붙여 `match_food_candidates()`만
   부르고, 화면이 실제로 타는 `scan_menu_lines()` 경로를 **아예 지나지 않는다.**
   줄 단위 코드를 고쳐도 그 수치는 움직이지 않는다.
2. 정오 판정이 "등록 이름이 그 메뉴판의 **어떤 메뉴명에든** 부분 문자열이면 정답"이라,
   `육회비빔밥` 한 줄에서 `육회`와 `비빔밥`이 **둘 다 정답**으로 잡힌다. 중복을
   없애는 옳은 수정이 그 지표에서는 재현율 하락으로 읽힌다.

그래서 "한 메뉴 줄에서 카드가 몇 장 나오는가"를 직접 세는 지표를 따로 둔다.

## 정답 판정을 하지 않는다

카드가 2장이라고 무조건 틀린 게 아니다. `제주흑돼지김치찌개&명란비빔밥`은 두 장이
맞고 `육회비빔밥`은 한 장이 맞다. 자동으로 가릴 방법이 없으므로 이 스크립트는
**분포와 실제 사례를 뽑아 놓기만 한다.** 옳고 그름은 사람이 전후를 비교해 판단한다.

판단을 돕기 위해, 카드가 2장 이상인 줄은 두 후보 이름이 줄 글자에서 어떤 위치
관계인지도 함께 센다(`src/ocr/match.py`의 `_normalize` = 공백 제거 기준).

    겹침    두 이름이 같은 글자를 나눠 쓴다 (갈비탕 / 갈비)
    맞닿음  두 이름이 빈틈없이 이어 붙어 있다 (육회 / 비빔밥)
    떨어짐  사이에 다른 글자가 있다 (제주흑돼지김치찌개 & 명란비빔밥)
    위치불명 이름이 줄 글자에 통짜로 없다 (닮은 정도로만 걸린 후보)

## 캐시

OCR은 맥 CPU에서 장당 20초가 넘는다. 전후 비교를 하려면 두 번 다 돌려야 하므로,
인식 결과(글자 상자)를 `--cache`에 저장해 재사용한다. 저장하는 것이 이어붙인
글자가 아니라 **상자 목록**인 점만 `measure_match_precision.py`와 다르다 —
줄 나누기가 좌표를 쓰기 때문이다.

## 실행 예 (저장소 루트에서)

    PYTHONPATH=. python eval/measure_cards_per_line.py \\
        --images ~/Downloads/메뉴판_테스트용 --glob '[0-9][0-9]_*.jpg' --limit 10 \\
        --cache eval/.cards_per_line_test_cache.json

    PYTHONPATH=. python eval/measure_cards_per_line.py \\
        --images "~/Downloads/222.관광 음식메뉴판 데이터/.../VS_09. 강원" --limit 40 \\
        --cache eval/.cards_per_line_ocr_cache.json
"""

import argparse
import glob
import itertools
import json
import os
import random
from pathlib import Path

import src.ocr.match as match
from src.ocr.price import TextBox


def collect_boxes(image_dir: str, pattern: str, limit: int, cache_path: Path) -> dict[str, list[TextBox]]:
    """실제 OCR을 돌려 글자 상자를 모은다. 이미 캐시에 있는 이미지는 건너뛴다."""
    # 무거운 import라 실제로 OCR을 돌릴 때만 한다.
    from src.ocr.infer import recognize_boxes_with_mapping

    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    images = sorted(glob.glob(os.path.join(image_dir, pattern)))
    random.shuffle(images)
    images = images[:limit]

    for index, image in enumerate(images, 1):
        stem = Path(image).stem
        if stem in cache:
            continue
        try:
            boxes, _mapping = recognize_boxes_with_mapping(image)
        except Exception as error:  # 한 장이 깨져도 배치 전체를 멈추지 않는다
            print("[%d] %s OCR 실패: %s" % (index, stem, error), flush=True)
            continue
        cache[stem] = [list(box) for box in boxes]
        cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        print("[%d/%d] %s" % (index, len(images), stem), flush=True)

    wanted = {Path(image).stem for image in images}
    return {
        stem: [TextBox(*box) for box in boxes]
        for stem, boxes in cache.items()
        if stem in wanted
    }


def relation(line: str, first: str, second: str) -> str:
    """두 이름이 줄 글자에서 어떤 위치 관계인지 — 겹침 / 맞닿음 / 떨어짐 / 위치불명.

    같은 이름이 줄에 여러 번 나올 수 있어, 조합 중 **가장 가까운 배치**를 기준으로
    본다(겹침이 가장 가깝다). 두 이름이 실제로 같은 글자를 나눠 쓰고 있는지를
    보려는 것이므로, 가장 붙어 있는 쪽이 판단 근거가 된다.
    """
    normalized = match._normalize(line)
    spots = []
    for name in (first, second):
        name = match._normalize(name)
        found = []
        start = normalized.find(name)
        while start >= 0:
            found.append((start, start + len(name)))
            start = normalized.find(name, start + 1)
        if not found:
            return "위치불명"
        spots.append(found)

    gap = min(
        max(a[0], b[0]) - min(a[1], b[1])
        for a in spots[0]
        for b in spots[1]
    )
    if gap < 0:
        return "겹침"
    if gap == 0:
        return "맞닿음"
    return "떨어짐"


def scan(pages: dict[str, list[TextBox]]) -> tuple[dict[int, int], dict[str, int], list[dict]]:
    """메뉴판마다 줄 단위로 훑어 줄당 카드 수·위치 관계·사례를 모은다."""
    per_line: dict[int, int] = {}
    relations: dict[str, int] = {}
    cases: list[dict] = []

    for stem in sorted(pages):
        candidates, _unsupported = match.scan_menu_lines(pages[stem])

        lines: dict[int, list[dict]] = {}
        for candidate in candidates:
            lines.setdefault(candidate["line_no"], []).append(candidate)

        for line_no in sorted(lines):
            cards = lines[line_no]
            per_line[len(cards)] = per_line.get(len(cards), 0) + 1
            if len(cards) < 2:
                continue
            names = [card["name_kr"] for card in cards]
            line = cards[0]["menu_text"]
            pairs = []
            for first, second in itertools.combinations(names, 2):
                kind = relation(line, first, second)
                relations[kind] = relations.get(kind, 0) + 1
                pairs.append("%s/%s %s" % (first, second, kind))
            cases.append({"stem": stem, "line": line, "names": names, "pairs": pairs})

    return per_line, relations, cases


def report(pages: dict[str, list[TextBox]], per_line: dict[int, int],
           relations: dict[str, int], cases: list[dict], examples: int) -> None:
    matched_lines = sum(per_line.values())
    total_cards = sum(count * lines for count, lines in per_line.items())

    print("\n메뉴판 %d장 / 후보가 나온 줄 %d개 / 카드 %d장" % (len(pages), matched_lines, total_cards))

    # 3장 이상은 한 칸으로 묶는다 — 개수 자체보다 "여러 장으로 쪼개졌다"가 볼 지점이다.
    rows = [
        ("1장", per_line.get(1, 0)),
        ("2장", per_line.get(2, 0)),
        ("3장 이상", sum(lines for count, lines in per_line.items() if count >= 3)),
    ]
    print("\n줄당 카드 수 분포")
    print("%8s %7s %8s" % ("카드 수", "줄", "비율"))
    for label, lines in rows:
        share = lines / matched_lines * 100 if matched_lines else 0.0
        print("%8s %7d %7.1f%%" % (label, lines, share))

    print("\n2장 이상인 줄의 이름 쌍 위치 관계")
    print("%10s %7s" % ("관계", "쌍"))
    for kind in ("겹침", "맞닿음", "떨어짐", "위치불명"):
        if kind in relations:
            print("%10s %7d" % (kind, relations[kind]))

    print("\n2장 이상인 줄 사례 (%d개 중 %d개)" % (len(cases), min(len(cases), examples)))
    for case in cases[:examples]:
        print("  %s" % case["stem"])
        print("    줄  : %s" % case["line"])
        print("    카드: %s" % ", ".join(case["names"]))
        print("    관계: %s" % " | ".join(case["pairs"]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", required=True, help="원천 이미지 폴더")
    parser.add_argument("--glob", default="*.jpg", help="이미지 파일 패턴")
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--cache", default="eval/.cards_per_line_ocr_cache.json")
    parser.add_argument("--examples", type=int, default=30, help="출력할 사례 개수")
    parser.add_argument("--seed", type=int, default=0, help="표본을 고정해 비교 가능하게 한다")
    args = parser.parse_args()

    random.seed(args.seed)
    pages = collect_boxes(
        os.path.expanduser(args.images), args.glob, args.limit, Path(args.cache)
    )
    if not pages:
        parser.error("측정할 메뉴판이 없다 — --images 경로를 확인해라")

    per_line, relations, cases = scan(pages)
    report(pages, per_line, relations, cases, args.examples)


if __name__ == "__main__":
    main()
