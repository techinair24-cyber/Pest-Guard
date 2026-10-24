from pathlib import Path
from datetime import datetime
import shutil
import sys

ROOT = Path.cwd()
MAIN = ROOT / "backend" / "main.py"
if not MAIN.is_file():
    sys.exit("ERROR: Run this script from the Pest guard repository root; backend/main.py was not found.")

text = MAIN.read_text(encoding="utf-8")
old_block = '''        # Preserve the top trained class for display, but do not treat its
        # uncalibrated score as a verified identification.
        predicted_pest = (
            result["pest"] if result["pest"] in class_names else None
        )
        species_metadata = _resolve_species_metadata(predicted_pest, db)
'''
new_block = '''        # Reject weak model outputs rather than displaying an arbitrary top class.
        # This cutoff reduces weak suggestions; it does not guarantee correctness
        # because the model score has not been calibrated as a true probability.
        model_confidence = float(result["confidence"])
        candidate_pest = (
            result["pest"] if result["pest"] in class_names else None
        )
        predicted_pest = (
            candidate_pest
            if (
                candidate_pest is not None
                and model_confidence >= PEST_IDENTIFICATION_CONFIDENCE
            )
            else None
        )
        prediction_message = (
            "Unverified model prediction"
            if predicted_pest
            else "Low-confidence model prediction rejected"
        )
        species_metadata = _resolve_species_metadata(predicted_pest, db)
'''
if text.count(old_block) != 1:
    sys.exit(f"ERROR: Expected exactly one live prediction block, found {text.count(old_block)}. No files changed.")
text = text.replace(old_block, new_block, 1)

# Patch only the /api/ai/predict function body so unrelated flows stay untouched.
route_start = text.find('@app.post("/api/ai/predict")')
if route_start < 0:
    sys.exit('ERROR: Could not locate /api/ai/predict. No files changed.')
route_end = text.find('\n@app.', route_start + 1)
if route_end < 0:
    route_end = len(text)
route = text[route_start:route_end]
confidence_field = '"confidence": result["confidence"],'
if route.count(confidence_field) != 1:
    sys.exit(f"ERROR: Expected one response confidence field in prediction route, found {route.count(confidence_field)}. No files changed.")
route = route.replace('"confidence": result["confidence"],', '"confidence": model_confidence,', 1)
if route.count('confidence=float(result["confidence"]),') != 1:
    sys.exit('ERROR: Expected one persisted confidence field in prediction route. No files changed.')
route = route.replace('confidence=float(result["confidence"]),', 'confidence=model_confidence,', 1)
if route.count('"message": "Unverified model prediction",') != 1:
    sys.exit('ERROR: Expected one response message field in prediction route. No files changed.')
route = route.replace('"message": "Unverified model prediction",', '"message": prediction_message,', 1)
if route.count('message="Unverified model prediction",') != 1:
    sys.exit('ERROR: Expected one persisted message field in prediction route. No files changed.')
route = route.replace('message="Unverified model prediction",', 'message=prediction_message,', 1)
text = text[:route_start] + route + text[route_end:]

backup = MAIN.with_name(f"main.py.backup_before_confidence_reject_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
shutil.copy2(MAIN, backup)
MAIN.write_text(text, encoding="utf-8", newline="\n")
print("SUCCESS: /api/ai/predict now rejects model scores below PEST_IDENTIFICATION_CONFIDENCE.")
print("SUCCESS: rejected low-score results do not attach a candidate species or candidate risk metadata.")
print("SUCCESS: confidence score is preserved for diagnostics; device, website and other detection routes were not changed.")
print(f"Backup: {backup}")
print("NEXT: run backend/test_prediction_safety.py. Do not commit or deploy until tests pass and the new behavior is checked.")
