import json
from collections import defaultdict
from pathlib import Path

import librosa
import numpy as np
import tensorflow as tf


ROOT = Path.cwd()
DATA_ROOT = (
    Path.home()
    / "Desktop"
    / "Pest_Guard_New_Datasets"
)

CANDIDATE = (
    ROOT
    / "backend"
    / "ai_model"
    / "pest_new_dataset_candidate"
)

SAMPLE_RATE = 16000
CLIP_SECONDS = 5
TARGET_LENGTH = SAMPLE_RATE * CLIP_SECONDS

model = tf.keras.models.load_model(
    CANDIDATE / "best_candidate.keras",
    compile=False,
)

scientific_names = json.loads(
    (CANDIDATE / "class_names.json").read_text(
        encoding="utf-8"
    )
)

common_names = json.loads(
    (CANDIDATE / "common_names.json").read_text(
        encoding="utf-8"
    )
)

manifest = json.loads(
    (CANDIDATE / "split_manifest.json").read_text(
        encoding="utf-8"
    )
)

if not (
    len(scientific_names)
    == len(common_names)
    == model.output_shape[-1]
):
    raise RuntimeError("Model and name mappings do not match.")

rows = [
    row for row in manifest
    if row["split"] == "validation"
]

if not rows:
    raise RuntimeError("No validation recordings were found.")

mel_matrix = tf.signal.linear_to_mel_weight_matrix(
    num_mel_bins=128,
    num_spectrogram_bins=513,
    sample_rate=SAMPLE_RATE,
    lower_edge_hertz=50.0,
    upper_edge_hertz=8000.0,
)


def make_feature(audio):
    audio = tf.convert_to_tensor(
        audio,
        dtype=tf.float32,
    )

    peak = tf.reduce_max(tf.abs(audio))

    audio = tf.cond(
        peak > 0,
        lambda: audio / peak,
        lambda: audio,
    )

    spec = tf.signal.stft(
        audio,
        frame_length=1024,
        frame_step=512,
        fft_length=1024,
    )

    mel = tf.matmul(
        tf.square(tf.abs(spec)),
        mel_matrix,
    )

    mel = tf.math.log(mel + 1e-6)
    mel = (
        mel - tf.reduce_mean(mel)
    ) / (
        tf.math.reduce_std(mel) + 1e-6
    )

    return mel[..., tf.newaxis].numpy().astype(np.float32)


# Keep edited versions together and evaluate by recording group.
groups = defaultdict(list)

for row in rows:
    key = (
        row["class_index"],
        row["group"],
    )
    groups[key].append(row)

group_predictions = []
skipped_files = 0

for index, (key, group_rows) in enumerate(
    sorted(groups.items()),
    start=1,
):
    file_probabilities = []

    for row in group_rows:
        audio_path = DATA_ROOT / row["file"]

        try:
            audio, _ = librosa.load(
                str(audio_path),
                sr=SAMPLE_RATE,
                mono=True,
            )
        except Exception as error:
            print(
                "Skipped unreadable file:",
                row["file"],
                type(error).__name__,
            )
            skipped_files += 1
            continue

        features = []

        for start in range(0, len(audio), TARGET_LENGTH):
            clip = audio[start:start + TARGET_LENGTH]

            if len(clip) < SAMPLE_RATE:
                continue

            if len(clip) < TARGET_LENGTH:
                clip = np.pad(
                    clip,
                    (0, TARGET_LENGTH - len(clip)),
                )

            feature = make_feature(clip)

            if np.all(np.isfinite(feature)):
                features.append(feature)

        if not features:
            skipped_files += 1
            continue

        probabilities = model.predict(
            np.stack(features),
            verbose=0,
        )

        # Combine clips from the same audio file.
        file_probabilities.append(
            np.mean(probabilities, axis=0)
        )

    if not file_probabilities:
        continue

    # Combine edited files from the same original recording group.
    mean_probabilities = np.mean(
        file_probabilities,
        axis=0,
    )

    true_index = key[0]
    predicted_index = int(
        np.argmax(mean_probabilities)
    )

    group_predictions.append(
        (true_index, predicted_index)
    )

    if index % 25 == 0 or index == len(groups):
        print(
            f"Evaluated {index}/{len(groups)} groups",
            flush=True,
        )


if not group_predictions:
    raise RuntimeError("No validation groups could be evaluated.")

correct = sum(
    actual == predicted
    for actual, predicted in group_predictions
)

accuracy = correct / len(group_predictions)

print("\nCANDIDATE EVALUATION RESULTS")
print("=" * 65)
print("Validation groups evaluated:", len(group_predictions))
print("Correct groups:", correct)
print("Incorrect groups:", len(group_predictions) - correct)
print(f"Group-level accuracy: {accuracy:.2%}")
print("Unreadable or unusable files skipped:", skipped_files)

per_class = defaultdict(lambda: [0, 0])

for actual, predicted in group_predictions:
    per_class[actual][1] += 1

    if actual == predicted:
        per_class[actual][0] += 1

print("\nPER-SPECIES RESULTS")
print("-" * 65)

for class_index, name in enumerate(scientific_names):
    good, total = per_class[class_index]

    if total:
        print(
            f"{common_names[class_index]} "
            f"({name}): {good}/{total} correct "
            f"({good / total:.1%})"
        )
    else:
        print(
            f"{common_names[class_index]} "
            f"({name}): no evaluable validation groups"
        )

print("\nEvaluation complete.")
print("Production model was not changed.")