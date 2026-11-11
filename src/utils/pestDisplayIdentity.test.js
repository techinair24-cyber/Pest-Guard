import assert from 'node:assert/strict'
import test from 'node:test'

import { getVerifiedDetectionDisplayName, buildPestDirectory } from './pestNames.js'
import { getLatestDetectionSpeciesName } from './liveMonitoringStatus.js'

test('Dashboard and Solutions use the same verified common name without scientific metadata', () => {
  const detection = {
    status: 'HARMFUL_PEST',
    pest: 'European Field Cricket',
    pest_id: 'european_field_cricket',
    pest_verified: true,
    common_name: 'European Field Cricket',
    scientific_name: null,
    confidence: 0.677,
    group_score: 0.728,
    risk: 'HIGH',
    top_predictions: [
      {
        pest: 'European Field Cricket',
        common_name: 'European Field Cricket',
        score: 0.677,
        subtype_confidence: 0.677,
      },
    ],
  }
  const directory = buildPestDirectory([
    {
      pest_id: 'european_field_cricket',
      name: 'European Field Cricket',
      scientific_name: null,
      risk: 'HIGH',
    },
  ])
  const solutionsName = getVerifiedDetectionDisplayName(detection, directory)
  const dashboardName = getLatestDetectionSpeciesName(detection, directory)

  assert.equal(solutionsName, 'European Field Cricket')
  assert.equal(dashboardName, solutionsName)
  assert.equal(detection.confidence, 0.677)
  assert.equal(detection.group_score, 0.728)
  assert.equal(detection.risk, 'HIGH')
})

test('missing scientific name does not hide an available common name', () => {
  assert.equal(
    getVerifiedDetectionDisplayName({
      status: 'HARMFUL_PEST',
      pest_verified: true,
      pest_id: 'known_pest',
      common_name: 'Known Common Name',
      scientific_name: null,
    }),
    'Known Common Name',
  )
})

test('API common name remains visible when the reference entry has no display name', () => {
  const directory = buildPestDirectory([
    {
      pest_id: 'known_pest',
      name: '',
      risk: 'HIGH',
    },
  ])

  assert.equal(
    getVerifiedDetectionDisplayName(
      {
        status: 'HARMFUL_PEST',
        pest_verified: true,
        pest_id: 'known_pest',
        common_name: 'Known Common Name',
        scientific_name: null,
      },
      directory,
    ),
    'Known Common Name',
  )
})

test('unknown or unverified species retains the safe fallback', () => {
  assert.equal(
    getVerifiedDetectionDisplayName({
      status: 'UNKNOWN',
      pest_verified: false,
      pest_id: null,
      common_name: 'Possible Candidate',
    }),
    'Unknown pest',
  )
  assert.equal(
    getVerifiedDetectionDisplayName({
      status: 'HARMFUL_PEST',
      pest_verified: true,
      pest_id: 'known_pest',
      common_name: null,
      pest: null,
    }),
    'Unknown pest',
  )
})
