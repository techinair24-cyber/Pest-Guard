"""Evaluate the loaded production inference stages on the validation manifest.

Run from the backend directory with the local dataset and split manifest present:
    python evaluate_hierarchical_classifier.py

This script does not train or overwrite model artifacts.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly
from sklearn.metrics import accuracy_score, f1_score, top_k_accuracy_score

import main

DATASET_ROOT = Path.home() / "Desktop" / "Pest_Guard_New_Datasets"
MANIFEST_PATH = main.CANDIDATE_DIR / "split_manifest.json"
REPORT_LABELS = {
    "Gryllus bimaculatus",
    "Platypleura sp. 12 cf. hirtipennis",
    "Pseudochorthippus montanus",
}


def read_validation_audio(path_value: str) -> np.ndarray:
    path = Path(path_value)
    if not path.is_absolute():
        path = DATASET_ROOT / path
    audio, sample_rate = sf.read(str(path), dtype="float32", always_2d=True)
    audio = np.mean(audio, axis=1, dtype=np.float32)
    if not audio.size:
        raise ValueError("Audio file is empty.")
    if sample_rate != main.SAMPLE_RATE:
        divisor = math.gcd(int(sample_rate), main.SAMPLE_RATE)
        audio = resample_poly(
            audio,
            main.SAMPLE_RATE // divisor,
            int(sample_rate) // divisor,
        ).astype(np.float32)
    return audio


def hierarchical_scores(embedding: np.ndarray) -> np.ndarray:
    bundle = main._HIERARCHICAL_BUNDLE
    if bundle is None:
        raise RuntimeError("Required hierarchical classifier was not initialized.")

    group_model = bundle["group_model"]
    group_probs = np.asarray(group_model.predict_proba(embedding), dtype=np.float64)[0]
    group_ids = [int(class_id) for class_id in group_model[-1].classes_]
    if group_probs.shape != (len(group_ids),) or not np.all(np.isfinite(group_probs)):
        raise RuntimeError("Group probabilities do not match the saved group classes.")
    group_probability_by_id = {
        group_id: float(group_probs[column])
        for column, group_id in enumerate(group_ids)
    }

    class_scores = np.zeros(len(main.class_names), dtype=np.float64)
    for group_id, group in enumerate(bundle["groups"]):
        expert = bundle["experts"][group]
        specialist_probs = np.asarray(
            expert.predict_proba(embedding),
            dtype=np.float64,
        )[0]
        specialist_ids = [int(class_id) for class_id in expert[-1].classes_]
        if specialist_probs.shape != (len(specialist_ids),) or not np.all(
            np.isfinite(specialist_probs)
        ):
            raise RuntimeError(
                f"Specialist probabilities do not match saved class labels for {group}."
            )
        group_probability = group_probability_by_id[group_id]
        for class_id, class_probability in zip(specialist_ids, specialist_probs):
            class_scores[class_id] = group_probability * float(class_probability)

    score_sum = float(np.sum(class_scores))
    if not np.all(np.isfinite(class_scores)) or score_sum <= 0.0:
        raise RuntimeError("Hierarchical classifier returned invalid class scores.")
    return class_scores / score_sum


def main_eval() -> int:
    if not MANIFEST_PATH.is_file():
        raise FileNotFoundError(f"Validation manifest not found: {MANIFEST_PATH}")
    if main._HIERARCHICAL_BUNDLE is None:
        raise RuntimeError("Required hierarchical classifier was not initialized.")

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8-sig"))
    rows = [row for row in manifest if row.get("split") == "validation"]
    if not rows:
        raise ValueError(f"No validation rows found in {MANIFEST_PATH}")

    y_true: list[int] = []
    cnn_scores: list[np.ndarray] = []
    hierarchical_scores_list: list[np.ndarray] = []
    gate_scores: list[float] = []
    named_counts = {
        label: {"correct": 0, "total": 0, "gate_rejected": 0}
        for label in REPORT_LABELS
    }
    named_examples: dict[str, tuple[np.ndarray, int]] = {}
    failures: list[str] = []

    for row in rows:
        label_index = int(row["class_index"])
        label = main.class_names[label_index]
        try:
            waveform = read_validation_audio(row["file"])
            gate_score = main._pest_light_gate_score(waveform)
            features = main.prepare_audio(waveform)
            embedding_batch, cnn_batch = main._HIERARCHICAL_INFERENCE_MODEL(
                features[None, ...],
                training=False,
            )
            embedding = np.asarray(embedding_batch, dtype=np.float32).reshape(1, -1)
            cnn_probabilities = np.asarray(cnn_batch, dtype=np.float64)[0]
            species_scores = hierarchical_scores(embedding)
            if cnn_probabilities.shape != (len(main.class_names),):
                raise RuntimeError("CNN output does not match the 47 class labels.")

            y_true.append(label_index)
            cnn_scores.append(cnn_probabilities)
            hierarchical_scores_list.append(species_scores)
            gate_scores.append(gate_score)
            if label in REPORT_LABELS:
                stats = named_counts[label]
                stats["total"] += 1
                stats["correct"] += int(int(np.argmax(species_scores)) == label_index)
                stats["gate_rejected"] += int(
                    gate_score < main._PEST_LIGHT_GATE_THRESHOLD
                )
                named_examples.setdefault(label, (waveform, label_index))
        except Exception as error:
            failures.append(f"{row.get('file', '<missing file>')}: {type(error).__name__}: {error}")

    if failures:
        print(f"Failed validation rows: {len(failures)}/{len(rows)}")
        for error in failures[:10]:
            print(f"  {error}")
        return 1

    y = np.asarray(y_true, dtype=np.int64)
    cnn = np.asarray(cnn_scores)
    hierarchical = np.asarray(hierarchical_scores_list)
    labels = list(range(len(main.class_names)))

    print(
        f"Loaded path=hierarchical; classes={len(main.class_names)}; "
        f"validation recordings={len(y)}"
    )
    for name, scores in (("CNN baseline", cnn), ("Hierarchical", hierarchical)):
        predicted = np.argmax(scores, axis=1)
        accuracy = accuracy_score(y, predicted)
        macro_f1 = f1_score(
            y,
            predicted,
            labels=labels,
            average="macro",
            zero_division=0,
        )
        top3 = top_k_accuracy_score(y, scores, k=3, labels=labels)
        print(
            f"{name}: accuracy={accuracy * 100:.2f}% "
            f"macro-F1={macro_f1 * 100:.2f}% top-3={top3 * 100:.2f}%"
        )

    gate = np.asarray(gate_scores)
    print(
        f"Gate: runtime threshold={main._PEST_LIGHT_GATE_THRESHOLD:.2f}; "
        f"rejected={int(np.sum(gate < main._PEST_LIGHT_GATE_THRESHOLD))}/{len(gate)}; "
        f"rejected at 0.25={int(np.sum(gate < 0.25))}/{len(gate)}"
    )
    for label, stats in named_counts.items():
        print(
            f"{label}: hierarchical={stats['correct']}/{stats['total']}; "
            f"gate-rejected={stats['gate_rejected']}/{stats['total']}"
        )
        if label in named_examples:
            waveform, _ = named_examples[label]
            result = main.predict_pest(waveform)
            print(
                f"  production predict_pest(): {result['pest']} "
                f"(uncalibrated score={result['confidence']:.4f})"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main_eval())
