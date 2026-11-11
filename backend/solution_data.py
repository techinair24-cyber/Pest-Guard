from pest_data import PEST_DATA


SOLUTION_RECORDS = [
    {
        "solution_id": "rhinoceros_beetle_coconut_high_2026_11_11",
        "pest_id": "rhinoceros_beetle",
        "crop_id": "coconut",
        "risk_level": "HIGH",
        "status": "NEEDS_REVIEW",
        "region": "India; regional applicability requires review",
        "scientific_name": "Oryctes rhinoceros",
        "description": None,
        "identification_signs": None,
        "crop_damage": None,
        "recommended_treatment": None,
        "immediate_control_measures": None,
        "biological_control_options": (
            "The TNAU coconut pest-management page recommends incorporating "
            "Metarhizium anisopliae in manure pits and field release of "
            "Baculovirus-inoculated adult rhinoceros beetles. Confirm local "
            "availability and suitability with the state agricultural "
            "extension service."
        ),
        "cultural_control_methods": (
            "The TNAU coconut pest-management page recommends removing and "
            "burning dead coconut trees that can serve as breeding sites, and "
            "collecting and destroying beetle life stages found in manure pits."
        ),
        "mechanical_control_methods": (
            "The TNAU coconut pest-management page recommends examining palm "
            "crowns at harvest and hooking out and killing adult beetles."
        ),
        "chemical_control_options": None,
        "prevention": None,
        "monitoring": (
            "The TNAU coconut pest-management page recommends examining palm "
            "crowns at each harvest."
        ),
        "safety_precautions": None,
        "expert_advice": (
            "Seek guidance from the local State Agricultural University, "
            "Krishi Vigyan Kendra, or agriculture department before treatment. "
            "No chemical product or dosage is specified in this record."
        ),
        "source_references": [
            {
                "title": "Coconut Pest and Disease Management",
                "organization": "Tamil Nadu Agricultural University (TNAU)",
                "url": (
                    "https://agritech.tnau.ac.in/horticulture/"
                    "horti_pcrops_coconut_pest_dis_mgnt.html"
                ),
                "reviewed_on": "2026-11-11",
                "supports": [
                    "scientific_name",
                    "crop_id",
                    "biological_control_options",
                    "cultural_control_methods",
                    "mechanical_control_methods",
                    "monitoring",
                ],
            }
        ],
        "reviewed_on": "2026-11-11",
    }
]

PEST_COVERAGE_DATA = [
    {
        "pest_id": pest_id,
        "review_status": "NEEDS_REVIEW",
        "unresolved_fields": [
            "scientific_name",
            "verified_crop_associations",
            "crop_damage",
            "identification_signs",
            "crop_and_region_specific_ipm",
            "prevention",
            "safety_precautions",
            "source_review",
        ],
        "reviewed_on": "2026-11-11",
    }
    for pest_id in (pest["pest_id"] for pest in PEST_DATA)
]
