"""내레이션 테스트 — src/text_gen/narration.py가 style을 맞게 정하고 문장 3개를 잇는지 확인한다.

검사하는 건 네 가지다.
1. spice_level(맵기 1~5)에 따라 style이 GUIDE인지 CAUTION인지 — 경계는 4 이상이면 CAUTION
2. narration_text + PRONUNCIATION + ALLERGY 세 문장이 이 순서로 이어붙는지
3. TTS로 넘길 tts_text에서 음식명이 한글 표기로 바뀌는지 (화면용 text는 로마자 그대로)
4. tts_text의 발음 안내가 PRONUNCIATION_TTS로 갈아끼워지는지 (없으면 화면용으로 폴백)

DB는 건드리지 않는다. cache 함수들을 patch로 가짜 값으로 바꿔치기해서 로직만 검사한다.

실행: python -m pytest tests/test_narration.py
"""

import unittest
from unittest.mock import patch

from src.db import cache
from src.text_gen import narration


class NarrationTests(unittest.TestCase):
    def test_get_narration_returns_guide_text_and_style(self):
        """맵기 3(4 미만) → GUIDE. 그리고 문장 3개가 순서대로 이어붙는지 함께 확인."""
        with (
            # patch.object = "이 함수가 불리면 진짜 대신 이 값을 돌려줘라"
            patch.object(
                cache,
                "get_food",
                return_value={
                    "spice_level": 3,
                    "name_en": "Bibimbap",
                    "name_kr": "비빔밥",
                },
            ),
            patch.object(cache, "get_narration_text", return_value="Bibimbap is a mild dish."),
            patch.object(
                cache,
                "get_food_details",
                return_value={"PRONUNCIATION": "Pronounced 'ay'.", "ALLERGY": "Contains egg."},
            ),
        ):
            result = narration.get_narration(1)

        # 순서가 중요하다: 내레이션 → 발음 → 알레르기
        self.assertEqual(
            result,
            {
                "text": "Bibimbap is a mild dish. Pronounced 'ay'. Contains egg.",
                "tts_text": "비빔밥 is a mild dish. Pronounced 'ay'. Contains egg.",
                "style": "GUIDE",
            },
        )

    def test_get_narration_returns_caution_text_and_style(self):
        """맵기 4(경계값) → CAUTION. 이 경계가 TTS 톤(경고 목소리)을 결정한다."""
        with (
            patch.object(
                cache,
                "get_food",
                return_value={
                    "spice_level": 4,
                    "name_en": "Tteokbokki",
                    "name_kr": "떡볶이",
                },
            ),
            patch.object(cache, "get_narration_text", return_value="It is spicy."),
            patch.object(
                cache,
                "get_food_details",
                return_value={"PRONUNCIATION": "Pronounced 'ay'.", "ALLERGY": "Contains egg."},
            ),
        ):
            result = narration.get_narration(1)

        self.assertEqual(
            result,
            {
                "text": "It is spicy. Pronounced 'ay'. Contains egg.",
                "tts_text": "It is spicy. Pronounced 'ay'. Contains egg.",
                "style": "CAUTION",
            },
        )

    def test_get_narration_raises_for_unknown_food(self):
        """등록 안 된 음식이면 빈 문장을 만들지 말고 에러를 내야 한다 (엉뚱한 안내 방지)."""
        with patch.object(cache, "get_food", return_value=None):
            with self.assertRaisesRegex(ValueError, "foods 데이터가 없습니다"):
                narration.get_narration(999)

    def test_get_narration_raises_when_pronunciation_missing(self):
        """발음 문장이 없으면 그냥 건너뛰지 말고 에러 — 빠진 걸 조용히 넘기면 나중에 못 찾는다."""
        with (
            patch.object(cache, "get_food", return_value={"spice_level": 2}),
            patch.object(cache, "get_narration_text", return_value="A dish."),
            # ALLERGY만 있고 PRONUNCIATION이 없는 상황을 일부러 만든다
            patch.object(cache, "get_food_details", return_value={"ALLERGY": "Contains soy."}),
        ):
            with self.assertRaisesRegex(ValueError, "PRONUNCIATION가 없습니다"):
                narration.get_narration(1)

    def test_get_narration_raises_when_allergy_missing(self):
        """알레르기 문장이 없어도 마찬가지로 에러 — 안전 정보라 빠뜨리면 안 된다."""
        with (
            patch.object(cache, "get_food", return_value={"spice_level": 2}),
            patch.object(cache, "get_narration_text", return_value="A dish."),
            patch.object(cache, "get_food_details", return_value={"PRONUNCIATION": "Pronounced 'ay'."}),
        ):
            with self.assertRaisesRegex(ValueError, "ALLERGY가 없습니다"):
                narration.get_narration(1)


    def test_tts_text_replaces_only_the_food_name(self):
        """음식명만 한글 표기로 바뀌고 나머지 영어 문장은 그대로여야 한다.

        부분 문자열이 아니라 단어 경계로 매칭해야 한다 — Galbi가 Tteokgalbi 안쪽을
        파먹으면 발음이 통째로 깨진다.
        """
        with (
            patch.object(
                cache,
                "get_food",
                return_value={
                    "spice_level": 1,
                    "name_en": "Galbi",
                    "name_kr": "갈비",
                },
            ),
            patch.object(
                cache,
                "get_narration_text",
                return_value="Galbi is grilled beef, unlike Tteokgalbi.",
            ),
            patch.object(
                cache,
                "get_food_details",
                return_value={"PRONUNCIATION": "Say it slowly.", "ALLERGY": "Contains soy."},
            ),
        ):
            result = narration.get_narration(1)

        self.assertEqual(
            result["tts_text"],
            "갈비 is grilled beef, unlike Tteokgalbi. Say it slowly. Contains soy.",
        )
        # 화면용 원문은 건드리지 않는다 — 여행자가 로마자로 읽어야 하기 때문
        self.assertEqual(
            result["text"],
            "Galbi is grilled beef, unlike Tteokgalbi. Say it slowly. Contains soy.",
        )

    def test_tts_text_falls_back_to_original_when_name_kr_missing(self):
        """name_kr이 비어 있으면 치환하지 않고 원문 그대로.

        등록된 50개는 전부 name_kr을 갖고 있지만, 비어 있어도 그 음식만 로마자로 읽힐 뿐
        안내가 끊기면 안 된다(경위: src/db/README.md)."""
        with (
            patch.object(
                cache,
                "get_food",
                return_value={"spice_level": 2, "name_en": "Bossam", "name_kr": None},
            ),
            patch.object(cache, "get_narration_text", return_value="Bossam is boiled pork."),
            patch.object(
                cache,
                "get_food_details",
                return_value={"PRONUNCIATION": "Say it slowly.", "ALLERGY": "Contains pork."},
            ),
        ):
            result = narration.get_narration(1)

        self.assertEqual(result["tts_text"], result["text"])
        self.assertIn("Bossam", result["tts_text"])


    def test_tts_text_uses_the_tts_pronunciation_sentence(self):
        """TTS용 발음 안내는 PRONUNCIATION_TTS를 쓴다 — 화면용 문장을 그대로 쓰면
        `비빔밥 is pronounced "bee-bim-bap."`가 되어 같은 이름을 한국어 발음으로 한 번,
        로마자 표기로 한 번 연달아 읽는다."""
        with (
            patch.object(
                cache,
                "get_food",
                return_value={
                    "spice_level": 1,
                    "name_en": "Bibimbap",
                    "name_kr": "비빔밥",
                },
            ),
            patch.object(cache, "get_narration_text", return_value="Bibimbap is a rice bowl."),
            patch.object(
                cache,
                "get_food_details",
                return_value={
                    "PRONUNCIATION": 'Bibimbap is pronounced "bee-bim-bap."',
                    "PRONUNCIATION_TTS": "Say it like this: Bibimbap.",
                    "ALLERGY": "Contains egg.",
                },
            ),
        ):
            result = narration.get_narration(1)

        self.assertEqual(
            result["tts_text"],
            "비빔밥 is a rice bowl. Say it like this: 비빔밥. Contains egg.",
        )
        # 화면용은 로마자 발음 표기를 그대로 유지한다 — 여행자가 읽어야 하는 정보다
        self.assertEqual(
            result["text"],
            'Bibimbap is a rice bowl. Bibimbap is pronounced "bee-bim-bap." Contains egg.',
        )

    def test_tts_text_falls_back_to_screen_pronunciation_when_tts_row_missing(self):
        """PRONUNCIATION_TTS 행이 아직 DB에 없어도 안내가 끊기지 않아야 한다 —
        코드를 먼저 배포하고 행을 나중에 넣는 순서를 허용하기 위한 폴백이다."""
        with (
            patch.object(
                cache,
                "get_food",
                return_value={
                    "spice_level": 1,
                    "name_en": "Japchae",
                    "name_kr": "잡채",
                },
            ),
            patch.object(cache, "get_narration_text", return_value="Japchae is glass noodles."),
            patch.object(
                cache,
                "get_food_details",
                return_value={
                    "PRONUNCIATION": 'Japchae is pronounced "jap-chae."',
                    "ALLERGY": "Contains soy.",
                },
            ),
        ):
            result = narration.get_narration(1)

        self.assertEqual(
            result["tts_text"],
            '잡채 is glass noodles. 잡채 is pronounced "jap-chae." Contains soy.',
        )


if __name__ == "__main__":
    unittest.main()
