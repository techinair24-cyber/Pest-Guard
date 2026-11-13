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
        "description": (
            "The Coconut Rhinoceros Beetle is a large, stout, shiny black or "
            "dark-brown beetle, approximately 30–50 mm long. Males have a "
            "prominent curved horn on the head. Adults are mainly active at "
            "night. The larvae are creamy-white to yellowish-white C-shaped "
            "grubs with a brown head capsule and three pairs of thoracic legs. "
            "Larvae develop in decaying organic matter."
        ),
        "identification_signs": (
            "Adult: large dark-brown or black body, prominent curved horn "
            "in males, thick oval shape, strong legs and hard wing covers. "
            "Larva: cream-coloured C-shaped grub with a brown head and "
            "three pairs of legs. Field signs include holes in the central "
            "spindle, freshly chewed fibres around the crown and V-shaped "
            "cuts on opened fronds."
        ),
        "crop_damage": (
            "Adult beetles enter the palm crown and bore into unopened "
            "spear leaves, feeding on tender developing tissues. Damaged "
            "leaves show V-shaped or triangular cuts when they unfold. "
            "Repeated attacks can weaken young palms. Severe damage to "
            "the growing point can cause palm death. Feeding wounds may "
            "also provide entry points for secondary pests and pathogens."
        ),
        "affected_plant_parts": (
            "Central spindle, unopened spear leaves, opened leaves, leaf "
            "bases, crown, unopened inflorescences and growing point. "
            "Young palm collars may also be affected."
        ),
        "recommended_treatment": (
            "Use integrated pest management combining mechanical removal "
            "of adults, management of breeding sites, suitable biological "
            "control, pheromone-based monitoring and physical protection "
            "of vulnerable young palms."
        ),
        "immediate_control_measures": (
            "Inspect the central spindle and crown for fresh holes and "
            "chewed fibres. Carefully extract confirmed adult beetles using "
            "a suitable GI beetle hook without damaging the growing point. "
            "Inspect nearby manure pits, compost heaps and decaying organic "
            "material. Manage confirmed breeding sites and monitor for "
            "fresh attacks."
        ),
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
            "crowns at each harvest and hooking out and killing adult beetles. "
            "It also recommends castor-cake water pots, split tender-coconut "
            "stem or green-petiole traps, light traps after the first summer "
            "and monsoon rains, and Rhinolure pheromone traps at one per "
            "0.5 hectare."
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
        "safety_precautions": (
            "Wear gloves and suitable footwear during inspection. Use GI "
            "hooks carefully and avoid damaging the palm growing point. "
            "Use trained personnel for work at height. Follow approved "
            "product labels and protective-equipment requirements when "
            "handling biological or chemical products."
        ),
        "expert_advice": (
            "Inspect unopened spear leaves regularly. Manage breeding "
            "sites rather than concentrating only on adult beetles. Use "
            "suitable biological control and strategically placed "
            "pheromone traps. Protect young palms and monitor for "
            "secondary Red Palm Weevil attacks and bud rot following injury."
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
                    "description",
                    "identification_signs",
                    "crop_damage",
                    "affected_plant_parts",
                    "recommended_treatment",
                    "immediate_control_measures",
                    "biological_control_options",
                    "cultural_control_methods",
                    "mechanical_control_methods",
                    "monitoring",
                    "prevention",
                    "safety_precautions",
                    "expert_advice",
                ],
            }
        ],
        "reviewed_on": "2026-11-11",
    },
    {
        "solution_id": "european_mole_cricket_potato_2026_11_12",
        "pest_id": "european_mole_cricket",
        "crop_id": "potato",
        "risk_level": "HIGH",
        "status": "NEEDS_REVIEW",
        "region": "General guidance; confirm local applicability in India",
        "scientific_name": "Gryllotalpa gryllotalpa",
        "description": (
            "The European Mole Cricket is a large, brown, underground-dwelling "
            "insect with a cylindrical body, short antennae and powerful "
            "shovel-like forelegs adapted for digging. Adults and nymphs tunnel "
            "through soil and can damage seedlings, roots and underground "
            "plant parts."
        ),
        "identification_signs": (
            "Look for a brown to yellow-brown cylindrical insect with enlarged, "
            "shovel-like front legs, a broad thorax and short antennae. Soil "
            "mounds, raised tunnels and loose soil around damaged plants may "
            "also indicate activity."
        ),
        "crop_damage": (
            "Feeding and tunnelling may injure roots and underground plant "
            "parts. Young plants may wilt, become loose in the soil or suffer "
            "poor establishment. Damage can occur in patches, especially "
            "where populations are high."
        ),
        "affected_plant_parts": (
            "Roots, underground shoots, young stems near soil level, seedlings "
            "and underground storage parts such as tubers."
        ),
        "recommended_treatment": (
            "Use an integrated pest management approach. Inspect the soil and "
            "confirm live mole crickets before choosing a control method. "
            "Prioritise monitoring, suitable mechanical measures and field "
            "sanitation. Consider chemical control only when justified and "
            "when a product is registered and labelled for the crop and target "
            "pest in India."
        ),
        "immediate_control_measures": (
            "Inspect around wilted or damaged plants and carefully examine "
            "the soil for tunnels and live insects. Collect visible crickets "
            "where practical, protect newly planted seedlings and record "
            "locations where fresh damage is found."
        ),
        "biological_control_options": (
            "Encourage natural predators such as birds and ground-dwelling "
            "predators. Entomopathogenic nematodes and fungi such as "
            "Metarhizium anisopliae or Beauveria bassiana may be investigated "
            "only where locally suitable, supported by evidence and available "
            "as approved products."
        ),
        "cultural_control_methods": (
            "Maintain suitable field drainage and avoid excessive irrigation. "
            "Remove unnecessary weeds and crop residues, use healthy planting "
            "material, prepare fields appropriately and inspect nursery beds "
            "before transplanting. Crop rotation and deeper cultivation should "
            "be considered only where suitable for the crop and soil."
        ),
        "mechanical_control_methods": (
            "Hand-collect visible insects where practical. Inspect and excavate "
            "identified tunnels carefully. Pitfall or manure traps may help "
            "monitor or capture mole crickets. Shallow soil disturbance may "
            "expose insects, but should be appropriate for the crop and its "
            "growth stage."
        ),
        "chemical_control_options": (
            "No specific pesticide or dose is recommended here. If infestation "
            "is economically significant, consult current Indian registration "
            "and product-label information. Use only a product approved for "
            "the target pest and crop, following its labelled dose, application "
            "method, protective equipment and waiting period. Do not treat "
            "foreign-study treatments as Indian recommendations."
        ),
        "prevention": (
            "Maintain suitable drainage, avoid excessive soil moisture, remove "
            "unnecessary weeds and residues, inspect nursery soil and planting "
            "material, and monitor fields with a history of mole cricket "
            "activity. Avoid transferring potentially infested soil."
        ),
        "monitoring": (
            "Look for fresh soil mounds, raised tunnels, wilting seedlings, "
            "loose plants and root or tuber injury. Inspect soil around damaged "
            "plants and use suitable traps to monitor activity. Record catches "
            "and new damage over time. No universal action threshold is "
            "specified for all crops and regions."
        ),
        "safety_precautions": (
            "Wear gloves and suitable footwear during soil inspection and "
            "insect collection. Wash hands after handling soil or insects. "
            "For any pesticide, follow the product label and required personal "
            "protective equipment. Keep pesticides away from children, animals "
            "and water sources."
        ),
        "expert_advice": (
            "Confirm the insect identification before taking control action. "
            "Damage is often most serious during seedling establishment. "
            "Consult a local agricultural extension officer or entomologist "
            "if damage persists or identification is uncertain."
        ),
        "source_references": [],
        "reviewed_on": None,
    },
    {
        "solution_id": "european_mole_cricket_cabbage_2026_11_12",
        "pest_id": "european_mole_cricket",
        "crop_id": "cabbage",
        "risk_level": "HIGH",
        "status": "NEEDS_REVIEW",
        "region": "General guidance; confirm local applicability in India",
        "scientific_name": "Gryllotalpa gryllotalpa",
        "description": (
            "The European Mole Cricket is a large, brown, underground insect "
            "with a cylindrical body and powerful shovel-like forelegs. Its "
            "tunnelling and feeding can injure roots and young plants."
        ),
        "identification_signs": (
            "Look for a brown cylindrical insect with enlarged digging "
            "forelegs and short antennae. Raised soil tunnels, small soil "
            "mounds and damaged seedlings may indicate activity."
        ),
        "crop_damage": (
            "Feeding and tunnelling may injure roots and cut young stems near "
            "soil level. Seedlings may wilt, loosen or fail to establish, "
            "causing patchy crop growth."
        ),
        "affected_plant_parts": (
            "Roots, underground shoots, stem bases and young seedlings."
        ),
        "recommended_treatment": (
            "Use integrated pest management. Inspect the soil and confirm "
            "live mole crickets before selecting control measures. Prioritise "
            "monitoring, field sanitation and suitable mechanical methods. "
            "Use chemical control only when justified and when a product is "
            "registered and labelled for cabbage and the target pest in India."
        ),
        "immediate_control_measures": (
            "Inspect around wilted or loose seedlings. Examine nearby soil "
            "for tunnels and live insects, collect visible crickets where "
            "practical, protect new transplants and record fresh damage."
        ),
        "biological_control_options": (
            "Encourage natural predators. Entomopathogenic nematodes and fungi "
            "such as Metarhizium anisopliae or Beauveria bassiana are potential "
            "options to investigate only where locally supported and approved."
        ),
        "cultural_control_methods": (
            "Maintain suitable drainage, avoid excessive irrigation, remove "
            "unnecessary weeds and residues, use healthy transplants and "
            "inspect nursery beds and field soil before planting."
        ),
        "mechanical_control_methods": (
            "Hand-collect visible insects where practical. Carefully inspect "
            "and excavate identified tunnels. Pitfall or manure traps may help "
            "monitor activity. Use shallow soil disturbance only when suitable "
            "for the crop stage."
        ),
        "chemical_control_options": (
            "No specific pesticide or dose is recommended here. If control is "
            "necessary, check current Indian registration and product labels "
            "for cabbage and the target pest. Follow the approved dose, "
            "application method, protective equipment and waiting period."
        ),
        "prevention": (
            "Maintain suitable drainage, avoid excessive soil moisture, "
            "remove unnecessary weeds and residues, inspect nursery soil and "
            "monitor fields with a history of mole cricket activity."
        ),
        "monitoring": (
            "Inspect for fresh tunnels, soil mounds, wilted or missing "
            "seedlings and root injury. Check soil around damaged plants and "
            "record trap catches and new damage."
        ),
        "safety_precautions": (
            "Wear gloves and suitable footwear during inspection. Wash hands "
            "after handling soil or insects. Follow all pesticide label "
            "instructions and keep products away from children, animals and "
            "water sources."
        ),
        "expert_advice": (
            "Confirm the insect identification and assess seedling damage "
            "before choosing control measures. Seek local agricultural advice "
            "if damage continues."
        ),
        "source_references": [],
        "reviewed_on": None,
    },
    {
        "solution_id": "european_mole_cricket_tomato_2026_11_12",
        "pest_id": "european_mole_cricket",
        "crop_id": "tomato",
        "risk_level": "HIGH",
        "status": "NEEDS_REVIEW",
        "region": "General guidance; confirm local applicability in India",
        "scientific_name": "Gryllotalpa gryllotalpa",
        "description": (
            "The European Mole Cricket is a large, brown, underground insect "
            "with a cylindrical body and strong shovel-like forelegs. It "
            "tunnels through soil and may injure roots and young plants."
        ),
        "identification_signs": (
            "Look for a brown cylindrical insect with enlarged digging "
            "forelegs and short antennae. Soil mounds, raised tunnels and "
            "wilting or loosened young plants may indicate activity."
        ),
        "crop_damage": (
            "Tunnelling and feeding may injure roots and cut young stems near "
            "the soil surface. Young tomato plants may wilt, become loose or "
            "fail to establish properly."
        ),
        "affected_plant_parts": (
            "Roots, underground shoots, stem bases and young seedlings."
        ),
        "recommended_treatment": (
            "Use integrated pest management. Confirm live mole crickets and "
            "assess damage before selecting control measures. Prioritise "
            "monitoring, sanitation and suitable mechanical methods. Use "
            "chemical control only when justified and approved for tomato "
            "and the target pest in India."
        ),
        "immediate_control_measures": (
            "Inspect around wilted or loose plants, examine soil for tunnels "
            "and live insects, collect visible crickets where practical and "
            "record affected areas."
        ),
        "biological_control_options": (
            "Encourage natural predators. Entomopathogenic nematodes and fungi "
            "such as Metarhizium anisopliae or Beauveria bassiana may be "
            "investigated only where suitable evidence and locally approved "
            "products are available."
        ),
        "cultural_control_methods": (
            "Maintain suitable drainage, avoid excessive irrigation, remove "
            "unnecessary weeds and residues, use healthy seedlings and "
            "inspect nursery beds and field soil before transplanting."
        ),
        "mechanical_control_methods": (
            "Hand-collect visible insects where practical. Carefully inspect "
            "and excavate identified tunnels. Pitfall or manure traps may help "
            "monitor activity. Use shallow soil disturbance only when suitable "
            "for the crop and growth stage."
        ),
        "chemical_control_options": (
            "No specific pesticide or dose is recommended here. If infestation "
            "requires chemical control, check current Indian registration and "
            "the product label for tomato and the target pest. Follow the "
            "approved dose, application method, protective equipment and "
            "waiting period."
        ),
        "prevention": (
            "Maintain suitable drainage, avoid excessive soil moisture, "
            "remove unnecessary weeds and residues, inspect nursery soil and "
            "monitor fields with a history of mole cricket activity."
        ),
        "monitoring": (
            "Look for fresh soil mounds, raised tunnels, wilting plants, "
            "missing seedlings and root injury. Inspect around affected plants "
            "and record trap catches and new damage."
        ),
        "safety_precautions": (
            "Wear gloves and suitable footwear during inspection. Wash hands "
            "after handling soil or insects. Follow pesticide label "
            "instructions and keep pesticides away from children, animals "
            "and water sources."
        ),
        "expert_advice": (
            "Confirm the insect identification and assess the extent of root "
            "and seedling injury. Seek local agricultural advice if damage "
            "persists."
        ),
        "source_references": [],
        "reviewed_on": None,
    },
    {
        "solution_id": "european_mole_cricket_onion_2026_11_12",
        "pest_id": "european_mole_cricket",
        "crop_id": "onion",
        "risk_level": "HIGH",
        "status": "NEEDS_REVIEW",
        "region": "General guidance; confirm local applicability in India",
        "scientific_name": "Gryllotalpa gryllotalpa",
        "description": (
            "The European Mole Cricket is a large, brown, underground insect "
            "with a cylindrical body and strong shovel-like forelegs. Its "
            "tunnelling and feeding may injure roots and young plants."
        ),
        "identification_signs": (
            "Look for a brown cylindrical insect with enlarged digging "
            "forelegs and short antennae. Raised tunnels, soil mounds and "
            "damaged or wilting seedlings may indicate activity."
        ),
        "crop_damage": (
            "Feeding and tunnelling may injure roots and underground shoots "
            "and cut young stems near soil level. Seedlings may wilt, loosen "
            "or fail to establish, leading to patchy growth."
        ),
        "affected_plant_parts": (
            "Roots, underground shoots, stem bases and young seedlings."
        ),
        "recommended_treatment": (
            "Use integrated pest management. Inspect the soil and confirm "
            "live mole crickets before choosing control measures. Prioritise "
            "monitoring, sanitation and suitable mechanical methods. Use "
            "chemical control only when justified and approved for onion and "
            "the target pest in India."
        ),
        "immediate_control_measures": (
            "Inspect around damaged or wilted seedlings, examine soil for "
            "tunnels and live insects, collect visible crickets where "
            "practical and record locations with fresh damage."
        ),
        "biological_control_options": (
            "Encourage natural predators. Entomopathogenic nematodes and fungi "
            "such as Metarhizium anisopliae or Beauveria bassiana are potential "
            "options to investigate only where locally supported and approved."
        ),
        "cultural_control_methods": (
            "Maintain suitable drainage, avoid excessive irrigation, remove "
            "unnecessary weeds and residues, use healthy planting material "
            "and inspect nursery beds and soil before planting."
        ),
        "mechanical_control_methods": (
            "Hand-collect visible insects where practical. Carefully inspect "
            "and excavate identified tunnels. Pitfall or manure traps may help "
            "monitor activity. Use shallow soil disturbance only when suitable "
            "for the crop and growth stage."
        ),
        "chemical_control_options": (
            "No specific pesticide or dose is recommended here. If chemical "
            "control is necessary, check current Indian registration and "
            "product labels for onion and the target pest. Follow the approved "
            "dose, application method, protective equipment and waiting period."
        ),
        "prevention": (
            "Maintain suitable drainage, avoid excessive soil moisture, "
            "remove unnecessary weeds and residues, inspect planting material "
            "and monitor fields with a history of mole cricket activity."
        ),
        "monitoring": (
            "Look for fresh tunnels, soil mounds, wilted or missing seedlings "
            "and root injury. Inspect soil around affected plants and record "
            "trap catches and new damage."
        ),
        "safety_precautions": (
            "Wear gloves and suitable footwear during inspection. Wash hands "
            "after handling soil or insects. Follow pesticide label "
            "instructions and keep products away from children, animals and "
            "water sources."
        ),
        "expert_advice": (
            "Confirm the insect identification and assess seedling and root "
            "damage before choosing control measures. Seek local agricultural "
            "advice if damage continues."
        ),
        "source_references": [],
        "reviewed_on": None,
    },
    {
        "solution_id": "european_mole_cricket_tobacco_2026_11_12",
        "pest_id": "european_mole_cricket",
        "crop_id": "tobacco",
        "risk_level": "HIGH",
        "status": "NEEDS_REVIEW",
        "region": "General guidance; confirm local applicability in India",
        "scientific_name": "Gryllotalpa gryllotalpa",
        "description": (
            "The European Mole Cricket is a large, brown, underground insect "
            "with a cylindrical body and strong shovel-like forelegs. It "
            "tunnels through soil and may damage roots and young plants."
        ),
        "identification_signs": (
            "Look for a brown cylindrical insect with enlarged digging "
            "forelegs and short antennae. Soil mounds, raised tunnels and "
            "wilting or loosened seedlings may indicate activity."
        ),
        "crop_damage": (
            "Feeding and tunnelling may injure roots and cut young stems near "
            "soil level. Young plants may wilt, loosen or fail to establish, "
            "resulting in patchy crop growth."
        ),
        "affected_plant_parts": (
            "Roots, underground shoots, stem bases and young seedlings."
        ),
        "recommended_treatment": (
            "Use integrated pest management. Confirm live mole crickets and "
            "assess damage before choosing control measures. Prioritise "
            "monitoring, sanitation and suitable mechanical methods. Chemical "
            "control should be considered only when justified and approved "
            "for tobacco and the target pest in India."
        ),
        "immediate_control_measures": (
            "Inspect around wilted or loose plants, examine nearby soil for "
            "tunnels and live insects, collect visible crickets where practical "
            "and record affected areas."
        ),
        "biological_control_options": (
            "Encourage natural predators. Entomopathogenic nematodes and fungi "
            "such as Metarhizium anisopliae or Beauveria bassiana may be "
            "investigated only where suitable evidence and locally approved "
            "products are available."
        ),
        "cultural_control_methods": (
            "Maintain suitable drainage, avoid excessive irrigation, remove "
            "unnecessary weeds and residues, use healthy planting material "
            "and inspect nursery beds and field soil before planting."
        ),
        "mechanical_control_methods": (
            "Hand-collect visible insects where practical. Carefully inspect "
            "and excavate identified tunnels. Pitfall or manure traps may help "
            "monitor activity. Use shallow soil disturbance only when suitable "
            "for the crop and growth stage."
        ),
        "chemical_control_options": (
            "No specific pesticide or dose is recommended here. If chemical "
            "control is necessary, check current Indian registration and "
            "product labels for tobacco and the target pest. Follow the "
            "approved dose, application method, protective equipment and "
            "waiting period."
        ),
        "prevention": (
            "Maintain suitable drainage, avoid excessive soil moisture, "
            "remove unnecessary weeds and residues, inspect nursery soil and "
            "monitor fields with a history of mole cricket activity."
        ),
        "monitoring": (
            "Look for fresh soil mounds, raised tunnels, wilting plants, "
            "missing seedlings and root injury. Inspect soil around damaged "
            "plants and record trap catches and new damage."
        ),
        "safety_precautions": (
            "Wear gloves and suitable footwear during inspection. Wash hands "
            "after handling soil or insects. Follow pesticide label "
            "instructions and keep products away from children, animals and "
            "water sources."
        ),
        "expert_advice": (
            "Confirm the insect identification and assess root and seedling "
            "injury before choosing control measures. Seek local agricultural "
            "advice if damage persists."
        ),
        "source_references": [],
        "reviewed_on": None,
    },
    {
        "solution_id": "greyback_cane_grub_sugarcane_high",
        "pest_id": "greyback_cane_grub",
        "crop_id": "sugarcane",
        "risk_level": "HIGH",
        "status": "NEEDS_REVIEW",
        "region": "Queensland, Australia",
        "scientific_name": "Dermolepida albohirtum (Waterhouse)",
        "description": (
            "Greyback cane grub is a soil-dwelling scarab beetle pest. "
            "Its larvae feed on sugarcane roots, reducing water and nutrient "
            "uptake. Severe infestations can weaken stools, reduce crop growth "
            "and cause mature cane to lodge or die. The species-specific "
            "information here is primarily based on Australian reports and "
            "has not been verified for Indian conditions."
        ),
        "identification_signs": (
            "Larvae are creamy-white, soft-bodied and C-shaped, with a brown "
            "head capsule and three pairs of thoracic legs. Adults are about "
            "35 mm long, brown and covered with grey hairs on the thorax and "
            "wing covers. Grey hairs may rub off. Confirm identification "
            "because other scarab grubs can look similar."
        ),
        "crop_damage": (
            "Larvae feed underground on sugarcane roots. Root damage reduces "
            "water and nutrient uptake, resulting in yellowing, reduced growth, "
            "wilting, drying leaves and poor crop establishment. Severe damage "
            "weakens root anchorage, causing stools to loosen and mature cane "
            "to lean or fall. Heavy infestations may kill plants. Older larvae, "
            "particularly the third instar, cause substantial damage."
        ),
        "affected_plant_parts": (
            "Roots and underground root system are directly affected. The "
            "root crown and stem base may be indirectly affected by loss of "
            "root support. Leaf yellowing and wilting are secondary symptoms."
        ),
        "recommended_treatment": (
            "Use an integrated pest management approach. Confirm the grub "
            "species, assess larval numbers and root damage, and consult local "
            "agricultural experts before selecting a treatment. Australian "
            "management information must not be treated as an Indian pesticide "
            "recommendation."
        ),
        "immediate_control_measures": (
            "Inspect affected sugarcane stools. Carefully dig around damaged "
            "plants and examine the soil and roots. Collect and count grubs, "
            "record their developmental stages, map affected field sections "
            "and seek expert confirmation of the species."
        ),
        "biological_control_options": (
            "Metarhizium anisopliae has been investigated against this species, "
            "but field performance may vary. Preserve naturally occurring soil "
            "predators and beneficial organisms. Use biological formulations "
            "only when locally registered and supported by verified application "
            "guidance."
        ),
        "cultural_control_methods": (
            "Where locally suitable, use appropriate soil cultivation and "
            "deep ploughing to expose soil-dwelling larvae. Consider crop "
            "rotation and planting schedules based on local agronomic advice. "
            "Monitor fields with a history of infestation, including ratoon "
            "fields, and avoid moving infested soil between fields."
        ),
        "mechanical_control_methods": (
            "Dig and collect exposed larvae during field inspection. Soil "
            "sampling and examination of damaged stools help estimate "
            "infestation. Adult beetles may be collected during emergence. "
            "Light traps can assist adult monitoring but should not be assumed "
            "to provide adequate large-scale control."
        ),
        "chemical_control_options": (
            "Australian literature reports the use of imidacloprid and mentions "
            "historical or reported use of chlorpyrifos and cadusafos. These "
            "are research references only, not recommendations for Indian "
            "sugarcane. No Indian registration, product, dose or application "
            "schedule for this exact pest-crop combination has been verified. "
            "Check current CIB&RC registration and the approved product label "
            "before any chemical use."
        ),
        "prevention": (
            "Review previous infestation records before planting. Conduct "
            "pre-planting soil inspections where appropriate, monitor adult "
            "emergence, maintain healthy crop growth, avoid transferring "
            "infested soil and continue monitoring affected and ratoon fields."
        ),
        "monitoring": (
            "Monitor adult emergence and activity, particularly following "
            "seasonal rainfall in reported Australian regions. Sample soil "
            "around affected stools, count larvae per stool, identify larval "
            "stages, assess root damage and map affected areas. No universal "
            "action threshold is established here; use confirmed infestation "
            "and local expert guidance."
        ),
        "safety_precautions": (
            "Wear gloves and suitable footwear when handling soil and grubs. "
            "Wash hands after inspection and avoid unnecessary root damage. "
            "For any pesticide, follow the locally approved label, required "
            "PPE, application restrictions and environmental precautions. "
            "Protect irrigation water, children and animals from exposure."
        ),
        "expert_advice": (
            "Obtain expert confirmation of Dermolepida albohirtum because "
            "other scarab larvae may appear similar. Pay attention to larval "
            "stage, root damage and field infestation history. Seek regional "
            "advice before intervention, especially because late-stage root "
            "damage may be difficult to reverse."
        ),
        "source_references": [],
        "reviewed_on": None,
    },
    {
        "solution_id": "greyback_cane_grub_banana_high",
        "pest_id": "greyback_cane_grub",
        "crop_id": "banana",
        "risk_level": "HIGH",
        "status": "NEEDS_REVIEW",
        "region": "Queensland, Australia",
        "scientific_name": "Dermolepida albohirtum (Waterhouse)",
        "description": (
            "Greyback cane grub is a scarab beetle. Banana is reported as an "
            "associated host in the supplied pest profile, with adult beetle "
            "foliage feeding reported. This crop association and its relevance "
            "to Indian conditions require further verification."
        ),
        "identification_signs": (
            "Adults are approximately 35 mm long, brown and covered with grey "
            "hairs on the thorax and wing covers. The hairs may rub off. "
            "Species identification should be confirmed by an expert because "
            "other scarab beetles can look similar."
        ),
        "crop_damage": (
            "Adult beetle feeding on banana foliage has been reported in the "
            "supplied profile. The available information does not establish "
            "the extent or economic severity of banana damage, nor does it "
            "confirm larval root damage to banana."
        ),
        "affected_plant_parts": (
            "Banana foliage may be affected by reported adult feeding. "
            "Specific affected plant parts and larval damage on banana "
            "require further verification."
        ),
        "recommended_treatment": (
            "Confirm the beetle species and assess actual feeding damage "
            "before choosing management measures. The available Australian "
            "information does not establish a verified banana-specific "
            "treatment recommendation for Indian conditions."
        ),
        "immediate_control_measures": (
            "Inspect banana foliage for adult beetles and feeding damage. "
            "Photograph and collect specimens for expert identification. "
            "Record affected plants and monitor whether feeding continues."
        ),
        "biological_control_options": (
            "No banana-specific biological control recommendation for this "
            "exact pest association has been verified. Preserve beneficial "
            "organisms and consult local experts before selecting a biological "
            "control product."
        ),
        "cultural_control_methods": (
            "Maintain field sanitation and regularly inspect banana plants "
            "for adult beetles and feeding symptoms. Avoid moving potentially "
            "infested soil or plant material without inspection."
        ),
        "mechanical_control_methods": (
            "Where practical, manually collect observed adult beetles during "
            "inspection. Record adult activity and feeding damage to support "
            "monitoring."
        ),
        "chemical_control_options": (
            "No verified Indian pesticide recommendation, registered product "
            "or dose has been established for Greyback cane grub on banana. "
            "Australian pesticide reports must not be used as Indian treatment "
            "instructions. Check current CIB&RC registration and approved "
            "product labels before considering chemical control."
        ),
        "prevention": (
            "Inspect banana plants regularly for adult beetles and feeding "
            "symptoms. Maintain field records and seek expert identification "
            "when unusual beetle activity is observed."
        ),
        "monitoring": (
            "Observe adult beetle presence and foliage feeding. Record "
            "affected plants, feeding symptoms and changes over time. "
            "Confirm the species before deciding on control."
        ),
        "safety_precautions": (
            "Wear gloves when collecting beetles and wash hands after handling. "
            "Avoid unnecessary pesticide use. Follow approved product labels "
            "and PPE requirements if a locally verified treatment is prescribed."
        ),
        "expert_advice": (
            "Confirm the species and the banana host association with an "
            "agricultural expert. Do not assume that sugarcane larval root "
            "damage or Australian management recommendations also apply "
            "to banana."
        ),
        "source_references": [],
        "reviewed_on": None,
    },
    {
        "solution_id": "june_beetle_turfgrass_high",
        "pest_id": "june_beetle",
        "crop_id": "turfgrass",
        "risk_level": "HIGH",
        "status": "NEEDS_REVIEW",
        "region": "Species-dependent; Indian occurrence not established",
        "scientific_name": "Phyllophaga spp.",
        "description": (
            "June Beetles are scarab beetles whose larvae are commonly called "
            "white grubs. Larvae of some Phyllophaga species feed on grass roots. "
            "Damage and host suitability depend on the exact species."
        ),
        "identification_signs": (
            "Adults are robust brown or reddish-brown beetles with hard wing "
            "covers, club-shaped antennae and strong legs. Larvae are creamy-white, "
            "C-shaped grubs with a brown head capsule and three pairs of thoracic "
            "legs. Raster patterns help distinguish species."
        ),
        "crop_damage": (
            "Susceptible larvae may feed on grass roots, causing root loss, "
            "yellowing, wilting, patchy drying, weak turf and poor establishment. "
            "Severe feeding may cause turf to loosen or die. These symptoms are "
            "species-dependent and are not confirmed for an Indian June Beetle."
        ),
        "affected_plant_parts": (
            "Roots and underground root systems are the main reported larval "
            "feeding sites. Adult foliage feeding varies by species."
        ),
        "recommended_treatment": (
            "Confirm the white grub species and assess root damage before "
            "treatment. Use integrated pest management and locally approved "
            "recommendations."
        ),
        "immediate_control_measures": (
            "Inspect yellowing or drying turf. Carefully examine soil and roots, "
            "collect visible grubs, record their numbers and obtain expert "
            "identification."
        ),
        "biological_control_options": (
            "Potential agents include Metarhizium anisopliae, Beauveria bassiana, "
            "Heterorhabditis spp. and Steinernema spp. Effectiveness depends on "
            "species, soil moisture, temperature and application method."
        ),
        "cultural_control_methods": (
            "Use suitable field preparation, crop rotation where applicable, "
            "appropriate drainage and irrigation, and regular monitoring of "
            "previously infested areas."
        ),
        "mechanical_control_methods": (
            "Collect exposed grubs, inspect damaged roots, take soil samples "
            "and use suitable cultivation to expose underground larvae. Light "
            "traps may help monitor adult beetles but do not control root-feeding "
            "larvae."
        ),
        "chemical_control_options": (
            "Imidacloprid, chlorantraniliprole and chlorpyrifos are mentioned "
            "in white grub management references. These are not blanket "
            "recommendations for Phyllophaga spp. in India. Verify current "
            "CIB&RC registration, exact pest-crop label, dose and application "
            "method before any use."
        ),
        "prevention": (
            "Inspect soil before planting, monitor adult emergence, use healthy "
            "planting material, maintain suitable field conditions and monitor "
            "areas with previous white grub infestation."
        ),
        "monitoring": (
            "Look for adult beetles around outdoor lights during evening hours. "
            "Inspect affected turf, collect soil samples, count grubs, examine "
            "root damage and repeat monitoring to track population changes."
        ),
        "safety_precautions": (
            "Wear gloves and suitable footwear during soil inspection. Wash "
            "hands after handling grubs. Follow pesticide label instructions "
            "and required protective equipment if an approved treatment is used."
        ),
        "expert_advice": (
            "Do not identify every white grub as a June Beetle. Confirm the "
            "species using adult characteristics or larval raster patterns. "
            "Use local recommendations and species-specific action thresholds."
        ),
        "source_references": [],
        "reviewed_on": None,
    },
    {
        "solution_id": "june_beetle_maize_high",
        "pest_id": "june_beetle",
        "crop_id": "maize",
        "risk_level": "HIGH",
        "status": "NEEDS_REVIEW",
        "region": "Species-dependent; Indian occurrence not established",
        "scientific_name": "Phyllophaga spp.",
        "description": (
            "June Beetles belong to the scarab beetle genus Phyllophaga. "
            "Larvae of certain species can feed on crop roots, including "
            "roots of susceptible agricultural plants. The exact species "
            "and maize association require confirmation."
        ),
        "identification_signs": (
            "Adults are generally brown to reddish-brown, oval and robust, "
            "with hard forewings and club-shaped antennae. Larvae are creamy-white, "
            "C-shaped grubs with a brown head and three pairs of thoracic legs. "
            "Species identification requires examination of diagnostic features."
        ),
        "crop_damage": (
            "Root-feeding white grubs may damage maize roots, reducing water "
            "and nutrient uptake. Possible symptoms include yellowing, wilting, "
            "poor seedling establishment, reduced growth and plant weakening. "
            "This damage is species-dependent and has not been confirmed for "
            "the Indian June Beetle entry."
        ),
        "affected_plant_parts": (
            "Roots and underground root systems are the potential direct "
            "feeding sites. Above-ground symptoms may include yellowing, "
            "wilting and reduced growth."
        ),
        "recommended_treatment": (
            "Confirm the grub species and assess infestation before selecting "
            "control. Use integrated pest management and follow locally "
            "approved maize-specific recommendations."
        ),
        "immediate_control_measures": (
            "Inspect poorly growing or wilting maize plants. Carefully examine "
            "the root zone, collect visible grubs, count larvae in soil samples "
            "and seek expert identification."
        ),
        "biological_control_options": (
            "Potential biological agents include Metarhizium anisopliae, "
            "Beauveria bassiana, Heterorhabditis spp. and Steinernema spp. "
            "Effectiveness varies with grub species and soil conditions."
        ),
        "cultural_control_methods": (
            "Practise suitable crop rotation, prepare fields appropriately, "
            "maintain proper drainage and monitor fields with previous white "
            "grub infestations."
        ),
        "mechanical_control_methods": (
            "Collect exposed grubs during field inspection. Examine damaged "
            "roots, take soil samples and use suitable cultivation to expose "
            "underground larvae."
        ),
        "chemical_control_options": (
            "Imidacloprid, chlorantraniliprole and chlorpyrifos appear in "
            "white grub management references. Their suitability for this "
            "exact pest and maize combination in India is not established. "
            "Check current CIB&RC registration and the approved crop-pest "
            "label. Do not use an unverified dose or application schedule."
        ),
        "prevention": (
            "Inspect soil before planting, monitor adult beetle emergence, "
            "use healthy planting material, maintain field sanitation and "
            "monitor fields with a history of grub infestation."
        ),
        "monitoring": (
            "Inspect maize plants showing yellowing, wilting or poor growth. "
            "Take soil samples, count grubs, examine roots and record affected "
            "field locations. Monitor adult beetles during evening activity."
        ),
        "safety_precautions": (
            "Wear gloves and suitable footwear when handling soil and grubs. "
            "Wash hands after inspection. Follow approved pesticide labels, "
            "protective equipment requirements and environmental precautions."
        ),
        "expert_advice": (
            "Confirm the exact Phyllophaga species before attributing maize "
            "damage to June Beetle. Do not transfer recommendations between "
            "different white grub species or crops."
        ),
        "source_references": [],
        "reviewed_on": None,
    },
    {
        "solution_id": "pine_weevil_multi_host_high_2026_11_12",
        "pest_id": "pine_weevil",
        "crop_id": None,
        "potential_host_crops": [
            {"crop_id": "pine", "crop_name": "Pine"},
            {"crop_id": "spruce", "crop_name": "Spruce"},
            {"crop_id": "fir", "crop_name": "Fir"},
            {"crop_id": "douglas_fir", "crop_name": "Douglas Fir"},
            {"crop_id": "hemlock", "crop_name": "Hemlock"},
        ],
        "risk_level": "HIGH",
        "status": "NEEDS_REVIEW",
        "region": "Palearctic forestry; not established in India",
        "scientific_name": "Hylobius abietis",
        "description": (
            "Pine Weevil (Large Pine Weevil) is a robust dark-brown beetle "
            "with irregular yellowish or light-brown patches on its wing covers, "
            "a long curved snout, elbowed antennae and strong legs. Adults are "
            "approximately 10–13 mm long excluding the snout. Larvae are "
            "cream-coloured, curved, legless grubs with brown head capsules, "
            "approximately 14–16 mm when fully developed. Adults attack young "
            "living conifers, while larvae develop mainly beneath the bark of "
            "dead or felled conifer stumps and roots."
        ),
        "identification_signs": (
            "Adults: dark-brown body, elongated curved snout, yellowish patches "
            "on wing covers, elbowed antennae, strong legs and nocturnal activity. "
            "Larvae: cream-coloured curved legless body, brown head capsule, "
            "found beneath the bark of dead or felled conifer stumps."
        ),
        "crop_damage": (
            "Adult beetles chew irregular patches of bark on young living "
            "conifer stems. Repeated feeding damages the cambial region, "
            "weakens stems and may cause girdling and seedling death. "
            "Larvae feed beneath the bark of dead or felled stumps and roots; "
            "this breeding activity should not be confused with adult feeding "
            "damage to living seedlings."
        ),
        "affected_plant_parts": (
            "Living young trees: lower stem bark, cambial region, root collar "
            "and occasionally young branches. Secondary symptoms may appear "
            "in the canopy. Dead or felled conifer stumps and roots are larval "
            "development sites."
        ),
        "recommended_treatment": (
            "Use integrated forest pest management. Inspect young conifer "
            "seedlings, monitor adult activity, manage breeding material according "
            "to forestry guidance, protect vulnerable stems and consider suitable "
            "biological controls. Chemical treatment requires verified local "
            "registration and an approved product label."
        ),
        "immediate_control_measures": (
            "Inspect young conifer seedlings for lower-stem bark removal and "
            "resin bleeding. Collect adult specimens for identification, inspect "
            "nearby felled stumps, protect vulnerable seedlings with suitable "
            "physical barriers, record damaged plantation sections and monitor "
            "for fresh feeding scars."
        ),
        "biological_control_options": (
            "Potential agents include Beauveria bassiana, Metarhizium anisopliae "
            "and entomopathogenic nematodes. Natural predators and parasitoids "
            "may also be conserved. Forest Research experimental lure-and-kill "
            "work reported mortality of up to 70% under investigated conditions; "
            "this is not a guaranteed field-control rate. Verify local suitability "
            "and regulatory requirements before use."
        ),
        "cultural_control_methods": (
            "Manage recently felled conifer stumps according to forestry "
            "guidance. Plan harvesting and restocking schedules carefully, "
            "consider suitable fallow periods, prepare planting sites properly, "
            "maintain healthy seedlings, consider less susceptible tree species "
            "where appropriate and maintain forest sanitation."
        ),
        "mechanical_control_methods": (
            "Hand-collect adult beetles, use suitable pitfall traps or validated "
            "lure-and-kill systems, apply physical seedling stem barriers or "
            "protective collars, and manage infested breeding material according "
            "to forestry guidance."
        ),
        "chemical_control_options": (
            "Alpha-cypermethrin, acetamiprid and cypermethrin have been reported "
            "in foreign forestry programmes. These are research references only, "
            "not verified Indian recommendations. Verify CIB&RC registration for "
            "the exact target, host tree and application method. Do not provide "
            "doses without an approved product label. Protect water bodies and "
            "non-target organisms."
        ),
        "prevention": (
            "Inspect seedlings before planting, monitor recently cleared conifer "
            "sites, manage suitable breeding material, use healthy planting stock, "
            "consider physical stem protection and maintain records of previous "
            "weevil damage."
        ),
        "monitoring": (
            "Inspect lower stems of young trees for fresh bark scars and resin "
            "bleeding. Look for adult weevils and activity near recently felled "
            "stumps. Use suitable traps, collect specimens for identification, "
            "record fresh damage and seedling mortality, and repeat inspections "
            "throughout the vulnerable establishment period. April–September "
            "is reported as an important period in UK conditions only; timing "
            "varies by region."
        ),
        "safety_precautions": (
            "Wear gloves and suitable protective clothing during insect "
            "collection and forestry inspections. Follow trap instructions and "
            "forestry safety procedures. Use pesticides only according to an "
            "approved label and required protective equipment. Avoid contamination "
            "of water sources and protect non-target organisms."
        ),
        "expert_advice": (
            "Distinguish Hylobius abietis from Pissodes species and related "
            "native conifer weevils. Inspect lower stems of young trees, especially "
            "in recently replanted conifer plantations. Monitor breeding material "
            "and adult emergence. Combine physical protection, forestry management "
            "and suitable biological control. Consult a forestry entomologist "
            "when identification or treatment decisions are uncertain."
        ),
        "source_references": [],
        "reviewed_on": None,
    }
]


