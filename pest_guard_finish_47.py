from __future__ import annotations

import re
import sys
from pathlib import Path


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def method_bounds(text: str, name: str) -> tuple[int, int]:
    lines = text.splitlines(keepends=True)
    start_line = None
    for i, line in enumerate(lines):
        if re.match(rf"^    (?:async\s+)?def\s+{re.escape(name)}\s*\(", line):
            start_line = i
            break
    if start_line is None:
        fail(f"Could not find test method: {name}")
    end_line = len(lines)
    for i in range(start_line + 1, len(lines)):
        if re.match(r"^    (?:async\s+)?def\s+\w+\s*\(", lines[i]) or re.match(r"^class\s+\w+", lines[i]):
            end_line = i
            break
    starts = sum(len(x) for x in lines[:start_line])
    ends = sum(len(x) for x in lines[:end_line])
    return starts, ends


def transform_method(text: str, name: str, transform) -> str:
    start, end = method_bounds(text, name)
    return text[:start] + transform(text[start:end]) + text[end:]


def replace_in_method(text: str, name: str, replacements: dict[str, str]) -> str:
    def change(block: str) -> str:
        for old, new in replacements.items():
            if old not in block:
                fail(f"Expected text {old!r} not found inside {name}")
            block = block.replace(old, new)
        return block
    return transform_method(text, name, change)


def replace_method(text: str, name: str, replacement: str) -> str:
    start, end = method_bounds(text, name)
    return text[:start] + replacement.rstrip() + "\n\n" + text[end:]


