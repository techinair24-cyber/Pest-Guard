// Common names for the NEW 47-class Pest Guard model.
// Keys are normalized scientific names used by the CNN.
export const MODEL_CLASS_COMMON_NAMES = Object.freeze({
  achetadomesticus: 'House Cricket',
  barbitistesyersini: "Yersin's Bush-cricket",
  chorthippusalbomarginatus: 'Lesser Marsh Grasshopper',
  chorthippusapricarius: 'Steppe Grasshopper',
  chorthippusbiguttulus: 'Bow-winged Grasshopper',
  chorthippusbrunneus: 'Common Field Grasshopper',
  chorthippusmollis: 'Chorthippus mollis',
  chorthippusvagans: 'Heath Grasshopper',
  chrysochraondispar: 'Large Gold Grasshopper',
  conocephalusdorsalis: 'Short-winged Conehead',
  conocephalusfuscus: 'Long-winged Conehead',
  decticusverrucivorus: 'Wart-biter',
  ephippigerdiurnus: 'Saddle-backed Bush-cricket',
  eupholidopteraschmidti: "Schmidt's Bush-cricket",
  gampsocleisglabra: 'Gampsocleis glabra',
  gomphocerippusrufus: 'Rufous Grasshopper',
  gomphocerussibiricus: 'Siberian Grasshopper',
  gryllusbimaculatus: 'Two-spotted Cricket',
  grylluscampestris: 'Field Cricket',
  leptophyespunctatissima: 'Speckled Bush-cricket',
  melanogryllusdesertus: 'Melanogryllus desertus',
  metriopterabrachyptera: 'Bog Bush-cricket',
  myrmeleotettixmaculatus: 'Mottled Grasshopper',
  nemobiussylvestris: 'Wood Cricket',
  oecanthuspellucens: 'Pale Tree Cricket',
  omocestuspetraeus: 'Steppe Grasshopper',
  omocestusrufipes: 'Red-legged Grasshopper',
  omocestusviridulus: 'Common Green Grasshopper',
  phaneropterafalcata: 'Sickle-bearing Bush-cricket',
  phaneropteranana: 'Phaneroptera nana',
  pholidopteraaptera: 'Alpine Dark Bush-cricket',
  pholidopteragriseoaptera: 'Dark Bush-cricket',
  pholidopteralittoralis: 'Pholidoptera littoralis',
  platycleisalbopunctata: 'Platycleis albopunctata',
  platypleuracfcatenata: 'Platypleura cf. catenata',
  platypleuraplumosa: 'Platypleura plumosa',
  platypleurasp10: 'Platypleura sp. 10',
  platypleurasp12cfhirtipennis:
    'Platypleura sp. 12 cf. hirtipennis',
  platypleurasp13: 'Platypleura sp. 13',
  pseudochorthippusmontanus: 'Bog Grasshopper',
  pseudochorthippusparallelus: 'Meadow Grasshopper',
  roeselianaroeselii: "Roesel's Bush-cricket",
  stenobothruslineatus: 'Stripe-winged Grasshopper',
  stenobothrusstigmaticus: 'Lesser Mottled Grasshopper',
  tettigoniacantans: 'Singing Bush-cricket',
  tettigoniaviridissima: 'Great Green Bush-cricket',
  tylopsislilifolia: 'Lily Bush-cricket',
})

// Keep existing class risk estimates separate from name mapping.
export const PEST_CLASS_RISK_ESTIMATES = Object.freeze({
  desertlocust: Object.freeze({
    canonicalName: 'Desert locust',
    risk: 'HIGH',
    source: 'FAO Desert Locust Information Service',
    sourceUrl: 'https://www.fao.org/locusts/en/',
    rationale:
      'FAO documents rapid population growth and the potential for a 1 km² swarm to consume food comparable to 35,000 people in one day.',
  }),
  katydid: Object.freeze({
    canonicalName: 'Katydid',
    risk: 'MEDIUM',
    source: 'UC Statewide IPM Program',
    sourceUrl: 'https://ipm.ucanr.edu/agriculture/citrus/katydids/',
    rationale:
      'Some katydid species can damage leaves and young fruit. Impact varies by species and crop.',
  }),
})

export function normalizePestName(value) {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]/g, '')
}

export function buildPestDirectory(items) {
  const directory = {}

  if (!Array.isArray(items)) return directory

  items.forEach((item) => {
    const name = String(item?.name || '').trim()
    const scientificName = String(
      item?.scientific_name || '',
    ).trim()

    const commonName =
      name &&
      normalizePestName(name) !==
        normalizePestName(scientificName)
        ? name
        : ''

    const entry = {
      commonName,
      scientificName,
      pestId: String(item?.pest_id || '').trim(),
      description: item?.description || '',
      symptoms: item?.symptoms || '',
      risk: item?.risk || '',
    }

    ;[name, scientificName, entry.pestId].forEach(
      (candidate) => {
        const key = normalizePestName(candidate)
        if (key) directory[key] = entry
      },
    )
  })

  return directory
}

export function getPestRiskEstimate(
  pest,
  directory = {},
) {
  const key = normalizePestName(pest)

  if (!key) {
    return {
      risk: 'UNKNOWN',
      source: null,
      rationale: '',
    }
  }

  const classEstimate = PEST_CLASS_RISK_ESTIMATES[key]

  if (classEstimate) return classEstimate

  const catalogRisk = String(
    directory[key]?.risk || '',
  ).toUpperCase()

  if (['LOW', 'MEDIUM', 'HIGH'].includes(catalogRisk)) {
    return {
      risk: catalogRisk,
      source: 'Pest Guard pest catalogue',
      rationale:
        'Risk category recorded in the matching pest catalogue entry.',
    }
  }

  return {
    risk: 'UNKNOWN',
    source: null,
    rationale: '',
  }
}

export function getDetectionRiskEstimate(
  detection,
  directory = {},
) {
  const pestRecord = directory[normalizePestName(detection?.pest)]
  const independentlyVerified =
    detection?.pest_verified === true &&
    Boolean(detection?.pest_id) &&
    detection.pest_id === pestRecord?.pestId

  if (!independentlyVerified) {
    return {
      risk: 'UNKNOWN',
      source: null,
      rationale: '',
    }
  }

  return getPestRiskEstimate(detection.pest, directory)
}

export function getCommonPestName(
  pest,
  directory = {},
) {
  const rawName = String(pest || '').trim()

  if (!rawName) return 'Detected pest'

  const key = normalizePestName(rawName)
  const entry = directory[key]

  return (
    MODEL_CLASS_COMMON_NAMES[key] ||
    entry?.commonName ||
    rawName
  )
}

export function getDisplayPestName(
  pest,
  directory = {},
) {
  const rawName = String(pest || '').trim()

  if (!rawName) return 'Unknown pest'

  const key = normalizePestName(rawName)
  const entry = directory[key]
  const commonName = getCommonPestName(
    rawName,
    directory,
  )

  const scientificName = String(
    entry?.scientificName ||
      (MODEL_CLASS_COMMON_NAMES[key] ? rawName : ''),
  ).trim()

  if (!scientificName) {
    return commonName
  }

  if (
    normalizePestName(commonName) ===
    normalizePestName(scientificName)
  ) {
    return commonName
  }

  return `${commonName} (${scientificName})`
}