"""내레이션 텍스트 — spice_level로 style(GUIDE/CAUTION)을 정하고, 문장 3개를 이어붙인다.

매운 정도에 따라 안내 톤이 달라진다. 여기서 정한 style이 src/tts/로 넘어간다.
경계값은 docs/specs/text-generation.md에서 정한다.

narration_text(food_narration) + PRONUNCIATION(food_details) + ALLERGY(food_details)를
순서대로 이어붙여 반환한다. 셋 다 이미 완성된 문장이라 새로 생성하지 않고 그대로 조합만 한다.

화면용과 TTS용 텍스트를 따로 돌려준다(`text` / `tts_text`). 차이는 두 가지다.

1. 음식명 표기 — TTS 쪽은 음식명을 한글 표기(`foods.name_kr`)로 바꾼다. 영어 문장 안에서
   로마자 음식명은 모델이 영어 음운으로 읽어버려 발음이 부정확한데, 원인은 철자가 아니라 읽는
   음운 체계라서 영문 리스펠링(`Tteokbokki` → `Duck-bok-kee`)으로는 해결되지 않았다 —
   리스펠링한 21개뿐 아니라 원본 표기가 적절하다고 판정했던 29개까지 부정확했다. 한글로 적으면
   모델이 그 이름을 한국어 음운으로 읽는다. 화면에는 여행자가 소리 내어 읽을 수 있는 로마자가
   그대로 남아야 하므로 치환은 TTS 입력에만 적용한다.
   치환에 필요한 이름 쌍(`name_en`/`name_kr`)은 이미 조회해둔 `foods` 행에 다 있다 — 표기용
   컬럼을 따로 두지 않으므로 음식이 늘어도 TTS 쪽에 추가 작업이 없다.
2. 발음 안내 문장 — TTS 쪽은 PRONUNCIATION 대신 PRONUNCIATION_TTS 카테고리를 쓴다.
   화면용 문장은 `Bibimbap is pronounced "bee-bim-bap."`처럼 이름을 말한 뒤 발음 표기를 다시
   알려주는데, 여기에 1번 치환이 겹치면 `비빔밥 is pronounced "bee-bim-bap."`이 되어 같은
   이름을 한국어 발음으로 한 번, 영어 음운으로 읽히는 로마자 표기로 한 번 연달아 읽는다.
   음성에서는 한글로 읽어주는 이름 자체가 발음 안내이므로, 이름을 한 번만 말하는 문장으로
   갈아끼운다(DB의 food_details 행).
   PRONUNCIATION_TTS 행이 아직 없으면 화면용 PRONUNCIATION을 그대로 쓴다 — 코드를 먼저 배포하고
   DB 행을 나중에 넣어도 안내가 끊기지 않게 한다.
"""

import re

from src.db import cache

_NARRATION_DETAIL_CATEGORIES = ("PRONUNCIATION", "ALLERGY")
_TTS_PRONUNCIATION_CATEGORY = "PRONUNCIATION_TTS"


def _to_tts_text(text: str, food: dict) -> str:
    """문장 속 음식명을 한글 표기로 바꾼다. 단어 경계 기준으로 정확히 매칭한다.

    `name_kr`이 비어 있으면 치환하지 않고 원문을 그대로 돌려준다 — 그 음식만 로마자 표기로
    읽히고 안내 자체는 끊기지 않는다. 등록된 50개는 전부 `name_kr`을 갖고 있다
    (경위: src/db/README.md).

    단어 경계(`\\b`)로 매칭하는 이유는 짧은 이름이 긴 이름 안쪽을 파먹으면 발음이 통째로
    깨지기 때문이다 — 예를 들어 `Galbi`가 문장 속 `Tteokgalbi`를 건드리면 안 된다.
    """
    name_en = (food.get("name_en") or "").strip()
    name_kr = (food.get("name_kr") or "").strip()
    if not name_en or not name_kr:
        return text
    return re.sub(rf"\b{re.escape(name_en)}\b", name_kr, text)


def get_narration(food_id: int) -> dict[str, str]:
    """Return the combined narration text, the TTS-facing text, and the style for one food."""
    food = cache.get_food(food_id)
    if food is None:
        raise ValueError(f"food_id {food_id}에 대한 foods 데이터가 없습니다.")

    spice_level = food["spice_level"]
    if not isinstance(spice_level, int):
        raise ValueError(f"food_id {food_id}의 spice_level이 숫자가 아닙니다.")
    style = "CAUTION" if spice_level >= 4 else "GUIDE"

    narration_text = cache.get_narration_text(food_id, style)
    if narration_text is None:
        raise ValueError(f"food_id {food_id}, style {style}에 대한 narration이 없습니다.")
    narration_text = narration_text.strip()
    if not narration_text:
        raise ValueError(f"food_id {food_id}, style {style}의 narration_text가 비어 있습니다.")

    details_by_category = cache.get_food_details(
        food_id, _NARRATION_DETAIL_CATEGORIES + (_TTS_PRONUNCIATION_CATEGORY,)
    )

    sentences = [narration_text]
    for category in _NARRATION_DETAIL_CATEGORIES:
        detail_text = details_by_category.get(category)
        if not detail_text:
            raise ValueError(f"food_id {food_id}의 {category}가 없습니다.")
        sentences.append(detail_text.strip())

    tts_sentences = list(sentences)
    tts_pronunciation = (details_by_category.get(_TTS_PRONUNCIATION_CATEGORY) or "").strip()
    if tts_pronunciation:
        # sentences[1]이 PRONUNCIATION — _NARRATION_DETAIL_CATEGORIES 순서로 붙었다.
        tts_sentences[1] = tts_pronunciation

    text = " ".join(sentences)
    return {
        "text": text,
        "tts_text": _to_tts_text(" ".join(tts_sentences), food),
        "style": style,
        # 이름만 따로 읽어주는 음성(화면의 스피커 버튼)에 쓸 한글 표기.
        # 나레이션과 같은 이유로 한글을 넘긴다 — 로마자를 주면 모델이 영어 음운으로 읽는다.
        # 여기서 실어 보내는 이유는 이 함수가 이미 foods 행을 조회하고 있어서다.
        "name_kr": (food.get("name_kr") or "").strip(),
    }
