"""RapidFuzz 매칭 — 추출된 글자를 등록 음식명 50개와 유사도 비교한다.

OCR이 글자를 조금 틀리게 읽어도 가장 비슷한 등록 음식으로 이어주는 단계.

이름이 텍스트에 통째로 들어있는지 먼저 보고 거르던 때가 있었는데, 그러면 정확히 일치하는
것만 통과해서 점수가 항상 100이 되고(= 유사도 매칭이 무의미해지고) "빔밥"처럼 한 글자
어긋난 OCR 결과를 전부 놓쳤다. 지금은 유사도만으로 거른다.

메뉴 텍스트에 붙는 맵기·재료 수식어(예: "매운닭발")는 menu_modifiers 테이블 기준으로 매칭 후
따로 뽑아낸다. partial_ratio는 부분 문자열도 점수 100이 나오기 때문에 매칭 자체엔 수식어를
지울 필요가 없다 — 그냥 매칭된 음식명에 그 단어가 이미 들어있는 경우만(예: "매운탕"의 "매운")
수식어 목록에서 제외한다.
"""

import re
import statistics

from rapidfuzz import fuzz

from src.db import cache
from src.ocr.infer import group_boxes_into_row_groups, row_text
from src.ocr.price import (
    TextBox,
    box_confidence,
    extract_price_near,
    find_prices,
    format_price_krw,
    match_prices_to_names,
    strip_prices,
)

# 실측으로 정한 값 — AI Hub 관광 음식메뉴판 검증셋으로 스윕했다(eval/measure_match_precision.py).
#
# 원래 65였다. "한 글자 오인식까지 받아준다"는 의도였는데, 정답 라벨을 붙여 **오탐까지**
# 재보니 그 관대함이 값을 못 하고 있었다. 실측(메뉴판 100장):
#
#   임계값   정밀도   재현율   오탐   놓침
#      65    45.8%   88.7%   176     19
#      80    53.4%   88.7%   130     19
#      85    84.9%   86.9%    26     22   ← 지금 값
#      90    89.0%   86.3%    18     23
#
# 점수 구간별로 뜯어보면 이유가 분명하다 — **정탐의 93%가 100점(정확히 읽힌 것)이고,
# 80점대는 정탐 1 : 오탐 38이었다.** 3글자 이름에서 두 글자가 맞으면 무조건 80점이라,
# "빔밥→비빔밥"(살리고 싶은 것)과 "막국수→칼국수"(막고 싶은 것)가 같은 점수로 섞인다.
# OCR 인식률이 이미 97%대라 애초에 살려낼 오인식 자체가 드물었고, 낮은 임계값은 남의
# 이름 조각에 걸리는 부작용만 남기고 있었다.
#
# 그래서 사실상 "정확히 읽힌 것만 인정"으로 옮긴다. 긴 이름(7글자 이상)은 한 글자가
# 틀려도 85를 넘어 여전히 구제된다.
MATCH_THRESHOLD = 85

# 메뉴판에 정확히 적힌 이름과 이만큼 닮은 "퍼지" 후보는 오인식이 아니라 별개 메뉴로 본다.
# 아래 _is_kin_of_exact() 참고.
KIN_RATIO = 65

# 이름과 맞대볼 최소 구간 길이. name_score() 안의 설명 참고.
_MIN_WINDOW = 2

# 5단계 맵기 스케일 — 거의 안 바뀌는 값이라 DB 대신 상수로 둔다.
SPICE_TIERS = {
    1: {"label_en": "Mild", "emoji": "🌶️", "reference_pepper": "Jalapeño", "shu": 5000},
    2: {"label_en": "Medium", "emoji": "🌶️🌶️", "reference_pepper": "Cayenne", "shu": 40000},
    3: {"label_en": "Hot", "emoji": "🌶️🌶️🌶️", "reference_pepper": "Habanero", "shu": 250000},
    4: {"label_en": "Very Hot", "emoji": "🌶️🌶️🌶️🌶️", "reference_pepper": "Ghost Pepper", "shu": 1000000},
    5: {"label_en": "Extreme", "emoji": "🌶️🌶️🌶️🌶️🌶️", "reference_pepper": "Carolina Reaper", "shu": 2200000},
}

def _normalize(text: str) -> str:
    """비교 전에 공백을 없앤다 — 메뉴판이 "김치 찌개"로 띄어 써도 "김치찌개"에 걸리게."""
    return text.replace(" ", "")


def _extract_modifiers(normalized_text: str, matched_name: str) -> tuple[list[dict], list[dict]]:
    """긴 키워드부터 먼저 찾고, 이미 매칭된 글자 구간은 다시 쓰지 않는다.

    한 글자짜리 키워드(파, 김 등)가 "스파이시"처럼 상관없는 단어 안에 우연히
    끼어있는 걸 걸러내기 위함 — "스파이시"(4글자)가 먼저 그 구간을 차지하면
    그 안의 "파"(1글자)는 겹쳐서 못 잡힌다.
    """
    consumed = [False] * len(normalized_text)
    spice_hits = []
    ingredient_hits = []

    modifiers = sorted(cache.get_modifiers(), key=lambda row: len(row["keyword"]), reverse=True)

    for row in modifiers:
        keyword = row["keyword"]
        if keyword in matched_name:
            continue  # 매칭된 음식명 자체에 포함된 단어면 수식어로 보지 않는다

        start = 0
        found = False
        while True:
            idx = normalized_text.find(keyword, start)
            if idx == -1:
                break
            span = range(idx, idx + len(keyword))
            if not any(consumed[i] for i in span):
                for i in span:
                    consumed[i] = True
                found = True
                break
            start = idx + 1

        if not found:
            continue

        if row["category"] == "spice":
            # keyword_en을 같이 싣는다 — 화면에 보여줄 사람은 한국어를 못 읽는
            # 여행자다. DB(menu_modifiers)에는 이미 있는데 여기서 버리고 있었다.
            spice_hits.append(
                {"keyword": keyword, "keyword_en": row["keyword_en"], "tier": row["spice_tier"]}
            )
        else:
            ingredient_hits.append({"keyword": keyword, "keyword_en": row["keyword_en"]})

    return spice_hits, ingredient_hits


