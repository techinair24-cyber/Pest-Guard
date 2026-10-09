
export const FALLBACK_COMMON_PEST_NAMES = {
  Achetadomesticus: 'House Cricket',
  Aleetacurvicosta: 'Aleetacurvicosta',
  Atrapsaltacollina: 'Collina Cicada',
  Atrapsaltacorticina: 'Corticina Cicada',
  Atrapsaltaencaustica: 'Encaustica Cicada',
  Barbitistesyersini: 'Yersin’s Bush-cricket',
  Bicoloranabicolor: 'Bicolored Bush-cricket',
  Chorthippusalbomarginatus: 'Lesser Marsh Grasshopper',
  Chorthippusapricarius: 'Steppe Grasshopper',
  Chorthippusbiguttulus: 'Bow-winged Grasshopper',
  Chorthippusbrunneus: 'Field Grasshopper',
  Chorthippusmollis: 'Mottled Grasshopper',
  Chorthippusvagans: 'Heath Grasshopper',
  Chrysochraondispar: 'Large Marsh Grasshopper',
  Cicadaorni: 'Common Cicada',
  Clinopsaltaautumna: 'Autumn Cicada',
  Conocephalusdorsalis: 'Short-winged Conehead',
  Conocephalusfuscus: 'Long-winged Conehead',
  Cyclochilaaustralasiae: 'Green Grocer Cicada',
  Decticusverrucivorus: 'Wart-biter Bush-cricket',
  Diceroproctaeugraphica: 'Diceroprocta Cicada',
  Ephippigerdiurnus: 'Day Bush-cricket',
  Eumodicogryllusbordigalensis: 'Bordigalensis Cricket',
  Eupholidopteraschmidti: 'Schmidt’s Bush-cricket',
  Galangalabeculata: 'Galangalabeculata',
  Gampsocleisglabra: 'Gampsocleis Bush-cricket',
  Gomphocerippusrufus: 'Rufous Grasshopper',
  Gomphocerussibiricus: 'Siberian Grasshopper',
  Gryllusbimaculatus: 'Two-spotted Cricket',
  Grylluscampestris: 'Field Cricket',
  Leptophyespunctatissima: 'Speckled Bush-cricket',
  Melanogryllusdesertus: 'Desert Cricket',
  Metriopterabrachyptera: 'Short-winged Bush-cricket',
  Myrmeleotettixmaculatus: 'Mottled Grasshopper',
  Nemobiussylvestris: 'Woodland Ground Cricket',
  Neotibicenpruinosus: 'Scissor-grinder Cicada',
  Oecanthuspellucens: 'European Tree Cricket',
  Omocestuspetraeus: 'Steppe Grasshopper',
  Omocestusrufipes: 'Red-legged Grasshopper',
  Omocestusviridulus: 'Common Green Grasshopper',
  Phaneropterafalcata: 'Speckled Bush-cricket',
  Phaneropteranana: 'Phaneroptera nana',
  Pholidopteraaptera: 'Dark Bush-cricket',
  Pholidopteragriseoaptera: 'Dark Bush-cricket',
  Pholidopteralittoralis: 'Littoral Bush-cricket',
  Platycleisalbopunctata: 'White-spotted Bush-cricket',
  Platypleuracfcatenata: 'Platypleura cf. catenata',
  Platypleuraplumosa: 'Platypleura plumosa Cicada',
  Platypleurasp10: 'Platypleura sp. 10',
  Platypleurasp12cfhirtipennis: 'Platypleura sp. 12 cf. hirtipennis',
  Platypleurasp13: 'Platypleura sp. 13',
  Popplepsaltaaeroides: 'Aeroides Cicada',
  Popplepsaltanotialis: 'Notialis Cicada',
  Psaltodaplaga: 'Plaga Cicada',
  Pseudochorthippusmontanus: 'Lesser Mountain Grasshopper',
  Pseudochorthippusparallelus: 'Meadow Grasshopper',
  Roeselianaroeselii: "Roesel's Bush-cricket",
  Ruspolianitidula: 'Long-winged Conehead',
  Stauroderusscalaris: 'Stauroderus Grasshopper',
  Stenobothruslineatus: 'Stripe-winged Grasshopper',
  Stenobothrusstigmaticus: 'Stenobothrus Grasshopper',
  Tettigoniacantans: 'Roesel’s Katydid',
  Tettigoniaviridissima: 'Great Green Bush-cricket',
  Tylopsislilifolia: 'Lily Bush-cricket',
  Yoyettacelis: 'Celis Cicada',
  Yoyettarepetens: 'Repetens Cicada',
}

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
    const scientificName = String(item?.scientific_name || '').trim()
    const commonName =
      name && normalizePestName(name) !== normalizePestName(scientificName)
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

    ;[name, scientificName, entry.pestId].forEach((candidate) => {
      const key = normalizePestName(candidate)
      if (key) directory[key] = entry
    })
  })

  return directory
}

function getFallbackCommonName(...values) {
  for (const value of values) {
    const key = normalizePestName(value)
    const match = Object.entries(FALLBACK_COMMON_PEST_NAMES).find(
      ([scientificName]) => normalizePestName(scientificName) === key,
    )
    if (match) return match[1]
  }

  return ''
}

export function getCommonPestName(pest, directory = {}) {
  const rawName = String(pest || '').trim()
  if (!rawName) return 'Detected pest'

  const entry = directory[normalizePestName(rawName)]

  return (
    entry?.commonName ||
    getFallbackCommonName(rawName, entry?.scientificName) ||
    rawName
  )
}

export function getDisplayPestName(pest, directory = {}) {
  const rawName = String(pest || '').trim()
  if (!rawName) return 'Unknown pest'

  const entry = directory[normalizePestName(rawName)]
  const scientificName = String(entry?.scientificName || rawName).trim()
  const commonName = getCommonPestName(rawName, directory)

  if (normalizePestName(commonName) === normalizePestName(scientificName)) {
    return scientificName
  }

  return `${commonName} (${scientificName})`
}
