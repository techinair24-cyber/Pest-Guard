import math
import re


UNKNOWN_INSECT_GROUP = "Unknown insect group"

GROUP_DISPLAY_NAMES = {
    "bushcricketskatydids": "Bush-cricket / Katydid",
    "cicadas": "Cicada",
    "grasshoppers": "Grasshopper",
    "truecrickets": "Cricket",
}


def _normalize_label(value):
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def build_species_group_mapping(labels, group_by_label, groups):
    if len(labels) != len(group_by_label):
        raise ValueError("Species labels and group mapping must have equal lengths.")

    if len({_normalize_label(label) for label in labels}) != len(labels):
        raise ValueError("Species labels must be unique.")

    if len(set(groups)) != len(groups):
        raise ValueError("Hierarchical groups must be unique.")

    if not set(group_by_label).issubset(set(groups)):
        raise ValueError("Species mapping contains a group absent from the bundle.")

    return {
        _normalize_label(label): GROUP_DISPLAY_NAMES.get(
            _normalize_label(group),
            UNKNOWN_INSECT_GROUP,
        )
        for label, group in zip(labels, group_by_label)
    }


def get_species_group(species, species_groups):
    return species_groups.get(
        _normalize_label(species),
        UNKNOWN_INSECT_GROUP,
    )


def resolve_saved_group_prediction(species, saved_group, saved_score, species_groups):
    known_groups = set(species_groups.values()) - {UNKNOWN_INSECT_GROUP}
    if saved_group not in known_groups:
        return get_species_group(species, species_groups), None

    try:
        score = float(saved_score)
    except (TypeError, ValueError):
        return saved_group, None
    if not math.isfinite(score) or score < 0 or score > 1:
        return saved_group, None
    return saved_group, score


def enrich_top_predictions(predictions, common_names_by_species):
    if not isinstance(predictions, list):
        raise ValueError("Stored top predictions must be a list.")

    enriched = []
    for candidate in predictions:
        if not isinstance(candidate, dict):
            raise ValueError("Stored top prediction entries must be objects.")
        item = dict(candidate)
        if not str(item.get("common_name") or "").strip():
            common_name = common_names_by_species.get(
                _normalize_label(item.get("pest"))
            )
            if common_name:
                item["common_name"] = common_name
        enriched.append(item)
    return enriched


def aggregate_group_scores(labels, class_scores, species_groups):
    if len(labels) != len(class_scores):
        raise ValueError("Species labels and scores must have equal lengths.")

    if any(
        not math.isfinite(float(score)) or float(score) < 0
        for score in class_scores
    ):
        raise ValueError("Species scores must be finite and non-negative.")

    groups = [get_species_group(label, species_groups) for label in labels]
    if UNKNOWN_INSECT_GROUP in groups:
        return None

    score_sum = sum(float(score) for score in class_scores)
    if score_sum <= 0:
        raise ValueError("Species scores must have a positive total.")

    aggregated = {}
    for group, score in zip(groups, class_scores):
        aggregated[group] = aggregated.get(group, 0.0) + float(score) / score_sum
    return aggregated


def rank_species_predictions(labels, class_scores, common_names):
    if len(labels) != len(class_scores) or len(labels) != len(common_names):
        raise ValueError("Species labels, scores, and common names must align.")

    scores = [float(score) for score in class_scores]
    if any(
        not math.isfinite(score) or score < 0 or score > 1
        for score in scores
    ):
        raise ValueError("Species scores must be finite values between zero and one.")

    top_indices = sorted(
        range(len(labels)),
        key=lambda index: (-scores[index], index),
    )[:3]
    return [
        {
            "pest": labels[index],
            "score": scores[index],
            "common_name": common_names[index],
        }
        for index in top_indices
    ]
