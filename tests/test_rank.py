"""Regression tests for ranker input construction."""

import unittest

from src.models import Item
from src.rank import _item_line


class RankInputTests(unittest.TestCase):
    def test_item_line_includes_abstract_for_model_launches_with_generic_titles(self):
        item = Item(
            url="https://techcrunch.com/example",
            url_hash="a" * 40,
            title="A new kind of AI model from a ChatGPT inventor is thrilling developers",
            source_domain="techcrunch.com",
            lane=6,
            lane_weight=0.55,
            source_tier=4,
            tier_multiplier=0.8,
            content_type="news",
            collected_at="2026-09-19T08:31:58+09:00",
            abstract="Jev, a new kind of AI model, is showing developers a cheaper and faster path to software intelligence.",
        )

        line = _item_line(0, item)

        self.assertIn("Jev", line)


if __name__ == "__main__":
    unittest.main()
