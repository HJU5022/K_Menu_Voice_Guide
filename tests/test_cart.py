"""장바구니 테스트 — src/cart/store.py.

docs/specs/cart.md의 AC를 그대로 옮긴 것이다. 카트의 규칙은 네 줄로 요약되는데
(합치기 / 음수 금지 / 0이면 삭제 / 전체 상태 반환) 이게 깨지면 화면에 수량이 -1인 줄이
남거나 같은 메뉴가 두 줄로 갈라져서 총계가 틀어진다.

store는 모듈 전역 dict에 담아두므로, 테스트끼리 영향을 주지 않도록 매번 비우고 시작한다.

실행: python -m pytest tests/test_cart.py
"""

import unittest

from src.cart import store

CART_ID = "test-cart"


class CartStoreTests(unittest.TestCase):
    def setUp(self):
        store.clear_all()

    def add(self, food_id, name_kr, name_en, price_krw, quantity_delta, menu_text=None):
        return store.change_quantity(
            CART_ID,
            food_id=food_id,
            name_kr=name_kr,
            name_en=name_en,
            price_krw=price_krw,
            quantity_delta=quantity_delta,
            menu_text=menu_text,
        )

    def test_new_cart_is_empty_instead_of_missing(self):
        """AC-05 · 처음 보는 카트 ID여도 에러가 아니라 빈 카트다."""
        cart = store.get_cart("never-seen-before")

        self.assertEqual(cart["items"], [])
        self.assertEqual(cart["item_count"], 0)
        self.assertEqual(cart["total_krw"], 0)
        self.assertEqual(cart["total_krw_display"], "₩0")
        self.assertFalse(cart["has_unpriced_items"])

    def test_adding_returns_the_whole_cart(self):
        """AC-01 · 담으면 그 줄만이 아니라 카트 전체 상태가 돌아온다."""
        cart = self.add(1, "비빔밥", "Bibimbap", 9000, 1)

        self.assertEqual(len(cart["items"]), 1)
        item = cart["items"][0]
        self.assertEqual(item["food_id"], 1)
        self.assertEqual(item["name_en"], "Bibimbap")
        self.assertEqual(item["quantity"], 1)
        self.assertEqual(item["line_total_krw"], 9000)
        self.assertEqual(item["line_total_display"], "₩9,000")
        self.assertEqual(cart["item_count"], 1)
        self.assertEqual(cart["total_krw"], 9000)
        self.assertEqual(cart["total_krw_display"], "₩9,000")

    def test_same_food_merges_into_one_line(self):
        """AC-02 · 같은 음식을 또 담아도 줄이 늘지 않고 수량만 오른다."""
        self.add(1, "비빔밥", "Bibimbap", 9000, 1)
        cart = self.add(1, "비빔밥", "Bibimbap", 9000, 1)

        self.assertEqual(len(cart["items"]), 1)
        self.assertEqual(cart["items"][0]["quantity"], 2)
        self.assertEqual(cart["items"][0]["line_total_krw"], 18000)
        self.assertEqual(cart["total_krw"], 18000)

    def test_same_food_on_different_menu_lines_stays_separate(self):
        """물만두와 군만두는 둘 다 "만두"지만 메뉴판에서는 다른 줄이다.

        food_id로만 묶으면 화면에는 카드가 둘인데 카트에서 하나로 합쳐지고,
        가격이 다른 둘을 한 줄로 만들어 총계까지 틀린다.
        """
        self.add(1, "만두", "Mandu", 5000, 1, menu_text="물만두 5,000")
        cart = self.add(1, "만두", "Mandu", 6000, 1, menu_text="군만두 6,000")

        self.assertEqual([item["menu_text"] for item in cart["items"]],
                         ["물만두 5,000", "군만두 6,000"])
        self.assertEqual(cart["total_krw"], 11000)

    def test_same_menu_line_still_merges(self):
        """같은 줄을 두 번 담으면 수량만 오른다 — 줄이 늘어나면 안 된다."""
        self.add(1, "만두", "Mandu", 5000, 1, menu_text="물만두 5,000")
        cart = self.add(1, "만두", "Mandu", 5000, 1, menu_text="물만두 5,000")

        self.assertEqual(len(cart["items"]), 1)
        self.assertEqual(cart["items"][0]["quantity"], 2)

    def test_removing_one_line_leaves_the_other(self):
        """한 줄을 빼도 같은 음식의 다른 줄은 남아 있어야 한다."""
        self.add(1, "만두", "Mandu", 5000, 1, menu_text="물만두 5,000")
        self.add(1, "만두", "Mandu", 6000, 1, menu_text="군만두 6,000")

        cart = self.add(1, "만두", "Mandu", 5000, -1, menu_text="물만두 5,000")

        self.assertEqual([item["menu_text"] for item in cart["items"]], ["군만두 6,000"])

    def test_without_menu_text_it_merges_by_food_id(self):
        """줄 정보가 없으면 예전처럼 음식 기준으로 묶는다.

        좌표 없이 매칭된 경로에는 줄 구분 정보 자체가 없다. 그때는 나누는 근거가
        없으므로 합치는 쪽이 맞다.
        """
        self.add(1, "만두", "Mandu", 5000, 1)
        cart = self.add(1, "만두", "Mandu", 5000, 1)

        self.assertEqual(len(cart["items"]), 1)
        self.assertEqual(cart["items"][0]["quantity"], 2)

    def test_quantity_zero_removes_the_line(self):
        """AC-03 · 수량이 0이 되면 그 줄이 사라진다 (수량 0짜리 줄을 남기지 않는다)."""
        self.add(1, "비빔밥", "Bibimbap", 9000, 1)
        cart = self.add(1, "비빔밥", "Bibimbap", 9000, -1)

        self.assertEqual(cart["items"], [])
        self.assertEqual(cart["item_count"], 0)
        self.assertEqual(cart["total_krw"], 0)

    def test_quantity_never_goes_negative(self):
        """AC-04 · 담긴 수량보다 더 빼도 음수인 줄이 남지 않는다."""
        self.add(1, "비빔밥", "Bibimbap", 9000, 2)
        cart = self.add(1, "비빔밥", "Bibimbap", 9000, -5)

        self.assertEqual(cart["items"], [])
        self.assertEqual(cart["item_count"], 0)

    def test_removing_a_food_that_is_not_in_the_cart_does_nothing(self):
        """EC-02 · 카트에 없는 음식을 빼면 no-op — 수량 0짜리 빈 줄을 만들지 않는다."""
        cart = self.add(1, "비빔밥", "Bibimbap", 9000, -1)

        self.assertEqual(cart["items"], [])

    def test_unpriced_food_counts_as_zero_and_is_flagged(self):
        """AC-05 · 가격을 못 읽은 메뉴도 담기지만, 총계가 일부만 반영됐음을 알린다."""
        cart = self.add(7, "모둠전", "Assorted Jeon", None, 1)

        self.assertEqual(len(cart["items"]), 1)
        self.assertIsNone(cart["items"][0]["price_krw"])
        self.assertIsNone(cart["items"][0]["line_total_krw"])
        self.assertIsNone(cart["items"][0]["line_total_display"])
        self.assertEqual(cart["total_krw"], 0)
        self.assertTrue(cart["has_unpriced_items"])

    def test_total_sums_every_line(self):
        """AC-06 · 총계는 모든 줄의 (가격 × 수량) 합이고, item_count는 줄 수가 아니라 수량 합이다."""
        self.add(1, "비빔밥", "Bibimbap", 9000, 2)
        cart = self.add(2, "불고기", "Bulgogi", 12000, 1)

        self.assertEqual(cart["total_krw"], 30000)
        self.assertEqual(cart["total_krw_display"], "₩30,000")
        self.assertEqual(cart["item_count"], 3)
        self.assertEqual(len(cart["items"]), 2)

    def test_price_is_filled_in_when_a_later_photo_reads_it(self):
        """EC-04 · 처음엔 가격을 못 읽었어도, 나중에 읽히면 그때부터 총계에 반영된다."""
        self.add(7, "모둠전", "Assorted Jeon", None, 1)
        cart = self.add(7, "모둠전", "Assorted Jeon", 18000, 1)

        self.assertEqual(len(cart["items"]), 1)
        self.assertEqual(cart["items"][0]["price_krw"], 18000)
        self.assertEqual(cart["total_krw"], 36000)
        self.assertFalse(cart["has_unpriced_items"])

    def test_known_price_survives_a_photo_that_could_not_read_it(self):
        """반대 방향 — 이미 아는 가격을 null로 덮어쓰지 않는다."""
        self.add(1, "비빔밥", "Bibimbap", 9000, 1)
        cart = self.add(1, "비빔밥", "Bibimbap", None, 1)

        self.assertEqual(cart["items"][0]["price_krw"], 9000)
        self.assertEqual(cart["total_krw"], 18000)

    def test_line_order_follows_when_it_was_first_added(self):
        """줄이 튀지 않아야 한다 — 수량을 바꿔도 처음 담은 순서를 지킨다."""
        self.add(1, "비빔밥", "Bibimbap", 9000, 1)
        self.add(2, "불고기", "Bulgogi", 12000, 1)
        cart = self.add(1, "비빔밥", "Bibimbap", 9000, 1)

        self.assertEqual([item["food_id"] for item in cart["items"]], [1, 2])

    def test_clear_cart_empties_it(self):
        """AC-08 · 비우면 빈 카트 전체 상태가 돌아온다."""
        self.add(1, "비빔밥", "Bibimbap", 9000, 2)
        self.add(2, "불고기", "Bulgogi", 12000, 1)

        cart = store.clear_cart(CART_ID)

        self.assertEqual(cart["items"], [])
        self.assertEqual(cart["item_count"], 0)
        self.assertEqual(cart["total_krw"], 0)
        self.assertEqual(store.get_cart(CART_ID)["items"], [])

    def test_clear_cart_leaves_other_carts_alone(self):
        """AC-08 · 남의 카트를 같이 비우면 안 된다."""
        self.add(1, "비빔밥", "Bibimbap", 9000, 1)
        store.change_quantity(
            "other", food_id=2, name_kr="불고기", name_en="Bulgogi", price_krw=12000, quantity_delta=1
        )

        store.clear_cart(CART_ID)

        self.assertEqual([item["food_id"] for item in store.get_cart("other")["items"]], [2])

    def test_clear_cart_on_an_unknown_id_is_not_an_error(self):
        """한 번도 담은 적 없는 카트를 비워도 빈 카트를 정상 응답한다."""
        cart = store.clear_cart("never-used")

        self.assertEqual(cart["items"], [])
        self.assertEqual(cart["cart_id"], "never-used")

    def test_carts_are_isolated_by_cart_id(self):
        """다른 사람 카트가 섞이면 안 된다 — 카트 ID로 완전히 분리된다."""
        self.add(1, "비빔밥", "Bibimbap", 9000, 1)
        store.change_quantity(
            "another-cart",
            food_id=2,
            name_kr="불고기",
            name_en="Bulgogi",
            price_krw=12000,
            quantity_delta=1,
        )

        self.assertEqual([item["food_id"] for item in store.get_cart(CART_ID)["items"]], [1])
        self.assertEqual([item["food_id"] for item in store.get_cart("another-cart")["items"]], [2])


if __name__ == "__main__":
    unittest.main()