EUROPEAN_FIELD_CRICKET_ADVISORY_DATA = [
    {
        "pest_id": "european_field_cricket",
        "scientific_name": "Gryllus campestris",
        "risk_level": "LOW",
        "status": "ADVISORY",
        "crop_id": None,
        "crop_name": None,
        "habitat": [
            "Sunny grasslands",
            "Short vegetation",
            "Patches of bare ground",
            "Individual soil burrows",
        ],
        "description": (
            "European Field Cricket is a low-risk species associated "
            "with sunny grasslands, short vegetation and bare-ground "
            "patches. Significant crop damage is not established."
        ),
        "identification_signs": [
            "Shiny black or very dark brown body",
            "Body approximately 17-23 mm long",
            "Yellowish area at the base of the forewings",
            "Large rounded head",
            "Strong hind legs",
            "Female has a long straight ovipositor",
            "Male produces repeated chirping calls near burrow entrances",
        ],
        "crop_damage": (
            "Serious crop damage is not well documented. Occasional "
            "vegetation feeding does not establish economically "
            "significant crop injury."
        ),
        "affected_plant_parts": [],
        "recommended_treatment": (
            "Chemical treatment is generally not recommended. "
            "Confirm the species, assess actual damage, monitor "
            "vegetation around burrows and preserve natural grassland."
        ),
        "immediate_control_measures": [
            "Inspect affected vegetation.",
            "Confirm the cricket species.",
            "Examine burrows near damaged plants.",
            "Record the affected area.",
            "Monitor new feeding damage.",
            "Protect vulnerable seedlings using physical barriers if required.",
            "Avoid destroying natural burrows without a demonstrated need.",
        ],
        "biological_control_options": [
            "Insect-eating birds",
            "Spiders",
            "Predatory insects",
            "Small mammals",
            "Amphibians such as toads",
            "Naturally occurring insect pathogens",
        ],
        "cultural_control_methods": [
            "Maintain healthy vegetation.",
            "Practise appropriate weed management.",
            "Maintain suitable field sanitation.",
            "Inspect vulnerable seedlings.",
            "Monitor vegetation near field boundaries.",
            "Preserve beneficial organisms and natural grassland habitats.",
        ],
        "mechanical_control_methods": [
            "Hand collection of visible insects when necessary.",
            "Physical protection of vulnerable seedlings.",
            "Inspection of burrow entrances.",
            "Monitoring of affected vegetation.",
            "Removal of insects from sensitive nursery areas when necessary.",
        ],
        "chemical_control_options": None,
        "prevention": [
            "Maintain healthy crop vegetation.",
            "Monitor field boundaries.",
            "Inspect young plants regularly.",
            "Avoid unnecessary insecticide applications.",
            "Maintain appropriate field sanitation.",
            "Monitor unusual increases in cricket activity.",
            "Preserve natural grassland habitats.",
        ],
        "monitoring": [
            "Inspect grassy areas.",
            "Observe burrow entrances.",
            "Listen for male calling sounds.",
            "Check vegetation around burrows.",
            "Photograph collected specimens.",
            "Record actual crop damage.",
            "Monitor population changes.",
        ],
        "safety_precautions": [
            "Wear gloves when collecting specimens.",
            "Avoid unnecessary soil excavation.",
            "Wear suitable footwear during field inspection.",
            "Wash hands after handling soil.",
            "Avoid pesticide use without a demonstrated need.",
            "Protect beneficial insects and grassland organisms.",
        ],
        "expert_advice": (
            "Confirm Gryllus campestris rather than assuming every "
            "field cricket belongs to this species. Keep it separate "
            "from generic Field Cricket and Fall Field Cricket "
            "(Gryllus pennsylvanicus). Do not confuse burrow activity "
            "with crop damage. Investigate other pests if serious "
            "seedling destruction occurs."
        ),
        "action_threshold": (
            "No established universal economic threshold. Take action "
            "only when species identity is confirmed and increasing "
            "crop damage is documented."
        ),
        "source_references": [
            {
                "source": "Orthoptera and Allied Insects",
                "supports": ["identification", "biology"],
            },
            {
                "source": "IUCN Species of the Day: Field Cricket",
                "supports": ["ecological importance"],
            },
            {
                "source": "Frontiers research on Gryllus campestris",
                "supports": ["reproductive biology", "grassland ecology"],
            },
            {
                "source": "University of California IPM",
                "supports": ["field cricket damage", "management context"],
            },
        ],
    }
]


