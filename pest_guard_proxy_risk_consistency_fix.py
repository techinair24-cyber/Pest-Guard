from pathlib import Path
import re
import shutil
from datetime import datetime

ROOT = Path.cwd()
MAIN = ROOT / "backend" / "main.py"
TESTS = ROOT / "backend" / "test_prediction_safety.py"

if not MAIN.exists() or not TESTS.exists():
    raise SystemExit("ERROR: Run this script from the Pest guard repository root.")

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
main_backup = MAIN.with_name(f"main.py.backup_before_risk_consistency_{stamp}")
test_backup = TESTS.with_name(f"test_prediction_safety.py.backup_before_risk_consistency_{stamp}")
shutil.copy2(MAIN, main_backup)
shutil.copy2(TESTS, test_backup)

main_text = MAIN.read_text(encoding="utf-8")
old_risk_logic = '''    model_risk = str((metadata or {}).get("risk") or "").strip().upper()
    catalog_risk = str(getattr(pest_record, "risk", "") or "").strip().upper()
    model_risk_is_valid = model_risk in {"LOW", "MEDIUM", "HIGH"}
    catalog_risk_is_valid = catalog_risk in {"LOW", "MEDIUM", "HIGH"}
    risk = (
        model_risk
        if model_risk_is_valid
        else catalog_risk
        if catalog_risk_is_valid
        else "UNKNOWN"
    )
    risk_uses_catalog = not model_risk_is_valid and catalog_risk_is_valid
'''
new_risk_logic = '''    model_risk = str((metadata or {}).get("risk") or "").strip().upper()
    catalog_risk = str(getattr(pest_record, "risk", "") or "").strip().upper()
    # Related-taxon/ecology tiers are explicitly provisional. Prefer a valid
    # matching catalogue risk over a proxy tier; direct model metadata remains
    # highest priority when it is not marked as a proxy.
    model_risk_is_proxy = bool((metadata or {}).get("risk_basis"))
    model_risk_is_valid = (
        model_risk in {"LOW", "MEDIUM", "HIGH"} and not model_risk_is_proxy
    )
    model_proxy_risk_is_valid = (
        model_risk in {"LOW", "MEDIUM", "HIGH"} and model_risk_is_proxy
    )
    catalog_risk_is_valid = catalog_risk in {"LOW", "MEDIUM", "HIGH"}
    risk = (
        model_risk
        if model_risk_is_valid
        else catalog_risk
        if catalog_risk_is_valid
        else model_risk
        if model_proxy_risk_is_valid
        else "UNKNOWN"
    )
    risk_uses_catalog = not model_risk_is_valid and catalog_risk_is_valid
'''
if main_text.count(old_risk_logic) != 1:
    raise SystemExit(f"ERROR: Expected exactly one risk-resolver block, found {main_text.count(old_risk_logic)}. No source changes made.")
main_text = main_text.replace(old_risk_logic, new_risk_logic, 1)

old_detection_logic = '''    detection_status = payload.status
    detection_pest = payload.pest if payload.pest in class_names else None
    detection_risk = payload.risk
    if detection_status == "HARMFUL_PEST":
        # Keep a trained class only as an unverified suggestion.
        detection_status = "UNKNOWN"
        detection_risk = "UNKNOWN"
    elif detection_status == "UNKNOWN":
        detection_risk = "UNKNOWN"
    else:
        detection_pest = None
        detection_risk = "LOW"
'''
new_detection_logic = '''    detection_status = payload.status
    detection_pest = payload.pest if payload.pest in class_names else None
    if detection_status == "HARMFUL_PEST":
        # Retain a trained class only as an unconfirmed suggestion.
        detection_status = "UNKNOWN"

    if detection_status == "UNKNOWN":
        # Keep the persisted risk consistent with the matching model metadata;
        # ignore any risk sent by the device for an unconfirmed prediction.
        detection_risk = (
            _resolve_species_metadata(detection_pest)["risk"]
            if detection_pest
            else "UNKNOWN"
        )
    else:
        detection_pest = None
        detection_risk = "LOW"
'''
if main_text.count(old_detection_logic) != 1:
    raise SystemExit(f"ERROR: Expected exactly one device-risk block, found {main_text.count(old_detection_logic)}. No source changes made.")
main_text = main_text.replace(old_detection_logic, new_detection_logic, 1)

# Test expectations changed because metadata now intentionally supplies proxy
# tiers for classes that previously had no researched tier. Keep the catalog
# precedence assertion as HIGH in its dedicated test.
test_text = TESTS.read_text(encoding="utf-8")

def replace_in_test(text, test_name, old, new, expected=1):
    match = re.search(rf"(?m)^    def {re.escape(test_name)}\(self\):.*?(?=^    def |^class |\Z)", text, re.S)
    if not match:
        raise SystemExit(f"ERROR: Could not find test {test_name}. No source changes made.")
    section = match.group(0)
    n = section.count(old)
    if n != expected:
        raise SystemExit(f"ERROR: In {test_name}, expected {expected} occurrences of assertion, found {n}. No source changes made.")
    section = section.replace(old, new, expected)
    return text[:match.start()] + section + text[match.end():]

expected_proxy = 'main._resolve_species_metadata(main.class_names[0])["risk"]'
test_text = replace_in_test(
    test_text,
    "test_ai_prediction_is_persisted_before_broadcast",
    'self.assertEqual(detection.risk, "UNKNOWN")',
    f'self.assertEqual(detection.risk, {expected_proxy})',
)
test_text = replace_in_test(
    test_text,
    "test_high_model_score_keeps_class_as_unverified_suggestion",
    'self.assertEqual(response["risk"], "UNKNOWN")',
    f'self.assertEqual(response["risk"], {expected_proxy})',
)
test_text = replace_in_test(
    test_text,
    "test_unvalidated_device_score_is_not_stored_as_a_pest",
    'self.assertEqual(detection.risk, "UNKNOWN")',
    f'self.assertEqual(detection.risk, {expected_proxy})',
)
test_text = replace_in_test(
    test_text,
    "test_unvalidated_device_score_is_not_stored_as_a_pest",
    'self.assertEqual(event["risk"], "UNKNOWN")',
    f'self.assertEqual(event["risk"], {expected_proxy})',
)
test_text = replace_in_test(
    test_text,
    "test_one_device_event_is_committed_and_returned_once_by_history",
    'self.assertEqual(history["detections"][0]["risk"], "UNKNOWN")',
    f'self.assertEqual(history["detections"][0]["risk"], {expected_proxy})',
)

# Only write once every exact match has been verified.
MAIN.write_text(main_text, encoding="utf-8", newline="\n")
TESTS.write_text(test_text, encoding="utf-8", newline="\n")
print("SUCCESS: risk precedence now prefers a matching catalogue risk over provisional proxy tiers.")
print("SUCCESS: unconfirmed device records persist the same risk tier that their serializer returns.")
print("SUCCESS: tests now expect model-metadata risk where an explicit proxy tier exists.")
print(f"Backup: {main_backup}")
print(f"Backup: {test_backup}")
print("Next: run backend/test_prediction_safety.py; do not commit until tests pass.")
