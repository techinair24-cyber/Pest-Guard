from pathlib import Path
import json
import numpy as np
import tensorflow as tf
from keras.initializers import GlorotUniform

PROJECT = Path(__file__).resolve().parent
MODEL_DIR = PROJECT / "ai_model"
MANIFEST = MODEL_DIR / "candidate_extra_manifest.json"
START_MODEL = MODEL_DIR / "candidate_insectset459.keras"
OUTPUT_MODEL = MODEL_DIR / "candidate_final.keras"
HISTORY_FILE = MODEL_DIR / "candidate_final_history.json"
DATA_ROOT = Path.home() / "Desktop" / "InsectSound1000_Training"
EXTRA = DATA_ROOT / "Chorthippus_extra_segments" / "Chorthippusalbomarginatus"
BATCH_SIZE = 4
EPOCHS = 5
LEARNING_RATE = 1e-5

def main():
    original = GlorotUniform.from_config

    @classmethod
    def compatible_from_config(cls, config):
        config = dict(config)
        config.pop("input_axes", None)
        config.pop("output_axes", None)
        return original.__func__(cls, config)

    GlorotUniform.from_config = compatible_from_config

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    train_paths = manifest["train_paths"]
    train_labels = manifest["train_labels"]
    val_paths = manifest["validation_paths"]
    val_labels = manifest["validation_labels"]
    classes = manifest["classes"]

    labels_file = json.loads(
        (MODEL_DIR / "class_names.json").read_text(encoding="utf-8")
    )
    if classes != labels_file:
        raise RuntimeError("Class order mismatch.")
    if len(train_paths) != len(train_labels) or len(val_paths) != len(val_labels):
        raise RuntimeError("Manifest path/label counts differ.")

    extra_files = list(EXTRA.glob("*.npy"))
    train_set = {str(Path(p).resolve()) for p in train_paths}
    val_set = {str(Path(p).resolve()) for p in val_paths}
    if len(extra_files) != 489:
        raise RuntimeError(f"Expected 489 extra segments, found {len(extra_files)}")
    if any(str(p.resolve()) not in train_set for p in extra_files):
        raise RuntimeError("Extra segments missing from training manifest.")
    if any(str(p.resolve()) in val_set for p in extra_files):
        raise RuntimeError("Extra segment overlaps validation.")

    mel_matrix = tf.signal.linear_to_mel_weight_matrix(
        num_mel_bins=128,
        num_spectrogram_bins=513,
        sample_rate=16000,
        lower_edge_hertz=50.0,
        upper_edge_hertz=8000.0,
    )

    def features(path):
        audio = np.load(path).astype(np.float32).reshape(-1)
        if len(audio) > 80000:
            audio = audio[:80000]
        elif len(audio) < 80000:
            audio = np.pad(audio, (0, 80000 - len(audio)))
        peak = np.max(np.abs(audio))
        if peak > 0:
            audio /= peak
        spec = tf.signal.stft(
            audio, frame_length=1024, frame_step=512, fft_length=1024
        )
        mel = tf.matmul(tf.square(tf.abs(spec)), mel_matrix)
        mel = tf.math.log(mel + 1e-6)
        mel = (mel - tf.reduce_mean(mel)) / (
            tf.math.reduce_std(mel) + 1e-6
        )
        result = mel[..., tf.newaxis].numpy().astype(np.float32)
        if result.shape != (155, 128, 1):
            raise ValueError(f"Unexpected feature shape {result.shape}: {path}")
        return result

    def generator(paths, labels):
        for path, label in zip(paths, labels):
            yield features(path), np.int32(label)

    output_signature = (
        tf.TensorSpec(shape=(155, 128, 1), dtype=tf.float32),
        tf.TensorSpec(shape=(), dtype=tf.int32),
    )

    train_ds = tf.data.Dataset.from_generator(
        lambda: generator(train_paths, train_labels),
        output_signature=output_signature,
    )
    train_ds = train_ds.shuffle(2048, seed=42).batch(BATCH_SIZE).prefetch(1)

    val_ds = tf.data.Dataset.from_generator(
        lambda: generator(val_paths, val_labels),
        output_signature=output_signature,
    ).batch(BATCH_SIZE).prefetch(1)

    print("Training segments:", len(train_paths))
    print("Validation segments:", len(val_paths))
    print("Extra segments included:", len(extra_files))
    print("Loading starting candidate...", flush=True)

    model = tf.keras.models.load_model(START_MODEL, compile=False)
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=LEARNING_RATE),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )

    callbacks = [
        tf.keras.callbacks.EarlyStopping(
            monitor="val_loss", patience=2, restore_best_weights=True
        ),
        tf.keras.callbacks.ModelCheckpoint(
            str(OUTPUT_MODEL), monitor="val_loss", save_best_only=True
        ),
    ]

    history = model.fit(
        train_ds,
        validation_data=val_ds,
        epochs=EPOCHS,
        callbacks=callbacks,
    )
    HISTORY_FILE.write_text(
        json.dumps(history.history, indent=2), encoding="utf-8"
    )
    print("Candidate saved:", OUTPUT_MODEL)
    print("History saved:", HISTORY_FILE)
    print("Production model unchanged.")

if __name__ == "__main__":
    main()

