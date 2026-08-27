"""메뉴판 원화 가격 인식 — OCR 텍스트에서 "9,000원"·"9,000" 같은 가격 토큰을 찾아 음식명과 짝짓는다.

메뉴판마다 가격을 적는 자리가 다르다 — 이름 오른쪽, 이름 바로 아래(사진형 메뉴판),
2단 구성이라 한 줄에 메뉴가 둘. 그래서 글자를 이어붙인 문자열이 아니라 **사진 위의
좌표**를 보고 짝짓는다(match_prices_to_names). `src/ocr/infer.py`의 recognize_boxes()가
주는 (x, y, w, h, text) 상자 목록이 입력이다.

extract_price_near()는 좌표가 없을 때(옛 호출부·테스트)만 쓰는 글자 거리 기반 대체 경로다.
"""

import re
import statistics
from typing import NamedTuple

class TextBox(NamedTuple):
    """OCR이 찾은 글자 상자 하나 — src/ocr/infer.py의 recognize_boxes() 출력.

    confidence는 인식 모델이 이 글자를 얼마나 확신했는지(0~1)다. 좌표와 글자만 쓰는 곳은
    앞의 다섯 개만 보므로, 그런 자리에는 5개짜리 평범한 튜플을 넘겨도 그대로 동작한다.
    """

    x: int
    y: int
    width: int
    height: int
    text: str
    confidence: float = 1.0

    @property
    def center_x(self) -> float:
        return self.x + self.width / 2

    @property
    def center_y(self) -> float:
        return self.y + self.height / 2

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        """(좌, 상, 우, 하) — 좌상단/우하단 좌표."""
        return self.x, self.y, self.x + self.width, self.y + self.height


def box_confidence(box: TextBox | None) -> float:
    """상자를 읽을 때의 인식 신뢰도. 신뢰도가 없는 5개짜리 튜플이면 1.0으로 본다."""
    if box is None or len(box) < 6:
        return 1.0
    return float(box[5])

# 숫자 토큰을 넓게 잡고, 가격인지 아닌지는 아래 _is_price()에서 판정한다.
# 실제 메뉴판은 "9,000원"보다 "9,000"·"9000"처럼 원 없이 숫자만 적는 경우가 훨씬 많아서
# 정규식 단계에서 "원"을 요구하면 대부분의 가격을 놓친다.
#
# 앞뒤 lookaround로 "더 긴 숫자열의 일부"를 잘라 쓰는 걸 막는다 —
# 전화번호(010-1234-5678)나 사업자번호처럼 하이픈으로 이어진 숫자를 통째로 배제하기 위함.
_NUMBER_TOKEN = re.compile(
    r"(?<![0-9,.\-])"
    r"(?P<currency>[₩\\])?\s*"
    r"(?P<digits>\d{1,3}(?:[,.]\d{3})+|\d{3,6})"
    r"(?![0-9,.\-])"
    r"\s*(?P<won>원)?"
)

# 천 단위를 줄여 적은 표기 — "13.0"은 13,000원, "3.5"는 3,500원이다.
#
# 한국 메뉴판에서 꽤 흔한 방식인데(실측: 강원 칠판 메뉴판 한 장이 전부 이 표기),
# 위 _NUMBER_TOKEN은 점 뒤에 **세 자리**를 요구해서 "13.0"을 아예 못 잡는다.
# 그래서 가격이 통째로 비어 보이고, 메뉴 줄인지 판단하는 근거도 사라진다.
#
# 소수 한 자리만 받는다. "9.000"처럼 세 자리가 오는 유럽식 천 단위 표기는 위
# _NUMBER_TOKEN이 이미 처리하므로 여기서 겹치지 않는다.
_THOUSAND_TOKEN = re.compile(
    r"(?<![0-9,.\-])(?P<whole>\d{1,3})[.](?P<tenth>\d)(?![0-9,.\-])"
)