def name_score(text: str, name: str, score_cutoff: int = 0) -> int:
    """text 안에 name이 (오탈자를 감안해) 얼마나 잘 나타나는지 0~100으로 잰다.

    fuzz.partial_ratio를 쓰지 않는다. 그 함수는 짧은 쪽을 needle로 삼고 정렬 구간 길이도
    스스로 고르기 때문에, **주변 글자가 얼마나 많은지에 따라 같은 이름의 점수가 달라진다**.
    실측: 잡음 없는 짧은 메뉴판에서 오탐 80개, 안내문이 섞인 중간 길이에서 31개로 요동쳤다.

    대신 이름과 길이가 같은(±1) 구간만 이름과 맞대본다. 비교 단위를 이름 길이에 고정하면
    "이 이름이 여기 있나?"라는 질문이 텍스트 길이와 무관해진다. ±1은 글자가 하나 빠지거나
    끼어든 OCR 결과를 받아주기 위한 것이다.

    score_cutoff를 주면 그 아래 점수는 정확히 재지 않고 0으로 돌려준다. 글자마다 창을 밀며
    비교하는 구조라 호출 수가 많은데, 어차피 기준 미달이면 정확한 값이 필요 없으므로
    rapidfuzz가 일찍 포기하게 해서 시간을 줄인다.
    """
    best = 0
    cutoff = score_cutoff
    for width in (len(name) - 1, len(name), len(name) + 1):
        # 창이 이보다 좁아지면 글자 하나만 겹쳐도 점수가 뛴다 — 2글자 이름에서 창이 1글자가
        # 되면 "떡"만 맞아도 67점이 나온다. 길이 가드가 필요한 지점이 정확히 여기다.
        if width < _MIN_WINDOW or width > len(text):
            continue
        for start in range(len(text) - width + 1):
            # 기준 미달이면 rapidfuzz가 0을 돌려준다 — 그대로 버린다
            score = fuzz.ratio(text[start : start + width], name, score_cutoff=cutoff)
            if score > best:
                best = score
                cutoff = max(cutoff, score)
            if best == 100:
                return 100
    return round(best)


# 메뉴판에는 메뉴가 아닌 글자가 함께 실린다. 그런 문구에 음식 이름이 들어 있으면
# 메뉴로 잘못 잡힌다 — 실제 사진에서 관측된 사례:
#   "돼지고기(국내산)쌀(국내산),고추가루(중국산"  -> 불고기      (법정 원산지 표시)
#   "제공하는돼지갈비무한리필전문점입니다"          -> 갈비        (가게 홍보 문구)
#   "당일 삶은 족발만 판매합니다"                   -> 족발        (가게 안내 문구)
# 아래 말이 들어간 상자는 "메뉴 줄"이 아니라고 본다.
# 메뉴 줄에는 절대 안 나오는 말만 넣는다. 넓게 잡으면 진짜 메뉴가 사라진다 —
# 처음에 "무한리필"을 넣었다가 실제 사진의 "된장찌개(무한리필이몽시)"가 통째로
# 걸러졌다(무한리필 식당에서 "무한리필 이용 시"는 메뉴 조건 문구다).
_NON_MENU_MARKERS = (
    "원산지",                                   # 원산지 표시 머리말
    "전문점",                                   # "...무한리필전문점입니다" 같은 홍보 문구
    "영업시간", "브레이크타임", "라스트오더",
    "사업자", "등록번호", "대표자",
    # 문장 종결 어미 — "당일 삶은 족발만 판매합니다", "재료 소진 시 조기 마감했습니다",
    # "주문 전 말씀 바랍니다" 같은 안내 문장을 가리킨다.
    # 메뉴 이름은 **항상 명사구**다("족발", "돼지족발", "족발정식"). 서술어로 끝나는
    # 음식 이름은 한국어 표기에 존재하지 않으므로, 이 네 개는 어떤 진짜 메뉴 이름에도
    # 부분 문자열로 들어갈 수 없다 — 등록 음식 50개에도 물론 하나도 없다.
    # 이름 옆에 조건을 덧붙인 메뉴 줄도 안전하다. 그런 문구는 명사나 연결형으로 끝나기
    # 때문이다 — "된장찌개(무한리필이용시)", "한우불고기(국내산)", "공기밥 추가".
    # 종결 어미 전체("...니다")로 넓히지 않은 이유도 같다. 실제로 본 안내문만 넣는다.
    "합니다", "습니다", "입니다", "바랍니다",
    # 부탁하는 안내 문장의 종결 어미 — 실측: "산낙지주문시미리말쏨해주세요"가 옆 칸
    # "칼국수사리"와 한 줄로 묶여 주문 화면에 그대로 나왔다(2026-08-27).
    # 위 네 개와 같은 이유로 안전하다. 메뉴 이름은 명사구라 청유형으로 끝나지 않는다.
    "주세요",
)

# 원산지 표시는 "원산지"라는 말 없이 산지만 나열하기도 한다
# (실측: "돼지고기(국내산)쌀(국내산),고추가루(중국산"). 산지 표기가 **두 개 이상**일 때만
# 원산지 블록으로 본다 — "한우불고기(국내산)"처럼 메뉴에 산지가 하나 붙는 경우를 살리기 위해서다.
_ORIGIN_MARKERS = ("국내산", "수입산", "중국산", "미국산", "호주산", "러시아산")
_ORIGIN_BLOCK_MIN_HITS = 2

# 가게 이름(간판·로고)은 메뉴 줄보다 글자가 훨씬 크고 사진 위쪽에 있다.
# 두 조건을 함께 요구한다 — 크기만 보면 큰 글씨로 적은 메뉴를, 위치만 보면 맨 윗줄
# 메뉴를 떨어뜨린다.
# 1.8배로 뒀더니 간판이 본문보다 1.5배쯤만 큰 사진에서 안 걸렸다. 1.35배로 낮춘다 —
# 세 조건(큰 글씨 + 위쪽 + 가격 없음)을 모두 요구하므로 이 정도는 안전하다.
# 더 낮추면 "맨 위에 큼직하게 적고 가격을 안 붙인 대표 메뉴"가 걸리기 시작한다.
_SHOP_NAME_HEIGHT_RATIO = 1.35
_SHOP_NAME_TOP_RATIO = 0.2      # 글자 영역 위쪽 몇 %까지를 머리말 구역으로 볼지


def _is_non_menu_box(box: TextBox, boxes: list[TextBox]) -> bool:
    """이 상자가 메뉴 줄이 아니라 안내 문구나 가게 이름인가."""
    text = box[4]
    if any(marker in text for marker in _NON_MENU_MARKERS):
        return True
    if sum(marker in text for marker in _ORIGIN_MARKERS) >= _ORIGIN_BLOCK_MIN_HITS:
        return True

    # 가게 이름 판정: 눈에 띄게 큰 글자 + 사진 위쪽 + 가격이 없음.
    # 가격 조건을 함께 걸어야 "큰 글씨로 적힌 대표 메뉴"를 살릴 수 있다.
    heights = [float(other[3]) for other in boxes]
    tops = [float(other[1]) for other in boxes]
    bottoms = [float(other[1] + other[3]) for other in boxes]
    if not heights:
        return False

    content_height = max(bottoms) - min(tops)
    is_large = box[3] >= _SHOP_NAME_HEIGHT_RATIO * statistics.median(heights)
    is_near_top = content_height > 0 and (box[1] - min(tops)) <= _SHOP_NAME_TOP_RATIO * content_height
    return is_large and is_near_top and not find_prices(text)


