import hashlib
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
import train_lightweight_background_gate as gate_trainer


def _write_valid_manifest(tmp_path):
    dataset = tmp_path / "dataset"
    rows = []
    for group_index, group in enumerate(gate_trainer.GROUP_LABELS):
        group_dir = dataset / group
        group_dir.mkdir(parents=True)
        for split in ("train", "validation"):
            relative = f"{group}/recording_{split}.wav"
            audio_path = dataset / relative
            content = f"{group}:{split}".encode()
            audio_path.write_bytes(content)
            rows.append({
                "path": relative,
                "group": group,
                "subtype": None,
                "sha256": hashlib.sha256(content).hexdigest(),
                "source_ids": [f"source-{group_index}-{split}"],
                "component_id": f"component-{group_index}-{split}",
                "split": split,
            })
    payload = {
        "format_version": 1,
        "dataset_root": str(dataset.resolve()),
        "group_labels": list(gate_trainer.GROUP_LABELS),
        "subclass_labels": {group: [] for group in gate_trainer.GROUP_LABELS},
        "recordings": rows,
    }
    manifest = tmp_path / "split_manifest.json"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    return dataset, manifest, payload


def test_accepts_verified_eight_group_manifest_and_resolves_class_indices(tmp_path):
    dataset, manifest, payload = _write_valid_manifest(tmp_path)

    result = gate_trainer.load_manifest(manifest, dataset)

    assert len(result["train"]) == len(gate_trainer.GROUP_LABELS)
    assert len(result["validation"]) == len(gate_trainer.GROUP_LABELS)
    assert {row["label_index"] for row in result["train"]} == set(range(8))
    assert result["manifest_sha256"] == hashlib.sha256(manifest.read_bytes()).hexdigest()
    assert result["dataset_root"] == str(dataset.resolve())


def test_rejects_stale_47_class_manifest(tmp_path):
    dataset, manifest, _ = _write_valid_manifest(tmp_path)
    manifest.write_text(json.dumps({
        "train": [{"path": "old.wav", "label_index": 0}],
        "validation": [],
    }), encoding="utf-8")

    with pytest.raises(ValueError, match="versioned eight-group JSON"):
        gate_trainer.load_manifest(manifest, dataset)


def test_rejects_seven_group_order_and_wrong_dataset_root(tmp_path):
    dataset, manifest, payload = _write_valid_manifest(tmp_path)
    payload["group_labels"] = list(gate_trainer.GROUP_LABELS[:-1])
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="approved eight groups"):
        gate_trainer.load_manifest(manifest, dataset)

    payload["group_labels"] = list(gate_trainer.GROUP_LABELS)
    payload["dataset_root"] = str(tmp_path / "other_dataset")
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="does not match --dataset"):
        gate_trainer.load_manifest(manifest, dataset)


def test_rejects_duplicate_paths_hash_mismatch_and_split_leakage(tmp_path):
    dataset, manifest, payload = _write_valid_manifest(tmp_path)
    payload["recordings"].append(dict(payload["recordings"][0]))
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="recording count"):
        gate_trainer.load_manifest(manifest, dataset)

    dataset, manifest, payload = _write_valid_manifest(tmp_path / "hash_case")
    payload["recordings"][0]["sha256"] = "0" * 64
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="content differs"):
        gate_trainer.load_manifest(manifest, dataset)

    dataset, manifest, payload = _write_valid_manifest(tmp_path / "leak_case")
    payload["recordings"][1]["component_id"] = payload["recordings"][0]["component_id"]
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="component crosses splits"):
        gate_trainer.load_manifest(manifest, dataset)
