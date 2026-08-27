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


def _fill_missing_from_row(candidates: list[dict], line: str, row: list[TextBox]) -> None:
    """줄 단위로 훑을 때만 쓰는 보정 — 이름을 글자로 못 찾아 비어 버린 자리를 그 줄에서 채운다.

    find_source_box()와 match_prices_to_names()는 등록된 이름이 상자 글자에 **그대로**
    들어 있어야 찾아낸다. 그런데 매칭 자체는 닮은 정도로도 성립한다(임계값 85) —
    메뉴판의 "콩물국수"가 등록된 "콩국수"에 걸리는 식이다. 그러면 이름이 어느 상자에도
    통짜로 없어서 위치도 가격도 잃고, 화면에는 **사진 상자도 가격도 없는 카드**만 남는다.

    여기서는 이 줄 하나가 메뉴 하나라는 것을 이미 알고 있으므로 줄에서 직접 집어 채운다.
    집는 방법은 _unsupported_menu_line()이 쓰는 것과 같다.

    가격은 **줄에 값이 하나뿐이고 그 줄의 후보도 하나뿐일 때만** 채운다. 줄 나누기가
    2단 메뉴판에서 좌우 칸을 한 줄로 묶는 일이 있어("낙지볶음 20171 코다리회무침"),
    그런 줄에서 값을 나눠주면 남의 가격이 붙는다. 없는 것보다 틀린 것이 나쁘다는
    기존 판단(가격은 추정하지 않는다)을 그대로 지킨다.
    """
    if not row:
        return

    # 이름 쪽 상자를 위치 표시에 쓴다 — 가격 상자를 가리키면 엉뚱한 곳에 상자가 그려진다.
    name_box = next((box for box in row if not find_prices(box[4])), row[0])

    row_prices = find_prices(line)
    lone_price = row_prices[0][2] if len(row_prices) == 1 and len(candidates) == 1 else None

    for candidate in candidates:
        if candidate.get("source_box") is None:
            candidate["source_text"] = name_box[4]
            candidate["source_box"] = tuple(name_box[:4])
        if candidate.get("price_krw") is None and lone_price is not None:
            candidate["price_krw"] = lone_price
            candidate["price_krw_display"] = format_price_krw(lone_price)


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

        # 한 줄에서 같은 음식이 두 번 나오면 점수가 높은 쪽만 남긴다. 줄 하나가
        # 카드 하나라는 약속이 깨지면 화면에 같은 카드가 겹쳐 보인다.
        # 가격을 뗀 이름 쪽 글자. 화면이 가격을 따로 보여주므로 이름 자리에는 이걸 쓴다.
        # 뗄 것이 없으면(가격 없는 줄) 줄 글자가 그대로 남는다.
        name_text = strip_prices(line) or line

        seen: dict[int, dict] = {}
        for candidate in matches:
            candidate["menu_text"] = line
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


def _menu_entries(boxes: list[TextBox]) -> list[list[TextBox]]:
    """글자 상자를 **메뉴 항목 단위**로 묶는다.

    [group_boxes_into_row_groups]는 세로 위치만 보고 줄을 나눈다. 1단 메뉴판에서는
    그게 곧 메뉴 하나지만, **2단 메뉴판에서는 왼쪽 칸과 오른쪽 칸이 같은 높이라
    한 줄로 뭉친다.** 그러면 한 항목에 이름과 가격이 두 벌씩 들어가, 어느 가격을
    집어도 틀린다(실측 예: "김치김밥 3,500 퍼퍼00 5,000 다 슬 기 9,").

    가로로 훑다가 **가격이 이미 나온 뒤에 또 이름이 나오면** 거기를 칸 경계로 본다.
    1단에서는 이름 뒤에 가격이 오고 끝나므로 쪼개지지 않고, 2단에서는
    [이름][가격][이름][가격]이라 정확히 사이에서 갈린다.

    칸이 셋 이상이어도 같은 규칙이 그대로 적용된다.
    """
    entries: list[list[TextBox]] = []
    for row in group_boxes_into_row_groups(boxes):
        current: list[TextBox] = []
        seen_price = False
        for box in row:
            text = box[4]
            if seen_price and _looks_like_a_name(text):
                entries.append(current)
                current = []
                seen_price = False
            current.append(box)
            if find_prices(text):
                seen_price = True
        if current:
            entries.append(current)
    return entries


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
        "name_text": strip_prices(line) or line,
        "price_krw": price_krw,
        "price_krw_display": format_price_krw(price_krw),
        "source_text": name_box[4],
        "source_box": tuple(name_box[:4]),
    }


def match_food(text: str) -> dict | None:
    """Return the highest-ranked supported food candidate for existing callers."""
    candidates = match_food_candidates(text)
    return candidates[0] if candidates else None