def _best_matching_box(boxes: list[TextBox], name: str) -> tuple[TextBox | None, int]:
    """이 음식명의 근거가 된 상자와 그 점수.

    find_source_box와 달리 **어긋나게 읽힌 상자도 받아들인다.** 그쪽은 사진 위에 상자를
    그리는 용도라 이름이 통째로 들어있을 때만 인정해야 하지만, 여기서 찾는 건 "이 후보가
    어디서 나왔나"라서 오인식된 상자가 오히려 정답인 경우가 많다.
    """
    best_box, best_score = None, 0
    for box in boxes:
        score = name_score(_normalize(box[4]), name)
        if score > best_score:
            best_box, best_score = box, score
    return best_box, best_score


def _appears_on_a_menu_line(
    boxes: list[TextBox],
    name: str,
    reference: list[TextBox] | None = None,
) -> bool:
    """음식명이 '메뉴 줄'로 볼 만한 상자에 한 번이라도 나타나는가.

    이름을 통째로 담은 상자가 여럿이면 그중 하나라도 메뉴 줄이면 통과다 — 간판에도 있고
    메뉴에도 있는 이름(김밥천국의 "김밥")을 간판을 이유로 지우면 안 된다.

    통째로 담은 상자가 없으면 가장 잘 맞는 상자로 판단한다. 퍼지 매칭으로 들어온 후보가
    여기 해당한다 — 실측: 원산지 표시 "돼지고기(국내산)..."이 "불고기"를 만들어냈는데,
    이름이 통째로 든 상자가 없다는 이유로 판단을 보류하면 그대로 새어나간다.
    근거 상자를 아예 못 찾을 때만 보류한다(이름이 여러 상자에 걸쳐 잘린 경우).

    **판정 대상(boxes)과 견줄 기준(reference)을 나눠 받는다.** 줄 단위 매칭에서는
    boxes에 그 줄의 상자만 들어와야 한다 — 사진 전체를 넘기면 간판 줄을 판정할 때도
    "다른 곳에 진짜 메뉴 줄이 있다"는 이유로 위 any()가 통과시켜, 간판의 가게 이름이
    메뉴로 올라온다(실측: "연정김치찌개" 간판이 김치찌개 후보가 됐다).
    반면 "이 글자가 유난히 큰가"는 사진 전체와 견줘야 알 수 있어 reference를 쓴다.
    """
    reference = reference if reference is not None else boxes
    hosts = [box for box in boxes if name in _normalize(box[4])]
    if not hosts:
        best_box, best_score = _best_matching_box(boxes, name)
        if best_box is None or best_score < MATCH_THRESHOLD:
            return True
        hosts = [best_box]
    return any(not _is_non_menu_box(box, reference) for box in hosts)


def _reading_confidence(boxes: list[TextBox] | None, name: str) -> float:
    """이 음식명을 읽어낸 상자의 인식 신뢰도. 근거 상자를 못 찾으면 1.0(점수를 깎지 않음)."""
    if not boxes:
        return 1.0
    best_box, best_score = _best_matching_box(boxes, name)
    return box_confidence(best_box) if best_score >= MATCH_THRESHOLD else 1.0


def _is_kin_of_exact(name: str, exact_names: list[str]) -> bool:
    """메뉴판에 정확히 적힌 다른 이름과 한 글자 차이인가.

    "감자탕"이 그대로 적힌 메뉴판에서 "감자전"도 67점으로 걸린다. 하지만 이건 OCR이
    감자전을 잘못 읽어서가 아니라 두 이름이 원래 닮았기 때문이라, 후보로 올리면 안 된다.
    반대로 정확히 적힌 이름이 하나도 없으면(전부 오인식된 상황) 퍼지 후보를 살려야 하므로,
    "정확 일치가 있을 때만" 거른다.

    한계: 닮은 메뉴 둘이 같은 메뉴판에 있는데 그중 하나가 오인식되면(감자탕은 제대로,
    감자전은 깨져서) 깨진 쪽이 걸러진다. 대신 매번 딸려 나오는 오탐을 없애는 쪽을 택했다.
    """
    return any(fuzz.ratio(name, exact) >= KIN_RATIO for exact in exact_names)


def _is_part_of_longer_exact(name: str, exact_names: list[str]) -> bool:
    """이 줄에 그대로 적힌 **더 긴** 이름 안에 이 이름이 통째로 들어 있는가.

    "황기갈비탕" 한 줄에서 `갈비탕`과 `갈비`가 둘 다 정확 일치로 잡힌다. 둘 다 글자가
    실제로 있으니 _is_kin_of_exact로는 걸러지지 않는데(그건 한 글자 차이인 닮은 이름을
    보는 검사다), 짧은 쪽은 긴 쪽의 일부일 뿐 별개 메뉴가 아니다. 화면에는 같은 줄이
    "Galbitang"과 "Galbi" 두 카드로 나와, 없는 메뉴를 주문하게 만든다(실측 2026-08-26).

    줄 단위로 매칭하므로(scan_menu_lines) `갈비`와 `갈비탕`이 **각각 다른 줄**에 있는
    메뉴판은 서로 다른 호출이라 영향받지 않는다 — 둘 다 그대로 후보로 남는다.
    """
    return any(len(other) > len(name) and name in other for other in exact_names)


def find_source_box(boxes: list[TextBox], food_name: str) -> TextBox | None:
    """음식명이 적힌 글자 상자를 찾는다 — 이 후보가 사진 어디에서 나왔는지 추적하기 위한 것.

    food_name은 공백이 제거된 상태로 받고, 상자의 글자는 여기서 정규화해 비교한다
    (상자의 원본 글자를 그대로 돌려줘야 "OCR이 실제로 뭐라고 읽었는지"를 보여줄 수 있다).

    이름이 두 상자에 걸쳐 잘린 경우에는 어느 상자에도 통째로 안 들어있어서 None이 된다 —
    그때는 위치 표시 없이 후보만 보여준다(엉뚱한 자리에 상자를 그리는 것보다 낫다).
    """
    hosts = [box for box in boxes if food_name in _normalize(box[4])]
    if not hosts:
        return None

    # 이름이 간판에도 있고 메뉴 줄에도 있으면 **메뉴 줄** 쪽을 가리켜야 한다.
    # 실측(손칼국수·등뼈찜 메뉴판): "칼국수"가 맨 위 간판 "손칼국수·등뼈찜"과 면류 목록의
    # "칼국수 7,000" 두 곳에 있는데, 그냥 첫 상자를 고르면 검출 순서상 간판이 잡혀서
    # 사진 위 상자가 간판에 그려진다 — 후보는 맞는데 간판을 메뉴로 읽은 것처럼 보인다.
    return next((box for box in hosts if not _is_non_menu_box(box, boxes)), hosts[0])


