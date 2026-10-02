"""Regression tests for ranker input construction."""

import unittest

from src.models import Item
from src.rank import _item_line
from src.select import compute_final_scores, select


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

    def test_major_model_launch_is_selected_ahead_of_a_higher_scored_regular_item(self):
        launch = Item(
            url="https://typesafe.ai/jev",
            url_hash="b" * 40,
            title="Introducing Jev",
            source_domain="typesafe.ai",
            lane=6,
            lane_weight=0.55,
            source_tier=4,
            tier_multiplier=0.8,
            content_type="news",
            collected_at="2026-09-19T08:31:58+09:00",
            abstract="TypeSafe AI releases a new model for structured decisions.",
            category="llm-foundation-model",
            base_score=3.0,
            coverage_priority=True,
        )
        regular = Item(
            url="https://example.com/regular",
            url_hash="c" * 40,
            title="Regular model commentary",
            source_domain="example.com",
            lane=1,
            lane_weight=1.0,
            source_tier=1,
            tier_multiplier=1.0,
            content_type="blog",
            collected_at="2026-09-19T08:31:58+09:00",
            category="llm-foundation-model",
            base_score=8.0,
        )
        compute_final_scores([launch, regular])

        chosen = select(
            [launch, regular],
            [{"id": "llm-foundation-model", "min": 1, "max": 1}],
            total_max=1,
        )

        self.assertEqual([launch], chosen)

    def test_major_launch_event_score_is_not_reduced_by_source_lane_weight(self):
        launch = Item(
            url="https://new-lab.example/model",
            url_hash="d" * 40,
            title="NewLab launches Frontier-1",
            source_domain="new-lab.example",
            lane=10,
            lane_weight=0.55,
            source_tier=4,
            tier_multiplier=0.8,
            content_type="news",
            collected_at="2026-09-19T08:31:58+09:00",
            category="llm-foundation-model",
            base_score=3.0,
            event_score=8.0,
            coverage_priority=True,
        )

        compute_final_scores([launch])

        self.assertEqual(8.0, launch.final_score)

    def test_irrelevant_item_is_excluded_before_category_quota_selection(self):
        irrelevant = Item(
            url="https://example.com/consumer-news",
            url_hash="e" * 40,
            title="Unrelated consumer story",
            source_domain="example.com",
            lane=6,
            lane_weight=0.55,
            source_tier=4,
            tier_multiplier=0.8,
            content_type="news",
            collected_at="2026-09-19T08:31:58+09:00",
            category="llm-foundation-model",
            base_score=10.0,
            is_relevant=False,
        )
        compute_final_scores([irrelevant])

        chosen = select(
            [irrelevant],
            [{"id": "llm-foundation-model", "min": 1, "max": 1}],
            total_max=1,
        )

        self.assertEqual([], chosen)


if __name__ == "__main__":
    unittest.main()
