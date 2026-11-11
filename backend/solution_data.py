import csv
import json
from pathlib import Path

from pest_data import PEST_DATA


SOLUTION_RECORDS = [
    {
        "solution_id": "rhinoceros_beetle_coconut_high_2026_11_11",
        "pest_id": "rhinoceros_beetle",
        "crop_id": "coconut",
        "risk_level": "HIGH",
        "status": "VERIFIED",
        "region": "India (TNAU guidance; confirm local applicability)",
        "scientific_name": "Oryctes rhinoceros",
        "description": None,
        "identification_signs": None,
        "crop_damage": "Leaf and crown damage.",
        "affected_plant_parts": "Leaves and crown.",
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
        "prevention": (
            "Remove and burn dead coconut trees that may serve as breeding "
            "sites, and collect and destroy beetle stages found in manure pits."
        ),
        "monitoring": (
            "The TNAU coconut pest-management page recommends examining palm "
            "crowns at each harvest."
        ),
        "safety_precautions": None,
        "expert_advice": None,
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
                    "crop_damage",
                    "affected_plant_parts",
                    "biological_control_options",
                    "cultural_control_methods",
                    "mechanical_control_methods",
                    "monitoring",
                    "prevention",
                ],
            }
        ],
        "reviewed_on": "2026-11-11",
    }
]

_PEST_BY_ID = {pest["pest_id"]: pest for pest in PEST_DATA}
_SOLUTION_BY_IDENTITY = {
    (item["pest_id"], item["crop_id"]): item
    for item in SOLUTION_RECORDS
}
_MATRIX_PATH = Path(__file__).resolve().parent.parent / "pest_crop_evidence_matrix.csv"


def _matrix_sources(row):
    sources = []
    fields = (
        (
            "source_title",
            "source_organization",
            "source_url",
            "source_publication_date",
            ["crop_id", "crop_damage"]
            if row.get("relationship_status") == "CONFIRMED_HOST"
            else ["related_taxon_or_context"],
        ),
        (
            "taxonomy_source_title",
            "taxonomy_source_organization",
            "taxonomy_source_url",
            "taxonomy_publication_date",
            ["taxonomy"],
        ),
        (
            "indian_occurrence_source_title",
            "indian_occurrence_source_organization",
            "indian_occurrence_source_url",
            "indian_occurrence_publication_date",
            ["indian_occurrence"],
        ),
    )
    for title_field, organization_field, url_field, date_field, supports in fields:
        title = row.get(title_field, "").strip()
        organization = row.get(organization_field, "").strip()
        url = row.get(url_field, "").strip()
        if not (title and organization and url):
            continue
        sources.append(
            {
                "title": title,
                "organization": organization,
                "url": url,
                "publication_date": row.get(date_field, "").strip() or None,
                "reviewed_on": row.get("review_date", "").strip() or None,
                "supports": supports,
            }
        )
    try:
        management_sources = json.loads(
            row.get("management_source_references", "") or "[]"
        )
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Invalid management_source_references for {row.get('pest_id')}"
        ) from error
    if not isinstance(management_sources, list):
        raise ValueError(
            f"management_source_references must be a list for {row.get('pest_id')}"
        )
    sources.extend(management_sources)

    merged = {}
    for source in sources:
        key = source.get("url")
        if not key:
            continue
        existing = merged.get(key)
        if existing:
            existing["supports"] = sorted(
                set(existing.get("supports", []))
                | set(source.get("supports", []))
            )
        else:
            merged[key] = source
    return list(merged.values())


def _read_matrix_list(row, field):
    value = row.get(field, "").strip()
    if not value:
        return []
    try:
        result = json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Invalid {field} JSON for {row.get('pest_id')}"
        ) from error
    if not isinstance(result, list):
        raise ValueError(f"{field} must be a list for {row.get('pest_id')}")
    return result