def _resolve_prices(normalized_text: str, names: list[str], boxes: list[TextBox] | None) -> dict[str, int]:
    """매칭된 음식들의 가격을 한 번에 찾는다 — 좌표가 있으면 위치로, 없으면 글자 거리로.

    좌표 기반은 음식별로 따로 못 구한다. "이 가격은 이미 옆 메뉴가 가져갔다"를 알아야
    가격 없는 메뉴가 남의 가격을 가로채는 걸 막을 수 있어서, 전체를 같이 봐야 한다.
    """
    if boxes is None:
        prices = {name: extract_price_near(normalized_text, name) for name in names}
        return {name: price for name, price in prices.items() if price is not None}

    normalized_boxes = [tuple(box[:4]) + (_normalize(box[4]),) for box in boxes]
    return match_prices_to_names(normalized_boxes, names)


def match_food_candidates(
    text: str,
    boxes: list[TextBox] | None = None,
    all_boxes: list[TextBox] | None = None,
) -> list[dict]:
    """Return every supported food candidate, ordered by match score.

    boxes(메뉴판 사진의 글자 상자 좌표)를 주면 가격을 사진 위 위치로 짝짓는다 — 가격이
    이름 오른쪽에 있든 아래 줄에 있든 찾아낸다. 좌표 없이 통짜 문자열만 보면 바로 옆에
    놓인 다른 메뉴의 가격이 붙기 쉬우므로, 가능하면 항상 boxes를 넘기는 게 맞다
    (src/pipeline.py의 analyze_image()가 그렇게 한다).

    all_boxes는 **간판 판정에서 "이 글자가 유난히 큰가"를 견줄 기준**으로만 쓴다.
    줄 단위로 부를 때 boxes에는 그 줄의 상자만 들어오는데, 크기는 사진 전체와
    비교해야 알 수 있기 때문이다. 판정 **대상**은 어디까지나 boxes(그 줄)다.
    안 주면 boxes를 그대로 쓴다(기존 호출부는 그대로 동작한다).
    """
    normalized_text = _normalize(text)
    foods = cache.get_foods()

    scored = []
    for food in foods:
        name = _normalize(food["name_kr"])
        # 완전일치 부분문자열만 통과시키던 조건을 뺐다 — 그 조건을 통과한 이름은
        # partial_ratio가 항상 100을 내서, 아래 임계값 검사가 한 번도 작동하지 않았다
        # (OCR이 한 글자만 틀려도 후보에서 사라지는 문제).  — f4d8aa2
        #
        # 그 뒤 partial_ratio 자체도 name_score로 바꿨다. 게이트를 없애고 보니 이번엔
        # 주변 글자 양에 따라 같은 이름의 점수가 요동쳐서(실측: 오탐 80 -> 31 -> 80),
        # 임계값이 사진마다 다르게 작동했다. 자세한 내용은 name_score() 설명 참고.
        score = name_score(normalized_text, name, score_cutoff=MATCH_THRESHOLD)
        if score < MATCH_THRESHOLD:
            continue
        scored.append((food, name, score))

    # 메뉴가 아닌 문구(원산지 표시·홍보 문구·가게 이름)에서만 발견된 이름을 걸러낸다.
    # 좌표가 없으면 어느 상자에서 나왔는지 알 수 없어 이 검사를 건너뛴다.
    if boxes is not None:
        # 판정 대상은 이 줄의 상자, 크기를 견줄 기준은 사진 전체다.
        scored = [
            entry
            for entry in scored
            if _appears_on_a_menu_line(boxes, entry[1], reference=all_boxes or boxes)
        ]

    # 메뉴판에 글자 그대로 적혀 있는 이름들. 퍼지 후보를 거를 기준이 된다.
    exact_names = [name for _food, name, _score in scored if name in normalized_text]
    matches = [
        (food, name, score)
        for food, name, score in scored
        if not _is_part_of_longer_exact(name, exact_names)
        and (name in normalized_text or not _is_kin_of_exact(name, exact_names))
    ]

    prices = _resolve_prices(normalized_text, [name for _food, name, _score in matches], boxes)

    candidates = []
    for food, name, score in matches:
        spice_hits, ingredient_hits = _extract_modifiers(normalized_text, name)
        price_krw = prices.get(name)
        source_box = find_source_box(boxes, name) if boxes is not None else None
        # 이름이 얼마나 정확히 읽혔나(score)에, 그 글자를 읽을 때 인식 모델이 얼마나
        # 확신했나(신뢰도)를 곱한다. 글자만 보면 "비빔밥"과 정확히 일치하지만 모델이
        # 0.6밖에 확신하지 못한 경우와, 또렷하게 읽은 경우를 구분하기 위해서다.
        score = round(score * _reading_confidence(boxes, name))
        candidates.append(
            {
                "food_id": food["id"],
                "name_kr": food["name_kr"],
                "name_en": food["name_en"],
                "score": score,
                "modifiers": {"spice": spice_hits, "ingredient": ingredient_hits},
                # 그 음식 자체의 맵기(1~5). 후보 카드에 불꽃 눈금을 그리는 값이다.
                # 여기서 싣지 않으면 화면은 값을 못 받아 눈금을 영영 그리지 못한다.
                # .get()인 이유는 thumbnail과 같다 — 오래된 테스트 fixture에는 이 컬럼이 없다.
                "spice_level": food.get("spice_level"),
                # 이 후보가 사진 어디에서 나왔는지 — 좌표는 아직 전처리 이미지 기준이라
                # src/pipeline.py가 원본 사진 비율로 옮긴 뒤 응답에 싣는다.
                "source_text": source_box[4] if source_box else None,
                "source_box": source_box[:4] if source_box else None,
                # .get()으로 읽는 이유: 기존 테스트 fixture나 아직 사진이 없는 음식 row에는
                # 이 두 컬럼이 없을 수 있다 — 없으면 None으로 두고 프론트가 번호 아이콘으로 대체한다.
                "thumbnail_url": food.get("thumbnail_url"),
                "thumbnail_attribution": food.get("thumbnail_attribution"),
                # 메뉴판 사진 자체에서 읽은 가격이다(추정 아님) — 근처에 가격이 없으면 None.
                "price_krw": price_krw,
                "price_krw_display": format_price_krw(price_krw),
            }
        )

    return sorted(
        candidates,
        key=lambda candidate: (-candidate["score"], -len(candidate["name_kr"])),
    )