# 통화 표시(₩ 또는 원)가 붙은 경우 허용 범위 — 100원짜리 사이드부터 99만원대 코스까지.
_MARKED_MIN, _MARKED_MAX = 100, 999_999
# 표시가 없는 맨숫자는 오탐 위험이 크므로 더 좁게 본다.
_BARE_MIN, _BARE_MAX = 500, 500_000

# 상자 두 개를 "같은 줄"로 볼 세로 겹침 비율 (낮은 쪽 높이 기준). 사진이 살짝 기울어
# 글자 상자가 어긋나도 같은 줄로 묶이도록 넉넉하게 잡는다.
_ROW_OVERLAP_RATIO = 0.4
# 상자 두 개를 "같은 칸(세로 열)"으로 볼 가로 겹침 비율 (좁은 쪽 폭 기준).
# 이름보다 가격 글자가 짧은 게 보통이라 이쪽은 더 느슨하게 본다.
_COLUMN_OVERLAP_RATIO = 0.3
# 이름 위/아래 가격을 짝으로 볼 최대 세로 간격 — 글자 높이의 배수.
# 바로 다음 줄이 아니어도(사이에 설명 줄이 있는 메뉴판) 잡히도록 3줄까지 본다.
_MAX_VERTICAL_GAP_LINES = 3.0
# 같은 줄에서 이름과 가격이 떨어져 있어도 짝으로 볼 최대 가로 간격 — 글자 영역 전체 폭 대비.
# 넉넉하게 잡는다. 가격을 오른쪽 끝에 몰아 적는 메뉴판에서는 **이름이 짧을수록 간격이
# 벌어져서**, 좁게 잡으면 "순대" 같은 두 글자 메뉴만 골라서 가격을 잃는다(실측: 간격 762 >
# 상한 715). 실질적인 안전장치는 아래 _rank_pair()의 "사이에 다른 메뉴 이름 없음" 검사이고,
# 이 상한은 같은 줄 반대편 끝의 무관한 숫자를 걸러내는 최후의 방어선일 뿐이다.
_MAX_HORIZONTAL_GAP_RATIO = 0.9

# 좌표 없이 글자 거리만으로 찾을 때(extract_price_near) 짝으로 볼 최대 글자 수.
_MAX_DISTANCE_CHARS = 20


# OCR이 숫자를 글자로 헷갈리는 대표 쌍. 실제 관측된 오인식에서 뽑았다 —
# eval/measure_ocr_final.json(실제 메뉴판 50장)에 '0I', 's0' 같은 토큰이 남아 있고,
# eval/measure_digits.py 실행 결과에는 '9,000' -> 'C0' 처럼 9가 C로 바뀐 사례가 있다.
_DIGIT_LOOKALIKES = {
    "O": "0", "o": "0", "D": "0", "Q": "0", "C": "0",
    "I": "1", "l": "1", "i": "1", "|": "1",
    "Z": "2", "z": "2",
    "S": "5", "s": "5",
    "G": "6",
    "B": "8",
}

# 숫자·숫자 닮은꼴·자릿수 구분자로만 이루어진 덩어리. 이 덩어리 안에서만 복원한다.
_NUMERIC_RUN = re.compile(r"[0-9%s,.₩]{2,}" % "".join(_DIGIT_LOOKALIKES))


def _repair_run(run: str) -> str:
    """숫자 덩어리 하나를 복원한다. 진짜 숫자가 하나도 없으면 손대지 않는다.

    "진짜 숫자가 최소 하나"라는 조건이 안전장치다. 이게 없으면 "SOS"나 "ISBN" 같은
    멀쩡한 글자가 "505", "158N"으로 바뀐다.
    """
    if not any(character.isdigit() for character in run):
        return run
    return "".join(_DIGIT_LOOKALIKES.get(character, character) for character in run)


