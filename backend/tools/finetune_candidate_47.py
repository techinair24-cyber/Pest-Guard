from pathlib import Path
import json, random
import numpy as np
import soundfile as sf
import tensorflow as tf
from scipy.signal import resample_poly
from sklearn.utils.class_weight import compute_class_weight

random.seed(459)
np.random.seed(459)
tf.random.set_seed(459)

ROOT = Path.cwd()
D = ROOT / "backend" / "ai_model" / "pest_new_dataset_candidate"
DATA = Path.home() / "Desktop" / "Pest_Guard_New_Datasets"
MODEL_IN = D / "best_candidate.keras"
MODEL_OUT = D / "best_candidate_finetuned.keras"
HISTORY_OUT = D / "best_candidate_finetuned_history.json"
MANIFEST = D / "split_manifest.json"
LABELS = json.loads((D / "class_names.json").read_text(encoding="utf-8"))
records = json.loads(MANIFEST.read_text(encoding="utf-8"))

if MODEL_OUT.exists() or HISTORY_OUT.exists():
    raise FileExistsError("Fine-tuned output already exists; refusing to overwrite.")
if len(LABELS) != 47:
    raise RuntimeError(f"Expected 47 labels, found {len(LABELS)}")

train = [r for r in records if r.get("split") == "train"]
val = [r for r in records if r.get("split") == "validation"]
if not train or not val:
    raise RuntimeError("Training or validation records missing.")

for r in train + val:
    i = int(r["class_index"])
    if i < 0 or i >= len(LABELS) or LABELS[i] != r["scientific_name"]:
        raise RuntimeError(f"Label mismatch: {r}")

mel_matrix = tf.signal.linear_to_mel_weight_matrix(
    128, 513, 16000, 50.0, 8000.0
)

def load_features(record):
    path = DATA / record["file"]
    audio, sr = sf.read(path, dtype="float32", always_2d=True)
    audio = audio.mean(axis=1)
    if sr != 16000:
        from math import gcd
        g = gcd(int(sr), 16000)
        audio = resample_poly(audio, 16000 // g, int(sr) // g).astype(np.float32)
    audio = audio[:80000]
    if len(audio) < 80000:
        audio = np.pad(audio, (0, 80000 - len(audio)))
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak
    stft = tf.signal.stft(audio, 1024, 512, 1024)
    mel = tf.matmul(tf.square(tf.abs(stft)), mel_matrix)
    mel = tf.math.log(mel + 1e-6)
    mel = (mel - tf.reduce_mean(mel)) / (tf.math.reduce_std(mel) + 1e-6)
    return mel[..., None].numpy().astype(np.float32)

def make_arrays(rows):
    xs, ys = [], []
    for n, r in enumerate(rows, 1):
        xs.append(load_features(r))
        ys.append(int(r["class_index"]))
        if n % 100 == 0 or n == len(rows):
            print(f"Prepared {n}/{len(rows)}", flush=True)
    return np.stack(xs), np.asarray(ys, dtype=np.int32)

print("Preparing training recordings...")
X_train, y_train = make_arrays(train)
print("Preparing validation recordings...")
X_val, y_val = make_arrays(val)

model = tf.keras.models.load_model(MODEL_IN, compile=False)
if model.input_shape != (None, 155, 128, 1) or model.output_shape != (None, 47):
    raise RuntimeError(f"Unexpected model shapes: {model.input_shape}, {model.output_shape}")

weights = compute_class_weight(
    class_weight="balanced", classes=np.unique(y_train), y=y_train
)
class_weights = {int(c): float(min(w, 3.0)) for c, w in zip(np.unique(y_train), weights)}

model.compile(
    optimizer=tf.keras.optimizers.Adam(learning_rate=1e-6),
    loss="sparse_categorical_crossentropy",
    metrics=["accuracy"],
)
callbacks = [
    tf.keras.callbacks.ModelCheckpoint(
        str(MODEL_OUT), monitor="val_loss", save_best_only=True, verbose=1
    ),
    tf.keras.callbacks.EarlyStopping(
        monitor="val_loss", patience=2, restore_best_weights=True
    ),
]
history = model.fit(
    X_train, y_train,
    validation_data=(X_val, y_val),
    batch_size=8,
    epochs=5,
    class_weight=class_weights,
    callbacks=callbacks,
    verbose=1,
)
MODEL_OUT.write_bytes(MODEL_OUT.read_bytes())
HISTORY_OUT.write_text(
    json.dumps({k: [float(v) for v in vals] for k, vals in history.history.items()}, indent=2),
    encoding="utf-8",
)
print("Separate candidate saved:", MODEL_OUT)
print("History saved:", HISTORY_OUT)
print("Production model was not changed.")