def match_food_candidates_by_line(boxes: list[TextBox]) -> list[dict]:
    """메뉴판을 **줄 단위로** 매칭한다 — 줄 하나가 후보 하나가 된다.

    ## 왜 줄 단위인가

    [match_food_candidates]는 메뉴판 글자를 한 덩어리로 보고 "등록 음식 하나당 후보
    하나"를 만든다. 그래서 두 가지가 어긋난다(2026-08-23 실측, 메뉴판 400장):

    1. **메뉴가 사라진다.** "물만두"와 "군만두"가 둘 다 있어도 `만두` 후보 하나로
       합쳐진다. 메뉴판의 32.8%에서 일어나고, 그렇게 사라지는 줄이 433개였다.
    2. **수식어가 남의 메뉴에 붙는다.** 수식어를 글자 덩어리 전체에서 찾아 모든
       후보에 똑같이 붙이기 때문에, 메뉴판 어딘가에 "해물"이 있으면 비빔밥에도
       "해물"이 붙는다. 수식어 부착 8,067건 중 **97.0%가 그 줄에 없는 것**이었다.

    줄로 잘라 넣으면 둘 다 사라진다. 정확도도 손해 보지 않는다 — 같은 표본에서
    정밀도 97.7% → 98.6%로 오히려 올랐다. 줄이 짧아 남의 이름 조각에 걸릴 여지가
    줄기 때문이다. (근거 스크립트: eval/measure_match_precision.py)

    ## 반환값

    [match_food_candidates]와 같은 모양에 `menu_text`(그 줄에 인쇄된 글자 그대로)가
    붙는다. **같은 `food_id`가 여러 번 나올 수 있다** — 그게 이 함수의 목적이다.
    호출하는 쪽은 food_id를 유일 키로 쓰면 안 된다.

    순서는 메뉴판을 읽는 순서(위→아래)다. 점수순으로 섞으면 화면의 카드 순서가
    실제 메뉴판과 어긋나서, 사용자가 눈으로 대조하기 어려워진다.
    """
    return scan_menu_lines(boxes)[0]


def _price_nearest_to_name(row: list[TextBox], name_box: TextBox | None) -> int | None:
    """줄에 값이 여럿일 때, 이름 상자에서 가장 가까운 값 하나를 고른다. 근거가 없으면 None.

    고르는 규칙을 새로 만들지 않고 match_prices_to_names()를 그대로 쓴다 — "같은 줄
    오른쪽 > 같은 줄 왼쪽 > 아래 > 위" 순서, "가격 하나는 메뉴 하나에만", 간격 상한이
    이미 그 안에 있다.

    그 함수가 이런 후보에서 빈손으로 돌아오는 이유는 **등록된 이름이 상자 글자에 통짜로
    없기 때문**이다(등록 "비빔국수" vs 상자 "코다리비빔막국수" — 닮은 정도로만 걸렸다).
    그래서 여기서는 등록 이름 대신 **이름 상자의 글자 자체**를 넘겨 그 문제를 비켜간다.

    기준으로 삼을 이름 상자가 없으면(줄이 전부 가격 상자) 고르지 않는다 — 어느 값이
    이 메뉴 것인지 가릴 근거가 없다.
    """
    if name_box is None:
        return None
    name = _normalize(name_box[4])
    if not name:
        return None
    normalized_row = [tuple(box[:4]) + (_normalize(box[4]),) for box in row]
    return match_prices_to_names(normalized_row, [name]).get(name)


def _fill_missing_from_row(candidates: list[dict], line: str, row: list[TextBox]) -> None:
    """줄 단위로 훑을 때만 쓰는 보정 — 이름을 글자로 못 찾아 비어 버린 자리를 그 줄에서 채운다.

    find_source_box()와 match_prices_to_names()는 등록된 이름이 상자 글자에 **그대로**
    들어 있어야 찾아낸다. 그런데 매칭 자체는 닮은 정도로도 성립한다(임계값 85) —
    메뉴판의 "콩물국수"가 등록된 "콩국수"에 걸리는 식이다. 그러면 이름이 어느 상자에도
    통짜로 없어서 위치도 가격도 잃고, 화면에는 **사진 상자도 가격도 없는 카드**만 남는다.

    여기서는 이 줄 하나가 메뉴 하나라는 것을 이미 알고 있으므로 줄에서 직접 집어 채운다.
    집는 방법은 _unsupported_menu_line()이 쓰는 것과 같다.

    ## 가격을 채울지 말지

    기준은 **값이 몇 개냐가 아니라 그 줄의 후보가 몇 개냐**다.

    - 후보가 둘 이상인 줄에서는 채우지 않는다. 줄 나누기가 2단 메뉴판에서 좌우 칸을
      한 줄로 묶는 일이 있어("낙지볶음 20171 코다리회무침"), 그런 줄에서 값을 나눠주면
      남의 가격이 붙는다.
    - 후보가 하나면, 줄에 값이 여럿이어도 채운다. 이 줄 = 이 메뉴 하나라는 것을 이미
      알고 있으니, 어느 값인지만 고르면 된다 — 이름 상자에서 가장 가까운 값을 쓴다
      (_price_nearest_to_name). 원래는 "값도 하나일 때"만 채웠는데, 그 조건이 너무 좁아
      실제 실패를 대부분 못 막았다(실측: "산낙지섯가 코다리비빔막국수 8,000 3,000"의
      비빔국수가 값을 못 받아 화면에 "가격 없음"이 떴다 — 지금은 가까운 8,000이 붙는다).
    - 고를 근거가 애매하면(이름 상자를 못 구했다, 간격이 상한을 넘는다) 채우지 않는다.

    없는 것보다 틀린 것이 나쁘다는 기존 판단(가격은 추정하지 않는다)은 그대로다 —
    넓힌 것은 "어느 값인지 확실히 가릴 수 있는 경우"까지일 뿐이다.
    """
    if not row:
        return

    # 이름 쪽 상자 — 가격이 없는 첫 상자다. 위치 표시에 쓰고(가격 상자를 가리키면 엉뚱한
    # 곳에 상자가 그려진다), 가격을 고를 때의 기준점으로도 쓴다.
    name_box = next((box for box in row if not find_prices(box[4])), None)
    source_box = name_box if name_box is not None else row[0]

    row_prices = find_prices(line)
    if len(candidates) != 1 or not row_prices:
        row_price = None
    elif len(row_prices) == 1:
        row_price = row_prices[0][2]
    else:
        row_price = _price_nearest_to_name(row, name_box)

    for candidate in candidates:
        if candidate.get("source_box") is None:
            candidate["source_text"] = source_box[4]
            candidate["source_box"] = tuple(source_box[:4])
        if candidate.get("price_krw") is None and row_price is not None:
            candidate["price_krw"] = row_price
            candidate["price_krw_display"] = format_price_krw(row_price)