EUROPEAN_TREE_CRICKET_ADVISORY_DATA = [
    {
        "solution_id": "european_tree_cricket_general_advisory",
        "pest_id": "european_tree_cricket",
        "crop_id": None,
        "risk_level": "LOW",
        "status": "ADVISORY",
        "scientific_name": "Oecanthus pellucens",
        "description": (
            "European Tree Cricket is a small, vegetation-dwelling "
            "omnivorous cricket. Localised grapevine stem injury from "
            "female egg-laying has been reported in European vineyards. "
            "An Indian commercial crop association is not established."
        ),
        "habitat": [
            "Tall grasses",
            "Herbs",
            "Shrubs",
            "Vegetation",
        ],
        "identification_signs": [
            "Slender elongated body",
            "Pale yellowish-brown or light brown colour",
            "Translucent wings",
            "Very long thin antennae",
            "Wings cover most or all of the abdomen",
            "Female has a short curved ovipositor",
            "Male produces a high-pitched continuous chirping or whistling song",
            "Adults approximately 10-20 mm long",
        ],
        "crop_damage": (
            "Localised egg-laying injury to grapevine stems has been "
            "reported in European vineyards. Repeated egg deposition "
            "may weaken affected stems. Widespread commercial crop "
            "losses are not established."
        ),
        "affected_plant_parts": [
            "Grapevine stems and shoots in reported European vineyard cases",
            "Herbaceous stems used for egg deposition",
        ],
        "recommended_treatment": (
            "Monitor plant stems and use targeted pruning where "
            "agronomically appropriate. Routine insecticide treatment "
            "is not recommended."
        ),
        "immediate_control_measures": [
            "Inspect stems for fresh egg-laying punctures",
            "Prune severely damaged plant portions where appropriate",
            "Check surrounding vegetation for high cricket populations",
            "Monitor affected plants for stem weakening or breakage",
        ],
        "biological_control_options": [
            "Conserve natural predators",
            "Recognise that this cricket also feeds on aphids and other small insects",
            "No commercially established species-specific biological-control agent is confirmed",
        ],
        "cultural_control_methods": [
            "Monitor vulnerable plants regularly",
            "Maintain balanced vegetation management",
            "Avoid unnecessary removal of beneficial vegetation",
            "Prune damaged grapevine stems appropriately where relevant",
        ],
        "mechanical_control_methods": [
            "Hand-collect visible adults when populations are small",
            "Remove severely affected stems where necessary",
            "Inspect stems for egg-laying punctures",
            "Use physical protection for vulnerable young plants if local injury is confirmed",
        ],
        "chemical_control_options": None,
        "prevention": [
            "Inspect vulnerable shoots and stems regularly",
            "Remove severely damaged plant material where appropriate",
            "Monitor cricket activity around crop boundaries",
            "Avoid unnecessary pesticide applications",
        ],
        "monitoring": [
            "Listen for the male's high-pitched song during evening and night",
            "Inspect tall vegetation and crop shoots",
            "Look for small egg-laying punctures on stems",
            "Record affected plants and extent of stem injury",
            "Recheck previously affected plants for fresh damage",
        ],
        "when_to_take_action": (
            "Consider action when repeated egg-laying injury weakens "
            "stems or causes visible plant damage. No reliable "
            "economic threshold is established."
        ),
        "safety_precautions": [
            "Wear gloves when handling insects or damaged plant material",
            "Use clean pruning tools",
            "Dispose of removed damaged material appropriately",
            "Follow approved pesticide labels if an independently justified treatment is used",
        ],
        "geographic_limitation": (
            "Grapevine injury is reported from European vineyards. "
            "This does not establish an Indian crop association or "
            "Indian occurrence."
        ),
        "expert_advice": (
            "Distinguish Oecanthus pellucens from the Indian tree "
            "cricket Oecanthus indicus. Do not assign the Indian "
            "species' distribution or biology to this entry."
        ),
        "source_references": [],
    },
]


LARGE_TREE_CRICKET_ADVISORY_DATA = [
    {
        "pest_id": "large_tree_cricket",
        "crop_id": None,
        "status": "ADVISORY",
        "risk_level": "LOW",
        "title": "Monitor tree cricket activity without unnecessary treatment",
        "damage_notes": (
            "No significant commercial crop damage is established for "
            "Oecanthus dulcisonans. A male was observed calling from a "
            "grapevine in Germany, but this does not establish grapevine "
            "as a damaged crop or confirmed feeding host."
        ),
        "management": [
            "Confirm the species before attributing plant damage to it.",
            "Listen for the characteristic continuous male calling song.",
            "Inspect shrubs and herbaceous vegetation for adults.",
            "Record sightings separately from confirmed plant injury.",
            "Inspect vulnerable plants if direct feeding is suspected.",
            "Avoid unnecessary pesticide applications.",
        ],
        "biological_control": [
            "Birds, spiders and predatory insects may consume tree crickets.",
            "No species-specific commercial biological-control agent is established.",
        ],
        "chemical_control_options": None,
        "economic_threshold": None,
        "geographic_qualification": (
            "European distribution and habitat observations. Indian "
            "occurrence and commercial crop damage are unconfirmed."
        ),
        "source_refs": [
            "https://www.gbif.org/taxon/6SGSW",
            "https://www.biotaxa.org/Zootaxa/article/view/zootaxa.2284.1.5",
            "https://pubmed.ncbi.nlm.nih.gov/27701294/",
            "https://dgfo-articulata.de/downloads/articulata/articulata_36_2021/Articulata_36_Hochkirch_et_al.pdf",
        ],
    }
]


SNOWY_TREE_CRICKET_ADVISORY_DATA = [
    {
        "pest_id": "snowy_tree_cricket",
        "scientific_name": "Oecanthus fultoni",
        "crop_id": None,
        "risk_level": "MEDIUM",
        "status": "ADVISORY",
        "chemical_control_options": None,
        "management": {
            "monitoring": [
                "Inspect young shoots and woody stems for egg-laying wounds.",
                "Check nursery plants and young orchard trees for broken or weakened shoots.",
                "Do not treat adult calling activity alone as evidence of crop damage.",
                "Confirm the species before considering pest-management action.",
            ],
            "mechanical_control": [
                "Prune affected shoots when egg-laying injury is confirmed.",
                "Remove and appropriately dispose of infested plant material.",
            ],
            "biological_control": [
                "Preserve beneficial predators.",
            ],
            "prevention": [
                "Avoid unnecessary broad-spectrum insecticides.",
                "Assess actual plant injury before considering intervention.",
            ],
        },
        "action_threshold": (
            "No Indian crop-specific action threshold is established. Consider management "
            "only after confirming injury and assessing its extent."
        ),
        "notes": (
            "Feeding and egg-laying injury to shoots and branches is reported in North American "
            "sources; typical damage is minor and localised. These regional reports do not "
            "establish Indian crop hosts or damage. No verified Indian chemical treatment is "
            "established."
        ),
    }
]


LESSER_FIELD_GRASSHOPPER_ADVISORY_DATA = [
    {
        "pest_id": "lesser_field_grasshopper",
        "crop_id": None,
        "status": "ADVISORY",
        "risk_level": "LOW",
        "title": "Monitor grassland activity and confirm crop feeding",
        "damage_notes": (
            "This species is primarily associated with dry grasslands, "
            "sandy vegetation and fallow habitats. No significant "
            "species-specific commercial crop damage is established."
        ),
        "management": [
            "Confirm the species using morphological features and male song.",
            "Inspect nearby crop plants for fresh feeding injury.",
            "Record insect abundance and affected area separately.",
            "Monitor field margins and adjacent grassland.",
            "Protect vulnerable seedlings only if direct feeding is confirmed.",
            "Avoid unnecessary insecticide applications.",
            "Preserve suitable natural grassland habitat.",
        ],
        "biological_control": [
            "Birds, spiders and predatory insects may naturally prey on grasshoppers.",
            "No species-specific commercial biological-control agent is established.",
        ],
        "chemical_control_options": None,
        "economic_threshold": None,
        "geographic_qualification": (
            "European and broader Eurasian habitat records. Indian occurrence "
            "and commercial crop damage are unconfirmed."
        ),
        "source_refs": [
            "https://www.gbif.org/taxon/5GFGC",
            "https://www.grasshoppersofeurope.com/linnaeus_ng/app/views/species/nsr_taxon.php?id=1156",
            "https://www.pyrgus.de/Chorthippus_mollis_en.html",
        ],
    }
]


MEADOW_GRASSHOPPER_ADVISORY_DATA = [
    {
        "pest_id": "meadow_grasshopper",
        "crop_id": None,
        "status": "ADVISORY",
        "risk_level": "LOW",
        "title": "Monitor grassland activity and confirm crop feeding",
        "damage_notes": (
            "This species primarily feeds on grasses and herbaceous "
            "vegetation in meadows, pastures and field margins. "
            "Significant commercial crop damage is not established."
        ),
        "management": [
            "Confirm the species before attributing plant damage to it.",
            "Inspect crop plants for fresh feeding injury.",
            "Record grasshopper abundance and affected areas.",
            "Monitor grassy field margins and nearby grassland.",
            "Protect vulnerable seedlings only if direct feeding is confirmed.",
            "Avoid unnecessary insecticide applications.",
            "Preserve natural grassland habitats and predators.",
        ],
        "biological_control": [
            "Birds, spiders and predatory insects may naturally consume grasshoppers.",
            "No species-specific commercial biological-control agent is established.",
        ],
        "chemical_control_options": None,
        "economic_threshold": None,
        "geographic_qualification": (
            "Primarily European grassland records. Indian occurrence "
            "and commercial crop damage are unconfirmed."
        ),
        "source_refs": [
            "https://www.grasshoppersofeurope.com/linnaeus_ng/app/views/species/nsr_taxon.php?cat=CTAB_NAMES&id=2461",
            "https://www.iucn-uk-peatlandprogramme.org/wildlife-explorer/grasshoppers-and-crickets/meadow-grasshopper",
            "https://orthoptera.org.uk/node/3356",
            "https://gd.eppo.int/taxon/CHOHPA",
        ],
    }
]


MARSH_CRICKET_ADVISORY_DATA = [
    {
        "pest_id": "marsh_cricket",
        "crop_id": None,
        "status": "ADVISORY",
        "risk_level": "LOW",
        "title": "Monitor wetland cricket activity",
        "damage_notes": (
            "No significant species-specific commercial crop damage "
            "is established. Occurrence in damp agricultural habitats "
            "does not establish crop injury."
        ),
        "management": [
            "Confirm the species before attributing plant damage.",
            "Listen for the characteristic high-pitched calling song.",
            "Inspect damp vegetation and wet field margins.",
            "Record sightings separately from confirmed plant injury.",
            "Protect vulnerable seedlings only if direct feeding is observed.",
            "Preserve wetland habitats and avoid unnecessary insecticide use.",
        ],
        "biological_control": [
            "General predators may consume small crickets.",
            "No species-specific commercial biological-control agent is established.",
        ],
        "chemical_control_options": None,
        "economic_threshold": None,
        "geographic_qualification": (
            "The nominate subspecies is documented in Europe. "
            "The species-level taxonomic treatment also includes "
            "an Indian-associated subspecies. Indian crop damage "
            "is not established."
        ),
        "source_refs": [
            "https://orthoptera.speciesfile.org/otus/833654/overview",
            "https://orthoptera.speciesfile.org/otus/833657",
            "https://orthoptera.hu/en/fajok/pteronemobius-heydenii/",
        ],
    }
]


WOOD_CRICKET_ADVISORY_DATA = [
    {
        "pest_id": "wood_cricket",
        "crop_id": None,
        "status": "ADVISORY",
        "risk_level": "LOW",
        "damage_notes": (
            "Woodland presence and associations with leaf litter and fungi are not "
            "evidence of crop infestation. No species-specific crop damage or Indian "
            "crop host is established."
        ),
        "management": [
            "No agricultural pest treatment is required.",
            "Do not classify woodland presence as evidence of crop infestation.",
            "Preserve natural leaf litter and woodland-edge habitats.",
            "Avoid unnecessary pesticide applications in woodland areas.",
            "If crop injury is observed, identify the actual damaging organism.",
            "Distinguish this species from other small ground crickets, including Pteronemobius species.",
        ],
        "chemical_control_options": None,
        "economic_threshold": None,
        "geographic_qualification": (
            "A two-year life cycle is reported in Britain; this duration is geographically "
            "qualified and should not be treated as universal. Indian crop occurrence "
            "and damage are not established."
        ),
    }
]


VERGE_CRICKET_ADVISORY_DATA = [
    {
        "pest_id": "verge_cricket",
        "crop_id": None,
        "status": "ADVISORY",
        "risk_level": "LOW",
        "title": "Monitor field margins and confirm feeding injury",
        "damage_notes": (
            "Indian occurrence is reported but requires local confirmation. "
            "Commercial crop hosts, significant crop damage, and economically "
            "important affected plant parts are not established. Regional "
            "agricultural observations, including the Iraqi survey, do not establish "
            "crop damage in India."
        ),
        "management": [
            "Confirm the cricket species before considering management.",
            "Inspect plants only when actual feeding injury is observed.",
            "Hand-collect visible crickets in small affected areas when necessary.",
            "Protect vulnerable seedlings with suitable insect-proof barriers.",
            "Monitor field margins and disturbed habitats.",
            "Preserve natural predators and avoid unnecessary insecticide applications.",
        ],
        "chemical_control_options": None,
        "economic_threshold": None,
        "geographic_qualification": (
            "Reported from Europe, North Africa, and Asia. Indian occurrence is "
            "reported but needs local confirmation; regional agricultural observations "
            "are not evidence of Indian crop damage."
        ),
    }
]