def main() -> None:
    root = Path.cwd()
    main_path = root / "backend" / "main.py"
    tests_path = root / "backend" / "test_prediction_safety.py"
    if not (root / ".git").exists() or not main_path.is_file() or not tests_path.is_file():
        fail("Run this script from the Pest guard repository root, containing .git, backend/main.py, and backend/test_prediction_safety.py.")

    main_text = main_path.read_text(encoding="utf-8")
    tests_text = tests_path.read_text(encoding="utf-8")
    if 'PEST_MODEL = os.getenv("PEST_MODEL", "new_dataset_candidate")' not in main_text:
        fail("The backend does not appear to use the new 47-class-only loader. No files were changed.")
    if "len(class_names) != 47" not in main_text:
        fail("The expected 47-class loader check was not found. No files were changed.")
    if "def test_every_yamnet_class_has_complete_metadata(self):" not in tests_text:
        fail("The expected legacy YAMNet test was not found. No files were changed.")

    # Make solutions fail closed when a request has an unknown-risk result or a label
    # that is not one of the current 47 active model classes.
    anchor = "    # Match the requested candidate against the database catalog.\n"
    guard = (
        "    # Sound-model output is an unverified candidate, not a confirmed identity.\n"
        "    # Do not use species-specific catalogue treatment when the risk is unknown\n"
        "    # or when the label is not part of this model's active 47-class vocabulary.\n"
        "    if (\n"
        "        payload.pest not in class_names\n"
        "        or str(payload.risk or '').strip().upper() == 'UNKNOWN'\n"
        "    ):\n"
        "        return _fallback_uncertain_solution(payload)\n\n"
    )
    if guard not in main_text:
        if anchor not in main_text:
            fail("Could not locate generate_ai_solution insertion point. No files were changed.")
        main_text = main_text.replace(anchor, guard + anchor, 1)

    # Update tests whose fixtures still named classes that were removed with the old model.
    old_label_methods = {
        "test_ai_prediction_is_persisted_before_broadcast": '"Cicada"',
        "test_ai_prediction_uses_catalog_risk_without_verifying_identity": '"Cicada"',
        "test_high_model_score_keeps_class_as_unverified_suggestion": '"Cicada"',
        "test_prediction_inference_is_dispatched_off_the_async_event_loop": '"Cicada"',
        "test_unvalidated_device_score_is_not_stored_as_a_pest": '"Cicada"',
        "test_one_device_event_is_committed_and_returned_once_by_history": '"Cicada"',
    }
    for name, old in old_label_methods.items():
        tests_text = replace_in_method(tests_text, name, {old: "main.class_names[0]"})

    old_species_methods = {
        "test_prediction_metadata_is_identical_in_database_and_websocket": '"Desert locust"',
        "test_ai_metadata_matches_saved_row_latest_history_and_websocket": '"Desert locust"',
    }
    for name, old in old_species_methods.items():
        tests_text = replace_in_method(tests_text, name, {old: "main.class_names[0]"})

    # Make the class-index test assert the selected model's real vocabulary.
    tests_text = tests_text.replace(
        "def test_model_class_index_maps_to_cicada_label(self):",
        "def test_model_class_index_maps_to_candidate_label(self):",
        1,
    )
    tests_text = replace_in_method(
        tests_text,
        "test_model_class_index_maps_to_candidate_label",
        {'"Cicada"': "main.class_names[0]"},
    )

    # The new metadata uses the common-name capitalization from common_names.json.
    tests_text = replace_in_method(
        tests_text,
        "test_scientific_name_matching_normalizes_class_formatting",
        {'"Common field grasshopper"': '"Common Field Grasshopper"'},
    )

    # Replace the legacy 20-class YAMNet metadata test with a 47-class integrity test.
    new_metadata_test = '''    def test_every_model_class_has_complete_metadata(self):
        self.assertEqual(len(main.class_names), 47)
        self.assertEqual(len(main.common_names), 47)
        self.assertEqual(len(main.MODEL_SPECIES_METADATA), 47)

        for model_class, common_name in zip(main.class_names, main.common_names):
            with self.subTest(model_class=model_class):
                key = main._normalize_pest_label(model_class)
                metadata = main.MODEL_SPECIES_METADATA[key]
                self.assertEqual(metadata["model_class"], model_class)
                self.assertEqual(metadata["common_name"], common_name)
                self.assertIn(metadata["risk"], {"LOW", "MEDIUM", "HIGH", "UNKNOWN"})
                self.assertTrue(metadata["risk_rationale"].strip())
                self.assertTrue(metadata["source_url"].startswith("https://"))
                self.assertIsInstance(metadata["affected_crops"], list)
'''
    tests_text = replace_method(
        tests_text,
        "test_every_yamnet_class_has_complete_metadata",
        new_metadata_test,
    )

    # Risk preference is now tested using a temporary, synthetic HIGH-risk metadata
    # entry; actual 47-class metadata remains UNKNOWN unless evidence has been verified.
    new_risk_test = '''    def test_valid_model_risk_wins_over_blank_catalog_risk(self):
        model_class = main.class_names[0]
        key = main._normalize_pest_label(model_class)
        metadata = main.MODEL_SPECIES_METADATA_BY_NAME[key]
        original_risk = metadata["risk"]
        metadata["risk"] = "HIGH"
        try:
            with patch.object(
                main,
                "_find_pest_record_normalized",
                return_value=Mock(risk="  "),
            ):
                resolved = main._resolve_species_metadata(model_class, self.database)
            self.assertEqual(resolved["risk"], "HIGH")
        finally:
            metadata["risk"] = original_risk
'''
    tests_text = replace_method(
        tests_text,
        "test_valid_model_risk_wins_over_blank_catalog_risk",
        new_risk_test,
    )

    # Do not partially patch either file: compile the backend and check that stale
    # YAMNet symbol expectations have been removed from the updated tests first.
    if "YAMNET_CLASS_NAMES" in tests_text or "test_every_yamnet_class_has_complete_metadata" in tests_text:
        fail("Legacy YAMNet references remain in tests after replacement. No files were written.")

    compile(main_text, str(main_path), "exec")

    # Write only after all transformation checks pass.
    main_path.write_text(main_text, encoding="utf-8", newline="\n")
    tests_path.write_text(tests_text, encoding="utf-8", newline="\n")

    print("SUCCESS")
    print("- Added a fail-closed solutions guard for unknown-risk or non-model labels.")
    print("- Updated obsolete prediction test fixtures to use the active 47-class vocabulary.")
    print("- Replaced the 20-class YAMNet metadata test with 47-class metadata coverage.")
    print("- Kept real species risk labels unchanged; synthetic HIGH risk is confined to its test.")
    print("- Backend Python syntax check passed.")
    print("Next: run the safety tests from backend, then inspect the results before committing.")


if __name__ == "__main__":
    main()
