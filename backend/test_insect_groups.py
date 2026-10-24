import json
import unittest
from pathlib import Path

import joblib

from insect_groups import (
    GROUP_DISPLAY_NAMES,
    UNKNOWN_INSECT_GROUP,
    aggregate_group_scores,
    build_species_group_mapping,
    get_species_group,
    rank_species_predictions,
    resolve_saved_group_prediction,
)


CANDIDATE_DIR = (
    Path(__file__).resolve().parent
    / "ai_model"
    / "pest_new_dataset_candidate"
)


class InsectGroupPredictionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.labels = json.loads(
            (CANDIDATE_DIR / "class_names.json").read_text(encoding="utf-8")
        )
        cls.metadata = json.loads(
            (CANDIDATE_DIR / "class_metadata.json").read_text(encoding="utf-8")
        )
        cls.common_names = json.loads(
            (CANDIDATE_DIR / "common_names.json").read_text(encoding="utf-8")
        )
        cls.bundle = joblib.load(
            CANDIDATE_DIR / "hierarchical_audio_classifier.joblib"
        )
        cls.species_groups = build_species_group_mapping(
            cls.bundle["labels"],
            cls.bundle["group_by_label"],
            cls.bundle["groups"],
        )

    def test_all_47_species_have_a_valid_or_explicit_unknown_group(self):
        self.assertEqual(len(self.labels), 47)
        self.assertEqual(len(self.common_names), 47)
        self.assertEqual(len(self.metadata), 47)
        self.assertEqual(self.bundle["labels"], self.labels)
        self.assertEqual(
            {
                "".join(
                    character
                    for character in entry["model_class"].casefold()
                    if character.isalnum()
                )
                for entry in self.metadata
            },
            {
                "".join(
                    character for character in label.casefold() if character.isalnum()
                )
                for label in self.labels
            },
        )
        self.assertEqual(set(self.species_groups), {
            "".join(character for character in label.casefold() if character.isalnum())
            for label in self.labels
        })
        self.assertTrue(
            all(
                get_species_group(label, self.species_groups)
                in (*GROUP_DISPLAY_NAMES.values(), UNKNOWN_INSECT_GROUP)
                for label in self.labels
            )
        )
        self.assertEqual(
            set(self.species_groups.values()),
            set(GROUP_DISPLAY_NAMES.values()),
        )
        self.assertNotIn(UNKNOWN_INSECT_GROUP, self.species_groups.values())

    def test_group_scores_are_sums_of_joint_species_scores(self):
        scores = [0.35, 0.25, 0.25, 0.15]
        mapping = build_species_group_mapping(
            ["one", "two", "three", "four"],
            ["grasshoppers", "grasshoppers", "cicadas", "true_crickets"],
            ["grasshoppers", "cicadas", "true_crickets"],
        )

        result = aggregate_group_scores(
            ["one", "two", "three", "four"],
            scores,
            mapping,
        )

        self.assertAlmostEqual(result["Grasshopper"], 0.60)
        self.assertAlmostEqual(result["Cicada"], 0.25)
        self.assertAlmostEqual(result["Cricket"], 0.15)
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

    def test_legacy_species_without_saved_group_fields_still_resolves(self):
        group, score = resolve_saved_group_prediction(
            self.labels[0],
            None,
            None,
            self.species_groups,
        )

        self.assertNotEqual(group, UNKNOWN_INSECT_GROUP)
        self.assertIsNone(score)

    def test_group_aggregate_can_differ_from_the_top_species_group(self):
        candidate_group = get_species_group(
            self.labels[0],
            self.species_groups,
        )
        other_group = next(
            group
            for group in GROUP_DISPLAY_NAMES.values()
            if group != candidate_group
        )

        group, score = resolve_saved_group_prediction(
            self.labels[0],
            other_group,
            0.61,
            self.species_groups,
        )

        self.assertEqual(group, other_group)
        self.assertEqual(score, 0.61)


if __name__ == "__main__":
    unittest.main()
