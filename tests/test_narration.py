"""내레이션 테스트 — src/text_gen/narration.py가 style을 맞게 정하고 DB 문장을 그대로 넘기는지 확인한다.

검사하는 건 세 가지다.
1. spice_level(맵기 1~5)에 따라 style이 GUIDE인지 CAUTION인지 — 경계는 4 이상이면 CAUTION
2. food_narration의 문장을 가공 없이 그대로 돌려주는지 (발음·알레르기는 그 문단에 이미 들어 있다)
3. TTS로 넘길 tts_text에서 음식명만 한글 표기로 바뀌는지 (화면용 text는 로마자 그대로)

DB는 건드리지 않는다. cache 함수들을 patch로 가짜 값으로 바꿔치기해서 로직만 검사한다.

실행: python -m pytest tests/test_narration.py
"""

import unittest
from unittest.mock import patch

from src.db import cache
from src.text_gen import narration


class NarrationTests(unittest.TestCase):
    def test_get_narration_returns_guide_text_and_style(self):
        """맵기 3(4 미만) → GUIDE. DB 문장이 그대로 나오는지 함께 확인."""
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
            patch.object(
                cache,
                "get_narration_text",
                return_value="Bibimbap is a mild dish. Contains egg.",
            ),
        ):
            result = narration.get_narration(1)

        self.assertEqual(
            result,
            {
                "text": "Bibimbap is a mild dish. Contains egg.",
                "tts_text": "비빔밥 is a mild dish. Contains egg.",
                "style": "GUIDE",
                "name_kr": "비빔밥",
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
        ):
            result = narration.get_narration(1)

        self.assertEqual(
            result,
            {
                "text": "It is spicy.",
                "tts_text": "It is spicy.",
                "style": "CAUTION",
                "name_kr": "떡볶이",
            },
        )

    def test_get_narration_raises_for_unknown_food(self):
        """등록 안 된 음식이면 빈 문장을 만들지 말고 에러를 내야 한다 (엉뚱한 안내 방지)."""
        with patch.object(cache, "get_food", return_value=None):
            with self.assertRaisesRegex(ValueError, "foods 데이터가 없습니다"):
                narration.get_narration(999)

    def test_get_narration_raises_when_narration_row_missing(self):
        """안내 문장이 통째로 없으면 빈 음성을 만들지 말고 에러 — 조용히 넘기면 나중에 못 찾는다."""
        with (
            patch.object(cache, "get_food", return_value={"spice_level": 2}),
            patch.object(cache, "get_narration_text", return_value=None),
        ):
            with self.assertRaisesRegex(ValueError, "narration이 없습니다"):
                narration.get_narration(1)

    def test_get_narration_raises_when_narration_text_is_blank(self):
        """공백만 있는 행도 없는 것과 같이 취급한다."""
        with (
            patch.object(cache, "get_food", return_value={"spice_level": 2}),
            patch.object(cache, "get_narration_text", return_value="   "),
        ):
            with self.assertRaisesRegex(ValueError, "narration_text가 비어 있습니다"):
                narration.get_narration(1)

    def test_screen_and_tts_text_differ_only_by_the_food_name(self):
        """화면 문장과 음성 문장은 음식명 표기 말고는 같아야 한다.

        예전에는 TTS용 발음 안내를 PRONUNCIATION_TTS로 갈아끼워 둘이 어긋났다. 안내 전문을
        food_narration 한 칸으로 모으면서 그 교체를 걷어냈고, 이 테스트가 그걸 고정한다.
        """
        with (
            patch.object(
                cache,
                "get_food",
                return_value={
                    "spice_level": 2,
                    "name_en": "Japchae",
                    "name_kr": "잡채",
                },
            ),
            patch.object(
                cache,
                "get_narration_text",
                return_value='Japchae is glass noodles. Japchae is pronounced "jap-chae."',
            ),
        ):
            result = narration.get_narration(1)

        self.assertEqual(
            result["text"],
            'Japchae is glass noodles. Japchae is pronounced "jap-chae."',
        )
        self.assertEqual(
            result["tts_text"],
            '잡채 is glass noodles. 잡채 is pronounced "jap-chae."',
        )
        # 음식명만 되돌리면 두 문장이 정확히 겹친다
        self.assertEqual(result["tts_text"].replace("잡채", "Japchae"), result["text"])

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
        ):
            result = narration.get_narration(1)

        self.assertEqual(
            result["tts_text"],
            "갈비 is grilled beef, unlike Tteokgalbi.",
        )
        # 화면용 원문은 건드리지 않는다 — 여행자가 로마자로 읽어야 하기 때문
        self.assertEqual(
            result["text"],
            "Galbi is grilled beef, unlike Tteokgalbi.",
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
        ):
            result = narration.get_narration(1)

        self.assertEqual(result["tts_text"], result["text"])
        self.assertIn("Bossam", result["tts_text"])


if __name__ == "__main__":
    unittest.main()