def repair_digit_lookalikes(text: str) -> str:
    """가격 파싱 전에 숫자 오인식을 되돌린다.

    글자 수가 변하지 않는 1:1 치환만 한다 — find_prices()가 돌려주는 위치가 원본 텍스트
    기준으로 유지돼야 가격 상자를 사진 위에서 다시 찾을 수 있기 때문이다.
    """
    return _NUMERIC_RUN.sub(lambda match: _repair_run(match.group(0)), text)


def _is_price(value: int, *, has_currency_mark: bool, has_separator: bool) -> bool:
    """숫자 토큰 하나가 "메뉴 가격"으로 볼 만한지 판정한다.

    ₩·원이 붙어 있으면 그 자체가 가격이라는 표시이므로 범위만 확인한다.
    아무 표시 없는 맨숫자는 자릿수 구분(9,000)이 있거나 100원 단위로 떨어질 때만
    가격으로 인정한다 — 한국 메뉴 가격은 사실상 전부 100원 단위라서, 이 조건만으로도
    좌석번호·연도·수량 같은 숫자를 상당 부분 걸러낼 수 있다.
    """
    if has_currency_mark:
        return _MARKED_MIN <= value <= _MARKED_MAX
    if not (_BARE_MIN <= value <= _BARE_MAX):
        return False
    return has_separator or value % 100 == 0


def find_prices(text: str) -> list[tuple[int, int, int]]:
    """text에 있는 모든 원화 가격 토큰을 (시작 위치, 끝 위치, 가격) 목록으로 돌려준다.

    위치는 **원본 text 기준**이다. 숫자 오인식 복원은 글자 수를 바꾸지 않으므로
    복원본에서 찾은 위치를 그대로 쓸 수 있다.
    """
    repaired = repair_digit_lookalikes(text)

    prices = []
    for match in _NUMBER_TOKEN.finditer(repaired):
        digits = match.group("digits")
        has_separator = "," in digits or "." in digits
        has_currency_mark = bool(match.group("currency") or match.group("won"))
        value = int(digits.replace(",", "").replace(".", ""))
        if not _is_price(value, has_currency_mark=has_currency_mark, has_separator=has_separator):
            continue
        prices.append((match.start("digits"), match.end(), value))

    # "13.0" 같은 천 단위 축약 표기. 위 정규식은 점 뒤 세 자리를 요구해 이걸 못 잡는다.
    for match in _THOUSAND_TOKEN.finditer(repaired):
        value = int(match.group("whole")) * 1000 + int(match.group("tenth")) * 100
        # 맨숫자와 같은 잣대로 본다 — 축약 표기에도 통화 표시가 붙는 일은 드물다.
        if not _BARE_MIN <= value <= _BARE_MAX:
            continue
        prices.append((match.start(), match.end(), value))

    prices.sort()
    return prices


def extract_price_near(text: str, food_name: str, max_distance: int = _MAX_DISTANCE_CHARS) -> int | None:
    """text에서 food_name 근처(문자 max_distance 이내)의 원화 가격을 찾는다.

    여러 후보가 있으면 음식명과 가장 가까운 것을 쓴다 — 메뉴판에 다른 음식의 가격이
    더 뒤에 있어서 잘못 붙는 걸 줄이기 위해. 음식명을 못 찾거나 근처에 가격이 없으면
    None (가격 정보 없음 — 임의로 추정하지 않는다).
    """
    name_index = text.find(food_name)
    if name_index == -1:
        return None
    name_end = name_index + len(food_name)

    best_price = None
    best_key = None  # (거리, 뒤쪽이면 0 앞쪽이면 1) — 거리가 같으면 "이름 뒤 가격"을 우선한다
    for start, end, price in find_prices(text):
        if start >= name_end:
            distance, is_before = start - name_end, 0
        elif end <= name_index:
            distance, is_before = name_index - end, 1
        else:
            distance, is_before = 0, 0  # 겹치는 경우(사실상 있을 수 없지만) 가장 가까운 것으로 취급
        if distance > max_distance:
            continue

        key = (distance, is_before)
        if best_key is None or key < best_key:
            best_key, best_price = key, price

    return best_price


