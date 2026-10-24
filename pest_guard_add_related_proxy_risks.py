#!/usr/bin/env python3
"""Assign preliminary related-taxon crop-risk tiers for the 35 previously UNKNOWN classes.

This is a proxy-based screening pass, not a claim of species-specific pest status.
Run from the Pest guard repository root:
    python .\\pest_guard_add_related_proxy_risks.py
Only class_metadata.json is changed; a timestamped backup is created first.
"""
from __future__ import annotations
import json, shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODEL = ROOT / "backend" / "ai_model" / "pest_new_dataset_candidate"
CLASS_PATH = MODEL / "class_names.json"
COMMON_PATH = MODEL / "common_names.json"
META_PATH = MODEL / "class_metadata.json"

def norm(value):
    return "".join(ch for ch in str(value or "").casefold() if ch.isalnum())

# These 10 receive MEDIUM as a conservative related-taxon/feeding-guild screening tier.
# The rationales clearly distinguish direct experimental/related-taxon evidence from a
# species-specific crop-pest finding.
MEDIUM = {
    "Acheta domesticus": (
        "A 2024 controlled study found that house crickets consume and damage millet seeds and wheat grains, with smaller/softer seeds more susceptible. MEDIUM is a preliminary potential-risk tier based on experimental seed damage; this does not establish field losses or a local infestation.",
        ["Millet seeds", "Wheat grains"],
        "Science of the Total Environment (2024), phytosanitary threat study of Acheta domesticus",
        "https://www.sciencedirect.com/science/article/pii/S0048969724005114",
        "Seed damage was demonstrated experimentally; real field impact depends on abundance, crop stage, storage/field setting, and location.",
    ),
    "Chorthippus apricarius": (
        "PROXY TIER: this species is documented as a grass-feeding grasshopper associated with field margins and grasslands. Agricultural guidance notes that some grasshopper species can damage young crops at high densities, but that not all species are crop pests. MEDIUM is a cautious guild-level screening tier, not species-specific proof of economic damage.",
        [],
        "Agriculture and Agri-Food Canada, Reduced-Risk Strategy for Grasshopper Management; Orthoptera.ch species account",
        "https://agriculture.canada.ca/en/science/agriculture-and-agri-food-research-centres/pest-management-144",
        "Related-guild proxy only; crop injury depends on exact species, density, crop stage, and geography.",
    ),
    "Chorthippus biguttulus": (
        "PROXY TIER: a grass-feeding Acrididae grasshopper. Agricultural guidance confirms that some grasshopper species can damage crops, especially young plants, under high-density/outbreak conditions; it also cautions that pest and non-pest species differ. MEDIUM is a related-guild screening estimate, not a confirmed species-specific pest status.",
        [],
        "Agriculture and Agri-Food Canada, Reduced-Risk Strategy for Grasshopper Management; Orthoptera recording scheme species account",
        "https://agriculture.canada.ca/en/science/agriculture-and-agri-food-research-centres/pest-management-144",
        "Related-guild proxy only; no site-specific density or crop damage has been assessed.",
    ),
    "Chorthippus mollis": (
        "PROXY TIER: this grass-feeding species belongs to the Chorthippus grasshopper group, which includes species with documented crop/forage feeding. Agricultural guidance warns that only some grasshopper species cause economically meaningful damage and that outbreaks are density-dependent. MEDIUM is a cautious related-guild screening tier, not exact-species confirmation.",
        [],
        "Agriculture and Agri-Food Canada, Reduced-Risk Strategy for Grasshopper Management; Chorthippus brunneus species account as a related-guild reference",
        "https://agriculture.canada.ca/en/science/agriculture-and-agri-food-research-centres/pest-management-144",
        "Related-taxon proxy; local crop risk cannot be inferred without species validation and field monitoring.",
    ),
    "Chorthippus vagans": (
        "PROXY TIER: a grass-feeding Chorthippus grasshopper. General agricultural guidance documents crop losses from certain grasshoppers at high density, especially during young crop stages, but stresses that pest status differs among species. MEDIUM is a screening estimate by related feeding guild, not a direct finding that this species causes economic losses.",
        [],
        "Agriculture and Agri-Food Canada, Reduced-Risk Strategy for Grasshopper Management",
        "https://agriculture.canada.ca/en/science/agriculture-and-agri-food-research-centres/pest-management-144",
        "Related-guild proxy only; not a local infestation forecast.",
    ),
    "Conocephalus dorsalis": (
        "PROXY TIER: crop-feeding potential is inferred from the related genus Conocephalus. FAO rice-IPM material notes that C. longipennis can feed on rice panicles, while its role as a predator of rice stem-borer eggs is described as more important. MEDIUM signals a possible crop interaction, not established economic pest status for C. dorsalis.",
        ["Rice (genus-level analogue only)"],
        "FAO, Rice IPM in Asia: ecological principles underlying the Farmer Field School (related Conocephalus species)",
        "https://www.fao.org/4/ac834e/ac834e08.htm",
        "Genus-level proxy using a different species in rice systems; ecological role and risk can differ substantially.",
    ),
    "Conocephalus fuscus": (
        "PROXY TIER: crop-feeding potential is inferred from the related genus Conocephalus. FAO rice-IPM material notes that C. longipennis may feed on rice panicles, though predation on stem-borer eggs is considered more important. MEDIUM is a cautious related-genus screening estimate, not evidence that C. fuscus is an economic crop pest.",
        ["Rice (genus-level analogue only)"],
        "FAO, Rice IPM in Asia: ecological principles underlying the Farmer Field School (related Conocephalus species)",
        "https://www.fao.org/4/ac834e/ac834e08.htm",
        "Genus-level proxy using a different species; field impact depends on prey availability, crop, density, and region.",
    ),
    "Omocestus petraeus": (
        "PROXY TIER: a steppe grasshopper assigned a MEDIUM screening tier based on the general grasshopper crop-risk guild. Agricultural guidance documents crop injury by some grasshoppers at outbreak densities, particularly to young crops, but explicitly notes differences between pest and non-pest species. This is not direct evidence of economic damage by O. petraeus.",
        [],
        "Agriculture and Agri-Food Canada, Reduced-Risk Strategy for Grasshopper Management",
        "https://agriculture.canada.ca/en/science/agriculture-and-agri-food-research-centres/pest-management-144",
        "Related-guild proxy; no site-specific crop or population data.",
    ),
    "Pseudochorthippus parallelus": (
        "PROXY TIER: this meadow grasshopper is a grass-feeding herbivore, and field experiments document herbivory on grass mixtures. General grasshopper agricultural guidance describes possible crop damage by some species at high densities. MEDIUM is a cautious screening estimate for a widespread grass-feeding species, not proof of economic crop loss from this species at this site.",
        ["Grasses and forage (feeding-guild evidence)"],
        "Scientific Reports, full-lifecycle field experiment on Pseudochorthippus parallelus; Agriculture and Agri-Food Canada grasshopper management guidance",
        "https://www.nature.com/articles/s41598-020-64252-5",
        "Experimental herbivory and related-guild crop risk do not establish field economic injury; risk depends on crop, density, and region.",
    ),
    "Tettigonia cantans": (
        "PROXY TIER: MEDIUM is inferred from the same-genus Tettigonia viridissima, for which an agricultural handbook records economic crop interactions in some regions. This is not direct evidence that T. cantans causes the same damage; keep the tier provisional until species-specific agricultural evidence is found.",
        [],
        "USDA Agriculture Handbook 273, Crop Insects of Northeast Africa–Southwest Asia (related Tettigonia species evidence)",
        "https://www.govinfo.gov/content/pkg/GOVPUB-A-PURL-gpo22225/pdf/GOVPUB-A-PURL-gpo22225.pdf",
        "Same-genus proxy; host range and severity can differ by species and region.",
    ),
}