FALL_FIELD_CRICKET_ADVISORY_DATA = [
    {
        "pest_id": "fall_field_cricket",
        "scientific_name": "Gryllus pennsylvanicus",
        "risk_level": "MEDIUM",
        "status": "ADVISORY",
        "crop_id": None,
        "crop_name": None,
        "description": (
            "Fall Field Cricket is an omnivorous field-dwelling "
            "cricket found in fields, pastures and grassy habitats. "
            "It generally has low agricultural significance, but "
            "large populations may cause localised seed and "
            "seedling damage."
        ),
        "identification_signs": [
            "Shiny dark-brown to black body",
            "Large rounded head",
            "Long antennae",
            "Strong enlarged hind legs",
            "Brownish forewings",
            "Male repeated chirping sounds",
            "Female sword-shaped ovipositor",
            "Two cerci at the rear of the abdomen",
        ],
        "crop_damage": (
            "Potential feeding on seeds, seedlings, grasses, "
            "leaves, tender shoots and occasionally small fruits. "
            "Serious crop damage is not typical and is more likely "
            "during unusually large population outbreaks."
        ),
        "affected_plant_parts": [
            "Seeds",
            "Seedlings",
            "Leaves",
            "Tender shoots",
            "Young stems",
            "Flowers",
            "Small fruits",
            "Grass vegetation",
        ],
        "recommended_treatment": (
            "Use integrated monitoring and proportionate "
            "management. Confirm the cricket species, inspect "
            "seedlings and field margins, and protect vulnerable "
            "planting areas. Avoid routine insecticide treatment."
        ),
        "immediate_control_measures": [
            "Inspect damaged seedlings and vegetation.",
            "Check cricket activity during nighttime.",
            "Examine field margins and grassy areas.",
            "Collect visible crickets where practical.",
            "Protect vulnerable seedlings.",
            "Check for seed damage.",
            "Record affected areas.",
            "Monitor whether populations are increasing.",
        ],
        "biological_control_options": [
            "Insect-eating birds",
            "Toads and other amphibians",
            "Spiders",
            "Predatory insects",
            "Small mammals",
            "Parasitic insects",
            "Naturally occurring insect pathogens",
        ],
        "cultural_control_methods": [
            "Maintain proper field sanitation.",
            "Remove excessive weeds where appropriate.",
            "Inspect planting areas before sowing.",
            "Maintain healthy crop growth.",
            "Protect newly seeded areas.",
            "Monitor field margins.",
            "Avoid unnecessary accumulation of crop residues.",
            "Maintain suitable vegetation management.",
        ],
        "mechanical_control_methods": [
            "Hand collection of adult crickets.",
            "Night-time visual inspection.",
            "Physical protection of seedlings.",
            "Monitoring of field margins.",
            "Suitable trapping in concentrated infestation areas.",
            "Soil inspection for egg-laying activity when necessary.",
        ],
        "chemical_control_options": None,
        "prevention": [
            "Inspect fields before planting.",
            "Monitor seedling establishment.",
            "Maintain proper field sanitation.",
            "Control excessive weeds.",
            "Protect newly seeded crops.",
            "Monitor field margins during late summer.",
            "Encourage natural predators.",
            "Record previous cricket outbreaks.",
        ],
        "monitoring": [
            "Inspect fields during evening hours.",
            "Examine seedlings for feeding marks.",
            "Observe cricket activity around vegetation.",
            "Listen for adult male chirping.",
            "Record cricket numbers.",
            "Repeat inspections when populations increase.",
            "Monitor seed and seedling damage.",
        ],
        "safety_precautions": [
            "Wear gloves when collecting crickets.",
            "Use suitable footwear during field inspection.",
            "Wash hands after handling soil and insects.",
            "Avoid unnecessary soil disturbance.",
            "Protect beneficial predators.",
            "Use pesticides only when legally approved.",
            "Follow approved pesticide label instructions.",
            "Keep chemicals away from children and animals.",
        ],
        "expert_advice": (
            "Confirm Gryllus pennsylvanicus rather than identifying "
            "every dark field cricket as this species. Distinguish "
            "it from Spring Field Cricket (Gryllus veletis). "
            "Inspect crops at night, monitor seed and seedling "
            "damage, and remember that this species also consumes "
            "other insects. Consult an agricultural entomologist "
            "during unexplained outbreaks."
        ),
        "action_threshold": (
            "No universally established economic threshold is "
            "available for this species. Consider intervention "
            "when large populations and increasing seedling or "
            "seed damage are documented."
        ),
        "source_references": [
            {
                "source": (
                    "Agriculture and Agri-Food Canada: "
                    "Field Guide to the Identification of "
                    "Insects and Mites Associated with Crop Plants"
                ),
                "supports": [
                    "identification",
                    "agricultural context",
                ],
            },
            {
                "source": (
                    "Singing Insects of North America: "
                    "Gryllus pennsylvanicus"
                ),
                "supports": [
                    "identification",
                    "biology",
                ],
            },
            {
                "source": "Montana Field Guide",
                "supports": [
                    "biology",
                    "food habits",
                ],
            },
            {
                "source": "University of California IPM: Field Crickets",
                "supports": [
                    "field cricket damage",
                    "management context",
                ],
            },
        ],
    }
]


SPRING_FIELD_CRICKET_ADVISORY_DATA = [
    {
        "pest_id": "spring_field_cricket",
        "scientific_name": "Gryllus veletis",
        "risk_level": "LOW",
        "status": "ADVISORY",
        "crop_id": None,
        "crop_name": None,
        "description": (
            "Gryllus veletis is a North American field cricket. Typical "
            "injury is minor and localised; significant species-specific "
            "crop damage and Indian occurrence are not established. Do "
            "not infer Indian occurrence from general field-cricket "
            "family membership."
        ),
        "identification_signs": [
            "Dark or shiny black body with long antennae",
            "Strong hind legs adapted for jumping",
            "Females have a visible ovipositor",
            "Males produce a slow, usually irregular chirping call",
            "A cited North American account reports an approximate "
            "15-25 mm adult body length; this is not a definitive "
            "diagnostic measurement",
            "Spring and early-summer timing applies to the North American "
            "range, not Karnataka",
            "May be confused with Fall Field Cricket and related species",
        ],
        "crop_damage": (
            "Feeding on leaves, flowers, fruits, seeds, or roots is a "
            "general possibility and does not establish economically "
            "damaged crop parts. Canadian guidance about slight feeding "
            "on harvested or stored crop material refers to spring and "
            "fall field crickets collectively, not proven damage by "
            "Gryllus veletis. Typical injury is minor; significant "
            "species-specific crop damage is not established."
        ),
        "affected_plant_parts": (
            "Leaves, flowers, fruits, seeds, and roots are general "
            "feeding possibilities, not confirmed economically damaged "
            "crop parts."
        ),
        "recommended_treatment": (
            "No routine pest treatment is recommended. Monitor only "
            "when actual feeding injury is observed. Confirm the species "
            "before considering pest-management action."
        ),
        "immediate_control_measures": [
            "Hand-collect visible crickets in small growing areas when necessary",
            "Protect vulnerable seedlings with suitable insect netting",
            "Store harvested crop material in protected conditions; "
            "Canadian guidance on slight feeding concerns spring and "
            "fall field crickets collectively, not proven G. veletis damage",
        ],
        "biological_control_options": [
            "Conserve naturally occurring birds, spiders and predatory insects",
            "No species-specific biological-control agent is established "
            "as a reliable treatment for this cricket",
        ],
        "cultural_control_methods": [
            "Maintain field hygiene around vulnerable planting areas",
            "Manage excessive weeds or ground cover only when linked "
            "to observed crop damage",
            "Avoid unnecessary disturbance of beneficial wildlife",
        ],
        "mechanical_control_methods": [
            "Hand-collect visible crickets in small growing areas when necessary",
            "Protect vulnerable seedlings with suitable insect netting",
        ],
        "chemical_control_options": None,
        "prevention": [
            "Monitor plants only when actual feeding injury is observed",
            "Store harvested crop material in protected conditions",
            "Confirm the species before considering pest-management action",
            "Avoid unnecessary broad-spectrum insecticide use",
        ],
        "monitoring": [
            "Look for feeding injury rather than relying on calls alone",
            "Record cricket activity and confirmed plant injury",
            "Use North American season and calling behaviour only as "
            "supporting identification clues",
        ],
        "safety_precautions": [
            "Wear gloves when collecting insects or handling debris",
            "Avoid unnecessary pesticide application",
            "Use a pesticide only when its current Indian registration "
            "and label permit the specific crop and target pest",
        ],
        "expert_advice": (
            "Distinguish Spring Field Cricket from Fall Field Cricket "
            "(Gryllus pennsylvanicus) and West Coast Spring Field Cricket "
            "(Gryllus veletisoides). Their similarity means that location, "
            "season and specialist examination may be needed for reliable "
            "identification. Gryllus veletis generally overwinters as a "
            "nymph; do not assign this life-cycle trait to Fall Field "
            "Cricket. Do not assume this North American species is "
            "established in India."
        ),
        "life_cycle_notes": (
            "Generally one generation per year; Gryllus veletis primarily "
            "overwinters as a nymph. This is not a Fall Field Cricket "
            "life-cycle claim."
        ),
        "action_threshold": (
            "No verified economic threshold is available. Consider "
            "intervention only after repeated observations confirm "
            "feeding and measurable crop damage."
        ),
        "source_references": [
            "https://orthsoc.org/sina/488a.htm",
            "https://orthsoc.org/sina/s464wg-veletisgroup.pdf",
            "https://www.bugguide.net/node/view/250786",
            "https://publications.gc.ca/collections/collection_2009/agr/A52-161E.pdf",
        ],
    }
]


FIELD_CRICKET_ADVISORY_DATA = [
    {
        "pest_id": "field_cricket",
        "scientific_name": "Gryllus spp. (species undetermined)",
        "risk_level": "MEDIUM",
        "status": "ADVISORY",
        "crop_id": None,
        "crop_name": None,
        "description": (
            "Field crickets are a group of crickets that may occasionally "
            "damage crops, particularly newly emerging seedlings. The "
            "catalogue entry does not identify a particular Gryllus species. "
            "Crop associations and damage vary between species."
        ),
        "identification_signs": [
            "Dark brown to shiny black body",
            "Long thread-like antennae",
            "Strong enlarged hind legs for jumping",
            "Two cerci at the rear of the abdomen",
            "Females have a visible ovipositor",
            "Males produce chirping sounds by rubbing their forewings",
        ],
        "crop_damage": (
            "Some field-cricket species may feed on seeds, seedlings, "
            "young leaves and stems. High populations can damage newly "
            "emerging crop rows. These symptoms are not sufficient to "
            "identify a particular Gryllus species."
        ),
        "affected_plant_parts": (
            "Potentially seeds, germinating seedlings, young stems, "
            "stem bases and leaves. Actual feeding varies by species "
            "and crop."
        ),
        "recommended_treatment": (
            "Use integrated pest management. Confirm the cricket species, "
            "observe active feeding and assess seedling injury before "
            "considering intervention."
        ),
        "immediate_control_measures": [
            "Inspect damaged seedlings and nearby field edges",
            "Check beneath debris and weeds for sheltering crickets",
            "Protect vulnerable nursery beds with insect-proof netting",
            "Manage hiding places when they are associated with "
            "observed crop damage",
            "Replant only after checking that damaging activity has declined",
        ],
        "biological_control_options": [
            "Conserve birds, spiders and naturally occurring predatory insects",
            "Some wasps in the family Sphecidae are reported as cricket "
            "predators or parasitoids",
            "These natural enemies are not guaranteed commercial treatments "
            "for every Gryllus species",
        ],
        "cultural_control_methods": [
            "Manage weeds around nurseries and crop boundaries",
            "Reduce excessive debris and shelter near vulnerable seedlings",
            "Monitor fields bordering uncultivated or weedy areas",
            "Inspect crops carefully during seedling establishment",
            "Avoid unnecessary disturbance of beneficial organisms",
        ],
        "mechanical_control_methods": [
            "Hand-collect crickets in small affected areas",
            "Use insect-proof netting or protected nursery structures",
            "Inspect and remove crickets from seedling beds",
            "Use traps as monitoring aids where appropriate",
        ],
        "chemical_control_options": None,
        "prevention": [
            "Protect nursery beds during seedling establishment",
            "Manage weeds and debris around vulnerable crop areas",
            "Inspect field boundaries before sowing or transplanting",
            "Monitor locations with previous cricket activity",
        ],
        "monitoring": [
            "Inspect seedlings during early morning for fresh feeding injury",
            "Check beneath debris and in weedy areas during the day",
            "Observe cricket activity at night",
            "Record cricket numbers, affected plants and damaged rows",
            "Treat chirping as evidence of cricket presence, not proof "
            "of crop damage",
        ],
        "safety_precautions": [
            "Wear gloves when handling insects or debris",
            "Avoid unnecessary broad-spectrum insecticide applications",
            "Use only products currently registered and labelled for "
            "the exact crop and target pest in India",
            "Follow label instructions, protective equipment requirements "
            "and pre-harvest intervals",
        ],
        "expert_advice": (
            "Confirm the species before creating a crop-specific solution. "
            "The common name field cricket may refer to different species. "
            "Do not transfer host associations or pesticide recommendations "
            "from one Gryllus species to another. The supplied profile's "
            "reference to Liogryllus bimaculatus and Euscyrtus concinnus "
            "does not establish those species as the identity of this "
            "generic catalogue entry."
        ),
        "action_threshold": (
            "No universal economic threshold is established for all "
            "Gryllus species and crops. Consider intervention when repeated "
            "inspections confirm active feeding and increasing seedling "
            "damage, such as clipped plants or affected rows."
        ),
        "source_references": [
            "https://ipm.ucanr.edu/",
            "https://mdc.mo.gov/",
            "https://ask.ifas.ufl.edu/",
        ],
    }
]


HOUSE_CRICKET_ADVISORY_DATA = [
    {
        "pest_id": "house_cricket",
        "crop_id": None,
        "status": "ADVISORY",
        "risk_level": "MEDIUM",
        "title": "Monitor cricket activity and protect young plants",
        "damage_notes": (
            "House crickets are primarily household and storage-area "
            "nuisance insects. Indian field observations report occasional "
            "feeding injury to tender shoots, leaves and young seedlings. "
            "Do not assign wheat, guar or other crops as confirmed hosts "
            "without species-specific supporting evidence."
        ),
        "management": [
            "Confirm the species before attributing crop injury.",
            "Inspect young plants for fresh chewing damage.",
            "Observe whether crickets are directly feeding on affected plants.",
            "Hand-collect visible individuals in small affected areas.",
            "Protect vulnerable seedlings using suitable physical covers.",
            "Remove food scraps and unnecessary hiding places.",
            "Use sticky traps for indoor monitoring where appropriate.",
            "Keep stored food in sealed containers.",
        ],
        "biological_control": [
            "Birds, spiders and predatory insects may naturally consume crickets.",
            "No species-specific commercial biological-control agent is established.",
        ],
        "chemical_control_options": None,
        "economic_threshold": None,
        "geographic_qualification": (
            "Indian field observations report occasional plant injury. "
            "Crop-specific associations and economic thresholds require "
            "further verification."
        ),
        "source_refs": [
            "https://epubs.icar.org.in/index.php/AAZ/article/view/65126",
            "https://ask.ifas.ufl.edu/publication/IN220",
            "https://ddugu.ac.in/ePathshala_Attachments/E_PS155267%40d7832c66i.pdf",
        ],
    }
]


JUMPING_BUSH_CRICKET_ADVISORY_DATA = [
    {
        "pest_id": "jumping_bush_cricket",
        "crop_id": None,
        "status": "ADVISORY",
        "risk_level": "LOW",
        "title": "Observe cricket activity without unnecessary treatment",
        "damage_notes": (
            "No reliable species-specific evidence establishes this "
            "species as a commercial crop pest. Its presence in trees, "
            "shrubs or herbaceous vegetation does not establish crop injury."
        ),
        "management": [
            "Confirm the species before attributing plant damage to it.",
            "Inspect nearby plants for fresh feeding injury.",
            "Record sightings, calling activity and vegetation location.",
            "Observe direct feeding before recording crop damage.",
            "Avoid unnecessary removal of surrounding vegetation.",
            "Avoid routine insecticide application.",
        ],
        "biological_control": [
            "General predators such as birds and spiders may consume crickets.",
            "No species-specific commercial biological-control agent is established.",
        ],
        "chemical_control_options": None,
        "economic_threshold": None,
        "geographic_qualification": (
            "Primarily North American species. Indian occurrence and "
            "commercial crop damage are unconfirmed."
        ),
        "source_refs": [
            "https://www.fws.gov/species/jumping-bush-cricket-orocharis-saltator",
            "https://www.orthsoc.org/sina/686a.htm",
            "https://www.itis.gov/servlet/SingleRpt/SingleRpt?search_topic=TSN&search_value=102354",
        ],
    }
]


DESERT_FIELD_CRICKET_ADVISORY_DATA = [
    {
        "pest_id": "desert_field_cricket",
        "scientific_name": "Melanogryllus desertus",
        "risk_level": "MEDIUM",
        "status": "ADVISORY",
        "crop_id": None,
        "crop_name": None,
        "description": (
            "A relatively small dark field cricket reported from parts "
            "of Europe and western and central Asia. Agricultural damage "
            "may occur where populations are high, particularly during "
            "seedling establishment. Indian occurrence and Indian crop "
            "impact are not confirmed."
        ),
        "identification_signs": [
            "Relatively small dark or black field cricket",
            "Adults may measure approximately 12–18 mm in some "
            "European identification references",
            "Yellowish markings may occur on the forewings",
            "Long antennae and strong hind legs",
            "Females have a straight ovipositor",
            "May shelter in soil cracks and protected ground-level locations",
            "Species identification should be confirmed by an entomologist",
        ],
        "crop_damage": (
            "Overseas agricultural reports describe feeding on young "
            "plants and seedlings. Damage may include gnawed seedlings "
            "and tender plant tissue. These reports do not establish "
            "Indian crop damage by this species."
        ),
        "affected_plant_parts": (
            "Potentially young stems, seedlings, leaves and tender "
            "plant material. Exact affected parts vary by crop and "
            "regional evidence."
        ),
        "recommended_treatment": (
            "Use integrated pest management with early monitoring, "
            "field hygiene and physical protection of young plants. "
            "Confirm species identity and actual feeding before "
            "considering intervention."
        ),
        "immediate_control_measures": [
            "Inspect seedlings and soil around damaged plants",
            "Check soil cracks, debris and sheltered ground-level locations",
            "Protect vulnerable nursery plants with physical barriers",
            "Manage hiding places only where linked to observed infestation",
            "Reinspect the field after management to assess continuing damage",
        ],
        "biological_control_options": [
            "Conserve birds, spiders and naturally occurring predatory insects",
            "Some sphecid wasps are natural enemies of field crickets",
            "No reliable species-specific biological-control programme "
            "is established for Melanogryllus desertus",
        ],
        "cultural_control_methods": [
            "Manage weeds around vulnerable crop areas",
            "Reduce unnecessary accumulation of crop debris near seedlings",
            "Inspect fields before and after crop establishment",
            "Monitor areas with cracks and sheltered ground cover",
            "Maintain nursery and field hygiene",
        ],
        "mechanical_control_methods": [
            "Hand-collect crickets in small affected areas",
            "Use protective netting around nursery plants",
            "Inspect soil cracks and sheltered locations",
            "Use suitable traps as monitoring aids",
        ],
        "chemical_control_options": None,
        "prevention": [
            "Protect seedlings during early establishment",
            "Manage excessive weeds and debris around nursery areas",
            "Inspect fields before sowing and during seedling emergence",
            "Monitor locations where cricket activity has previously occurred",
        ],
        "monitoring": [
            "Inspect seedlings in the morning for fresh feeding injury",
            "Check under debris and inside soil cracks during the day",
            "Observe cricket activity during evening and night",
            "Record cricket numbers and damaged plants",
            "Confirm species identity before assigning species-specific treatment",
        ],
        "safety_precautions": [
            "Wear gloves when collecting crickets or handling field debris",
            "Avoid unnecessary broad-spectrum pesticide applications",
            "Use only products currently registered and labelled for "
            "the exact crop and target pest in India",
            "Follow label instructions, protective equipment requirements "
            "and pre-harvest intervals",
            "Protect beneficial organisms, livestock and water sources",
        ],
        "expert_advice": (
            "Melanogryllus desertus is reported from parts of Europe "
            "and western and central Asia. Overseas crop reports must "
            "not be treated as confirmed Indian host records. The "
            "Rajasthan ICAR cricket study cited in the supplied profile "
            "does not list this species. This leaves Indian occurrence "
            "unconfirmed; it does not prove absence from India."
        ),
        "action_threshold": (
            "No verified universal economic threshold is available. "
            "Consider intervention only when repeated inspections "
            "confirm active feeding and increasing seedling injury."
        ),
        "source_references": [
            "https://pubmed.ncbi.nlm.nih.gov/",
            "https://www.govinfo.gov/",
            "https://agritech.tnau.ac.in/",
        ],
    }
]


