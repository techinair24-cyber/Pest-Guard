
from pathlib import Path

import librosa
import numpy as np
import matplotlib.pyplot as plt

from backend.pest_guard_hierarchy_inference_8class import (
    PestGuardHierarchy8Class,
    SAMPLE_RATE,
    FEATURE_SHAPE,
)

DATASET_ROOT = Path(
    r"C:\Users\Deepthi MG\Desktop\Pest Guard Dataset"
)

CLASSES = [
    "Beetles",
    "Cicada",
    "Crickets",
    "Flies",
    "Grasshopper",
    "Katydid",
    "Mole Crickets",
    "Termite",
]

EXTENSIONS = {
    ".wav", ".wavex", ".mp3", ".flac",
    ".ogg", ".aiff", ".aif",
}


def find_sample(category):
    folder = DATASET_ROOT / category

    if not folder.is_dir():
        raise FileNotFoundError(f"Missing category: {folder}")

    files = sorted(
        path for path in folder.rglob("*")
        if path.is_file()
        and path.suffix.lower() in EXTENSIONS
    )

    if not files:
        raise RuntimeError(f"No audio recordings found in {category}")

    return files[0]


def main():
    print("Pest Guard: Eight-Class Spectrogram Test")
    print("Using the existing production feature function.")
    print(f"Sample rate: {SAMPLE_RATE} Hz")
    print(f"Expected feature shape: {FEATURE_SHAPE}\n")

    fig, axes = plt.subplots(4, 2, figsize=(15, 16))
    axes = axes.flatten()

    for index, category in enumerate(CLASSES):
        path = find_sample(category)

        waveform, _ = librosa.load(
            str(path),
            sr=SAMPLE_RATE,
            mono=True,
        )

        features = PestGuardHierarchy8Class._features(waveform)

        if features.shape != FEATURE_SHAPE:
            raise RuntimeError(
                f"{category}: unexpected shape {features.shape}"
            )

        if not np.isfinite(features).all():
            raise RuntimeError(
                f"{category}: non-finite feature values"
            )

        spectrogram = features[:, :, 0]

        image = axes[index].imshow(
            spectrogram.T,
            origin="lower",
            aspect="auto",
            extent=[0, 5, 0, 128],
            cmap="magma",
        )

        axes[index].set_title(
            f"{category}\n{path.name}",
            fontsize=9,
        )
        axes[index].set_xlabel("Time (seconds)")
        axes[index].set_ylabel("Mel bin")

        fig.colorbar(image, ax=axes[index], fraction=0.046)

        print(
            f"PASS: {category} | "
            f"{path.name} | "
            f"shape={features.shape}"
        )

    fig.suptitle(
        "Pest Guard: Production Log-Mel Spectrograms",
        fontsize=15,
    )
    fig.tight_layout()
    plt.show()

    print("\nAll eight spectrograms generated successfully.")


if __name__ == "__main__":
    main()