def _build_coverage_record(row):
    pest_id = row["pest_id"]
    pest = _PEST_BY_ID[pest_id]
    if row["risk_level"] != pest["risk"]:
        raise ValueError(f"Evidence matrix risk mismatch for pest_id={pest_id}")

    relationship_status = row.get("relationship_status") or "NEEDS_REVIEW"
    verified_host_crops = []
    if relationship_status == "CONFIRMED_HOST":
        if not row.get("crop_id") or not row.get("crop_name"):
            raise ValueError(
                f"Confirmed host relationship lacks crop identity for {pest_id}"
            )
        verified_host_crops.append(
            {
                "crop_id": row["crop_id"],
                "crop_name": row["crop_name"],
                "relationship_status": relationship_status,
                "damage_evidence": row.get("damage_evidence") or None,
                "source_references": _matrix_sources(row),
            }
        )

    solution = _SOLUTION_BY_IDENTITY.get((pest_id, row.get("crop_id", "")))
    if solution is None and len(verified_host_crops) == 1:
        solution = _SOLUTION_BY_IDENTITY.get(
            (pest_id, verified_host_crops[0]["crop_id"])
        )
    taxonomy_status = row.get("taxonomy_status") or "NEEDS_REVIEW"
    scientific_name = row.get("scientific_name", "").strip() or None
    if taxonomy_status not in {"TAXON_MATCH_CONFIRMED", "INDIAN_HOST_CONFIRMED"}:
        scientific_name = None
    if solution and solution.get("status") == "VERIFIED":
        scientific_name = solution.get("scientific_name") or scientific_name

    source_references = _matrix_sources(row)
    solution_sources = solution.get("source_references", []) if solution else []
    if solution_sources:
        source_references = solution_sources

    missing_fields = _read_matrix_list(row, "missing_evidence_fields")
    field_status = {
        "scientific_name": (
            "VERIFIED"
            if scientific_name
            else taxonomy_status
        ),
        "indian_occurrence": (
            row.get("indian_occurrence_status") or "NEEDS_REVIEW"
        ),
        "verified_host_crops": relationship_status,
        "crop_damage": row.get("damage_status") or "NOT_ESTABLISHED",
        "affected_plant_parts": (
            row.get("affected_plant_parts_status") or "NOT_ESTABLISHED"
        ),
        "cultural_management": (
            row.get("cultural_management_status") or "NOT_ESTABLISHED"
        ),
        "biological_management": (
            row.get("biological_management_status") or "NOT_ESTABLISHED"
        ),
        "chemical_management": (
            row.get("chemical_management_status") or "NOT_ESTABLISHED"
        ),
        "prevention": row.get("prevention_status") or "NOT_ESTABLISHED",
    }

    research_data = {
        "common_name": pest["name"],
        "insect_group": pest["insect_group"],
        "risk_level": pest["risk"],
        "research_status": row.get("research_status") or "NEEDS_REVIEW",
        "taxonomy_status": taxonomy_status,
        "scientific_name": scientific_name,
        "candidate_scientific_name": (
            row.get("candidate_scientific_name", "").strip() or None
        ),
        "accepted_synonyms": row.get("accepted_synonyms", "").strip() or None,
        "indian_occurrence_status": field_status["indian_occurrence"],
        "indian_occurrence_evidence": (
            row.get("indian_occurrence_evidence", "").strip() or None
        ),
        "relationship_status": relationship_status,
        "verified_host_crops": verified_host_crops,
        "unverified_crop_candidate": (
            {
                "crop_id": row.get("crop_id"),
                "crop_name": row.get("crop_name"),
            }
            if row.get("crop_id") and relationship_status != "CONFIRMED_HOST"
            else None
        ),
        "crop_damage": (
            row.get("crop_damage", "").strip() or None
            if field_status["crop_damage"] == "VERIFIED"
            else None
        ),
        "affected_plant_parts": (
            row.get("affected_plant_parts", "").strip() or None
            if field_status["affected_plant_parts"] == "VERIFIED"
            else None
        ),
        "management": {
            "cultural": row.get("cultural_management", "").strip() or None,
            "biological": row.get("biological_management", "").strip() or None,
            "chemical": row.get("chemical_management", "").strip() or None,
            "prevention": row.get("prevention_methods", "").strip() or None,
            "mechanical": solution.get("mechanical_control_methods") if solution else None,
            "monitoring": solution.get("monitoring") if solution else None,
        },
        "field_status": field_status,
        "source_references": source_references,
        "missing_evidence_fields": missing_fields,
        "verification_reason": row.get("verification_reason", "").strip() or None,
        "reviewed_on": row.get("review_date", "").strip() or None,
        "solution_status": solution.get("status") if solution else None,
    }

    return {
        "pest_id": pest_id,
        "review_status": research_data["research_status"],
        "unresolved_fields": missing_fields,
        "reviewed_on": research_data["reviewed_on"],
        "research_data": research_data,
    }


def _load_coverage_data():
    with _MATRIX_PATH.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))

    ids = [row.get("pest_id") for row in rows]
    expected_ids = set(_PEST_BY_ID)
    if len(rows) != len(expected_ids) or set(ids) != expected_ids:
        raise ValueError(
            "Evidence matrix must contain exactly one row for every catalogue pest"
        )
    return [_build_coverage_record(row) for row in rows]


PEST_COVERAGE_DATA = _load_coverage_data()