class _Token(NamedTuple):
    """사진 위에서 글자 조각 하나가 차지하는 사각형 — 이름 토큰과 가격 토큰 공용."""

    left: float
    right: float
    top: float
    bottom: float


def _slice_token(box: TextBox, start: int, end: int) -> _Token:
    """상자 하나 안에서 [start, end) 구간이 차지하는 위치를 글자 수 비례로 추정한다.

    detection이 "비빔밥 9,000"을 상자 하나로 잡는 경우가 흔하다. 그때 이름과 가격의
    좌우 관계를 알려면 상자 안에서의 대략적인 x 위치가 필요하다. 글자 폭이 다 같다고
    보고 나누는 근사지만, 좌우 순서를 가리는 데는 충분하다.
    """
    x, y, width, height, text = box[:5]
    length = len(text) or 1
    return _Token(
        left=x + width * (start / length),
        right=x + width * (end / length),
        top=float(y),
        bottom=float(y + height),
    )


def _overlap(a_low: float, a_high: float, b_low: float, b_high: float) -> float:
    """두 구간이 겹치는 길이. 안 겹치면 음수가 나오고, 그 부호를 호출부가 그대로 쓴다."""
    return min(a_high, b_high) - max(a_low, b_low)


def _is_same_row(a: _Token, b: _Token) -> bool:
    """두 글자 상자가 같은 줄에 있는가 — 세로로 얼마나 겹치는지로 판단한다.

    겹친 길이를 **짧은 쪽 높이**와 견준다. 큰 쪽에 견주면 큰 글자 옆의 작은 첨자가
    늘 "다른 줄"로 밀려난다.
    """
    shorter = min(a.bottom - a.top, b.bottom - b.top)
    return shorter > 0 and _overlap(a.top, a.bottom, b.top, b.bottom) >= _ROW_OVERLAP_RATIO * shorter


def _is_same_column(a: _Token, b: _Token) -> bool:
    """두 글자 상자가 세로로 같은 자리에 있는가 — 가로로 얼마나 겹치는지로 판단한다.

    가격을 이름 **아래**에 적는 사진형 메뉴판에서 이름과 값을 잇는 데 쓴다.
    """
    narrower = min(a.right - a.left, b.right - b.left)
    return narrower > 0 and _overlap(a.left, a.right, b.left, b.right) >= _COLUMN_OVERLAP_RATIO * narrower


