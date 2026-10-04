export const FALLBACK_COMMON_PEST_NAMES = {
  Popplepsaltanotialis: 'Cicada',
  Yoyettarepetens: 'Cicada',
  Yoyettacelis: 'Cicada',
  Neotibicenpruinosus: 'Cicada',
  Atrapsaltaencaustica: 'Cicada',
  Achetadomesticus: 'House Cricket',
  Grylluscampestris: 'Field Cricket',
  Gryllusbimaculatus: 'Two-spotted Cricket',
  Chorthippusvagans: 'Heath Grasshopper',
  Pseudochorthippusparallelus: 'Meadow Grasshopper',
  Oecanthuspellucens: 'European Tree Cricket',
  Roeselianaroeselii: "Roesel's Bush-cricket",
  Chorthippusbiguttulus: 'Bow-winged Grasshopper',
  Chorthippusbrunneus: 'Field Grasshopper',
}

export function normalizePestName(value) {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]/g, '')
}

export function buildPestDirectory(items) {
  const directory = {}

  if (!Array.isArray(items)) {
    return directory
  }

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
      if (key) {
        directory[key] = entry
      }
    })
  })

  return directory
}

function getFallbackCommonName(...values) {
  const fallbackEntries = Object.entries(FALLBACK_COMMON_PEST_NAMES)
  for (const value of values) {
    const key = normalizePestName(value)
    const entry = fallbackEntries.find(
      ([scientificName]) => normalizePestName(scientificName) === key,
    )
    if (entry) {
      return entry[1]
    }
  }
  return ''
}

export function getCommonPestName(pest, directory = {}) {
  const rawName = String(pest || '').trim()
  if (!rawName) {
    return 'Detected pest'
  }

  const entry = directory[normalizePestName(rawName)]
  return entry?.commonName || getFallbackCommonName(rawName, entry?.scientificName) || 'Detected pest'
}

export function getDisplayPestName(pest, directory = {}) {
  const rawName = String(pest || '').trim()
  if (!rawName) {
    return 'Unknown pest'
  }

  const entry = directory[normalizePestName(rawName)]
  const scientificName = String(entry?.scientificName || rawName).trim()
  const commonName = getCommonPestName(rawName, directory)

  return `${commonName} (${scientificName})`
}
