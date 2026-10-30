"""웹 데모 모드 데이터를 만든다 — 서버(GPU Space)가 꺼져 있어도 웹에서 체험할 수 있게.

우리가 직접 만든 예시 메뉴판 한 장을 **실제 파이프라인(analyze_image)으로** 분석하고, 그
결과·음식 상세·음성을 정적 파일로 저장한다. 웹은 데모 모드에서 서버 대신 이 파일을 읽는다
(frontend/client/src/lib/api.ts의 데모 부분).

[왜] 메뉴판을 직접 만든다: 시연용으로 골라 둔 메뉴판 사진(AI Hub 데이터셋)은 공개 웹에
다시 올려도 되는지 확인되지 않았다. 우리가 그린 메뉴판은 그 문제가 없다.
[왜] 미리 계산한 결과를 쓴다: OCR은 GPU 없이도 돌지만(맥 CPU 한 장 약 12초), 꺼진 서버를
대신할 곳이 없다. 메뉴판이 한 장으로 고정이면 결과도 고정이라 한 번 계산해 두면 된다.

실행(맥, 저장소 루트에서, OCR이 깔린 파이썬, .env에 SUPABASE_URL·SUPABASE_ANON_KEY):
  python deploy/web-demo/build_demo.py

만드는 것(frontend/client/public/demo/):
  menu.jpg    예시 메뉴판
  demo.json   분석 결과 + 메뉴판 음식의 상세 + 지원 음식 목록
  audio/      나레이션·이름 음성 m4a (static/tts_cache의 wav를 줄인 것)

[주의] 맥 전용이다. 메뉴판 글꼴(Apple SD Gothic Neo)과 음성 변환(afconvert)이 macOS 기본 제공이라
따로 설치할 것이 없는 대신, 다른 OS에서는 그대로 돌지 않는다.
[주의] 메뉴판의 줄이 하나라도 다른 음식으로 읽히거나 가격·상자가 빠지면 아무것도 쓰지 않고
멈춘다. 데모는 실제로 돌아가는 것만 보여 줘야 하기 때문이다.
"""

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from src.db.cache import get_food as get_food_row, get_foods  # noqa: E402
from src.pipeline import analyze_image  # noqa: E402
from src.text_gen.detail import get_details, get_food_info  # noqa: E402
from src.text_gen.narration import get_narration  # noqa: E402

OUT_DIR = ROOT / "frontend" / "client" / "public" / "demo"
TTS_CACHE_DIR = ROOT / "static" / "tts_cache"
FONT_PATH = "/System/Library/Fonts/AppleSDGothicNeo.ttc"

# 메뉴판에 적는 줄. (메뉴판 글자, 기대하는 food_id, 가격)
# 2026-10-27 맥 CPU 실측으로 12줄 모두 기대한 음식·가격·상자로 읽힌 조합이다.
# 돼지김치찌개(재료 수식어 '돼지')·매운 떡볶이(맵기 수식어 '매운')는 수식어 표시를,
# 떡볶이·낙지볶음은 CAUTION 나레이션을 보여 주려고 넣었다.
MENU = [
    ("식사", [("비빔밥", 1, "9,000"), ("돼지김치찌개", 4, "9,000"), ("된장찌개", 5, "8,000"),
              ("순두부찌개", 12, "9,000"), ("물냉면", 8, "9,000"), ("삼계탕", 13, "16,000")]),
    ("요리", [("불고기", 2, "15,000"), ("매운 떡볶이", 3, "7,000"), ("해물파전", 27, "14,000"),
              ("잡채", 10, "12,000"), ("낙지볶음", 23, "18,000"), ("김밥", 11, "4,000")]),
]
RESTAURANT = "한상 식당"


def render_menu(path: Path) -> None:
    """종이 메뉴판처럼 보이는 이미지 한 장을 그린다. 이름은 왼쪽, 가격은 같은 줄 오른쪽."""
    width, height = 1200, 1840
    paper, ink, accent, rule = (246, 239, 227), (38, 33, 28), (176, 52, 40), (196, 182, 160)

    def font(size: int, face: int) -> ImageFont.FreeTypeFont:
        # 글꼴 묶음 안의 번호: 2 Medium, 4 SemiBold, 6 Bold
        return ImageFont.truetype(FONT_PATH, size, index=face)

    img = Image.new("RGB", (width, height), paper)
    draw = ImageDraw.Draw(img)
    draw.rectangle([40, 40, width - 40, height - 40], outline=ink, width=4)
    draw.rectangle([56, 56, width - 56, height - 56], outline=rule, width=2)

    title_font, sub_font = font(96, 6), font(36, 2)
    draw.text(((width - draw.textlength(RESTAURANT, font=title_font)) / 2, 120), RESTAURANT, font=title_font, fill=accent)
    draw.text(((width - draw.textlength("MENU", font=sub_font)) / 2, 240), "MENU", font=sub_font, fill=ink)

    item_font, head_font = font(58, 4), font(44, 6)
    y = 340
    for head, items in MENU:
        draw.text((130, y), head, font=head_font, fill=accent)
        y += 70
        draw.line([130, y, width - 130, y], fill=rule, width=3)
        y += 30
        for name, _food_id, price in items:
            draw.text((150, y), name, font=item_font, fill=ink)
            draw.text((width - 150 - draw.textlength(price, font=item_font), y), price, font=item_font, fill=ink)
            y += 92
        y += 40
    img.save(path, quality=90)