TWO_SPOTTED_CRICKET_ADVISORY_DATA = [
    {
        "solution_id": "two_spotted_cricket_chickpea_advisory",
        "pest_id": "two_spotted_cricket",
        "crop_id": "chickpea",
        "risk_level": "MEDIUM",
        "status": "ADVISORY",
        "scientific_name": "Gryllus bimaculatus",
        "description": (
            "Two-spotted Cricket is recorded feeding on developing "
            "chickpea pods and seeds in India. Inspect affected areas and "
            "confirm active feeding before taking control measures."
        ),
        "identification_signs": [
            "Large, robust, dark cricket",
            "Two yellowish spots near the base of the forewings",
            "Long antennae and strong hind legs",
        ],
        "crop_damage": (
            "ICRISAT reports feeding on developing chickpea pods and seeds."
        ),
        "affected_plant_parts": ["Developing pods", "Seeds"],
        "recommended_treatment": (
            "Integrated pest management based on confirmed field activity."
        ),
        "immediate_control_measures": [
            "Inspect developing chickpea pods for feeding injury",
            "Check affected pods for damaged or partially eaten seeds",
            "Use hand collection or suitable physical protection where practical",
        ],
        "biological_control_options": [
            "Conserve naturally occurring birds, spiders and predatory insects"
        ],
        "cultural_control_methods": [
            "Manage excessive weeds and debris near vulnerable crop areas",
            "Monitor chickpea during pod development",
        ],
        "mechanical_control_methods": [
            "Hand-collect visible crickets in small growing areas when necessary",
            "Protect vulnerable seedlings with suitable insect netting",
        ],
        "chemical_control_options": None,
        "prevention": [
            "Avoid chemical treatment based on cricket presence alone",
            "Confirm the species before considering pest-management action",
        ],
        "monitoring": [
            "Monitor cricket activity during evening and night",
            "Inspect developing pods for fresh feeding injury",
            "Record cricket numbers and the proportion of pods affected",
        ],
        "safety_precautions": [
            "Avoid unnecessary broad-spectrum insecticides",
            "Use only pesticides registered and labelled for the exact crop and pest",
        ],
        "expert_advice": (
            "No universal economic threshold or species-specific pesticide "
            "recommendation is established in this profile."
        ),
        "source_references": [
            "https://oar.icrisat.org/2410/1/HostPlantResistanceAndInsect.pdf",
        ],
    },
    {
        "solution_id": "two_spotted_cricket_potato_advisory",
        "pest_id": "two_spotted_cricket",
        "crop_id": "potato",
        "risk_level": "MEDIUM",
        "status": "ADVISORY",
        "scientific_name": "Gryllus bimaculatus",
        "description": (
            "The Zoological Survey of India records potato plant damage, "
            "without specifying the affected part. A separate historical "
            "severe-damage report is attributed to Chopard (1969), as cited "
            "by a 2021 review. Confirm current injury before intervention."
        ),
        "identification_signs": [
            "Large, robust, dark cricket",
            "Two yellowish spots near the base of the forewings",
        ],
        "crop_damage": (
            "The Zoological Survey of India records potato plant damage "
            "without identifying the affected part. A historical severe "
            "plant-damage report is attributed to Chopard (1969), as cited "
            "by a 2021 review."
        ),
        "affected_plant_parts": [],
        "recommended_treatment": (
            "Integrated pest management based on confirmed field activity."
        ),
        "immediate_control_measures": [
            "Inspect potato plants for fresh gnawing or feeding injury",
            "Hand-collect crickets in small, localised infestations",
        ],
        "biological_control_options": [
            "Conserve naturally occurring predators"
        ],
        "cultural_control_methods": [
            "Manage excessive weeds and debris around vulnerable crop areas",
            "Inspect field boundaries and sheltered ground-level locations",
        ],
        "mechanical_control_methods": [
            "Hand collection in small affected areas",
            "Use suitable traps to monitor adult activity",
        ],
        "chemical_control_options": None,
        "prevention": [
            "Monitor fields during vulnerable growth stages",
            "Record locations with repeated cricket activity",
        ],
        "monitoring": [
            "Inspect plants for fresh feeding injury",
            "Record cricket numbers and affected plants",
        ],
        "safety_precautions": [
            "Avoid unnecessary broad-spectrum insecticides",
            "Follow pesticide registration and label requirements",
        ],
        "expert_advice": (
            "The available fauna record does not specify the affected potato "
            "plant part. The historical Chopard (1969) report is cited by a "
            "2021 review and does not establish an Indian pesticide recommendation "
            "or a current economic threshold."
        ),
        "source_references": [
            "https://faunaofindia.nic.in/PDFVolumes/spb/047/index.pdf",
        ],
    },
]


JAPANESE_BURROWING_CRICKET_ADVISORY_DATA = [
    {
        "solution_id": "japanese_burrowing_cricket_general_advisory",
        "pest_id": "japanese_burrowing_cricket",
        "crop_id": None,
        "risk_level": "LOW",
        "status": "ADVISORY",
        "scientific_name": "Velarifictorus micado",
        "description": (
            "Japanese Burrowing Cricket is associated with feeding on "
            "red clover and orchard grass in Japanese agricultural records. "
            "These records do not establish Indian crop-host relationships "
            "or significant economic crop losses."
        ),
        "identification_signs": [
            "Yellowish-brown body",
            "Irregular pale longitudinal markings on the head",
            "Pale band connecting the lateral ocelli",
            "Pale spots or blotches on the pronotum",
            "Strong hind legs and long antennae",
            "Burrowing behaviour",
        ],
        "crop_damage": (
            "Japanese records describe feeding on forage-crop leaves and "
            "stems. This damage evidence must not be presented as confirmed "
            "Indian crop damage."
        ),
        "affected_plant_parts": [],
        "recommended_treatment": (
            "General integrated pest management. Confirm the species and "
            "active feeding before considering intervention."
        ),
        "immediate_control_measures": [
            "Inspect plants for fresh chewing injury",
            "Check soil cracks and sheltered ground-level locations",
            "Observe cricket activity during evening and night",
            "Hand-collect individuals in small, localised infestations",
            "Protect vulnerable nursery plants with suitable physical barriers",
        ],
        "biological_control_options": [
            "Conserve naturally occurring birds, spiders and predatory insects",
            "No species-specific biological control agent is established",
        ],
        "cultural_control_methods": [
            "Monitor crop edges and sheltered locations",
            "Manage excessive weeds and unnecessary debris",
            "Maintain healthy forage and nursery areas",
            "Avoid unnecessary disturbance of natural predators",
        ],
        "mechanical_control_methods": [
            "Hand collection in small affected areas",
            "Physical protection of vulnerable nursery plants",
            "Inspect soil cracks and hiding places",
            "Use suitable traps to monitor adult activity",
        ],
        "chemical_control_options": None,
        "prevention": [
            "Inspect vulnerable plants regularly",
            "Monitor forage areas for fresh chewing injury",
            "Check nursery plants and soil before moving planting material",
            "Avoid unnecessary pesticide applications",
        ],
        "monitoring": [
            "Inspect leaves and stems for fresh chewing marks",
            "Search near soil cracks and sheltered areas",
            "Observe calling activity during suitable periods",
            "Record cricket numbers and affected plants",
            "Confirm species identity before assigning a species-specific solution",
        ],
        "safety_precautions": [
            "Wear gloves when collecting insects or handling debris",
            "Avoid unnecessary broad-spectrum insecticides",
            "Use only pesticides registered and labelled for the exact crop and pest",
            "Protect beneficial organisms, livestock and water sources",
        ],
        "expert_advice": (
            "Do not confuse Velarifictorus micado with V. aspersus. "
            "The presence of V. aspersus in India does not establish "
            "the presence of V. micado. No verified economic threshold "
            "or species-specific pesticide recommendation is available."
        ),
        "source_references": [],
    },
]


ALLARDS_GROUND_CRICKET_ADVISORY_DATA = [
    {
        "solution_id": "allards_ground_cricket_general_advisory",
        "pest_id": "allards_ground_cricket",
        "crop_id": None,
        "crop_name": None,
        "risk_level": "LOW",
        "status": "ADVISORY",
        "scientific_name": "Allonemobius allardi",
        "description": (
            "Allard's Ground Cricket is primarily documented in grassland "
            "and open habitats. Alfalfa is listed among its food plants, "
            "but economically significant damage to cultivated crops "
            "has not been established."
        ),
        "identification_signs": [
            "Small dark brown to black ground cricket",
            "Long antennae and strong hind legs",
            "Usually short forewings that do not cover the abdomen",
            "Three faint longitudinal head stripes generally absent",
        ],
        "crop_damage": (
            "Alfalfa is listed as a food plant. Economically significant "
            "damage to cultivated crops has not been established."
        ),
        "affected_plant_parts": [],
        "recommended_treatment": (
            "Monitor for confirmed cricket activity and actual feeding. "
            "Do not infer crop damage from the food-plant record alone."
        ),
        "immediate_control_measures": [
            "Confirm the cricket identification before considering intervention",
            "Inspect plants for fresh feeding injury",
            "Record observed cricket activity and affected locations",
        ],
        "biological_control_options": [
            "No species-specific biological-control recommendation is established",
            "Conserve naturally occurring beneficial organisms",
        ],
        "cultural_control_methods": [
            "Monitor areas where cricket activity is observed",
            "Do not treat alfalfa as a confirmed damaging crop host",
        ],
        "mechanical_control_methods": [
            "Use observation and suitable traps to monitor cricket activity",
        ],
        "chemical_control_options": None,
        "prevention": [
            "Confirm species identity and feeding before taking action",
            "Avoid unnecessary pesticide applications",
        ],
        "monitoring": [
            "Record cricket sightings and any observed feeding",
            "Distinguish food-plant records from confirmed crop damage",
        ],
        "safety_precautions": [
            "Use only pesticides registered and labelled for the exact crop and pest",
            "Follow label instructions and protect beneficial organisms",
        ],
        "expert_advice": (
            "Taxonomic identity, Indian occurrence, cultivated-crop damage, "
            "economic threshold and chemical management require further "
            "verification. Alfalfa is retained as a food-plant record only."
        ),
        "action_threshold": "No economic threshold is established.",
        "source_references": [],
    },
]


ASH_CICADA_ADVISORY_DATA = [
    {
        "solution_id": "ash_cicada_general_advisory",
        "pest_id": "ash_cicada",
        "crop_id": None,
        "risk_level": "LOW",
        "status": "ADVISORY",
        "scientific_name": "Cicada orni",
        "description": (
            "Ash Cicada is associated with manna ash and other trees. "
            "Female egg-laying can injure young branches, but the species "
            "is not established as a major agricultural pest."
        ),
        "identification_signs": [
            "Greyish-brown adult body",
            "Transparent, strongly veined wings",
            "Prominent compound eyes and short antennae",
            "Long piercing-sucking mouthpart",
            "Males produce a loud calling sound using tymbals",
            "Shed nymphal skins may remain attached to tree trunks",
        ],
        "crop_damage": (
            "Female egg-laying can produce slits or scars in young twigs "
            "and may cause local twig drying. Serious crop loss is not "
            "established."
        ),
        "affected_plant_parts": [
            "Roots",
            "Young branches",
            "Twigs",
        ],
        "recommended_treatment": (
            "No routine pesticide treatment is recommended. Monitor "
            "young trees and protect them if repeated egg-laying injury "
            "is observed."
        ),
        "immediate_control_measures": [
            "Inspect young branches for fresh egg-laying slits",
            "Remove severely damaged drying twigs where appropriate",
            "Protect vulnerable young trees with fine-mesh netting",
            "Avoid unnecessary insecticide application",
        ],
        "biological_control_options": [
            "Conserve birds, spiders and other natural predators",
            "No species-specific biological control agent is established",
        ],
        "cultural_control_methods": [
            "Maintain healthy trees through appropriate watering and care",
            "Monitor young trees during adult emergence",
            "Avoid unnecessary pruning of healthy branches",
            "Preserve natural predators",
        ],
        "mechanical_control_methods": [
            "Use fine-mesh netting to protect small trees",
            "Prune and dispose of severely damaged twigs",
            "Inspect trunks and branches for adult cicadas and shed skins",
        ],
        "chemical_control_options": None,
        "prevention": [
            "Protect young trees during periods of heavy cicada activity",
            "Maintain tree health",
            "Inspect branches for egg-laying injury",
            "Monitor newly planted trees carefully",
            "Preserve natural predators",
        ],
        "monitoring": [
            "Listen for male calling activity",
            "Inspect branches for egg-laying slits",
            "Look for drying or hanging twig tips",
            "Check trunks for shed nymphal skins",
            "Record adult activity and affected branches",
        ],
        "safety_precautions": [
            "Wear gloves when pruning damaged branches",
            "Use appropriate eye protection when pruning overhead",
            "Do not climb trees to collect cicadas",
            "Follow safe pruning practices",
            "Follow approved pesticide labels if chemical treatment is independently justified",
        ],
        "expert_advice": (
            "Indian occurrence of Cicada orni is not confirmed here. "
            "Do not confuse it with North American periodical cicadas "
            "(Magicicada spp.). No species-specific economic threshold "
            "or pesticide recommendation is established."
        ),
        "source_references": [],
    },
]


BLACK_CICADA_ADVISORY_DATA = [
    {
        "solution_id": "black_cicada_rose_apple_advisory",
        "pest_id": "black_cicada",
        "crop_id": "rose_apple",
        "risk_level": "LOW",
        "status": "ADVISORY",
        "scientific_name": "Huechys sanguinea",
        "description": (
            "Huechys sanguinea is recorded by NBAIR in association "
            "with rose apple. The available host record does not "
            "quantify crop losses or specify the damaged plant part."
        ),
        "identification_signs": [
            "Compact cicada with a black and scarlet colour pattern",
            "Newly emerged adults may initially be deep scarlet",
            "Mature adults become predominantly black",
            "Wings become smoky grey as they harden",
            "Prominent compound eyes and piercing-sucking mouthparts",
        ],
        "crop_damage": (
            "The available rose apple host record does not quantify crop "
            "losses or identify a specific damaged plant part."
        ),
        "affected_plant_parts": [],
        "recommended_treatment": (
            "Monitor rose apple trees for actual injury. A host association "
            "alone does not establish a need for treatment."
        ),
        "immediate_control_measures": [
            "Confirm cicada identity before considering intervention",
            "Inspect rose apple for observed injury",
            "Record adult activity and any damage separately",
            "Avoid pesticide application based on presence alone",
        ],
        "biological_control_options": [
            "Conserve naturally occurring predators",
            "No species-specific biological-control programme is established",
        ],
        "cultural_control_methods": [
            "Maintain healthy rose apple trees",
            "Monitor trees during observed adult activity",
            "Do not infer crop loss from a host record alone",
        ],
        "mechanical_control_methods": [
            "Inspect trees for adults and observed injury",
            "Protect young trees only if repeated injury is confirmed",
        ],
        "chemical_control_options": None,
        "prevention": [
            "Monitor rose apple trees for cicada activity",
            "Avoid unnecessary insecticide applications",
        ],
        "monitoring": [
            "Record cicada observations on rose apple",
            "Inspect for visible injury without assuming a specific plant part",
            "Document any confirmed damage and affected plant part",
        ],
        "safety_precautions": [
            "Use only pesticides registered and labelled for the exact crop and pest",
            "Follow approved product labels and protect beneficial organisms",
        ],
        "expert_advice": (
            "The supplied NBAIR record supports a rose apple association, "
            "not quantified crop damage or a specific affected plant part. "
            "The scientific-name match and exact source URLs remain to be "
            "independently verified."
        ),
        "source_references": [],
    },
]


BLACK_PRINCE_CICADA_ADVISORY_DATA = [
    {
        "solution_id": "black_prince_cicada_general_advisory",
        "pest_id": "black_prince_cicada",
        "crop_id": None,
        "risk_level": "LOW",
        "status": "ADVISORY",
        "scientific_name": "Psaltoda plaga",
        "description": (
            "Black Prince Cicada is native to eastern Australia and is "
            "associated with several tree species. Localised twig injury "
            "from egg-laying may occur, but serious commercial crop damage "
            "is not established."
        ),
        "identification_signs": [
            "Large, predominantly black adult cicada",
            "Brownish collar behind the head may be visible",
            "Transparent wings with dark veins",
            "Loud male calling sound",
            "Adults commonly rest on main tree stems",
            "Empty nymphal skins may remain attached to bark",
        ],
        "crop_damage": (
            "No distinctive crop symptoms or substantial commercial crop "
            "loss are established. Female egg-laying may injure small twigs."
        ),
        "affected_plant_parts": [
            "Roots",
            "Main stems",
            "Branches",
            "Young woody twigs",
        ],
        "recommended_treatment": (
            "No routine pesticide treatment. Monitor young trees and "
            "use non-chemical protection if repeated egg-laying injury "
            "is observed."
        ),
        "immediate_control_measures": [
            "Inspect young branches for egg-laying slits",
            "Monitor trees for emerging adults",
            "Prune severely damaged twigs where necessary",
            "Protect vulnerable young trees with suitable mesh",
            "Avoid spraying solely because adults are present or calling",
        ],
        "biological_control_options": [
            "Conserve birds, spiders and other natural predators",
            "The noisy friarbird is reported as a natural predator",
            "No commercial species-specific biological treatment is established",
        ],
        "cultural_control_methods": [
            "Maintain healthy trees",
            "Monitor young trees during adult emergence",
            "Remove badly damaged twigs when necessary",
            "Preserve natural predators",
            "Avoid unnecessary disturbance of native vegetation",
        ],
        "mechanical_control_methods": [
            "Use fine-mesh protection for vulnerable young trees",
            "Prune severely damaged branches",
            "Inspect trunks for emerging adults and shed skins",
            "Hand-remove adults from small nursery plants where practical",
        ],
        "chemical_control_options": None,
        "prevention": [
            "Monitor young trees for egg-laying damage",
            "Maintain healthy tree growth",
            "Protect vulnerable plants during adult emergence",
            "Preserve natural predators",
            "Avoid unnecessary pesticide applications",
        ],
        "monitoring": [
            "Listen for male calling activity",
            "Inspect main stems and branches for adults",
            "Look for egg-laying slits on young twigs",
            "Check tree bases for emerging nymphs",
            "Record affected branches and tree condition",
        ],
        "safety_precautions": [
            "Wear gloves when pruning damaged branches",
            "Use eye protection during pruning",
            "Do not climb trees to collect cicadas",
            "Follow safe disposal practices for damaged plant material",
            "Follow approved pesticide labels if chemical treatment is independently justified",
        ],
        "expert_advice": (
            "Psaltoda plaga is an Australian cicada, not an established "
            "Indian agricultural pest. Do not confuse it with Huechys "
            "sanguinea or Cryptotympana atrata."
        ),
        "source_references": [],
    },
]