def _rank_pair(
    name: _Token,
    price: _Token,
    rivals: list[_Token],
    line_height: float,
    content_width: float,
) -> tuple[int, float] | None:
    """이름 토큰과 가격 토큰이 짝일 가능성을 (순위, 간격)으로 매긴다. 짝이 아니면 None.

    순위는 메뉴판을 읽는 순서 그대로다: 같은 줄 오른쪽 > 같은 줄 왼쪽 > 바로 아래 > 바로 위.

    핵심은 rivals(다른 음식 이름들)를 이용한 "사이에 낀 것 없음" 검사다. 사람이 메뉴판을
    읽을 때 이름과 가격 사이에 다른 메뉴 이름이 끼어 있으면 그 가격은 내 것이 아니라고
    판단하는데, 그 규칙을 그대로 옮긴 것이다. 거리 상한만으로는 2단 메뉴판이나 줄 간격이
    넓은 메뉴판에서 남의 가격을 끌어오는 걸 막지 못한다.
    """
    if _is_same_row(name, price):
        if price.left >= name.right:
            gap, tier = price.left - name.right, 0
            blocked = any(
                _is_same_row(name, rival) and name.right <= rival.left < price.left for rival in rivals
            )
        elif price.right <= name.left:
            gap, tier = name.left - price.right, 1
            blocked = any(
                _is_same_row(name, rival) and price.right < rival.right <= name.left for rival in rivals
            )
        else:
            return None  # 이름과 가격이 겹쳐서 잡힘 — 좌우를 못 가린다
        if blocked or gap > _MAX_HORIZONTAL_GAP_RATIO * content_width:
            return None
        return tier, gap

    if _is_same_column(name, price):
        if price.top >= name.bottom:
            gap, tier = price.top - name.bottom, 2
            blocked = any(
                _is_same_column(name, rival) and name.bottom <= rival.top < price.top for rival in rivals
            )
        elif price.bottom <= name.top:
            gap, tier = name.top - price.bottom, 3
            blocked = any(
                _is_same_column(name, rival) and price.bottom < rival.bottom <= name.top for rival in rivals
            )
        else:
            return None
        if blocked or gap > _MAX_VERTICAL_GAP_LINES * line_height:
            return None
        return tier, gap

    # 같은 줄도 같은 칸도 아닌 **대각선** 배치. 이름은 왼쪽 위, 가격은 오른쪽 아래 식이다:
    #     등뼈찜
    #                 44,000
    # 이름 줄에 가격을 못 붙였을 때 마지막으로 여기까지 본다. 순위를 가장 뒤로 둬서,
    # 같은 줄이나 같은 칸에 짝이 있으면 그쪽이 먼저 확정되게 한다(그린디 배정).
    #
    # "사이에 다른 메뉴 이름이 없을 것"을 칸 상관없이 **읽기 순서**로 따진다 — 다음 줄에
    # 다른 메뉴가 있으면 그 가격은 그 메뉴 것이므로 여기서 끌어오면 안 된다.
    if price.top >= name.bottom:
        gap = price.top - name.bottom
        blocked = any(name.bottom <= rival.top < price.top for rival in rivals)
        if blocked or gap > _MAX_VERTICAL_GAP_LINES * line_height:
            return None
        return 4, gap

    return None


def match_prices_to_names(normalized_boxes: list[TextBox], food_names: list[str]) -> dict[str, int]:
    """메뉴판 사진의 글자 상자 위치를 보고 음식명마다 그 메뉴의 가격을 짝지어 돌려준다.

    가격이 음식명과 같은 줄에 없어도(이름 아래 줄에 적힌 사진형 메뉴판 등) 좌표로 찾아낸다.
    `src/ocr/infer.py`의 recognize_boxes()가 주는 (x, y, w, h, text) 목록을 그대로 받으며,
    text와 food_names는 공백이 제거된 상태여야 한다(정규화 규칙은 src/ocr/match.py의
    _normalize 하나로 통일).

    가격 하나는 메뉴 하나에만 붙인다. 가까운 짝부터 차례로 확정해서, 가격이 안 적힌 메뉴가
    옆 메뉴의 가격을 가로채지 못하게 막는다. 짝을 못 찾은 메뉴는 결과에 안 들어간다
    (호출부에서 None = 가격 정보 없음으로 본다 — 임의로 추정하지 않는다).
    """
    price_tokens: list[tuple[_Token, int]] = []
    name_tokens: list[tuple[_Token, str]] = []
    heights: list[float] = []
    lefts: list[float] = []
    rights: list[float] = []

    for box in normalized_boxes:
        x, _y, width, height, text = box[:5]
        if not text:
            continue
        heights.append(float(height))
        lefts.append(float(x))
        rights.append(float(x + width))

        for start, end, value in find_prices(text):
            price_tokens.append((_slice_token(box, start, end), value))

        # 한 상자 안에서 이름이 나타나는 자리를 모두 모은 뒤, 더 긴 이름 안에 통째로
        # 들어있는 짧은 이름은 버린다. "닭갈비" 상자에는 "갈비"도 들어있는데, 그대로 두면
        # 짧은 쪽이 긴 쪽의 가격을 가로챈다 — 실측: 갈비가 닭갈비의 12,000을 가져가고
        # 닭갈비는 가격을 잃었다. 후보 목록에서 갈비를 지우는 게 아니라, **가격을 붙일 때만**
        # 긴 이름을 우선한다.
        occurrences = []
        for name in food_names:
            index = text.find(name)
            while index != -1:
                occurrences.append((index, index + len(name), name))
                index = text.find(name, index + 1)

        for start, end, name in occurrences:
            covered_by_longer = any(
                other_start <= start and end <= other_end and len(other_name) > len(name)
                for other_start, other_end, other_name in occurrences
            )
            if not covered_by_longer:
                name_tokens.append((_slice_token(box, start, end), name))

    if not price_tokens or not name_tokens:
        return {}

    line_height = statistics.median(heights)
    content_width = max(rights) - min(lefts)

    ranked = []
    for name_token, name in name_tokens:
        rivals = [token for token, other in name_tokens if other != name]
        for price_index, (price_token, value) in enumerate(price_tokens):
            rank = _rank_pair(name_token, price_token, rivals, line_height, content_width)
            if rank is not None:
                ranked.append((rank, name, price_index, value))

    ranked.sort(key=lambda item: item[0])

    prices: dict[str, int] = {}
    claimed: set[int] = set()
    for _rank, name, price_index, value in ranked:
        if name in prices or price_index in claimed:
            continue
        prices[name] = value
        claimed.add(price_index)
    return prices