def _display_line(row: list[TextBox], boxes: list[TextBox]) -> str:
    """화면에 내보낼 줄 글자 — 그 줄에서 안내 문장 상자를 뺀 나머지.

    menu_text는 주문 화면에서 **종업원에게 그대로 보여주는 글자**라, 가게 안내문이
    섞이면 주문이 어긋난다(실측 2026-08-27: 후보 "칼국수"의 menu_text가
    "산낙지주문시미리말쏨해주세요 칼국수사리"였다).

    거르는 판정은 [_is_non_menu_box]로, _unsupported_menu_line()이 쓰는 것과 같다.
    글자 크기를 다른 상자와 견주는 판정이라 사진 전체(boxes)가 필요하다.
    """
    return row_text([box for box in row if not _is_non_menu_box(box, boxes)])


# 홀로 떨어진 한 글자 한자. 등록 음식 50개도 메뉴판의 음식 이름도 한글이라, **낱말 하나가
# 통째로 한자 한 글자**인 자리는 이름이 아니라 인분(人)·맵기(辛)·크기(小中大) 표시이거나
# OCR 잡음이다(실측 2026-08-27, 테스트 사진 10장: 04번 카드의 이름이 "된장찌개 花"였고,
# 상자 글자에는 "欢"도 있었다. 팀원 보고: "참치김치찌개 人").
#
# **붙어 있는 한자는 건드리지 않는다** — "두루치기(小)"의 "(小)"는 낱말의 일부다.
# 가격 바로 앞의 크기 표시는 strip_prices()가 이미 떼고 있어(_PRICE_MARKS), 여기까지
# 남는 것은 가격과 떨어져 홀로 선 글자뿐이다.
_LONE_HANJA = re.compile(r"^[一-鿿]$")

# 숫자와 자릿수 구분(`,`·`.`)으로만 이루어진 낱말. 통화·"원" 표시가 붙은 것까지 본다.
#
# **자릿수 구분을 반드시 요구한다.** 맨숫자 한 조각("1", "2")까지 지우면 OCR이 띄어
# 읽은 "1 인분"의 앞 글자를 깎을 수 있다. 구분이 들어간 숫자는 값으로 적은 것 말고는
# 메뉴 이름에 쓰일 일이 없다.
_NUMBER_ONLY_TOKEN = re.compile(r"^[₩\\Ww]?\d+[,.][\d,.]*\d원?$")


def _is_orphan_number(token: str) -> bool:
    """가격으로도 안 읽히고 이름에도 못 붙는 숫자 조각인가.

    OCR이 "6,900"의 자릿수를 하나 흘려 "6.90"으로 읽으면, 그게 6,900인지 690인지
    글자만으로는 알 수 없어 find_prices()가 값으로 인정하지 않는다. 그러면
    strip_prices()도 뗄 자리를 못 찾아, 그 숫자가 **이름 자리에 그대로 남는다**
    (팀원 보고 2026-08-27: 카드에 "비빔냉면6.90", 가격은 "없음").

    값을 추정하지는 않는다 — 값이 없는 것보다 틀린 것이 나쁘다(PR #106). 다만 이름
    자리는 다르다. 그 글자는 화면에 이름으로 보이고 종업원에게 들려줄 말로도 쓰이므로
    (frontend/docs/web-app.md), 이름이 아닌 숫자는 빼는 쪽이 맞다.

    가격으로 읽히는지는 find_prices()에 그대로 물어본다 — 판정 규칙을 새로 만들지 않는다.
    """
    return bool(_NUMBER_ONLY_TOKEN.match(token)) and not find_prices(token)


def _clean_name_text(name_text: str) -> str:
    """화면 이름 자리에 쓸 글자에서 **이름일 수 없는 낱말**만 걷어낸다.

    가격을 뗀 뒤에도 이름 자리에는 이름이 아닌 조각이 남는다. 지우는 대상은 위 두
    가지뿐이고, 낱말 가운데는 손대지 않는다 — "숯불소갈비살1인분"·"삼겹살 200g"·
    "계란찜추가시"처럼 숫자와 단위가 이름의 일부인 메뉴가 실제로 있다.

    다 걷어내 남는 낱말이 없으면 원래 글자를 그대로 돌려준다. 이름 자리가 비는 편이
    잡음이 남는 것보다 나쁘다 — strip_prices()의 되돌림 규칙과 같다.

    **menu_text는 여기를 거치지 않는다.** 그쪽은 종업원에게 보여줄 원문이라 사진에
    인쇄된 글자를 있는 그대로 두어야 한다.
    """
    kept = [
        token
        for token in name_text.split()
        if not _LONE_HANJA.match(token) and not _is_orphan_number(token)
    ]
    return " ".join(kept) or name_text


def scan_menu_lines(boxes: list[TextBox]) -> tuple[list[dict], list[dict]]:
    """메뉴판을 줄 단위로 훑어 **안내 가능한 후보**와 **그러지 못한 메뉴 줄**을 함께 돌려준다.

    등록 음식이 50개뿐이라 메뉴판 대부분은 매칭되지 않는다 — 실측(메뉴판 10,005장,
    음료·주류 제외) 결과 안내 가능한 줄은 **22.9%**뿐이었다. 매칭 안 된 줄을 버리면
    메뉴판의 대부분이 화면에서 사라져, 여행자는 그 메뉴가 존재하지 않는 것처럼 본다.

    설명을 못 해도 **이름과 가격은 보여줄 수 있다.** 이 앱의 주문 확인 화면은
    종업원에게 "이거 주세요"를 보여주는 자리이고, 그건 음식 설명 없이도 성립한다.

    다만 메뉴판에는 가게 이름·전화번호·원산지 표시 같은 줄도 있다. 그런 걸 다 내보내면
    목록이 쓰레기로 찬다. **가격이 붙어 있는 줄만** 메뉴로 본다 — 메뉴판에서 값이
    적혀 있다는 건 "파는 것"이라는 가장 확실한 신호다.

    반환: (후보 목록, 안내 못 하는 메뉴 줄 목록). 둘 다 `line_no`(위에서부터 센 줄
    번호)를 달고 있어, 화면이 둘을 합쳐 메뉴판 순서대로 늘어놓을 수 있다.
    """
    candidates: list[dict] = []
    unsupported: list[dict] = []

    for line_no, row in enumerate(_menu_entries(boxes)):
        line = row_text(row)
        if not line:
            continue

        # 간판 판별에는 사진 전체를 넘긴다 — 글자 크기를 서로 견줘야 알 수 있다.
        matches = match_food_candidates(line, boxes=row, all_boxes=boxes)

        # 화면에 나가는 글자에서만 안내 문장을 뺀다. 매칭·가격에 쓰는 line은 그대로 둔다 —
        # 그쪽은 이미 all_boxes로 안내 문구를 걸러내고 있어서(match_food_candidates,
        # _is_non_menu_box), 여기서 글자를 줄이면 판정 근거만 잃는다.
        # 안내 상자를 다 빼면 남는 글자가 없을 수 있다. 그때는 원래 줄 글자를 쓴다 —
        # 종업원에게 보여줄 것이 아예 없어지는 편이 더 나쁘다.
        display_line = _display_line(row, boxes) or line
        # 가격을 뗀 이름 쪽 글자. 화면이 가격을 따로 보여주므로 이름 자리에는 이걸 쓴다.
        # 뗄 것이 없으면(가격 없는 줄) 줄 글자가 그대로 남는다.
        # 가격을 떼도 이름이 아닌 조각은 남으므로 한 번 더 정리한다(_clean_name_text).
        name_text = _clean_name_text(strip_prices(display_line) or display_line)

        # 한 줄에서 같은 음식이 두 번 나오면 점수가 높은 쪽만 남긴다. 줄 하나가
        # 카드 하나라는 약속이 깨지면 화면에 같은 카드가 겹쳐 보인다.
        seen: dict[int, dict] = {}
        for candidate in matches:
            candidate["menu_text"] = display_line
            candidate["name_text"] = name_text
            candidate["line_no"] = line_no
            kept = seen.get(candidate["food_id"])
            if kept is None or candidate["score"] > kept["score"]:
                seen[candidate["food_id"]] = candidate

        if seen:
            _fill_missing_from_row(list(seen.values()), line, row)
            candidates.extend(seen.values())
            continue

        line_only = _unsupported_menu_line(line, row, boxes, line_no)
        if line_only is not None:
            unsupported.append(line_only)

    return candidates, unsupported