BLADDER_CICADA_ADVISORY_DATA = [
    {
        "solution_id": "bladder_cicada_general_advisory",
        "pest_id": "bladder_cicada",
        "crop_id": None,
        "risk_level": "LOW",
        "status": "ADVISORY",
        "scientific_name": "Cystosoma saundersii",
        "description": (
            "Bladder Cicada is native to eastern Australia and is "
            "associated with several trees, shrubs and grasses. "
            "Female egg-laying may injure small branches, but significant "
            "commercial crop losses are not established."
        ),
        "identification_signs": [
            "Large, usually green cicada",
            "Opaque leaf-like forewings with visible veins",
            "Pinkish-brown eyes",
            "Small bristle-like antennae",
            "Male has a greatly enlarged hollow balloon-like abdomen",
            "Male produces a deep frog-like call, especially around dusk",
            "Brown empty nymphal skins may remain attached to vegetation",
        ],
        "crop_damage": (
            "No distinctive crop symptoms or significant commercial "
            "crop damage are established. Heavy egg-laying may cause "
            "localised injury to small woody branches."
        ),
        "affected_plant_parts": [
            "Roots",
            "Stems",
            "Branches",
            "Young woody twigs",
        ],
        "recommended_treatment": (
            "No routine pesticide treatment is recommended. Monitor "
            "young trees and protect them if repeated egg-laying injury "
            "is confirmed."
        ),
        "immediate_control_measures": [
            "Inspect young branches for egg-laying slits",
            "Check tree trunks for emerging adults and shed nymphal skins",
            "Prune severely damaged or drying twigs where necessary",
            "Protect vulnerable nursery trees using suitable fine-mesh netting",
            "Avoid unnecessary pesticide spraying",
        ],
        "biological_control_options": [
            "Conserve naturally occurring birds, spiders and other predators",
            "No species-specific biological control agent is established",
        ],
        "cultural_control_methods": [
            "Maintain healthy trees through appropriate watering and care",
            "Monitor young trees during adult emergence",
            "Remove badly damaged branches where necessary",
            "Preserve natural predators",
            "Avoid unnecessary disturbance of native vegetation",
        ],
        "mechanical_control_methods": [
            "Use fine-mesh covers to protect vulnerable young trees",
            "Prune severely damaged twigs",
            "Inspect branches and trunks for adults and shed skins",
            "Hand-remove adults from small nursery plants where practical",
        ],
        "chemical_control_options": None,
        "prevention": [
            "Protect young trees during periods of heavy adult activity",
            "Maintain healthy tree growth",
            "Inspect branches for egg-laying injury",
            "Monitor trees and shrubs regularly",
            "Preserve natural predators",
            "Avoid unnecessary insecticide applications",
        ],
        "monitoring": [
            "Listen for the male's deep calling sound around dusk",
            "Inspect dense foliage for adult cicadas",
            "Look for small egg-laying slits on branches",
            "Check trunks for shed nymphal skins",
            "Monitor soil around host trees for emerging nymphs",
            "Record adult activity and affected branches",
        ],
        "safety_precautions": [
            "Wear gloves when pruning damaged branches",
            "Use eye protection during pruning",
            "Do not climb trees to collect cicadas",
            "Dispose of damaged plant material safely",
            "Follow approved pesticide labels if chemical treatment is independently justified",
        ],
        "expert_advice": (
            "Cystosoma saundersii is an Australian species, not an "
            "established Indian agricultural pest. Do not confuse it "
            "with Cystosoma schmeltzi, the Lesser Bladder Cicada."
        ),
        "source_references": [],
    },
]


BROWN_BUNYIP_CICADA_ADVISORY_DATA = [
    {
        "solution_id": "brown_bunyip_cicada_general_advisory",
        "pest_id": "brown_bunyip_cicada",
        "crop_id": None,
        "risk_level": "LOW",
        "status": "ADVISORY",
        "scientific_name": "Tamasa tristigma",
        "description": (
            "Brown Bunyip Cicada is a tree-associated Australian cicada. "
            "Its ecological host records include liquidambar, she-oak, "
            "wattle, jacaranda and eucalyptus. Significant commercial "
            "crop damage is not established."
        ),
        "identification_signs": [
            "Pale brown or yellowish-brown body",
            "Relatively narrow, elongated body",
            "Three dark spots near the tips of each male forewing",
            "Dark and light abdominal bands",
            "Transparent female wings",
            "Male produces a continuous low-pitched buzzing or rattling call",
            "Adults commonly rest on tree trunks and branches",
        ],
        "crop_damage": (
            "No significant commercial crop damage is established. "
            "General cicada biology includes sap feeding and egg deposition "
            "in woody tissue, but species-specific economic injury "
            "has not been confirmed."
        ),
        "affected_plant_parts": [
            "Roots",
            "Woody branches",
            "Twigs",
        ],
        "recommended_treatment": (
            "No routine pesticide treatment is recommended. Monitor "
            "young trees and use non-chemical protection if actual "
            "branch injury is observed."
        ),
        "immediate_control_measures": [
            "Inspect young branches for possible egg-laying slits",
            "Check trunks and branches for adult cicadas",
            "Look for shed nymphal skins",
            "Prune severely damaged twigs only where necessary",
            "Protect vulnerable nursery trees with suitable mesh",
        ],
        "biological_control_options": [
            "Conserve naturally occurring birds, spiders and other predators",
            "No species-specific biological control agent is established",
        ],
        "cultural_control_methods": [
            "Maintain healthy trees",
            "Monitor young trees during adult emergence",
            "Remove severely damaged branches only when necessary",
            "Preserve natural predators",
            "Avoid unnecessary disturbance of native vegetation",
        ],
        "mechanical_control_methods": [
            "Hand-remove adults from small nursery plants where practical",
            "Use fine-mesh covers to protect vulnerable young trees",
            "Prune badly damaged twigs",
            "Inspect tree trunks for emerging adults and shed skins",
        ],
        "chemical_control_options": None,
        "prevention": [
            "Maintain healthy trees and suitable growing conditions",
            "Inspect young branches during adult activity",
            "Protect vulnerable nursery trees where necessary",
            "Preserve natural predators",
            "Avoid unnecessary insecticide applications",
        ],
        "monitoring": [
            "Listen for the male's continuous low-pitched buzzing call",
            "Inspect tree trunks and branches for adults",
            "Look for possible egg-laying slits on young twigs",
            "Check for shed nymphal skins",
            "Record adult activity and visible plant injury",
        ],
        "safety_precautions": [
            "Wear gloves when handling damaged branches",
            "Use eye protection during pruning",
            "Avoid climbing trees to collect cicadas",
            "Dispose of damaged plant material safely",
            "Follow approved pesticide labels if chemical treatment is independently justified",
        ],
        "expert_advice": (
            "Tamasa tristigma is an Australian cicada, not an established "
            "Indian agricultural pest. Its underground developmental "
            "duration is not established in the supplied profile. "
            "Accurate identification is important because the genus "
            "contains other Bunyip cicada species."
        ),
        "source_references": [],
    },
]


CAROLINA_GROUND_CRICKET_ADVISORY_DATA = [
    {
        "solution_id": "carolina_ground_cricket_general_advisory",
        "pest_id": "carolina_ground_cricket",
        "crop_id": None,
        "risk_level": "LOW",
        "status": "ADVISORY",
        "scientific_name": "Eunemobius carolinus",
        "description": (
            "Carolina Ground Cricket is a small ground-dwelling cricket "
            "associated with moist meadows, damp woodland and sheltered "
            "ground vegetation. Significant agricultural crop damage "
            "has not been established."
        ),
        "identification_signs": [
            "Small shiny dark brown or black body",
            "Slightly flattened appearance",
            "Lighter greyish or yellowish-brown legs",
            "Long thin antennae",
            "Short wings in many individuals",
            "Male produces a continuous wavering buzzy trill",
        ],
        "crop_damage": (
            "No significant agricultural crop damage is documented "
            "in the supplied profile. Feeding on cultivated plants "
            "has not been confirmed for this species."
        ),
        "affected_plant_parts": [],
        "recommended_treatment": (
            "No routine pest treatment is recommended. Confirm direct "
            "feeding injury before considering any intervention."
        ),
        "immediate_control_measures": [
            "Confirm whether individuals are feeding on cultivated plants",
            "Inspect vegetation for directly observed feeding injury",
            "Monitor nursery plants if unexplained injury occurs",
            "Avoid unnecessary insecticide application",
        ],
        "biological_control_options": [
            "Conserve naturally occurring birds, spiders and predatory insects",
            "No species-specific biological control agent is established",
        ],
        "cultural_control_methods": [
            "Maintain normal field and nursery hygiene",
            "Monitor vulnerable seedlings for actual feeding damage",
            "Preserve natural predators and beneficial organisms",
            "Avoid unnecessary removal of natural vegetation",
        ],
        "mechanical_control_methods": [
            "Hand-collect individuals in small nursery areas only if actual damage is confirmed",
            "Inspect beneath stones, logs and ground debris",
            "Use physical seedling protection only when a verified infestation warrants it",
        ],
        "chemical_control_options": None,
        "prevention": [
            "Inspect nursery plants regularly",
            "Monitor areas with unexplained seedling injury",
            "Maintain appropriate field hygiene",
            "Avoid unnecessary pesticide applications",
            "Preserve natural ground-dwelling predators",
        ],
        "monitoring": [
            "Listen for the male's continuous wavering trill",
            "Search moist vegetation and sheltered ground habitats",
            "Inspect beneath stones and decaying logs",
            "Record cricket presence and directly observed plant injury",
            "Use physical characteristics and calling patterns for identification",
        ],
        "when_to_take_action": (
            "Take action only after repeated observations confirm direct "
            "feeding and measurable damage to cultivated plants. "
            "No economic injury threshold is established."
        ),
        "safety_precautions": [
            "Wear gloves when handling insects and field debris",
            "Avoid unnecessary pesticide applications",
            "Protect beneficial organisms and natural habitats",
            "Follow approved pesticide labels if treatment of a separately identified pest is necessary",
        ],
        "expert_advice": (
            "Eunemobius carolinus is reported from much of the United "
            "States and parts of southern Canada. It may be confused "
            "with related ground crickets, including Eunemobius "
            "confusus and Eunemobius melodius. Reliable identification "
            "may require detailed morphological or acoustic examination."
        ),
        "source_references": [],
    },
]


CHORUS_CICADA_KIWIFRUIT_ADVISORY_DATA = [
    {
        "solution_id": "chorus_cicada_kiwifruit_advisory",
        "pest_id": "chorus_cicada",
        "crop_id": "kiwifruit",
        "risk_level": "HIGH",
        "status": "ADVISORY",
        "scientific_name": "Amphipsalta zelandica",
        "description": (
            "Chorus Cicada is an economically important kiwifruit "
            "orchard pest in New Zealand when populations are abundant. "
            "Females damage current-season canes by cutting woody tissue "
            "and depositing eggs, creating characteristic herringbone scars."
        ),
        "identification_signs": [
            "Large robust cicada",
            "Mottled green and black body",
            "Transparent strongly veined wings",
            "Female has a prominent pointed ovipositor",
            "Males produce a loud continuous clicking or buzzing chorus",
            "Brown empty nymphal skins may be attached to trees and structures",
        ],
        "crop_damage": (
            "Female egg-laying wounds weaken kiwifruit canes and can "
            "contribute to branch breakage during winter training "
            "or fruit development. Sap feeding is also part of its "
            "biology but is not the main documented injury."
        ),
        "affected_plant_parts": [
            "Current-season canes",
            "Shoots",
            "Woody branches",
        ],
        "visible_symptoms": [
            "V-shaped or herringbone-pattern egg-laying scars",
            "Small cuts on current-season shoots",
            "Weakened or irregularly callused canes",
            "Broken branches",
        ],
        "recommended_treatment": (
            "Use integrated monitoring and non-chemical management. "
            "Inspect vulnerable canes, mark damaged shoots and prune "
            "severely weakened or broken branches where appropriate."
        ),
        "immediate_control_measures": [
            "Inspect current-season kiwifruit canes for fresh egg-laying wounds",
            "Mark heavily damaged shoots",
            "Prune severely weakened or broken canes where appropriate",
            "Protect vulnerable young plants with suitable physical barriers",
            "Monitor orchard blocks during adult emergence",
        ],
        "biological_control_options": [
            "Idiocentrus minus is reported as a natural enemy",
            "Ground beetle larvae may prey on large nymphs",
            "Birds may consume adult cicadas",
            "Isaria sinclairii has been reported infecting cicada nymphs",
            "These are reported natural enemies, not guaranteed commercial treatments",
        ],
        "cultural_control_methods": [
            "Regularly inspect kiwifruit canes",
            "Remove badly weakened or broken branches",
            "Monitor orchards during adult emergence",
            "Maintain suitable orchard structure and cane training",
            "Avoid unnecessary disturbance of natural predators",
        ],
        "mechanical_control_methods": [
            "Prune and remove heavily damaged canes",
            "Inspect branches for herringbone egg-laying scars",
            "Protect young plants using suitable physical barriers",
            "Remove accessible adults from nursery plants where practical",
        ],
        "chemical_control_options": None,
        "prevention": [
            "Inspect kiwifruit canes during adult emergence",
            "Protect vulnerable young shoots where practical",
            "Maintain healthy orchard canes",
            "Remove severely damaged branches when necessary",
            "Preserve natural parasitoids and predators",
        ],
        "monitoring": [
            "Listen for loud male chorus activity",
            "Inspect trees and orchard structures for emerging adults",
            "Look for herringbone-shaped egg-laying scars",
            "Check trunks and posts for shed nymphal skins",
            "Record adult abundance and the number of damaged canes",
        ],
        "when_to_take_action": (
            "Consider intervention when fresh egg-laying scars occur "
            "on productive kiwifruit canes, particularly where wounds "
            "may cause breakage during training or fruit development. "
            "No universal economic injury threshold is established."
        ),
        "safety_precautions": [
            "Wear gloves when pruning damaged canes",
            "Use appropriate eye protection and pruning equipment",
            "Dispose of damaged branches safely",
            "Avoid unnecessary insecticide applications",
            "Follow approved pesticide labels if chemical treatment is independently justified",
        ],
        "geographic_limitation": (
            "The documented agricultural impact and management context "
            "are from New Zealand. Indian occurrence and Indian crop "
            "damage are not established."
        ),
        "expert_advice": (
            "Amphipsalta zelandica is endemic to New Zealand. Approximate "
            "profile claims describe a 25-44 month nymphal period and a "
            "three-to-four-year life cycle; these are not universal exact "
            "durations. Accurate identification is important when "
            "distinguishing it from other large cicadas."
        ),
        "source_references": [],
    },
]


COMMON_CICADA_ADVISORY_DATA = [
    {
        "solution_id": "common_cicada_general_advisory",
        "pest_id": "common_cicada",
        "crop_id": None,
        "risk_level": "LOW",
        "status": "ADVISORY",
        "scientific_name": "Cicadidae spp.",
        "description": (
            "Common Cicada represents unidentified members of the "
            "family Cicadidae. Most cicadas cause little noticeable "
            "agricultural damage, although heavy emergence can result "
            "in egg-laying injury to young woody branches."
        ),
        "identification_signs": [
            "Broad head with prominent compound eyes",
            "Short antennae",
            "Transparent wings with visible veins",
            "Piercing-sucking mouthparts",
            "Male calling sounds such as buzzing, clicking or singing",
            "Shed nymphal skins may remain attached to tree trunks",
        ],
        "crop_damage": (
            "No species-specific crop damage is established for this "
            "unidentified entry. Some cicada species can cause twig "
            "splitting, drying and branch dieback through egg-laying."
        ),
        "affected_plant_parts": [
            "Roots",
            "Young woody branches",
            "Twigs",
        ],
        "recommended_treatment": (
            "Routine pesticide treatment is generally unnecessary. "
            "Monitor vulnerable young trees and confirm actual injury "
            "before taking action."
        ),
        "immediate_control_measures": [
            "Inspect young branches for fresh egg-laying slits",
            "Remove severely damaged twigs where appropriate",
            "Protect vulnerable young trees with suitable fine-mesh netting",
            "Monitor tree condition after adult emergence",
            "Avoid spraying solely because cicadas are calling",
        ],
        "biological_control_options": [
            "Conserve naturally occurring birds, spiders and predatory insects",
            "Some parasitoids and pathogens attack particular cicada species",
            "No universal species-specific biological control agent is established",
        ],
        "cultural_control_methods": [
            "Maintain healthy trees and shrubs",
            "Monitor young plants during cicada emergence",
            "Prune severely damaged branches where necessary",
            "Preserve natural predators",
            "Avoid unnecessary disturbance of surrounding vegetation",
        ],
        "mechanical_control_methods": [
            "Protect vulnerable young trees with fine-mesh netting",
            "Prune and remove severely damaged twigs",
            "Inspect trunks for emerging adults and shed nymphal skins",
            "Hand-remove adults from small nursery plants where practical",
        ],
        "chemical_control_options": None,
        "prevention": [
            "Maintain healthy trees and shrubs",
            "Protect young trees during heavy adult emergence",
            "Inspect branches regularly",
            "Remove badly damaged branches where necessary",
            "Preserve natural predators and beneficial organisms",
        ],
        "monitoring": [
            "Listen for male cicada calling sounds",
            "Inspect young branches for egg-laying slits",
            "Look for drying twig tips and branch flagging",
            "Check tree trunks for shed nymphal skins",
            "Record population levels and directly observed plant injury",
        ],
        "when_to_take_action": (
            "Take action only when repeated inspections confirm fresh "
            "egg-laying injuries or increasing branch damage, particularly "
            "on young trees. Adult presence or calling sounds alone "
            "do not justify treatment."
        ),
        "safety_precautions": [
            "Wear gloves when pruning damaged branches",
            "Use eye protection with pruning tools",
            "Avoid climbing trees to collect insects",
            "Dispose of damaged branches safely",
            "Follow approved pesticide labels if treatment of a separately identified pest is necessary",
        ],
        "expert_advice": (
            "Cicadas are members of Hemiptera and have piercing-sucking "
            "mouthparts. Their life cycles and emergence periods vary "
            "between species. Correct species identification is necessary "
            "before assigning crop hosts, economic thresholds or pesticide "
            "recommendations."
        ),
        "source_references": [],
    },
]


DARK_BUSH_CRICKET_ADVISORY_DATA = [
    {
        "solution_id": "dark_bush_cricket_general_advisory",
        "pest_id": "dark_bush_cricket",
        "crop_id": None,
        "risk_level": "LOW",
        "status": "ADVISORY",
        "scientific_name": "Pholidoptera griseoaptera",
        "description": (
            "Dark Bush-cricket is an omnivorous European bush-cricket "
            "found in woodland edges, hedgerows, bramble patches and "
            "other dense vegetation. It consumes plant material and "
            "small insects. Significant commercial crop damage has "
            "not been established."
        ),
        "identification_signs": [
            "Dark brown, grey-brown or reddish-brown body",
            "Yellowish or greenish-yellow underside",
            "Very short wings",
            "Long thread-like antennae",
            "Powerful hind legs",
            "Female has a prominent gently curved ovipositor",
            "Male produces short high-pitched chirps at irregular intervals",
        ],
        "crop_damage": (
            "No significant commercial crop damage is established. "
            "Plant feeding is documented on wild vegetation, while "
            "the species also consumes small insects."
        ),
        "affected_plant_parts": [],
        "recommended_treatment": (
            "No routine pest treatment is recommended. Preserve the "
            "species unless direct, measurable damage to cultivated "
            "plants is confirmed."
        ),
        "immediate_control_measures": [
            "Inspect plants for directly observed feeding injury",
            "Confirm the insect's identity before classifying it as a crop pest",
            "Avoid unnecessary insecticide applications",
            "Protect vulnerable nursery plants only if repeated feeding injury is observed",
        ],
        "biological_control_options": [
            "Conserve naturally occurring birds, spiders and predatory insects",
            "Recognise that this bush-cricket itself consumes aphids and other small insects",
            "No species-specific commercial biological-control agent is established",
        ],
        "cultural_control_methods": [
            "Maintain normal field and nursery hygiene",
            "Monitor crop boundaries and nursery vegetation",
            "Preserve natural vegetation and beneficial organisms",
            "Avoid destroying hedgerows or bramble habitats solely because this cricket is present",
        ],
        "mechanical_control_methods": [
            "Hand-collect individuals in small areas only if actual damage is confirmed",
            "Use physical protection around vulnerable nursery plants",
            "Inspect dense ground vegetation and sheltered locations",
            "Avoid unnecessary removal of natural habitat",
        ],
        "chemical_control_options": None,
        "prevention": [
            "Inspect nursery plants regularly",
            "Monitor crops for actual feeding injury",
            "Maintain suitable field hygiene",
            "Preserve natural predators",
            "Avoid unnecessary broad-spectrum insecticides",
        ],
        "monitoring": [
            "Listen for short irregular male chirps",
            "Inspect bramble patches and dense vegetation",
            "Look beneath leaves and inside hedgerows",
            "Record cricket presence and directly observed plant injury",
            "Confirm species identity before assigning crop-pest classification",
        ],
        "when_to_take_action": (
            "Take action only when repeated inspections confirm direct "
            "feeding and measurable damage to cultivated plants. "
            "No species-specific economic threshold is established."
        ),
        "safety_precautions": [
            "Wear gloves when handling insects or vegetation",
            "Avoid unnecessary pesticide applications",
            "Protect beneficial organisms and natural habitats",
            "Follow approved pesticide labels if treatment of another confirmed pest is necessary",
        ],
        "expert_advice": (
            "Pholidoptera griseoaptera is widespread across much of "
            "Europe. It is flightless and commonly inhabits woodland "
            "edges, hedgerows and scrubland. Its eggs may remain dormant "
            "through two winter periods. Do not apply its European "
            "seasonal pattern to Indian conditions."
        ),
        "source_references": [],
    },
]