# The remaining 25 get LOW as a provisional screening priority based on reported natural
# grassland/heath/woodland ecology or the absence of a reliable economic-crop-pest record in
# this rapid review. For Platypleura labels with unresolved species identity, the LOW tier is
# especially provisional and based only on a broad cicada analogue, not a Platypleura species study.
LOW_GROUPS = {
    "Barbitistes yersini": (
        "LOW PROXY: this European bush-cricket label had no reliable exact-species evidence of economic crop injury in this rapid review. LOW means lower screening priority under the available evidence, not harmlessness; confirm the species and inspect local crop damage if present.",
        "GBIF taxonomic search (species identity/reference only; crop-risk evidence not established)",
        "https://api.gbif.org/v1/species/search?q=Barbitistes%20yersini&limit=5",
        "Exact species-specific agricultural impact remains uncertain; tier is provisional and not treatment advice.",
    ),
    "Chrysochraon dispar": (
        "LOW PROXY: a regional Orthoptera account describes feeding on grasses, herbs and low bushes in wet, unmown habitats and tall-herb communities; the retrieved account focuses on habitat ecology rather than economic crop damage. LOW is a preliminary screening tier, not proof of zero crop risk.",
        "European locusts and their ecology: Chrysochraon dispar species account",
        "https://pyrgus.de/Chrysochraon_en.html",
        "Habitat information is European and does not establish local crop injury outside those contexts.",
    ),
    "Ephippiger diurnus": (
        "LOW PROXY: a habitat study treats Ephippiger diurnus as a specialist of low-productivity heathland and open landscapes; no reliable exact-species economic crop-damage evidence was established in this rapid review. LOW is a screening estimate, not a guarantee of no plant damage.",
        "Journal of Insect Conservation, habitat and reproduction of Ephippiger diurnus and Gampsocleis glabra",
        "https://link.springer.com/article/10.1007/s10841-024-00643-7",
        "Evidence is from northwestern European heathland systems; local plant interactions may differ.",
    ),
    "Gampsocleis glabra": (
        "LOW PROXY: published habitat research describes this bush-cricket as a specialist of xerothermic grassland and notes threatened/declining isolated populations; the study does not identify it as an economic crop pest. LOW represents lower crop-risk priority based on available evidence, not harmlessness.",
        "Journal of Insect Conservation, habitat requirements of Gampsocleis glabra",
        "https://link.springer.com/article/10.1007/s10841-020-00265-9",
        "The source concerns European grassland conservation and does not prove crop risk in other regions.",
    ),
    "Platypleura cf. catenata": (
        "LOW PROXY WITH VERY LOW CONFIDENCE: the model label is an uncertain taxonomic identification (cf.); no species-specific crop-risk evidence was established. General cicada extension guidance reports that adult feeding usually causes little plant injury but egg-laying by dense emergences can damage young woody plants. This North American cicada analogy must not be treated as direct evidence for Platypleura.",
        "University of Connecticut Periodical Cicada Information Pages (broad cicada analogue, not Platypleura-specific)",
        "https://cicadas.uconn.edu/pest-status/",
        "Species identification is unresolved and the source describes North American periodical cicadas, so risk confidence is very low.",
    ),
    "Platypleura plumosa": (
        "LOW PROXY WITH VERY LOW CONFIDENCE: no reliable species-specific crop-impact evidence was established in this rapid review. A broad cicada analogue suggests that adult feeding often causes little plant injury, although dense emergences may injure young woody plants through egg-laying. This is not direct evidence for Platypleura plumosa.",
        "University of Connecticut Periodical Cicada Information Pages (broad cicada analogue, not Platypleura-specific)",
        "https://cicadas.uconn.edu/pest-status/",
        "North American periodical-cicada evidence is not directly transferable to an African Platypleura species.",
    ),
    "Platypleura sp. 10": (
        "LOW PROXY WITH VERY LOW CONFIDENCE: this is an unresolved genus-level model label, not a confirmed species. A broad cicada analogue reports limited adult feeding damage in general but potential twig injury to young woody plants during dense emergence. Do not treat this as verified crop-risk evidence for the unidentified taxon.",
        "University of Connecticut Periodical Cicada Information Pages (broad cicada analogue, not Platypleura-specific)",
        "https://cicadas.uconn.edu/pest-status/",
        "Taxon is unresolved and the comparator is geographically/taxonomically different; risk tier is provisional only.",
    ),
    "Platypleura sp. 12 cf. hirtipennis": (
        "LOW PROXY WITH VERY LOW CONFIDENCE: the 'sp.' and 'cf.' label indicates an unresolved or tentative identification. No species-specific crop-impact evidence was established; a broad cicada analogue suggests adult feeding is often minor but dense emergences can injure young woody plants by egg-laying. This does not establish risk for this taxon.",
        "University of Connecticut Periodical Cicada Information Pages (broad cicada analogue, not Platypleura-specific)",
        "https://cicadas.uconn.edu/pest-status/",
        "Taxon is unresolved and the comparator is a North American cicada group, not this Platypleura taxon.",
    ),
    "Platypleura sp. 13": (
        "LOW PROXY WITH VERY LOW CONFIDENCE: unresolved genus-level label; this review found no reliable species-specific crop-risk source. A broad cicada analogue suggests adult feeding is generally limited, though dense emergence can damage young woody twigs during egg-laying. This is not verified evidence for the unidentified species.",
        "University of Connecticut Periodical Cicada Information Pages (broad cicada analogue, not Platypleura-specific)",
        "https://cicadas.uconn.edu/pest-status/",
        "Taxon is unresolved; analogue species are geographically different, so this tier has very low confidence.",
    ),
}