def check_analysis(result: dict) -> None:
    """메뉴판의 모든 줄이 기대한 음식·가격·상자로 읽혔는지 확인한다. 하나라도 어긋나면 멈춘다."""
    expected = [(food_id, int(price.replace(",", ""))) for _, items in MENU for _, food_id, price in items]
    got = [(c["food_id"], c["price_krw"]) for c in result["candidates"]]
    problems = []
    if result["status"] != "candidates_found":
        problems.append(f"status={result['status']}")
    if sorted(got) != sorted(expected):
        problems.append(f"기대 {sorted(expected)} / 실제 {sorted(got)}")
    problems += [f"상자 없음: {c['name_kr']}" for c in result["candidates"] if not c.get("source")]
    if problems:
        sys.exit("메뉴판이 기대대로 읽히지 않았다 — 아무것도 쓰지 않는다:\n  " + "\n  ".join(problems))


def to_m4a(src: Path, dest: Path) -> None:
    """음성 wav를 AAC(m4a, 모노 64kbps)로 줄인다. 말소리라 이 정도면 충분하고 크기는 약 1/6이 된다
    (실측 2026-10-27: food_1_GUIDE.wav 1.0MB → 175KB, 길이 21.06초 그대로). 주요 브라우저가 모두 재생한다."""
    if not src.exists():
        sys.exit(f"음성 캐시가 없다: {src} (src/tts/pregenerate.py로 먼저 만든다)")
    subprocess.run(["afconvert", "-f", "m4af", "-d", "aac", "-b", "64000", "-c", "1", str(src), str(dest)], check=True)


def food_detail(food_id: int) -> dict:
    """GET /api/foods/{id}(K_Menu_Talk.py get_food)와 같은 모양의 응답을 만든다.

    음성 경로만 다르다. 서버의 "/audio/..." 대신 웹 사이트 안의 "demo/audio/..."를 적고,
    웹의 resolveAudioUrl()은 "demo/"로 시작하는 경로를 서버가 아닌 사이트 기준으로 연다.
    """
    narration = get_narration(food_id)
    to_m4a(TTS_CACHE_DIR / f"food_{food_id}_{narration['style']}.wav", OUT_DIR / "audio" / f"food_{food_id}.m4a")
    to_m4a(TTS_CACHE_DIR / f"name_{food_id}.wav", OUT_DIR / "audio" / f"name_{food_id}.m4a")
    return {
        **get_food_info(food_id),
        "spice_level": get_food_row(food_id)["spice_level"],
        "details": get_details(food_id),
        "narration_text": narration["text"],
        "style": narration["style"],
        "tts_status": "ok",
        "narration_audio_path": f"demo/audio/food_{food_id}.m4a",
        "tts_latency_ms": 0.0,
        "name_audio_path": f"demo/audio/name_{food_id}.m4a",
        "name_tts_status": "ok",
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "audio").mkdir(exist_ok=True)

    menu_path = OUT_DIR / "menu.jpg"
    render_menu(menu_path)
    result = analyze_image(str(menu_path))
    check_analysis(result)

    foods = {str(c["food_id"]): food_detail(c["food_id"]) for c in result["candidates"]}
    # GET /api/foods(list_foods)와 같은 모양·순서. 설정 창의 지원 음식 목록이 서버 없이도 보이게 한다.
    supported = sorted(
        ({"food_id": f["id"], "name_kr": f["name_kr"], "name_en": f["name_en"]} for f in get_foods()),
        key=lambda f: f["name_en"],
    )
    demo = {
        "generated_at": date.today().isoformat(),
        "menu_image": "demo/menu.jpg",
        "analyze": result,
        "foods": foods,
        "supported": supported,
    }
    (OUT_DIR / "demo.json").write_text(json.dumps(demo, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"완료: 후보 {len(result['candidates'])}개, 상세 {len(foods)}개, 지원 음식 {len(supported)}개 → {OUT_DIR}")


if __name__ == "__main__":
    main()