# 가격 숫자 바로 앞에 붙는 표시들 — 통화 기호(₩, W, w)와 크기 표기(小/中/大).
#
# find_prices()가 돌려주는 구간은 **숫자 부분만**이라, 그 구간만 지우면 "김치전/부추전 W"
# 처럼 표시가 남는다. 그래서 숫자 앞쪽에 붙어 있는 표시까지 같이 걷어낸다.
# 문자열 끝($)에 붙은 것만 지운다 — 이름 가운데의 글자는 건드리지 않기 위함이다.
_PRICE_MARKS = re.compile(r"[₩\\Ww\s]*[小中大]?[₩\\Ww\s]*$")


def strip_prices(text: str) -> str:
    """메뉴판 줄 글자에서 가격을 떼어내고 이름 쪽만 남긴다.

    화면 카드는 가격을 이미 따로 큰 글씨로 보여준다. 그런데 이름 자리에도 줄 글자를
    그대로 쓰면 "김치전/부추전 ₩7,000" 아래에 다시 "₩7,000"이 붙어 같은 값이 두 번
    보인다(실측: 강원 메뉴판 한 장에서 미지원 줄 17개 전부).

    가격이 어디인지는 find_prices()가 이미 위치로 알려주므로, 그 구간과 바로 앞에
    붙은 통화·크기 표시를 지운다. 값을 다시 찾아 헤아리지 않는다.

    가격을 지우고 나면 남는 글자가 없을 수도 있다(숫자만 있는 줄). 그때는 빈
    문자열을 돌려주므로, 부르는 쪽이 원래 줄로 되돌릴지 정한다.
    """
    result = text
    # 뒤에서부터 지운다 — find_prices()의 위치는 원본 기준이라, 앞쪽부터 지우면
    # 뒤쪽 위치가 어긋난다.
    #
    # 지운 자리에 공백을 하나 남긴다. 가격 토큰은 뒤따르는 공백까지 포함하는 구간이라
    # 그냥 이어붙이면 앞뒤 낱말이 달라붙는다("장칼국수 8,000 SEASON" → "장칼국수SEASON").
    for start, end, _value in reversed(find_prices(text)):
        result = _PRICE_MARKS.sub("", result[:start]) + " " + result[end:]
    return " ".join(result.split())


def format_price_krw(price_krw: int | None) -> str | None:
    """숫자 원화 가격을 프론트 표시용 "₩12,000" 형식 문자열로 바꾼다."""
    if price_krw is None:
        return None
    return f"₩{price_krw:,}"