LARGE_DARK_BUSH_CRICKET_ADVISORY_DATA = [
    {
        "pest_id": "large_dark_bush_cricket",
        "crop_id": None,
        "status": "ADVISORY",
        "risk_level": "LOW",
        "title": "Monitor confirmed feeding before taking action",
        "damage_notes": (
            "No significant commercial crop damage is established "
            "for this species. It is classified as omnivorous and "
            "is associated with grassland and shrub habitats."
        ),
        "management": [
            "Confirm the species before attributing plant damage to it.",
            "Inspect plants for fresh chewing injury.",
            "Observe whether individuals are actually feeding on the crop.",
            "Hand-collect individuals only if confirmed localised injury occurs.",
            "Use physical protection for vulnerable seedlings if needed.",
            "Avoid unnecessary insecticide applications.",
        ],
        "biological_control": [
            "Natural predators may include birds, spiders and other predators.",
            "No species-specific commercial biological-control agent is established.",
        ],
        "chemical_control_options": None,
        "economic_threshold": None,
        "geographic_qualification": (
            "European distribution and habitat records. Indian occurrence "
            "and commercial crop damage are unconfirmed."
        ),
        "source_refs": [
            "https://www.gbif.org/taxon/4GLSR",
            "https://doi.org/10.3390/insects13070572",
            "https://www.tandfonline.com/doi/full/10.1080/00379271.2018.1521706",
        ],
    }
]


DOUBLE_DRUMMER_CICADA_ADVISORY_DATA = [
    {
        "solution_id": "double_drummer_cicada_general_advisory",
        "pest_id": "double_drummer_cicada",
        "crop_id": None,
        "risk_level": "LOW",
        "status": "ADVISORY",
        "scientific_name": "Thopha saccata",
        "description": (
            "Double Drummer Cicada is a large cicada native to eastern "
            "Australia. It is primarily associated with large eucalyptus "
            "trees. Significant commercial crop damage specific to this "
            "species has not been established."
        ),
        "identification_signs": [
            "Very large, broad and robust cicada",
            "Brown body with dark thoracic markings",
            "Transparent strongly veined wings",
            "Male has enlarged paired abdominal sound-producing structures",
            "Loud high-pitched buzzing or whirring call",
            "Clusters of muddy empty nymphal skins may occur near tree bases",
            "Adults commonly gather high on large trees",
        ],
        "crop_damage": (
            "No significant commercial crop damage is established. "
            "Females may lay eggs in woody twigs, potentially weakening "
            "small branches. This should not be interpreted as proof "
            "of commercial crop loss."
        ),
        "affected_plant_parts": [],
        "recommended_treatment": (
            "Routine pesticide treatment is not recommended. Monitor "
            "young trees for actual egg-laying injury rather than "
            "treating adult presence or calling activity."
        ),
        "immediate_control_measures": [
            "Inspect young branches for fresh egg-laying slits",
            "Check tree bases for emerging nymphs and shed skins",
            "Prune severely damaged twigs where necessary",
            "Protect vulnerable young trees with suitable fine-mesh screening",
            "Avoid unnecessary insecticide spraying",
        ],
        "biological_control_options": [
            "Conserve naturally occurring birds, spiders and other predators",
            "Ants and other predators may attack eggs or newly emerged nymphs",
            "No species-specific commercial biological-control agent is established",
        ],
        "cultural_control_methods": [
            "Maintain healthy trees and suitable growing conditions",
            "Monitor young trees during adult emergence",
            "Remove severely damaged branches where appropriate",
            "Preserve natural predators",
            "Avoid unnecessary disturbance of native eucalyptus woodland",
        ],
        "mechanical_control_methods": [
            "Use fine-mesh screening to protect vulnerable young trees",
            "Prune and dispose of severely damaged twigs",
            "Inspect trunks for emerging adults and shed nymphal skins",
            "Hand-remove adults from small nursery plants where practical",
        ],
        "chemical_control_options": None,
        "prevention": [
            "Monitor young trees during adult emergence",
            "Protect vulnerable nursery trees where necessary",
            "Maintain healthy tree growth",
            "Preserve natural predators",
            "Avoid unnecessary broad-spectrum insecticide applications",
        ],
        "monitoring": [
            "Listen for the distinctive male calling sound",
            "Inspect large eucalyptus trees for adult aggregations",
            "Look for clusters of empty nymphal skins near tree bases",
            "Check young twigs for egg-laying injury",
            "Record adult emergence and directly observed branch damage",
        ],
        "when_to_take_action": (
            "Take action only when repeated inspections confirm fresh "
            "egg-laying injuries or weakening of young branches. "
            "Adult emergence, loud calling and shed skins alone "
            "do not justify treatment."
        ),
        "safety_precautions": [
            "Wear gloves when pruning damaged branches",
            "Use appropriate eye protection and safe pruning equipment",
            "Do not climb tall trees to collect cicadas",
            "Avoid unnecessary pesticide applications",
            "Follow approved product labels if chemical treatment is independently justified",
        ],
        "expert_advice": (
            "Thopha saccata is native to eastern Australia. Adults "
            "commonly aggregate on large eucalyptus trees. Its loud "
            "chorus is produced by specialised male abdominal sound "
            "structures. Do not confuse it with Thopha sessiliba."
        ),
        "source_references": [],
    },
]


WHITE_DRUMMER_CICADA_ADVISORY_DATA = [
    {
        "pest_id": "white_drummer_cicada",
        "scientific_name": "Arunta perulata",
        "crop_id": None,
        "risk_level": "LOW",
        "status": "ADVISORY",
        "damage_notes": (
            "Australian distribution and ecological vegetation associations do not "
            "establish Indian occurrence or commercial crop hosts. General cicada root "
            "feeding and twig egg-laying are not confirmed economic damage by "
            "Arunta perulata. No chemical control is established."
        ),
        "identification_signs": [
            "Adult body length is approximately 40 mm.",
            "Males have white, sac-like tymbal covers.",
            "Females lack the male's enlarged tymbal covers.",
        ],
        "crop_damage": (
            "No significant species-specific commercial crop damage is established. "
            "Do not infer crop damage from adult presence, calling activity, general "
            "cicada root feeding, or twig egg-laying."
        ),
        "affected_plant_parts": [],
        "recommended_treatment": "No routine pest treatment is recommended.",
        "management": [
            "Identify the cicada before considering any control action.",
            "Monitor young woody plants only when actual injury is suspected.",
            "Inspect branches for genuine egg-laying wounds.",
            "Prune damaged twigs only when injury is confirmed and pruning is necessary.",
            "Use protective netting for vulnerable nursery plants if repeated injury is observed.",
            "Preserve natural predators and avoid unnecessary broad-spectrum insecticide use.",
            "Do not treat adult presence or calling activity as evidence of crop damage.",
        ],
        "chemical_control_options": None,
        "economic_threshold": None,
        "geographic_qualification": (
            "Australian records extend from Cooktown, Queensland, to Narooma, "
            "New South Wales, including far northern Cape York; the range may be "
            "broader. Indian occurrence is not established."
        ),
    }
]


GIANT_CICADA_ADVISORY_DATA = [
    {
        "pest_id": "giant_cicada",
        "crop_id": None,
        "status": "ADVISORY",
        "risk_level": "HIGH",
        "title": "Monitor underground nymph infestation",
        "geographic_scope": "Brazilian coffee plantations",
        "crop_context": [
            "Coffee (Coffea spp.): documented major pest association in Brazil",
            "Cocoa and avocado: reported host associations in the Americas",
        ],
        "damage_notes": (
            "Underground nymphs feed on root sap. Heavy infestations "
            "in Brazilian coffee plantations are associated with "
            "chlorosis, premature leaf loss, reduced growth and "
            "production, and sometimes plant death. This is not "
            "evidence of established damage in Indian plantations."
        ),
        "affected_parts": [
            "Main roots",
            "Thick lateral roots",
            "Underground root system",
        ],
        "management": [
            "Inspect declining plants for yellowing and premature leaf loss.",
            "Examine the root zone and soil for nymphs.",
            "Use soil trenches or other suitable sampling to estimate infestation.",
            "Record adult emergence and calling activity as supplementary evidence.",
            "Do not diagnose root infestation from adult detection alone.",
            "Consult a local agricultural specialist before treatment.",
            "Avoid moving potentially infested soil between fields.",
        ],
        "biological_control": [
            "Natural predators may attack eggs, nymphs and adults.",
            "No universally established commercial biological-control agent is confirmed.",
        ],
        "chemical_control_options": None,
        "economic_threshold": None,
        "geographic_qualification": (
            "Brazilian coffee damage evidence. Indian occurrence and "
            "Indian crop-specific treatment are unconfirmed."
        ),
        "source_refs": [
            "https://www.scielo.br/j/pab/a/PHTBrQCBk4Sh7Qj9cxXCvQt/",
            "https://repositorio.unesp.br/entities/publication/54cddc45-d577-4947-a993-dec5dac66188",
            "https://www.researchgate.net/publication/262738902_Description_of_the_nymphs_of_Quesada_gigas_Olivier_Hemiptera_Cicadidae_associated_with_coffee_plants",
        ],
    }
]


FLOURY_BAKER_CICADA_ADVISORY_DATA = [
    {
        "pest_id": "floury_baker_cicada",
        "crop_id": None,
        "status": "ADVISORY",
        "risk_level": "LOW",
        "title": "Monitor tree health and cicada activity",
        "damage_notes": (
            "No widespread commercial crop damage is established. "
            "An Australian Museum taxonomic study reports localised "
            "egg-laying damage to branches of fruit and nut trees in "
            "an Australian orchard. This observation must not be "
            "generalised to Indian crops."
        ),
        "management": [
            "Inspect trees for actual branch injury rather than relying on cicada presence.",
            "Record adult activity, emergence and shed nymphal skins.",
            "Monitor branches and young growth for egg-laying scars.",
            "Remove or manage damaged plant tissue only when necessary.",
            "Preserve natural predators and avoid unnecessary insecticide use.",
            "Seek expert identification if unusual tree decline occurs.",
        ],
        "biological_control": [
            "Birds and cicada-killer wasps are reported natural predators.",
            "No dedicated commercial biological-control agent is established.",
        ],
        "chemical_control_options": None,
        "economic_threshold": None,
        "geographic_qualification": (
            "Native to eastern Australia. Australian orchard observations "
            "are not evidence of Indian crop damage."
        ),
        "source_refs": [
            "https://journals.australian.museum/media/Uploads/Journals/17962/1386_complete.pdf"
        ],
    },
]


KAEMPFER_CICADA_ADVISORY_DATA = [
    {
        "pest_id": "kaempfer_cicada",
        "crop_id": None,
        "status": "ADVISORY",
        "risk_level": "LOW",
        "title": "Monitor cicada activity and actual tree injury",
        "damage_notes": (
            "No significant commercial crop damage is established. "
            "Tree-host associations and orchard observations do not "
            "automatically establish economically important injury."
        ),
        "management": [
            "Confirm the cicada's identity.",
            "Record adult activity and emergence.",
            "Inspect trees for measurable injury.",
            "Monitor tree health if unexplained decline occurs.",
            "Do not attribute root damage to the cicada without evidence.",
            "Avoid unnecessary pesticide applications.",
        ],
        "biological_control": [
            "Birds, spiders and predatory insects may naturally prey on cicadas.",
            "No species-specific commercial biological-control agent is established.",
        ],
        "chemical_control_options": None,
        "economic_threshold": None,
        "geographic_qualification": (
            "East Asian species. Chinese and Japanese host/orchard "
            "observations do not establish Indian crop damage."
        ),
        "source_refs": [
            "https://www.gbif.org/taxon/CL3M3",
            "https://pmc.ncbi.nlm.nih.gov/articles/PMC4137304/",
            "https://pmc.ncbi.nlm.nih.gov/articles/PMC9892791/",
            "https://www.jstage.jst.go.jp/article/jjaez1957/24/2/24_2_108/_pdf",
        ],
    }
]


LARGE_BROWN_CICADA_ADVISORY_DATA = [
    {
        "pest_id": "large_brown_cicada",
        "crop_id": None,
        "status": "ADVISORY",
        "risk_level": "MEDIUM",
        "title": "Monitor fruit injury and cicada activity",
        "damage_notes": (
            "Japanese research documented sucking injury to apple "
            "fruits by this cicada. Damage was localised and associated "
            "with particular orchard conditions. This does not establish "
            "widespread crop losses or Indian crop damage."
        ),
        "management": [
            "Confirm the species before attributing fruit injury to it.",
            "Inspect apple fruits for fresh sucking injury where relevant.",
            "Check upper tree canopies during adult activity.",
            "Inspect woody branches for egg-laying marks.",
            "Record adult activity separately from confirmed fruit injury.",
            "Prune damaged branches only when necessary.",
            "Avoid unnecessary insecticide applications.",
        ],
        "biological_control": [
            "Ant predation on eggs and newly hatched nymphs has been documented.",
            "Birds and other predators may also consume cicadas.",
            "No dedicated commercial biological-control agent is established.",
        ],
        "chemical_control_options": None,
        "economic_threshold": None,
        "geographic_qualification": (
            "Apple fruit injury documented in Japan. White pine was "
            "reported as an introduction pathway in Slovakia. Indian "
            "occurrence and Indian crop damage are unconfirmed."
        ),
        "source_refs": [
            "https://www.jstage.jst.go.jp/article/kitanihon1966/1984/35/1984_35_140/_article/-char/ja",
            "https://journals.savba.sk/index.php/fo/article/view/7645",
            "https://zenodo.org/records/10497591",
            "https://gd.eppo.int/taxon/GRAOCO",
        ],
    }
]


MEDITERRANEAN_WART_BITER_ADVISORY_DATA = [
    {
        "pest_id": "mediterranean_wart_biter",
        "status": "ADVISORY",
        "risk_level": "MEDIUM",
        "crop_id": None,
        "chemical_control_options": None,
        "management": {
            "monitoring": [
                "Inspect foliage and cereal ears for fresh feeding injury.",
                "Check dry grassland and field margins for adults.",
                "Use sweep-net sampling to assess population levels.",
                "Record insect abundance separately from crop injury.",
            ],
            "mechanical_control": [
                "Hand-collect individuals in small affected areas.",
                "Use physical protection for vulnerable seedlings where practical.",
            ],
            "cultural_control": [
                "Monitor fallow areas and field margins.",
                "Manage excessive weed growth where it is confirmed to provide shelter.",
                "Preserve natural predators and avoid unnecessary habitat destruction.",
            ],
            "biological_control": [
                "Conserve birds, spiders and predatory insects.",
                "No species-specific commercial biological-control agent is established.",
            ],
            "prevention": [
                "Inspect crops and field margins regularly.",
                "Monitor cereal ears and foliage during crop development.",
                "Avoid unnecessary pesticide application.",
            ],
        },
        "action_threshold": (
            "No validated economic threshold is available. "
            "Consider intervention only when repeated feeding causes "
            "measurable crop injury."
        ),
        "safety_notes": [
            "Wear gloves when collecting insects manually.",
            "Handle carefully because the insect may bite when provoked.",
        ],
        "notes": (
            "Crop-feeding observations are reported from Turkey for wheat, "
            "barley, maize, cotton, melon and forage crops, including cereal-ear "
            "injury and omnivorous feeding. These are regional observations, "
            "not confirmed Indian host records. Indian crop association and "
            "occurrence are not established. Confirm the insect and assess "
            "actual crop injury before intervention."
        ),
    }
]


NORTHERN_DUSK_SINGING_CICADA_ADVISORY_DATA = [
    {
        "pest_id": "northern_dusk_singing_cicada",
        "status": "ADVISORY",
        "risk_level": "LOW",
        "crop_id": None,
        "chemical_control_options": None,
        "management": {
            "monitoring": [
                "Listen for the characteristic low-pitched calling song around dusk.",
                "Inspect tree branches for adult cicadas.",
                "Look for shed nymphal skins attached to tree trunks.",
                "Record emergence activity and monitor actual tree injury.",
            ],
            "mechanical_control": [
                "Collect visible adults manually when practical.",
                "Prune damaged branches only when actual injury is confirmed.",
            ],
            "cultural_control": [
                "Maintain healthy trees and suitable growing conditions.",
                "Preserve natural predators.",
                "Avoid unnecessary disturbance of woodland vegetation.",
            ],
            "biological_control": [
                "Conserve birds, spiders and predatory insects.",
                "No species-specific commercial biological-control agent is established.",
            ],
            "prevention": [
                "Inspect woody plant material before moving it.",
                "Monitor unusual tree decline separately from normal cicada emergence.",
                "Avoid unnecessary insecticide applications.",
            ],
        },
        "action_threshold": (
            "No economic threshold is established. Investigate only when "
            "measurable plant injury occurs and evidence links it to this species."
        ),
        "notes": (
            "Primarily a North American woodland cicada associated with oak "
            "habitats. No confirmed commercial crop host or established Indian "
            "agricultural occurrence is recorded."
        ),
    }
]


NORTHERN_KATYDID_ADVISORY_DATA = [
    {
        "pest_id": "northern_katydid",
        "status": "ADVISORY",
        "risk_level": "LOW",
        "crop_id": None,
        "chemical_control_options": None,
        "management": {
            "monitoring": [
                "Listen for the characteristic repeated nighttime calling.",
                "Inspect tree canopies and leafy branches.",
                "Look for irregular leaf-chewing marks.",
                "Record adult and nymph numbers.",
                "Monitor the percentage of foliage affected.",
            ],
            "mechanical_control": [
                "Hand-collect visible insects where populations are small.",
                "Use sweep nets where vegetation height permits.",
                "Prune severely damaged portions only when necessary.",
            ],
            "cultural_control": [
                "Maintain healthy trees and shrubs.",
                "Monitor tree canopies during summer.",
                "Preserve natural predators.",
                "Avoid excessive pesticide use.",
            ],
            "biological_control": [
                "Conserve birds, spiders and predatory insects.",
                "No species-specific commercial biological-control agent is established.",
            ],
            "prevention": [
                "Inspect tree foliage during summer.",
                "Monitor unusually high katydid populations.",
                "Maintain healthy tree growth.",
                "Avoid unnecessary broad-spectrum insecticide application.",
            ],
        },
        "action_threshold": (
            "No validated economic threshold is established. "
            "Consider intervention only when unusually high populations "
            "cause substantial and continuing foliage loss."
        ),
        "notes": (
            "Primarily a North American tree-foliage-feeding katydid. "
            "Oak and other hardwood associations are ecological host records, "
            "not confirmed commercial crop associations. Indian agricultural "
            "occurrence is not established."
        ),
    }
]


