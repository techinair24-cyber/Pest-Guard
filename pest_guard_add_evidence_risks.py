#!/usr/bin/env python3
"""Apply a conservative, source-linked first-pass crop-risk review to Pest Guard's 47 classes.

Run from repository root:
    python .\\pest_guard_add_evidence_risks.py

Only updates backend/ai_model/pest_new_dataset_candidate/class_metadata.json.
The trained model, class order, common-name list, UI, database, and firmware are untouched.
"""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODEL_DIR = ROOT / "backend" / "ai_model" / "pest_new_dataset_candidate"
CLASS_PATH = MODEL_DIR / "class_names.json"
COMMON_PATH = MODEL_DIR / "common_names.json"
METADATA_PATH = MODEL_DIR / "class_metadata.json"


def normalize(value: object) -> str:
    return "".join(c for c in str(value or "").casefold() if c.isalnum())

# Every risk tier below is limited to what the linked source supports. Severity is
# regional/outbreak-dependent and is not a prediction of current local infestation.
EVIDENCE = {
    "Chorthippus albomarginatus": {
        "risk": "MEDIUM",
        "risk_rationale": (
            "Regional agricultural accounts report damage to cereals, hay meadows, pastures, "
            "and forage grasses when populations become high. This supports a context-dependent "
            "crop/forage concern, not a claim that damage is occurring at this site."
        ),
        "affected_crops": ["Cereals", "Hay meadows", "Pastures", "Forage grasses"],
        "source_name": "Regional agricultural species account for Chorthippus albomarginatus",
        "source_url": "https://hleb-produkt.ru/saranchovye/1652-stroynaya-ili-belopolosaya-kobylka-chorthippus-albomarginatus-dg.html",
        "geographic_limitations": "Evidence is regional and population-dependent; severity elsewhere is not established by this source.",
    },
    "Chorthippus brunneus": {
        "risk": "MEDIUM",
        "risk_rationale": (
            "A crop-insect field survey reported common field grasshopper damage in sesame. "
            "The source supports crop injury in that study context but does not establish a "
            "universal loss level or a current site-specific outbreak."
        ),
        "affected_crops": ["Sesame", "Cereal crops"],
        "source_name": "International Journal of Entomology Research crop-insect survey",
        "source_url": "https://www.entomologyjournals.com/assets/archives/2017/vol2issue3/2-2-22-906.pdf",
        "geographic_limitations": "Observed crop injury is geographically and density dependent.",
    },
    "Gomphocerus sibiricus": {
        "risk": "HIGH",
        "risk_rationale": (
            "A peer-reviewed global review describes this species as a serious agricultural pest "
            "in parts of the former USSR, Kazakhstan, Siberia, and Xinjiang, with severe damage "
            "reported to cereal crops and pasture/forage. HIGH describes documented potential in "
            "those regions, not confirmed damage at this site."
        ),
        "affected_crops": ["Wheat", "Rye", "Oats", "Barley", "Maize", "Millet", "Potato", "Cabbage", "Mustard", "Pasture", "Hay"],
        "source_name": "Frontiers in Ecology and Evolution, global review on locusts and grazing",
        "source_url": "https://www.frontiersin.org/journals/ecology-and-evolution/articles/10.3389/fevo.2019.00263/full",
        "geographic_limitations": "Serious damage is reported in specific eastern European/Asian regions and is not a site-specific risk forecast.",
    },
    "Gryllus bimaculatus": {
        "risk": "HIGH",
        "risk_rationale": (
            "Agricultural references document attacks on seedlings and economic crop damage; "
            "reports include wheat, crucifers, rice, and severe potato damage in some regions. "
            "HIGH reflects documented crop-pest potential in those contexts, not a verified "
            "field diagnosis or current outbreak."
        ),
        "affected_crops": ["Wheat", "Rice", "Potato", "Crucifers", "Cucurbits", "Cotton", "Tobacco"],
        "source_name": "USDA Agriculture Handbook 273, Crop Insects of Northeast Africa–Southwest Asia, with peer-reviewed Gryllidae review",
        "source_url": "https://www.govinfo.gov/content/pkg/GOVPUB-A-PURL-gpo22225/pdf/GOVPUB-A-PURL-gpo22225.pdf",
        "geographic_limitations": "The source documents strong regional differences; crop losses depend on abundance, crop, and location.",
    },
    "Gryllus campestris": {
        "risk": "MEDIUM",
        "risk_rationale": (
            "The USDA crop-insect handbook reports feeding on young leaves, buds, and seedlings, "
            "with medium-to-severe damage when populations are heavy enough. MEDIUM reflects "
            "this population-dependent crop-pest potential, not a confirmed local infestation."
        ),
        "affected_crops": ["Wheat", "Barley", "Cotton", "Tobacco", "Nursery plants", "Other young crops"],
        "source_name": "USDA Agriculture Handbook 273, Crop Insects of Northeast Africa–Southwest Asia",
        "source_url": "https://www.govinfo.gov/content/pkg/GOVPUB-A-PURL-gpo22225/pdf/GOVPUB-A-PURL-gpo22225.pdf",
        "geographic_limitations": "Damage is described as medium-to-severe under heavy populations in source regions.",
    },
    "Melanogryllus desertus": {
        "risk": "HIGH",
        "risk_rationale": (
            "Agricultural research from Central Anatolia identifies black cricket as a polyphagous "
            "pest of cultivated crops, with greatest damage from later nymphs and young adults; "
            "regional agricultural accounts also report damage to vegetables and field crops. "
            "HIGH reflects documented regional crop-pest potential, not current local damage."
        ),
        "affected_crops": ["Vegetables", "Field crops", "Vineyards", "Gardens", "Pastures"],
        "source_name": "Turkish Ministry of Agriculture research institute study on harmful black cricket in cultivated crops",
        "source_url": "https://arastirma.tarimorman.gov.tr/zmmae/Belgeler/Sol%20Menu/Yay%C4%B1nlar/Ara%C5%9Ft%C4%B1rma%20Y%C4%B1ll%C4%B1klar%C4%B1/ZMAY_1994_24-25.pdf",
        "geographic_limitations": "Evidence is strongest for Central Anatolia and nearby source regions; damage varies with crop, season, and population.",
    },
    "Decticus verrucivorus": {
        "risk": "MEDIUM",
        "risk_rationale": (
            "The USDA crop-insect handbook lists cereals and cotton as host crops and identifies "
            "the species as an economic species in Iran. MEDIUM indicates documented regional "
            "crop-pest potential; the source does not prove a current infestation at this site."
        ),
        "affected_crops": ["Cereals", "Cotton"],
        "source_name": "USDA Agriculture Handbook 273, Crop Insects of Northeast Africa–Southwest Asia",
        "source_url": "https://www.govinfo.gov/content/pkg/GOVPUB-A-PURL-gpo22225/pdf/GOVPUB-A-PURL-gpo22225.pdf",
        "geographic_limitations": "The economic-pest designation is specifically reported for Iran; local risk may differ.",
    },
    "Tettigonia viridissima": {
        "risk": "MEDIUM",
        "risk_rationale": (
            "The USDA crop-insect handbook reports this species as an economic species in Iran "
            "and Cyprus on cotton, cereals, beets, legumes, and other plants. A separate Hungarian "
            "maize-field study found only slight damage in the observed fields. MEDIUM reflects "
            "variable, region-dependent crop-pest potential."
        ),
        "affected_crops": ["Cotton", "Cereals", "Beets", "Legumes", "Maize", "Tobacco"],
        "source_name": "USDA Agriculture Handbook 273, Crop Insects of Northeast Africa–Southwest Asia",
        "source_url": "https://www.govinfo.gov/content/pkg/GOVPUB-A-PURL-gpo22225/pdf/GOVPUB-A-PURL-gpo22225.pdf",
        "geographic_limitations": "Impacts vary regionally; a Hungarian maize study reported slight damage, while the handbook notes economic-pest status in Iran and Cyprus.",
    },
    "Oecanthus pellucens": {
        "risk": "LOW",
        "risk_rationale": (
            "A crop-pest survey reported only a few specimens on young tobacco leaves and described "
            "the damage as slight. Other regional references list this species among plant-feeding "
            "insects, so LOW reflects the observed survey conditions rather than a universal guarantee."
        ),
        "affected_crops": ["Tobacco", "Cereals", "Cotton", "Grapes", "Fruit trees"],
        "source_name": "Crop Pest Fauna in Ethiopia survey",
        "source_url": "https://swfrec.ifas.ufl.edu/hlb/database/pdf/00002313.pdf",
        "geographic_limitations": "The slight-damage evidence is from a limited survey; abundance and crop context can change the result.",
    },
    "Leptophyes punctatissima": {
        "risk": "LOW",
        "risk_rationale": (
            "A fruit-crop handbook describes this as a minor fruit-tree pest. Although isolated "
            "reports of extensive leaf damage exist, the handbook says such damage is generally "
            "of little or no economic importance and is usually localized."
        ),
        "affected_crops": ["Apple", "Nectarine", "Peach", "Other stone-fruit trees"],
        "source_name": "Pests of Fruit Crops, Colour Handbook",
        "source_url": "https://books.tarbaweya.org/static/documents/uploads/pdf/Agriculture/Pests%20of%20Fruit%20Crops%20A%20Colour%20Handbook.pdf",
        "geographic_limitations": "The reference describes generally minor impacts, with occasional localized leaf injury in orchards.",
    },
    "Phaneroptera nana": {
        "risk": "LOW",
        "risk_rationale": (
            "A fruit-crop handbook records browsing on a range of plants but states that this "
            "species is not a significant fruit-crop pest and that crop damage is of little or no "
            "importance in the described contexts. LOW is not a statement that damage is impossible."
        ),
        "affected_crops": ["Pear", "Apple", "Grapevine", "Other fruit crops"],
        "source_name": "Pests of Fruit Crops, Colour Handbook",
        "source_url": "https://books.tarbaweya.org/static/documents/uploads/pdf/Agriculture/Pests%20of%20Fruit%20Crops%20A%20Colour%20Handbook.pdf",
        "geographic_limitations": "Evidence is from fruit-crop contexts; field risk elsewhere is not established by this reference.",
    },
    "Tylopsis lilifolia": {
        "risk": "LOW",
        "risk_rationale": (
            "A regional natural-history species profile describes this plant-feeding bush-cricket "
            "as not causing crop damage. LOW reflects that source's regional account; it should not "
            "be interpreted as a locally measured risk assessment."
        ),
        "affected_crops": [],
        "source_name": "Regional Orthoptera species profile (Phrygana.eu)",
        "source_url": "https://phrygana.eu/Fauna/Orthoptera/Tylopsis-lilifolia/Tylopsis-lilifolia.html",
        "geographic_limitations": "Regional species profile; local observations may differ.",
    },
}


