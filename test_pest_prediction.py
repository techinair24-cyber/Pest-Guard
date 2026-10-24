
import os
import json
import numpy as np
import librosa
import tensorflow as tf
import tensorflow_hub as hub

MODEL_PATH = "backend/ai_model/pest_yamnet_updated_candidate/best_candidate.keras"
LABELS_PATH = "backend/ai_model/pest_yamnet_updated_candidate/class_names.json"
DATASET_PATH = os.path.join(
    os.path.expanduser("~"), "Desktop", "Pest Sound Dataset"
)

SAMPLE_RATE = 16000
CLIP_SECONDS = 5


def main():
    with open(LABELS_PATH, "r", encoding="utf-8") as f:
        labels = json.load(f)

    print("\nLoading candidate model...")
    model = tf.keras.models.load_model(MODEL_PATH)

    print("Loading pretrained YAMNet...")
    yamnet = hub.load("https://tfhub.dev/google/yamnet/1")

    print("\nAvailable dataset folders:")
    folders = sorted(
        name for name in os.listdir(DATASET_PATH)
        if os.path.isdir(os.path.join(DATASET_PATH, name))
    )

    for i, folder in enumerate(folders, 1):
        print(f"{i}. {folder}")

    try:
        choice = int(input("\nEnter the folder number to test: "))
        folder = folders[choice - 1]
    except (ValueError, IndexError):
        print("Invalid folder number.")
        return

    folder_path = os.path.join(DATASET_PATH, folder)
    audio_files = sorted(
        name for name in os.listdir(folder_path)
        if name.lower().endswith((".wav", ".mp3", ".oga", ".ogg", ".flac", ".m4a"))
    )

    if not audio_files:
        print("No supported audio files found.")
        return

    print(f"\nAudio files in {folder}:")
    for i, name in enumerate(audio_files, 1):
        print(f"{i}. {name}")

    try:
        file_choice = int(input("\nEnter the audio file number: "))
        audio_path = os.path.join(
            folder_path, audio_files[file_choice - 1]
        )
    except (ValueError, IndexError):
        print("Invalid audio file number.")
        return

    print("\nProcessing audio...")
    audio, _ = librosa.load(
        audio_path, sr=SAMPLE_RATE, mono=True
    )

    if len(audio) == 0:
        print("Audio file is empty.")
        return

    clip_samples = SAMPLE_RATE * CLIP_SECONDS
    embeddings = []

    for start in range(0, len(audio), clip_samples):
        clip = audio[start:start + clip_samples]

        if len(clip) < SAMPLE_RATE:
            continue

        waveform = tf.convert_to_tensor(clip, dtype=tf.float32)
        _, embedding, _ = yamnet(waveform)
        embeddings.append(
            np.mean(embedding.numpy(), axis=0)
        )

    if not embeddings:
        print("Audio is too short to test.")
        return

    features = np.asarray(embeddings, dtype=np.float32)
    predictions = model.predict(features, verbose=0)

    if predictions.ndim != 2 or predictions.shape[1] != len(labels):
        print("Model output does not match the class labels.")
        print("Output shape:", predictions.shape)
        return

    average_scores = np.mean(predictions, axis=0)
    top_indices = np.argsort(average_scores)[::-1][:5]

    print("\n========== PREDICTION RESULTS ==========")
    print("Audio file:", os.path.basename(audio_path))
    print("Actual dataset folder:", folder)
    print("Audio duration:", round(len(audio) / SAMPLE_RATE, 2), "seconds")
    print("\nTop 5 predicted classes:")

    for rank, index in enumerate(top_indices, 1):
        print(
            f"{rank}. {labels[index]}: "
            f"{average_scores[index] * 100:.2f}%"
        )

    print("\nNote: These scores are model scores, not guaranteed probabilities.")
    print("This is a test candidate, not the production model.")


if __name__ == "__main__":
    main()