# Remaining low-tier entries use the relevant family/guild guidance. Those records are explicitly
# tagged as proxies because a rapid search did not confirm species-specific economic crop losses.
LOW_GENERIC = {
    "Eupholidoptera schmidti", "Gomphocerippus rufus", "Metrioptera brachyptera",
    "Myrmeleotettix maculatus", "Nemobius sylvestris", "Omocestus rufipes",
    "Omocestus viridulus", "Phaneroptera falcata", "Pholidoptera aptera",
    "Pholidoptera griseoaptera", "Pholidoptera littoralis", "Platycleis albopunctata",
    "Pseudochorthippus montanus", "Roeseliana roeselii", "Stenobothrus lineatus",
    "Stenobothrus stigmaticus",
}

# Every class left after the previously reviewed 12 is named here exactly.
EXPECTED_PROXY_CLASSES = set(MEDIUM) | set(LOW_GROUPS) | LOW_GENERIC

def main():
    for path in (CLASS_PATH, COMMON_PATH, META_PATH):
        if not path.is_file():
            raise SystemExit(f"Required file not found: {path.relative_to(ROOT)}")
    classes = json.loads(CLASS_PATH.read_text(encoding="utf-8"))
    common_names = json.loads(COMMON_PATH.read_text(encoding="utf-8"))
    metadata = json.loads(META_PATH.read_text(encoding="utf-8"))
    if len(classes) != 47 or len(common_names) != 47 or len(metadata) != 47:
        raise SystemExit(f"Expected 47 classes/common names/metadata records; got {len(classes)}/{len(common_names)}/{len(metadata)}. No changes made.")
    by_class = {norm(item.get("model_class")): item for item in metadata}
    if len(by_class) != 47 or set(norm(x) for x in classes) != set(by_class):
        raise SystemExit("Class labels and metadata records do not match exactly. No changes made.")
    existing_unknown = {item["model_class"] for item in metadata if item.get("risk") == "UNKNOWN"}
    expected = {name for name in classes if norm(name) in {norm(x) for x in EXPECTED_PROXY_CLASSES}}
    missing_mapping = EXPECTED_PROXY_CLASSES - set(classes)
    if missing_mapping:
        raise SystemExit("Risk mapping contains class(es) not in the model: " + ", ".join(sorted(missing_mapping)) + ". No changes made.")
    # Ensure this follow-up targets exactly the 35 formerly UNKNOWN entries. Existing evidence-based
    # tiers from the first review are preserved and never overwritten.
    if len(existing_unknown) != 35:
        raise SystemExit(f"Expected exactly 35 UNKNOWN entries before proxy pass, found {len(existing_unknown)}. No changes made.")
    expected_unknown_norm = {norm(x) for x in existing_unknown}
    if expected_unknown_norm != {norm(x) for x in EXPECTED_PROXY_CLASSES}:
        missing = existing_unknown - EXPECTED_PROXY_CLASSES
        extra = EXPECTED_PROXY_CLASSES - existing_unknown
        raise SystemExit(f"Proxy mappings do not match the 35 UNKNOWN entries. Unmapped={sorted(missing)}; already classified={sorted(extra)}. No changes made.")

    backup = META_PATH.with_name(f"class_metadata.backup_before_related_risks_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    shutil.copy2(META_PATH, backup)
    for label, record in MEDIUM.items():
        item = by_class[norm(label)]
        item["risk"] = "MEDIUM"
        item["risk_rationale"] = record[0]
        item["affected_crops"] = record[1]
        item["source_name"] = record[2]
        item["source_url"] = record[3]
        item["geographic_limitations"] = record[4]
        item["risk_basis"] = "RELATED_TAXON_OR_FEEDING_GUILD_PROXY"
        item["risk_confidence"] = "LOW"
    for label, record in LOW_GROUPS.items():
        item = by_class[norm(label)]
        item["risk"] = "LOW"
        item["risk_rationale"] = record[0]
        item["affected_crops"] = []
        item["source_name"] = record[1]
        item["source_url"] = record[2]
        item["geographic_limitations"] = record[3]
        item["risk_basis"] = "RELATED_TAXON_OR_ECOLOGY_PROXY"
        item["risk_confidence"] = "VERY_LOW" if "VERY LOW CONFIDENCE" in record[0] else "LOW"
    general_url = "https://agriculture.canada.ca/en/science/agriculture-and-agri-food-research-centres/pest-management-144"
    for label in LOW_GENERIC:
        item = by_class[norm(label)]
        item["risk"] = "LOW"
        item["risk_rationale"] = (
            "LOW PROXY: this rapid review did not establish reliable exact-species evidence of economically meaningful crop injury. "
            "The tier is a provisional screening priority based on available Orthoptera ecology and the caution that only some grasshoppers/bush-crickets become agricultural pests. "
            "It is not proof that this species is harmless; verify the insect and assess visible crop damage locally before making any control decision."
        )
        item["affected_crops"] = []
        item["source_name"] = "Agriculture and Agri-Food Canada, Reduced-Risk Strategy for Grasshopper Management (guild-level context; not exact-species confirmation)"
        item["source_url"] = general_url
        item["geographic_limitations"] = "Proxy only; the source discusses selected grasshopper pests, not this exact model class or necessarily its geographic range."
        item["risk_basis"] = "RELATED_TAXON_OR_ECOLOGY_PROXY"
        item["risk_confidence"] = "LOW"

    ordered = [by_class[norm(label)] for label in classes]
    temporary = META_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(ordered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(META_PATH)
    counts = {tier: sum(1 for entry in ordered if entry.get("risk") == tier) for tier in ("HIGH", "MEDIUM", "LOW", "UNKNOWN")}
    if sum(counts.values()) != 47 or counts["UNKNOWN"] != 0:
        raise SystemExit(f"Updated metadata failed tier count validation: {counts}. Backup: {backup}")
    print("SUCCESS: assigned related-taxon/ecology proxy tiers to all 35 previously UNKNOWN model classes.")
    print("Metadata records:", len(ordered))
    print("Risk counts:", counts)
    print("Proxy-assigned species:", len(EXPECTED_PROXY_CLASSES))
    print("Backup:", backup.relative_to(ROOT))
    print("IMPORTANT: These 35 assignments are explicitly provisional proxy tiers with risk_basis and risk_confidence fields. They are not species-confirmed field diagnoses. Platypleura labels with unresolved taxonomy have very-low-confidence genus-level proxies.")

if __name__ == "__main__":
    main()
