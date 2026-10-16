PEST_DATA = [
    {
        "pest_id": "rice_planthopper",
        "name": "Rice Planthopper",
        "scientific_name": "Nilaparvata lugens",
        "risk": "HIGH",
        "description": (
            "A common rice pest that feeds on plant sap and can cause "
            "yellowing, drying and serious crop damage."
        ),
        "symptoms": (
            "Yellowing of rice plants, drying patches and reduced plant growth."
        ),
    },
    {
        "pest_id": "rice_leaf_folder",
        "name": "Rice Leaf Folder",
        "scientific_name": "Cnaphalocrocis medinalis",
        "risk": "MEDIUM",
        "description": (
            "A rice pest whose larvae fold and feed inside leaves, "
            "reducing the effective leaf area."
        ),
        "symptoms": (
            "Folded leaves, scraped leaf surfaces and damaged green tissue."
        ),
    },
    {
        "pest_id": "brown_plant_hopper",
        "name": "Brown Planthopper",
        "scientific_name": "Nilaparvata lugens",
        "risk": "HIGH",
        "description": (
            "A sap-sucking rice pest that can rapidly damage plants "
            "under favorable conditions."
        ),
        "symptoms": (
            "Yellowing plants, hopper burn and patches of dried rice plants."
        ),
    },
    {
        "pest_id": "stem_borer",
        "name": "Rice Stem Borer",
        "scientific_name": "Scirpophaga incertulas",
        "risk": "HIGH",
        "description": (
            "A destructive rice pest whose larvae bore into plant stems "
            "and interfere with plant growth."
        ),
        "symptoms": (
            "Dead hearts in young plants and white heads during later growth."
        ),
    },
    {
        "pest_id": "armyworm",
        "name": "Armyworm",
        "scientific_name": "Spodoptera spp.",
        "risk": "HIGH",
        "description": (
            "Leaf-feeding caterpillars that can consume large amounts "
            "of crop foliage."
        ),
        "symptoms": (
            "Irregular holes, damaged leaves and rapid loss of foliage."
        ),
    },
    {
        "pest_id": "fall_armyworm",
        "name": "Fall Armyworm",
        "scientific_name": "Spodoptera frugiperda",
        "risk": "HIGH",
        "description": (
            "A serious crop pest that commonly attacks maize and other crops."
        ),
        "symptoms": (
            "Leaf holes, windowing, ragged foliage and caterpillar feeding damage."
        ),
    },
    {
        "pest_id": "aphid",
        "name": "Aphid",
        "scientific_name": "Aphididae",
        "risk": "MEDIUM",
        "description": (
            "Small sap-sucking insects that can weaken plants and affect "
            "new leaves and shoots."
        ),
        "symptoms": (
            "Curling leaves, sticky honeydew and weak or distorted new growth."
        ),
    },
    # Model class: Cicada
    {
        "pest_id": "cicada",
        "name": "Cicada",
        "scientific_name": "Cicada",
        "risk": "LOW",
        "description": "Cicadas feed on plant fluids. Their effect on crops varies by species.",
        "symptoms": "Check for twig injury, sap-feeding signs, and egg-laying scars.",
    },
    {
        "pest_id": "common_field_grasshopper",
        "name": "Common Field Grasshopper",
        "scientific_name": "Acrididae spp.",
        "risk": "MEDIUM",
        "description": "Grasshoppers can feed on leaves and other plant material. Impact varies by species and population.",
        "symptoms": "Chewed leaf margins, holes in leaves, and loss of foliage.",
    },
    {
        "pest_id": "desert_locust",
        "name": "Desert Locust",
        "scientific_name": "Schistocerca gregaria",
        "risk": "HIGH",
        "description": "A major migratory locust pest capable of causing extensive crop and vegetation damage during outbreaks.",
        "symptoms": "Rapid foliage loss, extensive chewing damage, and large locust aggregations.",
    },
    {
        "pest_id": "dog_day_cicada",
        "name": "Dog-day Cicada",
        "scientific_name": "Dog-day Cicada",
        "risk": "LOW",
        "description": "A cicada group whose effects vary by species and location; not every detection indicates crop damage.",
        "symptoms": "Look for twig injury or egg-laying scars and verify the species before assigning crop damage.",
    },
    {
        "pest_id": "field_crickt",
        "name": "Field Cricket",
        "scientific_name": "Gryllus campestris",
        "risk": "LOW",
        "description": "Field crickets are ground-dwelling insects. Crop impacts depend on the species, crop, and population.",
        "symptoms": "Inspect seedlings and nearby plant material for chewing damage.",
    },
    {
        "pest_id": "fruite_fly",
        "name": "Fruit Fly",
        "scientific_name": "Fruit Fly",
        "risk": "MEDIUM",
        "description": "Some fruit fly species damage fruit. The exact species is needed for reliable crop-specific advice.",
        "symptoms": "Inspect fruit for puncture marks, softening, internal larvae, and premature decay.",
    },
    {
        "pest_id": "grasshopper",
        "name": "Grasshopper",
        "scientific_name": "Acrididae spp.",
        "risk": "MEDIUM",
        "description": "Grasshoppers can feed on crop foliage, with damage depending on species and population density.",
        "symptoms": "Chewed leaf edges, missing foliage, and increasing defoliation.",
    },
    {
        "pest_id": "great_green_bush_cricket",
        "name": "Great Green Bush-cricket",
        "scientific_name": "Tettigonia viridissima",
        "risk": "LOW",
        "description": "A large bush-cricket that may feed on plant material and other small animals.",
        "symptoms": "Check for actual chewing injury on foliage before treating it as a crop pest.",
    },
    {
        "pest_id": "house_cricket",
        "name": "House Cricket",
        "scientific_name": "Acheta domesticus",
        "risk": "LOW",
        "description": "House crickets are generally associated with buildings and stored materials; field risk needs local verification.",
        "symptoms": "Inspect nearby seedlings or stored materials for chewing damage.",
    },
    {
        "pest_id": "katydid",
        "name": "Katydid",
        "scientific_name": "Katydid",
        "risk": "MEDIUM",
        "description": "Katydids generally cause limited damage, although some species and high populations can damage foliage or fruit.",
        "symptoms": "Check leaf edges for chewing and fruit for shallow scars or distorted growth.",
    },
    {
        "pest_id": "migratory_locust",
        "name": "Migratory Locust",
        "scientific_name": "Locusta migratoria",
        "risk": "HIGH",
        "description": "A migratory locust species that can cause substantial vegetation damage when populations build up.",
        "symptoms": "Look for extensive foliage loss and concentrated locust activity.",
    },
    {
        "pest_id": "mole_cricket",
        "name": "Mole Cricket",
        "scientific_name": "Gryllotalpidae spp.",
        "risk": "MEDIUM",
        "description": "Mole crickets live in soil and some species damage roots, seeds, or young plants.",
        "symptoms": "Inspect for disturbed soil, weakened seedlings, and root damage.",
    },
    {
        "pest_id": "rhinoceros_beetle",
        "name": "Rhinoceros Beetle",
        "scientific_name": "Oryctes rhinoceros",
        "risk": "HIGH",
        "description": "The coconut rhinoceros beetle is a significant palm pest. Confirm the species and host crop.",
        "symptoms": "On palms, check for V-shaped cuts on opened fronds and holes near the crown.",
    },
    {
        "pest_id": "roesels_bush_cricket",
        "name": "Roesel's Bush-cricket",
        "scientific_name": "Roeseliana roeselii",
        "risk": "LOW",
        "description": "A bush-cricket species whose presence alone does not establish economically significant crop damage.",
        "symptoms": "Check for visible feeding injury and identify the species locally.",
    },
    {
        "pest_id": "short_horned_grasshopper",
        "name": "Short-horned Grasshopper",
        "scientific_name": "Caelifera",
        "risk": "MEDIUM",
        "description": "Short-horned grasshoppers include species that feed on vegetation and may damage crops.",
        "symptoms": "Chewed foliage, damaged leaf margins, and increasing plant defoliation.",
    },
    {
        "pest_id": "snowy_tree_cricket",
        "name": "Snowy Tree Cricket",
        "scientific_name": "Oecanthus fultoni",
        "risk": "LOW",
        "description": "A tree cricket; crop significance should be judged from species confirmation and observed damage.",
        "symptoms": "Record the insect and inspect nearby plants for visible feeding injury.",
    },
    {
        "pest_id": "swamp_cicada",
        "name": "Swamp Cicada",
        "scientific_name": "Swamp Cicada",
        "risk": "LOW",
        "description": "A cicada class whose specific ecological and agricultural effects need species-level confirmation.",
        "symptoms": "Check for twig injury or egg-laying scars and verify the species.",
    },
    {
        "pest_id": "tree_cricket",
        "name": "Tree Cricket",
        "scientific_name": "Oecanthus spp.",
        "risk": "LOW",
        "description": "Tree crickets are a group of insects whose agricultural significance varies by species.",
        "symptoms": "Check for observable feeding injury rather than relying on sound alone.",
    },
    {
        "pest_id": "two_spotted_cricket",
        "name": "Two-spotted Cricket",
        "scientific_name": "Gryllus bimaculatus",
        "risk": "LOW",
        "description": "An omnivorous cricket whose crop impact depends on the local environment and food availability.",
        "symptoms": "Inspect seedlings and plant material for actual chewing injury.",
    },
    {
        "pest_id": "termite",
        "name": "Termite",
        "scientific_name": "Termitoidae",
        "risk": "MEDIUM",
        "description": "Termites feed on cellulose-rich material, and some species damage living plants or crops.",
        "symptoms": "Check for damaged stems or roots, galleries, and mud tubes where applicable.",
    },
]