# 이름으로 인정할 최소 한글 글자 수. 한 글자는 "원"·"소"·"대"처럼 값이나 크기 표시일
# 수 있어 이름으로 보기 어렵다.
_MIN_NAME_LETTERS = 2


def _has_korean_name(line: str, prices: list[tuple[int, int, int]]) -> bool:
    """가격 토큰을 뺀 자리에 한글 이름이 남아 있는가."""
    remaining = list(line)
    for start, end, _value in prices:
        for index in range(start, min(end, len(remaining))):
            remaining[index] = " "
    letters = sum(1 for char in remaining if "가" <= char <= "힣")
    return letters >= _MIN_NAME_LETTERS


def _looks_like_a_name(text: str) -> bool:
    """이 상자가 '메뉴 이름'을 담고 있는가 — 가격을 뺀 자리에 한글이 남는가."""
    return _has_korean_name(text, find_prices(text))


# 칸 경계로 인정하려면 몇 줄에서 같은 자리가 나와야 하는가. 한 줄만 그렇다고 사진
# 전체에 적용하면 우연히 벌어진 간격 하나로 멀쩡한 줄이 부서진다. 실측(테스트 10장 +
# 2단_최우선_후보)에서 진짜 칸 경계는 4~12줄이 같은 자리를 가리켰고, 근거가 1줄뿐인
# 자리는 전부 가짜였다(02번 x=689, 09번 x=616·1294). 2줄이면 가짜는 다 걸러지고,
# 09번 x=557(산낙지 칸 / 코다리 칸 경계)처럼 근거가 적은 진짜는 살아남는다.
_COLUMN_EVIDENCE_MIN_ROWS = 2


def _column_boundaries(rows: list[list[TextBox]], boxes: list[TextBox]) -> list[list[float]]:
    """줄마다 적용할 **칸 경계 x**를 구한다 — 돌려주는 목록은 `rows`와 길이가 같다.

    [_menu_entries]의 "가격 뒤 이름" 규칙은 줄 하나만 본다. 그래서 그 줄에 신호가
    없으면 못 자른다 — 실측 예: `산낙지섯가 코다리비빔막국수 8,000 3,000`은
    [이름][이름][가격]이라 두 이름 사이에 가격이 없고, `궁중삼계탕 쑥궁중 삼계탕`은
    줄에 가격이 아예 없다. 둘 다 왼쪽 칸과 오른쪽 칸이 한 항목으로 뭉친다.

    한 줄에는 신호가 없어도 **사진 전체를 모으면 경계가 드러난다.** 2단 메뉴판은 칸
    위치가 위아래로 같으므로, 규칙이 실제로 자른 자리의 x가 몇 줄에 걸쳐 같은 곳에
    뭉친다(실측 09번: 자른 자리 8곳 중 4곳이 x≈1041 한 자리). 그 자리를 칸 경계로
    보고, 규칙이 못 자른 줄에도 같이 적용한다.

    **근거를 규칙이 자른 자리에서만 얻는 것이 안전장치다.** 1단 메뉴판에서는 규칙이
    한 번도 안 걸리므로 경계가 하나도 안 나오고, 따라서 아무 줄도 쪼개지지 않는다
    (실측: 1단인 10번과 한 칸짜리인 01·03·07번 모두 0개).
    """
    per_row: list[list[float]] = [[] for _ in rows]
    if not boxes:
        return per_row

    # 규칙이 실제로 자른 자리 — (경계 x, 그 줄 번호).
    spots: list[tuple[float, int]] = []
    for row_no, row in enumerate(rows):
        seen_price = False
        previous: TextBox | None = None
        for box in row:
            if seen_price and previous is not None and _looks_like_a_name(box[4]):
                # 경계는 앞 상자가 끝난 곳과 이 상자가 시작하는 곳 사이 어딘가다.
                spots.append(((previous[0] + previous[2] + box[0]) / 2, row_no))
                seen_price = False
            previous = box
            if find_prices(box[4]):
                seen_price = True

    # 같은 칸 경계라도 줄마다 몇 픽셀씩 어긋난다. 글자 높이만큼 떨어진 것까지 한 자리로
    # 본다 — 줄 나누기(group_boxes_into_row_groups)도 상자 높이의 중앙값을 잣대로 쓴다.
    tolerance = statistics.median(float(box[3]) for box in boxes)

    for group in _cluster_by_gap(sorted(spots), tolerance):
        supporters = {row_no for _x, row_no in group}
        if len(supporters) < _COLUMN_EVIDENCE_MIN_ROWS:
            continue
        boundary = statistics.median(x for x, _row_no in group)
        for row_no in _rows_the_boundary_runs_through(rows, boundary, supporters):
            per_row[row_no].append(boundary)
    return per_row


def _cluster_by_gap(
    spots: list[tuple[float, int]],
    tolerance: float,
) -> list[list[tuple[float, int]]]:
    """x로 정렬된 자리들을 `tolerance`보다 멀리 떨어진 곳에서 끊어 묶는다."""
    groups: list[list[tuple[float, int]]] = []
    for spot in spots:
        if groups and spot[0] - groups[-1][-1][0] <= tolerance:
            groups[-1].append(spot)
        else:
            groups.append([spot])
    return groups


