# -*- coding: utf-8 -*-
import unittest
from types import SimpleNamespace

from shared.alignment import (
    DPI_REGLA,
    alinear_campos,
    distribuir_campos,
    pulgadas_a_pixeles,
    pixeles_a_pulgadas,
)
from shared.models import Position


def campo(x, y, width, height, order=1):
    return SimpleNamespace(
        position=Position(x=x, y=y, width=width, height=height),
        order=order,
    )


class AlignmentGeometryTests(unittest.TestCase):
    def test_horizontal_guide_aligns_top_center_and_bottom(self):
        for mode, expected_y in (("top", 100), ("center", 90), ("bottom", 80)):
            item = campo(10, 5, 30, 20)
            self.assertTrue(alinear_campos([item], "horizontal", 100, mode))
            self.assertEqual(item.position.y, expected_y)

    def test_vertical_guide_aligns_left_center_and_right(self):
        for mode, expected_x in (("left", 100), ("center", 90), ("right", 80)):
            item = campo(5, 10, 40, 20)
            self.assertTrue(alinear_campos([item], "vertical", 100, mode))
            self.assertEqual(item.position.x, expected_x)

    def test_horizontal_distribution_uses_equal_free_edge_gaps(self):
        items = [
            campo(10, 0, 10, 10, 1),
            campo(40, 0, 20, 10, 2),
            campo(100, 0, 10, 10, 3),
        ]
        self.assertTrue(distribuir_campos(items, "horizontal"))
        self.assertEqual([item.position.x for item in items], [10, 50, 100])
        gaps = [
            items[1].position.x - (items[0].position.x + items[0].position.width),
            items[2].position.x - (items[1].position.x + items[1].position.width),
        ]
        self.assertEqual(gaps, [30, 30])

    def test_vertical_distribution_uses_equal_free_edge_gaps(self):
        items = [
            campo(0, 10, 10, 10, 1),
            campo(0, 40, 10, 20, 2),
            campo(0, 100, 10, 10, 3),
        ]
        self.assertTrue(distribuir_campos(items, "vertical"))
        self.assertEqual([item.position.y for item in items], [10, 50, 100])

    def test_distribution_refuses_overlap_without_changing_positions(self):
        items = [campo(0, 0, 60, 10, 1), campo(40, 0, 60, 10, 2)]
        before = [(item.position.x, item.position.y) for item in items]
        self.assertFalse(distribuir_campos(items, "horizontal"))
        self.assertEqual(
            [(item.position.x, item.position.y) for item in items],
            before,
        )

    def test_ruler_uses_fixed_300_dpi(self):
        self.assertEqual(DPI_REGLA, 300)
        self.assertEqual(pulgadas_a_pixeles(2.5), 750)
        self.assertEqual(pixeles_a_pulgadas(750), 2.5)


if __name__ == "__main__":
    unittest.main()
