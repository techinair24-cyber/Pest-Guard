"""Eight-group Pest Guard hierarchy inference helper.

This is a separate candidate helper. It does not replace or edit the existing
seven-group inference module. It preserves the production 16 kHz / 80,000
sample / (155, 128, 1) feature contract and supports group-only branches.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import tensorflow as tf

SAMPLE_RATE = 16_000
N_SAMPLES = 80_000
FEATURE_SHAPE = (155, 128, 1)
EXPECTED_GROUP_COUNT = 8

MEL_MATRIX = tf.signal.linear_to_mel_weight_matrix(
    num_mel_bins=128,
    num_spectrogram_bins=513,
    sample_rate=SAMPLE_RATE,
    lower_edge_hertz=50.0,
    upper_edge_hertz=8_000.0,
)


class PestGuardHierarchy8Class:
    """Loads one eight-group model plus optional group-specific subtype experts."""

    def __init__(self, model_dir: str | Path):
        self.model_dir = Path(model_dir).resolve()
        manifest_path = self.model_dir / "manifest.json"
        if not manifest_path.is_file():
            raise FileNotFoundError(f"Eight-group hierarchy manifest is missing: {manifest_path}")

        self.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if self.manifest.get("format_version") not in (1, 2):
            raise RuntimeError("Unsupported eight-group hierarchy manifest version.")

        feature_config = self.manifest.get("feature_config") or {}
        if feature_config.get("feature_shape") != list(FEATURE_SHAPE):
            raise RuntimeError(
                f"Hierarchy feature shape must be {list(FEATURE_SHAPE)}, "
                f"found {feature_config.get('feature_shape')!r}."
            )
        expected_feature_fields = {
            "sample_rate": SAMPLE_RATE,
            "clip_seconds": 5,
            "samples": N_SAMPLES,
            "frame_length": 1024,
            "frame_step": 512,
            "fft_length": 1024,
            "mel_bins": 128,
            "mel_low_hz": 50.0,
            "mel_high_hz": 8_000.0,
        }
        for key, expected in expected_feature_fields.items():
            if feature_config.get(key) != expected:
                raise RuntimeError(
                    f"Feature configuration mismatch for {key}: "
                    f"expected {expected!r}, found {feature_config.get(key)!r}."
                )

        self.groups = list(self.manifest.get("group_labels") or [])
        if (
            len(self.groups) != EXPECTED_GROUP_COUNT
            or any(not isinstance(label, str) or not label.strip() for label in self.groups)
            or len(set(self.groups)) != EXPECTED_GROUP_COUNT
        ):
            raise RuntimeError("Eight-group manifest must contain exactly eight unique, non-empty labels.")

        group_info = self.manifest.get("group_model") or {}
        manifest_model_labels = list(group_info.get("labels") or [])
        if manifest_model_labels != self.groups:
            raise RuntimeError("Group model labels must exactly match group_labels in the same order.")

        group_model_path = self.model_dir / "group_model.keras"
        if not group_model_path.is_file():
            raise FileNotFoundError(f"Eight-group CNN is missing: {group_model_path}")
        self.group_model = tf.keras.models.load_model(group_model_path, compile=False)
        self._check_model_input(self.group_model, "eight-group CNN")
        if int(self.group_model.output_shape[-1]) != len(self.groups):
            raise RuntimeError("Eight-group CNN output width does not match the eight manifest labels.")

        self.subtype_manifest = self.manifest.get("subtype_models") or {}
        if not isinstance(self.subtype_manifest, dict):
            raise RuntimeError("subtype_models must be a JSON object keyed by group name.")
        unknown_groups = sorted(set(self.subtype_manifest) - set(self.groups))
        if unknown_groups:
            raise RuntimeError(f"Subtype manifest contains groups absent from group_labels: {unknown_groups}")

        self.experts: dict[str, Any] = {}
        for group, item in self.subtype_manifest.items():
            if not isinstance(item, dict):
                raise RuntimeError(f"Subtype manifest entry for {group!r} must be an object.")
            filename = item.get("model_file")
            labels = list(item.get("labels") or [])
            if not filename:
                if labels:
                    raise RuntimeError(
                        f"Group {group!r} has subtype labels but no subtype model file."
                    )
                continue
            if not isinstance(filename, str) or Path(filename).name != filename:
                raise RuntimeError(f"Unsafe subtype model filename for group {group!r}: {filename!r}")
            if not labels or any(not isinstance(label, str) or not label.strip() for label in labels):
                raise RuntimeError(f"Subtype model for {group!r} requires non-empty ordered labels.")
            if len(set(labels)) != len(labels):
                raise RuntimeError(f"Subtype labels for {group!r} contain duplicates.")

            model_path = self.model_dir / filename
            if not model_path.is_file():
                raise FileNotFoundError(f"Subtype model is missing for {group}: {model_path}")
            model = tf.keras.models.load_model(model_path, compile=False)
            self._check_model_input(model, f"{group} subtype model")
            if int(model.output_shape[-1]) != len(labels):
                raise RuntimeError(f"Subtype model output/label mismatch for group {group}.")
            self.experts[group] = model

    @staticmethod
    def _check_model_input(model: tf.keras.Model, name: str) -> None:
        input_shape = tuple(model.input_shape)
        if len(input_shape) != 4 or tuple(input_shape[1:]) != FEATURE_SHAPE:
            raise RuntimeError(
                f"{name} input shape must be (None, {FEATURE_SHAPE}), found {input_shape}."
            )

    @staticmethod
    def _features(waveform: np.ndarray) -> np.ndarray:
        x = np.asarray(waveform, dtype=np.float32).reshape(-1)
        if not x.size or not np.all(np.isfinite(x)):
            raise ValueError("Audio must be a non-empty finite waveform.")
        if x.size > N_SAMPLES:
            x = x[:N_SAMPLES]
        elif x.size < N_SAMPLES:
            x = np.pad(x, (0, N_SAMPLES - x.size))

        peak = float(np.max(np.abs(x)))
        if peak > 0.0:
            x = x / peak

        stft = tf.signal.stft(x, frame_length=1024, frame_step=512, fft_length=1024)
        mel = tf.matmul(tf.square(tf.abs(stft)), MEL_MATRIX)
        mel = tf.math.log(mel + 1e-6)
        mel = (mel - tf.reduce_mean(mel)) / (tf.math.reduce_std(mel) + 1e-6)
        features = mel[..., tf.newaxis].numpy().astype(np.float32)
        if features.shape != FEATURE_SHAPE or not np.all(np.isfinite(features)):
            raise ValueError(f"Unexpected audio feature shape/values: {features.shape}")
        return features

    @staticmethod
    def _checked_probabilities(values: Any, expected_count: int, label: str) -> np.ndarray:
        probabilities = np.asarray(values, dtype=np.float64).reshape(-1)
        if (
            probabilities.shape != (expected_count,)
            or not np.all(np.isfinite(probabilities))
            or np.any(probabilities < 0.0)
            or np.any(probabilities > 1.0)
        ):
            raise RuntimeError(f"{label} returned invalid probabilities.")
        total = float(probabilities.sum())
        if not np.isclose(total, 1.0, atol=1e-3):
            raise RuntimeError(f"{label} probabilities sum to {total:.6f}, not 1.")
        return probabilities / total

    @staticmethod
    def _top_predictions(
        labels: list[str], probabilities: np.ndarray, group_score: float
    ) -> list[dict[str, Any]]:
        order = np.argsort(probabilities)[::-1][:3]
        predictions = []
        for idx in order:
            subtype_probability = float(probabilities[int(idx)])
            confidence = float(group_score * subtype_probability)
            name = labels[int(idx)]
            predictions.append({
                "pest": name,
                "species": name,
                "scientific_name": name,
                "common_name": name,
                "confidence": confidence,
                "probability": confidence,
                "subtype_confidence": subtype_probability,
            })
        return predictions

    @staticmethod
    def _top_group_predictions(labels: list[str], probabilities: np.ndarray) -> list[dict[str, Any]]:
        order = np.argsort(probabilities)[::-1][:3]
        return [
            {"group": labels[int(i)], "confidence": float(probabilities[int(i)])}
            for i in order
        ]

    def predict(self, waveform: np.ndarray) -> dict[str, Any]:
        features = self._features(waveform)[None, ...]
        group_raw = self.group_model(features, training=False).numpy()[0]
        group_probabilities = self._checked_probabilities(
            group_raw, len(self.groups), "Eight-group model"
        )
        group_idx = int(np.argmax(group_probabilities))
        group_name = self.groups[group_idx]
        group_score = float(group_probabilities[group_idx])
        top_groups = self._top_group_predictions(self.groups, group_probabilities)

        group_threshold_info = (self.manifest.get("group_model") or {}).get("threshold") or {}
        group_threshold = float(group_threshold_info.get("minimum_confidence", 0.0))
        if not 0.0 <= group_threshold <= 1.0:
            raise RuntimeError(f"Invalid group confidence threshold: {group_threshold}")

        if group_score < group_threshold:
            return {
                "pest": None,
                "confidence": group_score,
                "insect_group": "UNKNOWN",
                "group_score": group_score,
                "top_predictions": [],
                "broad_group_prediction": "UNKNOWN",
                "broad_group_confidence": group_score,
                "broad_group_top_predictions": top_groups,
                "identification_label": "Unidentified sound",
                "rejection_reason": "group_confidence_below_validation_threshold",
            }

        expert = self.experts.get(group_name)
        expert_info = self.subtype_manifest.get(group_name, {})
        subtype_labels = list(expert_info.get("labels") or [])
        if expert is None or not subtype_labels:
            return {
                "pest": group_name,
                "confidence": group_score,
                "insect_group": group_name,
                "group_score": group_score,
                "top_predictions": self._top_predictions(
                    [group_name], np.asarray([1.0]), group_score
                ),
                "broad_group_prediction": group_name,
                "broad_group_confidence": group_score,
                "broad_group_top_predictions": top_groups,
                "identification_label": "Possible group match; subtype unavailable",
                "rejection_reason": None,
            }

        subtype_raw = expert(features, training=False).numpy()[0]
        subtype_probabilities = self._checked_probabilities(
            subtype_raw, len(subtype_labels), f"{group_name} subtype model"
        )
        subtype_idx = int(np.argmax(subtype_probabilities))
        subtype_score = float(subtype_probabilities[subtype_idx])
        threshold_info = expert_info.get("threshold") or {}
        subtype_threshold = float(threshold_info.get("minimum_confidence", 0.95))
        top_predictions = self._top_predictions(subtype_labels, subtype_probabilities, group_score)
        joint_confidence = float(group_score * subtype_score)

        if subtype_score < subtype_threshold:
            return {
                "pest": None,
                "confidence": joint_confidence,
                "insect_group": group_name,
                "group_score": group_score,
                "top_predictions": [],
                "broad_group_prediction": group_name,
                "broad_group_confidence": group_score,
                "broad_group_top_predictions": top_groups,
                "identification_label": "Group detected; subtype uncertain",
                "rejection_reason": "subtype_confidence_below_validation_threshold",
            }

        return {
            "pest": subtype_labels[subtype_idx],
            "confidence": joint_confidence,
            "insect_group": group_name,
            "group_score": group_score,
            "top_predictions": top_predictions,
            "broad_group_prediction": group_name,
            "broad_group_confidence": group_score,
            "broad_group_top_predictions": top_groups,
            "identification_label": "Possible match",
            "rejection_reason": None,
        }