def _rows_the_boundary_runs_through(
    rows: list[list[TextBox]],
    boundary: float,
    supporters: set[int],
) -> set[int]:
    """이 경계가 **끊기지 않고 이어지는** 줄들만 고른다.

    한 메뉴판 안에서도 구역마다 칸 짜임새가 다르다. 실측 06번이 그렇다 — 위쪽 음식
    구역은 [이름][인분][가격] 2단인데, 아래 술 구역은 [이름][가격][이름][가격] 4단이라
    x≈1112에 술 구역만의 경계가 생긴다. 그걸 사진 전체에 쓰면 위쪽 `아바이순대`와 그
    가격 `20,000` 사이를 갈라, 멀쩡하던 가격 6개가 사라졌다.

    경계는 사진 위의 **세로 빈 통로**다. 글자가 통로를 가로지르는 줄에서 통로는 끊긴다.
    그래서 근거가 나온 줄에서 위아래로, 가로지르는 줄을 만날 때까지만 넓힌다. 06번은
    `아바이순대모둠`(x 877~1136)이 1112를 가로질러 술 구역에서 딱 멈춘다.
    """
    covered: set[int] = set()
    segment: list[int] = []  # 통로가 안 끊긴 채 이어지는 줄 묶음
    for row_no, row in enumerate(rows):
        if any(box[0] < boundary < box[0] + box[2] for box in row):
            if supporters.intersection(segment):
                covered.update(segment)
            segment = []  # 여기서 통로가 끊긴다 — 다음 줄부터 새 묶음
        else:
            segment.append(row_no)
    if supporters.intersection(segment):  # 마지막 묶음
        covered.update(segment)
    return covered


def _menu_entries(boxes: list[TextBox]) -> list[list[TextBox]]:
    """글자 상자를 **메뉴 항목 단위**로 묶는다.

    [group_boxes_into_row_groups]는 세로 위치만 보고 줄을 나눈다. 1단 메뉴판에서는
    그게 곧 메뉴 하나지만, **2단 메뉴판에서는 왼쪽 칸과 오른쪽 칸이 같은 높이라
    한 줄로 뭉친다.** 그러면 한 항목에 이름과 가격이 두 벌씩 들어가, 어느 가격을
    집어도 틀린다(실측 예: "김치김밥 3,500 퍼퍼00 5,000 다 슬 기 9,").

    자르는 신호는 둘이고, **둘 중 하나만 걸려도 자른다.**

    1. 가로로 훑다가 **가격이 이미 나온 뒤에 또 이름이 나오면** 거기가 칸 경계다.
       1단에서는 이름 뒤에 가격이 오고 끝나므로 쪼개지지 않고, 2단에서는
       [이름][가격][이름][가격]이라 정확히 사이에서 갈린다.
    2. 사진 전체에서 구한 **칸 경계 x**를 지나가면 거기가 칸 경계다([_column_boundaries]).
       1번은 줄 하나만 봐서, 왼쪽 칸 가격이 그 줄에 없거나([이름][이름][가격]) 줄에
       가격이 아예 없으면 못 자른다. 2번은 그 줄에 신호가 없어도 자른다.

    칸이 셋 이상이어도 같은 규칙이 그대로 적용된다.
    """
    rows = group_boxes_into_row_groups(boxes)
    boundaries_by_row = _column_boundaries(rows, boxes)

    entries: list[list[TextBox]] = []
    for row, boundaries in zip(rows, boundaries_by_row):
        current: list[TextBox] = []
        seen_price = False
        for box in row:
            text = box[4]
            if current and (
                (seen_price and _looks_like_a_name(text))
                or _crosses_a_column_boundary(current, box, boundaries)
            ):
                entries.append(current)
                current = []
                seen_price = False
            current.append(box)
            if find_prices(text):
                seen_price = True
        if current:
            entries.append(current)
    return entries


def _crosses_a_column_boundary(
    current: list[TextBox],
    box: TextBox,
    boundaries: list[float],
) -> bool:
    """지금까지 모은 상자들과 이 상자 **사이의 빈틈**에 칸 경계가 들어 있는가.

    경계가 상자 한가운데를 지나면 자르지 않는다 — OCR이 이름과 가격을 한 상자로
    뭉쳐 읽은 경우(실측: "섞어국밥3.")가 그렇고, 그건 여기서 고칠 수 있는 일이 아니다.
    빈틈에 들어 있을 때만 자르므로 상자를 쪼개는 일은 생기지 않는다.
    """
    # 한 줄 안에서 상자가 겹쳐 읽히기도 해서(작은 첨자가 큰 이름 위에 겹침) 바로 앞
    # 상자가 아니라 지금까지 모은 것 중 가장 오른쪽 끝을 본다.
    left = max(kept[0] + kept[2] for kept in current)
    return any(left <= boundary <= box[0] for boundary in boundaries)


def _unsupported_menu_line(
    line: str,
    row: list[TextBox],
    boxes: list[TextBox],
    line_no: int,
) -> dict | None:
    """매칭되지 않은 줄을 '안내 없는 메뉴'로 내보낼지 판단하고, 내보낼 모양으로 만든다.

    가격이 없으면 메뉴 줄로 보지 않는다(가게 이름·안내문·전화번호). 안내 문구·원산지
    표시로 이미 걸러지는 줄도 제외한다 — 그 판정은 [_is_non_menu_box]가 한다.

    **가격을 뺀 자리에 한글 이름이 남아야 한다.** 숫자만 있는 줄은 메뉴가 아니다 —
    실측에서 생맥주 용량 표기 "(500/1700/2700)"이 값 세 개로 읽혀 메뉴 카드로
    올라왔다. 이름이 없는 메뉴는 존재하지 않으므로, 이름 유무가 가장 확실한 잣대다.
    """
    prices = find_prices(line)
    if not prices:
        return None
    if not _has_korean_name(line, prices):
        return None
    if all(_is_non_menu_box(box, boxes) for box in row):
        return None

    price_krw = prices[-1][2]  # 한 줄에 값이 여럿이면(小/大) 가장 뒤가 그 줄의 값이다
    # 이름 쪽 상자를 위치 표시에 쓴다 — 가격 상자에 상자를 그리면 엉뚱한 곳을 가리킨다.
    name_box = next((box for box in row if not find_prices(box[4])), row[0])
    return {
        "line_no": line_no,
        "menu_text": line,
        # 가격을 뗀 이름 쪽 글자. 이 줄은 등록 음식이 아니라 이름 자리에 줄 글자를
        # 그대로 쓰는데, 그러면 화면에 가격이 두 번 보인다.
        # 후보 줄과 같은 자리이므로 정리도 같은 것을 쓴다(_clean_name_text).
        "name_text": _clean_name_text(strip_prices(line) or line),
        "price_krw": price_krw,
        "price_krw_display": format_price_krw(price_krw),
        "source_text": name_box[4],
        "source_box": tuple(name_box[:4]),
    }