def main() -> None:
    for required in (CLASS_PATH, COMMON_PATH, METADATA_PATH):
        if not required.is_file():
            raise SystemExit(f"Required file not found: {required.relative_to(ROOT)}")

    classes = json.loads(CLASS_PATH.read_text(encoding="utf-8"))
    common_names = json.loads(COMMON_PATH.read_text(encoding="utf-8"))
    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))

    if len(classes) != 47 or len(common_names) != 47:
        raise SystemExit(
            f"Expected 47 model classes and common names; found {len(classes)} and {len(common_names)}. No files changed."
        )
    if not isinstance(metadata, list) or len(metadata) != 47:
        raise SystemExit(
            f"Expected 47 metadata records; found {len(metadata) if isinstance(metadata, list) else 'non-list'}. No files changed."
        )

    by_label: dict[str, dict] = {}
    for item in metadata:
        key = normalize(item.get("model_class"))
        if not key or key in by_label:
            raise SystemExit("Metadata has an empty or duplicate model_class. No files changed.")
        by_label[key] = item

    missing = [c for c in classes if normalize(c) not in by_label]
    if missing:
        raise SystemExit("Metadata is missing model classes: " + ", ".join(missing) + ". No files changed.")

    class_keys = {normalize(c) for c in classes}
    invalid_mapping = [name for name in EVIDENCE if normalize(name) not in class_keys]
    if invalid_mapping:
        raise SystemExit("Evidence mapping label(s) are not in this model: " + ", ".join(invalid_mapping) + ". No files changed.")

    backup = METADATA_PATH.with_name(
        f"class_metadata.backup_before_risk_review_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    shutil.copy2(METADATA_PATH, backup)

    for label, evidence in EVIDENCE.items():
        entry = by_label[normalize(label)]
        entry["risk"] = evidence["risk"]
        entry["risk_rationale"] = evidence["risk_rationale"]
        entry["affected_crops"] = evidence["affected_crops"]
        entry["source_name"] = evidence["source_name"]
        entry["source_url"] = evidence["source_url"]
        entry["geographic_limitations"] = evidence["geographic_limitations"]

    # Make UNKNOWN explicit for classes for which this review did not find enough
    # exact-species evidence to justify a LOW/MEDIUM/HIGH tier. Preserve the model's
    # existing source fields but ensure they are not described as proof of crop risk.
    reviewed_keys = {normalize(k) for k in EVIDENCE}
    for label in classes:
        entry = by_label[normalize(label)]
        if normalize(label) not in reviewed_keys:
            if entry.get("risk") not in {"LOW", "MEDIUM", "HIGH"}:
                entry["risk"] = "UNKNOWN"
                entry["risk_rationale"] = (
                    "No sufficiently reliable crop-damage evidence for this exact model class "
                    "was established in this rapid review to support a LOW, MEDIUM, or HIGH tier. "
                    "UNKNOWN does not mean zero risk. Assessment needs the crop, geography, "
                    "species confirmation, and local abundance."
                )
                entry["geographic_limitations"] = (
                    "No general tier assigned; risk may vary by crop, geography, season, and population density."
                )
                source = str(entry.get("source_name") or "")
                if "taxonomic" not in source.casefold():
                    entry["source_name"] = "Taxonomic search only; crop-risk evidence not established in rapid review"
                source_url = str(entry.get("source_url") or "")
                if not source_url.startswith("https://"):
                    query = label.replace(" ", "%20")
                    entry["source_url"] = f"https://api.gbif.org/v1/species/search?q={query}&limit=5"

    # Reorder metadata to the model class order for easy auditing.
    ordered = [by_label[normalize(label)] for label in classes]
    temporary = METADATA_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(ordered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(METADATA_PATH)

    # Reload and verify required backend metadata contract.
    result = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    if len(result) != 47:
        raise SystemExit("Post-write validation failed; restore backup: " + str(backup))
    if any(item.get("risk") not in {"LOW", "MEDIUM", "HIGH", "UNKNOWN"} for item in result):
        raise SystemExit("Post-write risk validation failed; restore backup: " + str(backup))
    if any(not str(item.get("risk_rationale") or "").strip() for item in result):
        raise SystemExit("Post-write rationale validation failed; restore backup: " + str(backup))
    if any(not str(item.get("source_url") or "").startswith("https://") for item in result):
        raise SystemExit("Post-write source URL validation failed; restore backup: " + str(backup))

    counts = {key: sum(1 for item in result if item["risk"] == key) for key in ("HIGH", "MEDIUM", "LOW", "UNKNOWN")}
    print("SUCCESS: updated species risk metadata with a conservative evidence-based review.")
    print("Metadata records:", len(result))
    print("Risk counts:", counts)
    print("Species assigned a sourced LOW/MEDIUM/HIGH tier:", len(EVIDENCE))
    print("Backup:", backup.relative_to(ROOT))
    print("Important: UNKNOWN entries are not classified as harmless; evidence was insufficient in this rapid review.")
    print("Risk is regional and population-dependent. This does not identify a pest or determine live field infestation.")

if __name__ == "__main__":
    main()