NORTHERN_MOLE_CRICKET_ADVISORY_DATA = [
    {
        "pest_id": "northern_mole_cricket",
        "status": "ADVISORY",
        "risk_level": "LOW",
        "crop_id": None,
        "chemical_control_options": None,
        "management": {
            "monitoring": [
                "Look for raised tunnels in moist soil.",
                "Inspect the root zone of affected seedlings.",
                "Check damp grassland and marshy areas.",
                "Collect specimens for identification.",
                "Record population levels separately from actual plant damage.",
            ],
            "mechanical_control": [
                "Inspect and collect exposed crickets manually.",
                "Examine tunnels and nearby soil to confirm the insect's presence.",
                "Avoid damaging underground plant roots during inspection.",
            ],
            "cultural_control": [
                "Maintain suitable soil drainage.",
                "Monitor moist areas and field margins.",
                "Avoid excessive irrigation that creates persistently waterlogged soil.",
                "Protect vulnerable young seedlings where necessary.",
            ],
            "biological_control": [
                "Conserve birds, amphibians and predatory insects.",
                "Do not assume nematode or fungal treatments effective against other mole crickets will control this species.",
            ],
            "prevention": [
                "Maintain proper soil drainage.",
                "Inspect moist field margins.",
                "Monitor young plants for root disturbance.",
                "Preserve natural predators.",
                "Confirm the species before implementing pest control.",
            ],
        },
        "action_threshold": (
            "No validated economic threshold is available. Consider intervention "
            "only when confirmed tunnelling or feeding causes measurable seedling "
            "or root damage."
        ),
        "notes": (
            "Primarily a North American species associated with moist soil "
            "and grassland habitats. Tunnelling alone does not prove crop "
            "damage. Indian agricultural occurrence is not established."
        ),
    }
]


PERIODICAL_CICADA_ADVISORY_DATA = [
    {
        "pest_id": "periodical_cicada",
        "status": "ADVISORY",
        "risk_level": "MEDIUM",
        "crop_id": None,
        "chemical_control_options": None,
        "management": {
            "monitoring": [
                "Monitor local brood emergence forecasts.",
                "Look for emerging nymphs and shed skins on tree trunks.",
                "Listen for loud male calling choruses.",
                "Inspect small branches for fresh egg-laying slits.",
                "Record affected trees and the extent of twig flagging.",
            ],
            "mechanical_control": [
                "Protect vulnerable young trees with fine insect-proof netting.",
                "Install netting before adult females begin egg laying.",
                "Remove severely damaged twigs where appropriate.",
                "Inspect protected trees regularly.",
            ],
            "cultural_control": [
                "Delay planting vulnerable young fruit trees until after major emergence where practical.",
                "Maintain healthy tree growth.",
                "Avoid unnecessary stress to recently transplanted trees.",
                "Monitor tree recovery after emergence.",
            ],
            "biological_control": [
                "Preserve birds and other natural predators.",
                "Do not rely on predators to prevent injury during extremely large synchronized emergences.",
                "No reliable commercial biological-control agent is established for managing Magicicada broods.",
            ],
            "prevention": [
                "Identify expected brood emergence years in affected regions.",
                "Protect recently transplanted trees before emergence.",
                "Inspect branches after emergence for egg-laying injury.",
                "Monitor tree recovery after the infestation period.",
            ],
        },
        "action_threshold": (
            "No universal economic threshold is established. Preventive protection "
            "is most relevant for young trees during predicted mass emergence."
        ),
        "notes": (
            "North American periodical cicadas with 13-year or 17-year life cycles "
            "depending on species and brood. Female egg laying can injure small "
            "branches, particularly on young fruit trees. Indian agricultural "
            "occurrence is not established."
        ),
    }
]


PLAINS_CICADA_ADVISORY_DATA = [
    {
        "pest_id": "plains_cicada",
        "status": "ADVISORY",
        "risk_level": "LOW",
        "crop_id": None,
        "chemical_control_options": None,
        "management": {
            "monitoring": [
                "Listen for the characteristic repeated buzzing call.",
                "Look for adult cicadas on trees and shrubs.",
                "Inspect small branches for fresh egg-laying slits.",
                "Check for weakened or broken twig tips.",
            ],
            "mechanical_control": [
                "Prune severely damaged twigs when necessary.",
                "Use protective netting on small valuable plants during unusually high adult activity.",
                "Remove damaged branches appropriately.",
            ],
            "cultural_control": [
                "Maintain healthy trees and shrubs.",
                "Inspect young woody plants during the adult emergence season.",
                "Avoid unnecessary pesticide use that harms natural predators.",
            ],
            "biological_control": [
                "Preserve birds and other insect-eating natural predators.",
                "No reliable species-specific commercial biological-control agent is established.",
            ],
            "prevention": [
                "Monitor young trees and shrubs during cicada emergence.",
                "Protect nursery plants if egg-laying injury is observed.",
                "Maintain plant health and avoid unnecessary insecticide applications.",
            ],
        },
        "action_threshold": (
            "No validated economic threshold is established. Consider intervention "
            "only when repeated egg-laying wounds weaken valuable young plants or nursery stock."
        ),
        "notes": (
            "Primarily a North American cicada. Localized twig injury may occur through "
            "female egg laying, but significant commercial crop losses and Indian "
            "agricultural occurrence are not established."
        ),
    }
]


WALKERS_CICADA_ADVISORY_DATA = [
    {
        "pest_id": "walkers_cicada",
        "status": "ADVISORY",
        "risk_level": "LOW",
        "crop_id": None,
        "chemical_control_options": None,
        "management": {
            "monitoring": [
                "Observe adult cicada activity on nearby woody vegetation.",
                "Inspect young branches only if actual injury is suspected.",
                "Confirm the cicada identity before considering management.",
            ],
            "mechanical_control": [
                "Prune damaged twigs only when genuine injury is confirmed.",
            ],
            "cultural_control": [
                "Preserve riverside woodland habitats.",
                "Avoid unnecessary broad-spectrum insecticide applications.",
            ],
            "biological_control": [
                "Preserve natural predators.",
            ],
        },
        "action_threshold": None,
        "notes": (
            "No routine pest treatment is recommended. Cottonwood, willow, sycamore, "
            "and maple are ecological tree associations, not established commercial "
            "crop hosts. Indian occurrence, significant crop damage, and chemical "
            "treatment are not established. The proposed historical name Tibicen "
            "pronotalis walkeri remains NEEDS_REVIEW."
        ),
    }
]


RAZOR_GRINDER_CICADA_ADVISORY_DATA = [
    {
        "pest_id": "razor_grinder_cicada",
        "status": "ADVISORY",
        "risk_level": "LOW",
        "crop_id": None,
        "chemical_control_options": None,
        "management": {
            "monitoring": [
                "Listen for the loud, harsh buzzing call.",
                "Inspect tree trunks for resting adults.",
                "Check small branches for egg-laying slits.",
                "Look for weakened or broken twig tips.",
            ],
            "mechanical_control": [
                "Prune severely damaged twigs where appropriate.",
                "Use protective netting on small valuable plants if heavy activity causes injury.",
                "Remove damaged branches appropriately.",
            ],
            "cultural_control": [
                "Maintain healthy trees and shrubs.",
                "Preserve natural predators.",
                "Avoid unnecessary insecticide applications.",
            ],
            "biological_control": [
                "Conserve birds and other insect-eating natural predators.",
                "No species-specific commercial biological-control agent is established.",
            ],
            "prevention": [
                "Monitor young woody plants during adult emergence.",
                "Inspect branches for egg-laying injury.",
                "Maintain plant health and avoid unnecessary chemical treatments.",
            ],
        },
        "action_threshold": (
            "No validated economic threshold is established. Consider intervention "
            "only when actual injury to valuable young trees, shrubs or nursery plants is observed."
        ),
        "notes": (
            "Eastern Australian cicada. Loud calling and adult presence do not establish "
            "plant injury. Species-specific commercial crop damage and Indian agricultural "
            "occurrence are not established."
        ),
    }
]


RED_SQUEAKER_CICADA_ADVISORY_DATA = [
    {
        "pest_id": "red_squeaker_cicada",
        "status": "ADVISORY",
        "risk_level": "LOW",
        "crop_id": None,
        "chemical_control_options": None,
        "management": {
            "monitoring": [
                "Listen for the characteristic male calling sound.",
                "Observe adult cicadas on nearby vegetation.",
                "Inspect twigs for possible egg-laying marks.",
                "Check plants for unusual branch drying or breakage.",
            ],
            "mechanical_control": [
                "Prune severely damaged twigs only when necessary.",
                "Use protective netting on vulnerable nursery plants if actual injury occurs.",
                "Remove damaged plant material appropriately.",
            ],
            "cultural_control": [
                "Maintain healthy trees and shrubs.",
                "Preserve natural predators.",
                "Monitor young plants during periods of adult activity.",
            ],
            "biological_control": [
                "Conserve birds, spiders and other insect-eating predators.",
                "No species-specific commercial biological-control agent is established.",
            ],
            "prevention": [
                "Monitor young woody plants for actual injury.",
                "Maintain plant health.",
                "Avoid unnecessary broad-spectrum insecticide use.",
                "Confirm the insect species before applying pest-control treatment.",
            ],
        },
        "action_threshold": (
            "No validated economic threshold is established. Consider intervention "
            "only when actual plant injury is observed. Adult presence or calling "
            "activity alone does not justify treatment."
        ),
        "notes": (
            "Australian endemic cicada. No significant commercial crop damage or "
            "established Indian agricultural occurrence is confirmed. General cicada "
            "root feeding and egg laying should not be treated as verified "
            "species-specific crop damage."
        ),
    }
]


SHORT_WINGED_CONEHEAD_ADVISORY_DATA = [
    {
        "pest_id": "short_winged_conehead",
        "status": "ADVISORY",
        "risk_level": "LOW",
        "crop_id": None,
        "chemical_control_options": None,
        "management": {
            "monitoring": [
                "Inspect tall grasses, rushes and sedges.",
                "Listen for the faint ticking or hissing male call.",
                "Look for small green bush-crickets with short wings.",
                "Check seed heads, buds and flowers for feeding injury.",
            ],
            "mechanical_control": [
                "Hand-collect individuals from small protected growing areas if necessary.",
                "Remove heavily damaged plant material only when justified.",
                "Use insect-proof netting on vulnerable plants if actual damage is observed.",
            ],
            "cultural_control": [
                "Maintain healthy cultivated plants.",
                "Avoid excessive disturbance of natural wetland vegetation.",
                "Preserve habitats supporting natural predators.",
            ],
            "biological_control": [
                "Conserve birds, spiders and predatory insects.",
                "No species-specific commercial biological-control agent is established.",
            ],
            "prevention": [
                "Monitor cultivated plants near wetland habitats.",
                "Maintain healthy vegetation.",
                "Preserve natural predators.",
                "Avoid unnecessary pesticide use.",
            ],
        },
        "action_threshold": (
            "No validated economic threshold is established. Consider intervention "
            "only when measurable feeding injury occurs on cultivated plants."
        ),
        "notes": (
            "Primarily a European wetland-associated bush-cricket. Grass, rush and sedge "
            "feeding does not establish commercial crop damage. Indian agricultural "
            "occurrence is not confirmed."
        ),
    }
]


SILVER_CICADA_ADVISORY_DATA = [
    {
        "pest_id": "silver_cicada",
        "status": "ADVISORY",
        "risk_level": "LOW",
        "crop_id": None,
        "chemical_control_options": None,
        "management": {
            "monitoring": [
                "Monitor plants for confirmed physical injury.",
                "Inspect young branches for possible egg-laying marks.",
                "Seek expert identification before treating an unfamiliar cicada.",
            ],
            "mechanical_control": [
                "Prune damaged twigs only when injury is confirmed.",
            ],
            "biological_control": [
                "Preserve natural predators.",
            ],
            "prevention": [
                "Avoid unnecessary insecticide use.",
                "Confirm the cicada species before considering treatment.",
            ],
        },
        "action_threshold": (
            "No crop-specific action threshold is established. Use general monitoring "
            "and consider action only after confirming physical injury."
        ),
        "notes": (
            "European cicada associated with grassland, scrub, garrigue, and open woodland. "
            "Indian occurrence, commercial crop hosts, and crop damage are not established. "
            "No Indian pesticide recommendation is supported."
        ),
    }
]


SILVER_PRINCESS_CICADA_ADVISORY_DATA = [
    {
        "pest_id": "silver_princess_cicada",
        "status": "ADVISORY",
        "risk_level": "LOW",
        "crop_id": None,
        "chemical_control_options": None,
        "management": {
            "monitoring": [
                "No routine pest control is necessary when plants remain healthy.",
                "Observe cicada activity on tea trees and paperbarks.",
                "Inspect plants only when actual injury is suspected.",
                "Confirm the species identification before considering management.",
            ],
            "mechanical_control": [
                "Prune branches only when genuine damage is confirmed.",
            ],
            "biological_control": [
                "Preserve natural predators.",
            ],
            "prevention": [
                "Avoid unnecessary insecticide use.",
                "Confirm actual injury and species before taking action.",
            ],
        },
        "action_threshold": (
            "No crop-specific action threshold is established. Do not intervene "
            "when plants remain healthy; assess confirmed injury before considering "
            "any management."
        ),
        "notes": (
            "Southeastern Australian cicada associated with Leptospermum spp. and "
            "Melaleuca spp. as ecological vegetation. Commercial crop hosts, crop "
            "damage, affected crop parts, and Indian occurrence are not established. "
            "No Indian chemical recommendation is supported."
        ),
    }
]


ZIPPING_AMBERTAIL_ADVISORY_DATA = [
    {
        "pest_id": "zipping_ambertail",
        "scientific_name": "Yoyetta repetens",
        "risk_level": "LOW",
        "status": "ADVISORY",
        "crop_id": None,
        "chemical_control_options": None,
        "management": [
            "No routine agricultural pest treatment is required.",
            "Identify the cicada before considering any control action.",
            "Do not interpret adult presence or calling activity as crop damage.",
            "Monitor woody plants only if actual injury is suspected.",
            "Inspect branches for genuine egg-laying wounds when injury is observed.",
            "Prune damaged twigs only when necessary and after confirming injury.",
            "Preserve native eucalyptus vegetation and natural predators.",
            "Avoid unnecessary broad-spectrum insecticide applications.",
        ],
        "economic_threshold": None,
        "geographic_qualification": (
            "Australian cicada associated with Grey Box and eucalyptus vegetation. "
            "These are ecological associations, not commercial crop hosts; Indian "
            "occurrence and crop damage are not established."
        ),
    }
]


SOUTHERN_BARK_SQUEAKER_ADVISORY_DATA = [
    {
        "pest_id": "southern_bark_squeaker",
        "scientific_name": "Atrapsalta corticina",
        "crop_id": None,
        "risk_level": "LOW",
        "status": "ADVISORY",
        "chemical_control_options": None,
        "management": {
            "monitoring": [
                "No routine pest treatment is recommended.",
                "Observe cicada activity on woody vegetation.",
                "Inspect twigs only when actual plant injury is suspected.",
                "Use photographs and calling recordings to support expert identification.",
            ],
            "mechanical_control": [
                "Prune damaged twigs only when injury is confirmed.",
            ],
            "biological_control": [
                "Preserve natural predators.",
            ],
            "prevention": [
                "Avoid unnecessary insecticide use.",
                "Confirm the species before considering management.",
            ],
        },
        "action_threshold": (
            "No crop-specific action threshold is established. Use general monitoring "
            "and consider action only after confirming actual plant injury."
        ),
        "notes": (
            "Australian cicada associated with woodland and woody vegetation. The common name "
            "Bark Squeaker is also used in some sources, and some records identify only "
            "Atrapsalta sp. near A. corticina; neither usage confirms this species. Indian "
            "occurrence, commercial crop hosts, and crop damage are not established. No Indian "
            "chemical recommendation is supported."
        ),
    }
]


SOUTHERN_RED_EYED_SQUEAKER_ADVISORY_DATA = [
    {
        "pest_id": "southern_red_eyed_squeaker",
        "scientific_name": "Popplepsalta notialis notialis",
        "crop_id": None,
        "risk_level": "LOW",
        "status": "ADVISORY",
        "chemical_control_options": None,
        "management": {
            "monitoring": [
                "No routine pest treatment is recommended.",
                "Observe adult cicada activity on nearby vegetation.",
                "Use photographs and calling recordings to support identification.",
                "Inspect branches only if actual plant injury is suspected.",
            ],
            "mechanical_control": [
                "Prune damaged twigs only when genuine injury is confirmed.",
            ],
            "biological_control": [
                "Preserve natural predators.",
            ],
            "prevention": [
                "Avoid unnecessary insecticide applications.",
                "Confirm the species before considering management.",
            ],
        },
        "action_threshold": (
            "No crop-specific action threshold is established. Use general monitoring "
            "and consider action only after confirming actual plant injury."
        ),
        "notes": (
            "Australian subspecies Popplepsalta notialis notialis; the parent species and "
            "Popplepsalta notialis incitata remain distinct. Commercial crop hosts, crop damage, "
            "and Indian occurrence are not established. No Indian chemical recommendation is supported."
        ),
    }
]


SWAMP_CICADA_ADVISORY_DATA = [
    {
        "pest_id": "swamp_cicada",
        "scientific_name": "Neotibicen tibicen",
        "crop_id": None,
        "risk_level": "LOW",
        "status": "ADVISORY",
        "chemical_control_options": None,
        "management": {
            "monitoring": [
                "Use general monitoring; no routine pest treatment is recommended.",
                "Observe cicada activity in wetlands, marshes, meadows and overgrown fields.",
                "Inspect plants only when actual injury is suspected.",
                "Confirm species identification before attributing plant damage.",
            ],
            "mechanical_control": [
                "Prune or remove plant material only when genuine injury is confirmed.",
            ],
            "prevention": [
                "Avoid unnecessary insecticide use.",
                "Record cicada activity separately from confirmed plant injury.",
            ],
        },
        "action_threshold": (
            "No crop-specific action threshold is established. Consider management "
            "only after confirming actual plant injury."
        ),
        "notes": (
            "North American species associated with wetlands, marshes, meadows and overgrown fields. "
            "The recognized subspecies are Neotibicen tibicen tibicen and N. t. australis; Southern "
            "Swamp Cicada refers to N. t. australis. Commercial crop hosts, crop damage, and Indian "
            "occurrence are not established. No Indian pesticide recommendation is supported."
        ),
    }
]


def validate_solution_records(records):
    seen = set()

    for item in records:
        identity = (item["pest_id"], item["crop_id"])

        if identity in seen:
            raise ValueError(f"Duplicate pest-crop solution: {identity}")

        seen.add(identity)

        if item["risk_level"] not in {"HIGH", "MEDIUM", "LOW"}:
            raise ValueError(f"Unsupported risk level: {item['risk_level']}")

        if item.get("crop_id") is None:
            potential_hosts = item.get("potential_host_crops")
            if (
                item["status"] != "NEEDS_REVIEW"
                or not isinstance(potential_hosts, list)
                or not potential_hosts
                or any(not isinstance(host, dict) for host in potential_hosts)
            ):
                raise ValueError(
                    f"Missing potential hosts for multi-host candidate: {item['pest_id']}"
                )
            potential_host_ids = [
                host.get("crop_id") for host in potential_hosts
            ]
            if (
                any(not crop_id for crop_id in potential_host_ids)
                or len(potential_host_ids) != len(set(potential_host_ids))
                or any(not host.get("crop_name") for host in potential_hosts)
            ):
                raise ValueError(
                    f"Invalid potential hosts for multi-host candidate: {item['pest_id']}"
                )

        if item["status"] == "VERIFIED":
            if not item.get("scientific_name"):
                raise ValueError(f"Missing scientific name: {item['pest_id']}")

            if not item.get("source_references"):
                raise ValueError(f"Missing sources: {item['pest_id']}")

    return True


validate_solution_records(SOLUTION_RECORDS)

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

    solution = _SOLUTION_BY_IDENTITY.get(
        (pest_id, row.get("crop_id") or "")
    )
    if solution is None:
        solution = _SOLUTION_BY_IDENTITY.get((pest_id, None))
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
        "potential_host_crops": (
            solution.get("potential_host_crops", [])
            if solution
            else []
        ),
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