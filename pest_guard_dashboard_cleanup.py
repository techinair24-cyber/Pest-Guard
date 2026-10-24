from pathlib import Path
import re

path = Path('src/pages/LiveMonitoring.jsx')
if not path.is_file():
    raise SystemExit(f'Cannot find {path}. Run this script from the Pest guard project root.')

source = path.read_text(encoding='utf-8')
original = source

# Remove the confusing word without claiming the identification is verified.
old_label = 'Unverified model prediction'
count = source.count(old_label)
if count != 1:
    raise SystemExit(f'Expected exactly one UI label {old_label!r}, found {count}. No changes made.')
source = source.replace(old_label, 'AI model prediction', 1)

# Hide the optional catalogue/symptoms card from Latest Detection only.
pattern = re.compile(
    r"\n\s*\{matchingPestRecord\?\.description\s*\|\|\s*matchingPestRecord\?\.symptoms\s*\?\s*\(\s*"
    r"<div className=\"latest-catalog-reference\">.*?"
    r"</div>\s*\)\s*:\s*null\s*\}\s*\n",
    re.DOTALL,
)
source, removed = pattern.subn('\n', source, count=1)
if removed != 1:
    raise SystemExit('Could not uniquely find the Latest Detection catalogue/symptoms card. No changes made.')

if source == original:
    raise SystemExit('No changes were made.')

path.write_text(source, encoding='utf-8', newline='\n')
print('SUCCESS: Replaced “Unverified model prediction” with “AI model prediction”.')
print('SUCCESS: Removed the Latest Detection catalogue description/symptoms card.')
print('Risk computation and Detect/Stop controls were not changed.')