SOLUTION_DATA = [
    {
        "pest_id": "cicada",
        "title": "Cicada Monitoring and Prevention",
        "description": "Cicada detections do not always indicate crop damage. Inspect the affected plants first.",
        "recommended_action": "Inspect twigs and branches for egg-laying scars or injury. Record the affected plants and seek local advice if damage is significant.",
        "prevention": "Monitor young plants, maintain plant health, and remove damaged material where appropriate.",
    },
    {
        "pest_id": "common_field_grasshopper",
        "title": "Common Field Grasshopper Management",
        "description": "Grasshopper feeding can damage foliage, especially when populations increase.",
        "recommended_action": "Inspect leaves for chewing damage. Monitor affected areas and protect young plants using crop-appropriate physical or integrated pest-management methods.",
        "prevention": "Monitor field margins and young crops regularly. Record changes in grasshopper numbers and crop damage.",
    },
    {
        "pest_id": "desert_locust",
        "title": "Desert Locust Monitoring",
        "description": "Desert locust outbreaks can cause extensive crop damage.",
        "recommended_action": "Record the location, approximate numbers, and affected crops. Report suspected outbreaks to the local agricultural authority. Do not attempt large-scale control without trained guidance.",
        "prevention": "Monitor crops and field margins, keep records of sightings, and follow official locust advisories.",
    },
    {
        "pest_id": "dog_day_cicada",
        "title": "Dog-day Cicada Monitoring",
        "description": "Confirm the cicada species and check for actual plant injury before taking action.",
        "recommended_action": "Inspect branches and twigs for damage. If significant injury is present, document it and seek local agricultural advice.",
        "prevention": "Monitor susceptible plants and maintain regular inspections during periods of insect activity.",
    },
    {
        "pest_id": "field_crickt",
        "title": "Field Cricket Management",
        "description": "Some field crickets may feed on seedlings or plant material.",
        "recommended_action": "Inspect seedlings and nearby soil for chewing damage. Confirm that crickets are responsible before choosing a control method.",
        "prevention": "Keep crop areas monitored, manage suitable hiding places where practical, and check seedlings regularly.",
    },
    {
        "pest_id": "fruite_fly",
        "title": "Fruit Fly Monitoring and Prevention",
        "description": "Some fruit flies lay eggs in fruit, where developing larvae can cause damage.",
        "recommended_action": "Inspect fruit for punctures, decay, or larvae. Remove and dispose of affected fruit appropriately, and use locally recommended monitoring methods for the confirmed species.",
        "prevention": "Collect fallen and damaged fruit regularly, maintain orchard sanitation, and follow local fruit-fly monitoring guidance.",
    },
    {
        "pest_id": "grasshopper",
        "title": "Grasshopper Management",
        "description": "Grasshoppers can feed on crop foliage and cause greater damage during population outbreaks.",
        "recommended_action": "Inspect the crop for fresh chewing damage and monitor affected areas. Protect vulnerable young plants with suitable integrated pest-management measures.",
        "prevention": "Inspect field edges and seedlings regularly, monitor population changes, and maintain crop records.",
    },
    {
        "pest_id": "great_green_bush_cricket",
        "title": "Great Green Bush-cricket Monitoring",
        "description": "Presence alone does not prove economically important crop damage.",
        "recommended_action": "Observe the insect and check nearby plants for feeding injury. Avoid unnecessary control when no meaningful damage is present.",
        "prevention": "Maintain plant monitoring and use species identification and observed damage to guide decisions.",
    },
    {
        "pest_id": "house_cricket",
        "title": "House Cricket Monitoring",
        "description": "House crickets are often associated with buildings and stored materials. Field damage needs confirmation.",
        "recommended_action": "Check seedlings, stored materials, and surrounding areas for actual damage. Remove accessible shelter and food sources when appropriate.",
        "prevention": "Keep storage areas clean, seal unnecessary entry points, and inspect susceptible materials.",
    },
    {
        "pest_id": "katydid",
        "title": "Katydid Monitoring and Management",
        "description": "Some katydids feed on leaves or fruit, but their impact varies by species and crop.",
        "recommended_action": "Inspect leaves and fruit for fresh chewing damage or scars. Monitor the affected plants and seek local advice if damage continues.",
        "prevention": "Check susceptible plants regularly, record damage, and avoid unnecessary insect control when no significant injury is found.",
    },
    {
        "pest_id": "migratory_locust",
        "title": "Migratory Locust Monitoring",
        "description": "Large migratory locust populations can damage vegetation and crops.",
        "recommended_action": "Record the location, crop affected, and observed numbers. Report suspected outbreaks to the local agricultural authority and follow official guidance.",
        "prevention": "Monitor crop edges and surrounding vegetation, and maintain records of sightings and crop damage.",
    },
    {
        "pest_id": "mole_cricket",
        "title": "Mole Cricket Management",
        "description": "Some mole cricket species damage roots, seeds, or young plants below the soil surface.",
        "recommended_action": "Inspect weakened seedlings and soil for tunnels or root injury. Confirm the responsible species before selecting a control method.",
        "prevention": "Monitor seedlings and soil conditions, use healthy planting material, and follow crop-specific local advice.",
    },
    {
        "pest_id": "rhinoceros_beetle",
        "title": "Rhinoceros Beetle Management",
        "description": "Certain rhinoceros beetles, including the coconut rhinoceros beetle, can seriously damage palms.",
        "recommended_action": "For suspected palm attacks, inspect the crown and fronds for characteristic cuts or holes. Confirm the species and contact a local agricultural extension service for appropriate management.",
        "prevention": "Inspect susceptible palms regularly and follow locally recommended sanitation and monitoring practices.",
    },
    {
        "pest_id": "roesels_bush_cricket",
        "title": "Roesel's Bush-cricket Monitoring",
        "description": "A sighting does not establish that the insect is causing economically significant crop damage.",
        "recommended_action": "Inspect nearby plants for feeding injury and confirm identification. Take control measures only when justified by observed damage and local guidance.",
        "prevention": "Monitor affected plants and keep records of insect sightings and changes in crop condition.",
    },
    {
        "pest_id": "short_horned_grasshopper",
        "title": "Short-horned Grasshopper Management",
        "description": "Some short-horned grasshoppers can damage crop foliage.",
        "recommended_action": "Inspect leaves for chewing and monitor population levels. Use crop-appropriate integrated pest-management measures when damage warrants action.",
        "prevention": "Check field margins and young crops frequently and document changes in foliage damage.",
    },
    {
        "pest_id": "snowy_tree_cricket",
        "title": "Snowy Tree Cricket Monitoring",
        "description": "Confirm the species and assess visible plant injury before treating the detection as a crop threat.",
        "recommended_action": "Record the insect and inspect nearby vegetation. If sustained damage is observed, seek advice suited to the crop and location.",
        "prevention": "Maintain regular plant inspections and avoid unnecessary control when no significant damage is evident.",
    },
    {
        "pest_id": "swamp_cicada",
        "title": "Swamp Cicada Monitoring",
        "description": "The agricultural significance of this cicada class requires confirmation of the species and observed damage.",
        "recommended_action": "Inspect twigs and branches for injury. Document any damage and seek local identification advice if symptoms persist.",
        "prevention": "Monitor susceptible plants and record insect activity and any changes in plant condition.",
    },
    {
        "pest_id": "tree_cricket",
        "title": "Tree Cricket Monitoring",
        "description": "Tree crickets should be assessed using species identification and actual crop damage.",
        "recommended_action": "Inspect nearby plants for feeding injury and observe whether damage is increasing. Avoid pest-specific treatment until the cause is confirmed.",
        "prevention": "Monitor plants and maintain records of insect activity and symptoms.",
    },
    {
        "pest_id": "two_spotted_cricket",
        "title": "Two-spotted Cricket Monitoring",
        "description": "The effect of this cricket on crops depends on local conditions and observed feeding damage.",
        "recommended_action": "Inspect seedlings and plant material for chewing. Confirm the insect is responsible before choosing any control measures.",
        "prevention": "Check seedlings regularly, remove suitable shelter when practical, and monitor crop condition.",
    },
    {
        "pest_id": "termite",
        "title": "Termite Monitoring and Management",
        "description": "Some termite species damage living plants, roots, wooden structures, or stored materials.",
        "recommended_action": "Inspect affected roots, stems, or structures for galleries and mud tubes. Confirm the termite species and seek locally appropriate management advice.",
        "prevention": "Monitor vulnerable plants and materials, reduce unnecessary wood-to-soil contact around structures, and address moisture problems where practical.",
    },
    {
        "pest_id": "rice_planthopper",
        "title": "Rice Planthopper Management",
        "description": (
            "Regular field monitoring is important for detecting planthopper "
            "activity early and preventing rapid spread."
        ),
        "recommended_action": (
            "Inspect affected areas, maintain proper field conditions and "
            "follow locally recommended integrated pest management practices."
        ),
        "prevention": (
            "Avoid excessive nitrogen application, maintain suitable plant "
            "spacing and regularly monitor the crop."
        ),
    },
    {
        "pest_id": "rice_leaf_folder",
        "title": "Rice Leaf Folder Management",
        "description": (
            "Early identification of folded and damaged leaves helps "
            "reduce crop damage."
        ),
        "recommended_action": (
            "Inspect damaged leaves and follow locally recommended integrated "
            "pest management practices when pest levels become significant."
        ),
        "prevention": (
            "Monitor the crop regularly and avoid unnecessary conditions "
            "that encourage excessive pest growth."
        ),
    },
    {
        "pest_id": "brown_plant_hopper",
        "title": "Brown Planthopper Management",
        "description": (
            "Brown planthopper outbreaks should be identified early because "
            "damage can develop quickly."
        ),
        "recommended_action": (
            "Inspect hopper populations and follow locally recommended "
            "integrated pest management guidance."
        ),
        "prevention": (
            "Avoid excessive nitrogen, monitor crop growth regularly and "
            "maintain appropriate field management."
        ),
    },
    {
        "pest_id": "stem_borer",
        "title": "Rice Stem Borer Management",
        "description": (
            "Regular crop inspection can help identify stem-borer damage "
            "before severe yield loss occurs."
        ),
        "recommended_action": (
            "Inspect plants for dead hearts or white heads and follow "
            "locally recommended integrated pest management practices."
        ),
        "prevention": (
            "Maintain field hygiene and regularly monitor the crop for "
            "early signs of stem-borer activity."
        ),
    },
    {
        "pest_id": "armyworm",
        "title": "Armyworm Management",
        "description": (
            "Early detection of leaf-feeding activity can help reduce "
            "rapid foliage damage."
        ),
        "recommended_action": (
            "Inspect affected crop areas and follow locally recommended "
            "integrated pest management guidance."
        ),
        "prevention": (
            "Monitor crop foliage frequently and remove severe infestations "
            "according to local agricultural guidance."
        ),
    },
    {
        "pest_id": "fall_armyworm",
        "title": "Fall Armyworm Management",
        "description": (
            "Regular scouting is important, especially in maize and other "
            "susceptible crops."
        ),
        "recommended_action": (
            "Inspect plants for characteristic feeding damage and follow "
            "locally recommended integrated pest management practices."
        ),
        "prevention": (
            "Scout fields regularly and respond early to newly detected "
            "infestations."
        ),
    },
    {
        "pest_id": "aphid",
        "title": "Aphid Management",
        "description": (
            "Aphid populations can increase quickly, so regular inspection "
            "of young leaves and shoots is useful."
        ),
        "recommended_action": (
            "Inspect affected plant parts and follow locally recommended "
            "integrated pest management guidance."
        ),
        "prevention": (
            "Monitor new plant growth and encourage healthy crop conditions."
        ),
    },
]