import unittest

from insect_groups import (
    GROUP_DISPLAY_NAMES,
    UNKNOWN_INSECT_GROUP,
    aggregate_group_scores,
    build_species_group_mapping,
    get_species_group,
    rank_species_predictions,
    resolve_saved_group_prediction,
)


class InsectGroupPredictionTests(unittest.TestCase):
    def setUp(self):
        self.labels = ["field grasshopper", "cicada alpha", "house cricket"]
        self.group_by_label = [
            "grasshoppers",
            "cicadas",
            "true_crickets",
        ]
        self.groups = ["grasshoppers", "cicadas", "true_crickets"]
        self.species_groups = build_species_group_mapping(
            self.labels,
            self.group_by_label,
            self.groups,
        )

    def test_group_mapping_uses_known_display_names(self):
        self.assertEqual(len(self.species_groups), len(self.labels))
        self.assertEqual(
            set(self.species_groups.values()),
            {
                GROUP_DISPLAY_NAMES[group.replace("_", "")]
                for group in self.groups
            },
        )
        self.assertEqual(
            get_species_group("FIELD_GRASSHOPPER", self.species_groups),
            "Grasshopper",
        )

    def test_duplicate_labels_are_rejected_after_normalization(self):
        with self.assertRaisesRegex(ValueError, "unique"):
            build_species_group_mapping(
                ["Field Grasshopper", "field_grasshopper"],
                ["grasshoppers", "grasshoppers"],
                ["grasshoppers"],
            )

    def test_group_scores_are_sums_of_joint_species_scores(self):
        scores = [0.35, 0.25, 0.40]
        result = aggregate_group_scores(
            self.labels,
            scores,
            self.species_groups,
        )

        self.assertAlmostEqual(result["Grasshopper"], 0.35)
        self.assertAlmostEqual(result["Cicada"], 0.25)
        self.assertAlmostEqual(result["Cricket"], 0.40)
        self.assertAlmostEqual(sum(result.values()), 1.0)

    def test_group_score_is_unavailable_if_any_species_is_unmapped(self):
        result = aggregate_group_scores(
            ["mapped", "unmapped"],
            [0.7, 0.3],
            {"mapped": "Grasshopper"},
        )

        self.assertIsNone(result)

    def test_top_three_species_are_sorted_by_model_score(self):
        result = rank_species_predictions(
            ["first", "second", "third", "fourth"],
            [0.2, 0.6, 0.1, 0.4],
            ["First", "Second", "Third", "Fourth"],
        )

        self.assertEqual(
            [(candidate["pest"], candidate["score"]) for candidate in result],
            [("second", 0.6), ("fourth", 0.4), ("first", 0.2)],
        )

    def test_saved_group_resolves_without_a_saved_score(self):
        group, score = resolve_saved_group_prediction(
            self.labels[0],
            None,
            None,
            self.species_groups,
        )

        self.assertEqual(group, "Grasshopper")
        self.assertIsNone(score)

    def test_valid_saved_group_and_score_are_preserved(self):
        group, score = resolve_saved_group_prediction(
            self.labels[0],
            "Cicada",
            0.61,
            self.species_groups,
        )

        self.assertEqual(group, "Cicada")
        self.assertEqual(score, 0.61)

    def test_invalid_saved_group_score_is_cleared(self):
        group, score = resolve_saved_group_prediction(
            self.labels[0],
            "Cicada",
            float("nan"),
            self.species_groups,
        )

        self.assertEqual(group, "Cicada")
        self.assertIsNone(score)
        self.assertEqual(UNKNOWN_INSECT_GROUP, "Unknown insect group")


if __name__ == "__main__":
    unittest.main()
